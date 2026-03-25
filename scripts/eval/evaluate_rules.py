#!/usr/bin/env python3
"""
按规则评估攻击强度（coverage + LLM accuracy drop）。

整体流程（简化版）：
1. 遍历数据集，对每条规则：
   - 用 rule_applicator.apply_rule_on_sample 统计候选/成功变换；
   - 为每个 task 生成一份“对抗代码”（只取第一个成功 target_token）。
2. 对“有成功变换”的子集：
   - 使用 evaluate.py 分别评估原始代码和对抗代码；
   - 计算 acc_orig、acc_adv、ASR、strength 等指标。

用法示例：

  python scripts/eval/evaluate_rules.py \\
    --rules T09 T10 T12 \\
    --dataset data/qualified_dataset.json \\
    --results-root rule_eval/results \\
    --eval-output rule_eval/metrics \\
    --provider local \\
    --model Qwen2.5-Coder-7B \\
    --base-url http://localhost:8000/v1 \\
    --sample-limit 500
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict
from pathlib import Path
from typing import List, Dict, Optional, Tuple
import sys

# 确保可以从项目根目录导入 rule_applicator、ast_transforms_loader 等模块
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import yaml

from rule_applicator import apply_rule_on_sample, RuleApplyStats
from ast_transforms_loader import create_engine, analyze
from textual_param_generator import generate_textual_rule_parameters


def _run(
    cmd: List[str],
    cwd: Path,
    stream: bool = False,
) -> None:
    """subprocess 封装。stream=True 时不捕获输出，便于 tqdm/逐条日志实时显示。"""
    if stream:
        proc = subprocess.run(cmd, cwd=str(cwd), text=True)
        if proc.returncode != 0:
            raise RuntimeError(f"Command failed: {' '.join(cmd)}（输出已打印到终端）")
    else:
        proc = subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)
        if proc.returncode != 0:
            raise RuntimeError(
                f"Command failed: {' '.join(cmd)}\nstdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
            )


def main() -> None:
    p = argparse.ArgumentParser(description="按规则评估 coverage + LLM 攻击强度")
    p.add_argument("--rules", nargs="+", required=True, help="规则 ID 列表，例如: T09 T10 T12")
    p.add_argument("--dataset", required=True, help="dataset.json 路径，例如 data/qualified_dataset.json")
    p.add_argument("--results-root", required=True, help="中间结果根目录，用于存放 per-rule 的 orig/adv 结果")
    p.add_argument("--eval-output", required=True, help="评估 summary 输出目录")
    p.add_argument("--provider", required=True, help="evaluate.py 的 provider，例如 local/openai/anthropic")
    p.add_argument("--model", required=True, help="模型名称，例如 Qwen2.5-Coder-7B 或 gpt-4o")
    p.add_argument("--base-url", default=None, help="local provider 时的 base-url，例如 http://localhost:8000/v1")
    p.add_argument("--api-key", default=None, help="远程 API 的 key，可选")
    p.add_argument("--sample-limit", type=int, default=None, help="每条规则最多评估多少条样本（可选）")
    p.add_argument("--repeat", type=int, default=1, help="evaluate.py 的 --repeat 次数")
    p.add_argument(
        "--progress",
        action="store_true",
        help="每条规则：数据集变换阶段 tqdm；调用 evaluate.py 时显示任务级 tqdm（子进程不捕获输出）",
    )
    # qwen25coder：仅用于生成“文字变换类规则”的 parameters
    p.add_argument("--param-model", default=None, help="参数生成模型名称（默认从 config.yaml 取 target_model.model）")
    p.add_argument("--param-base-url", default=None, help="参数生成 base-url（默认从 config.yaml 取 target_model.base_url）")
    p.add_argument("--param-api-key", default=None, help="参数生成 api-key（默认从 config.yaml 取 target_model.api_key）")
    p.add_argument("--param-temperature", type=float, default=0.0, help="参数生成 temperature")
    p.add_argument("--param-max-tokens", type=int, default=256, help="参数生成 max_tokens")
    # 全局缓存：只缓存 original 模式的 LLM verdict，用于跨规则复用并避免重复调用 original eval
    p.add_argument(
        "--orig-verdict-cache",
        default="rule_eval/orig_verdict_cache.json",
        help="original verdict 全局缓存文件路径（会按模型/服务区分）",
    )
    # 结果目录清理/复用开关：避免清空 adv 中间结果（尤其是你已经生成了一大批 adv code）
    p.add_argument(
        "--skip-clean-adv",
        action="store_true",
        help="不清空 rule_eval/results_full_all_rules/<rule>/adv 下已有的 q*.json（会复用已有 adv 结果）",
    )
    p.add_argument(
        "--reuse-existing-adv",
        action="store_true",
        help="如果 adv 文件已存在，则跳过该 task 的变换/参数生成步骤（仅复用现有 adv/orig JSON）",
    )
    args = p.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    dataset_path = project_root / args.dataset
    results_root = project_root / args.results_root
    eval_output_root = project_root / args.eval_output

    results_root.mkdir(parents=True, exist_ok=True)
    eval_output_root.mkdir(parents=True, exist_ok=True)

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    engine = create_engine()

    # ---------------------------
    # Global original verdict cache
    # ---------------------------
    all_task_ids: List[str] = sorted({t.get("task_id") for t in data if t.get("task_id")})

    cache_path = project_root / args.orig_verdict_cache
    cache_path.parent.mkdir(parents=True, exist_ok=True)

    # cache key 记录“由什么模型给出的判断”
    cache_key = "|".join(
        [
            str(args.provider),
            str(args.model),
            str(args.base_url or ""),
            str(args.api_key or ""),
            "max_tokens=2048",
            # confidence 需要 evaluate.py 在 openai-compatible 请求中开启 logprobs
            "llm_confidence_from_logprobs=no_minus_yes_v4",
        ]
    )

    global_cache: Dict[str, Dict] = {}
    if cache_path.exists():
        try:
            global_cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            global_cache = {}

    if cache_key not in global_cache:
        global_cache[cache_key] = {
            "provider": args.provider,
            "model": args.model,
            "base_url": args.base_url or "",
            "api_key": args.api_key or "",
            "max_tokens": 2048,
            "tasks": {},  # task_id -> {"original_truth": bool/None, "original_passed": bool/None, "original_confidence": float/None}
        }

    cache_tasks: Dict[str, Dict[str, object]] = global_cache[cache_key].setdefault("tasks", {})
    # confidence 指标需要原始评估的 original_confidence；缺失则视为未缓存，后续会重跑 original
    missing = [
        tid
        for tid in all_task_ids
        if tid not in cache_tasks or cache_tasks.get(tid, {}).get("original_confidence") is None
    ]

    if missing:
        # 优先补齐：扫描已存在的 rule_eval/metrics_*/T*/orig_eval 里能覆盖更多 task 的目录
        target_missing = set(missing)

        candidates: List[Tuple[int, Path]] = []
        for rule_dir in sorted(eval_output_root.glob("T*/orig_eval")):
            if not rule_dir.is_dir():
                continue
            files = list(rule_dir.glob("q*_rep0.json"))
            if files:
                candidates.append((len(files), rule_dir))
        candidates.sort(reverse=True, key=lambda x: x[0])

        for _, orig_eval_dir in candidates:
            if not target_missing:
                break
            for f in orig_eval_dir.glob("q*_rep0.json"):
                tid = f.stem.split("_rep")[0]
                if tid not in target_missing:
                    continue
                try:
                    j = json.loads(f.read_text(encoding="utf-8"))
                except Exception:
                    continue
                if j.get("original_confidence") is None:
                    continue
                cache_tasks[tid] = {
                    "original_truth": j.get("original_truth"),
                    "original_passed": j.get("original_passed"),
                    "original_confidence": j.get("original_confidence"),
                }
                target_missing.remove(tid)
            if not target_missing:
                break

        global_cache[cache_key]["tasks"] = cache_tasks
        cache_path.write_text(json.dumps(global_cache, ensure_ascii=False, indent=2), encoding="utf-8")

    # 需要时，为指定 task_id 补齐 original_confidence（通过 evaluate.py 重新跑 original 模式）
    task_map: Dict[str, Dict] = {t.get("task_id"): t for t in data if t.get("task_id")}

    def ensure_original_confidence(tids: List[str], rule_id_for_tmp: str) -> None:
        need = [tid for tid in tids if cache_tasks.get(tid, {}).get("original_confidence") is None]
        if not need:
            return

        tmp_results_dir = eval_output_root / "_tmp_orig_conf_fill" / rule_id_for_tmp / "results"
        tmp_out_dir = eval_output_root / "_tmp_orig_conf_fill" / rule_id_for_tmp / "eval"
        tmp_results_dir.mkdir(parents=True, exist_ok=True)
        tmp_out_dir.mkdir(parents=True, exist_ok=True)

        for tid in need:
            task = task_map.get(tid)
            if not task:
                continue
            # evaluate.py 在 original 模式下会使用 task["canonical_solution"] 作为原始 RTL；
            # 这里仅为了满足其读取 attack_result["final"] 的结构要求，用同一个 canonical_solution 填充即可。
            rec_orig = {
                "task_id": tid,
                "rule_id": rule_id_for_tmp,
                "changed": False,
                "final": task.get("canonical_solution", ""),
                "rename_map": {},
            }
            (tmp_results_dir / f"{tid}.json").write_text(
                json.dumps(rec_orig, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # 跑 original 模式，为 need 中这些 tid 计算 confidence
        cmd_orig = [
            "python",
            "evaluate.py",
            "--dataset",
            str(dataset_path),
            "--provider",
            args.provider,
            "--model",
            args.model,
            "--temperature",
            "0.0",
            "--max-tokens",
            "2048",
            "--repeat",
            "1",
            "--results",
            str(tmp_results_dir),
            "--output",
            str(tmp_out_dir),
            "--modes",
            "original",
        ]
        if args.base_url:
            cmd_orig += ["--base-url", args.base_url]
        if args.api_key:
            cmd_orig += ["--api-key", args.api_key]
        if args.progress:
            cmd_orig.append("--progress")

        _run(cmd_orig, cwd=project_root, stream=args.progress)

        filled = 0
        for tid in need:
            f = tmp_out_dir / f"{tid}_rep0.json"
            if not f.exists():
                continue
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if j.get("original_confidence") is None:
                continue
            cache_tasks[tid] = {
                "original_truth": j.get("original_truth"),
                "original_passed": j.get("original_passed"),
                "original_confidence": j.get("original_confidence"),
            }
            filled += 1

        global_cache[cache_key]["tasks"] = cache_tasks
        cache_path.write_text(
            json.dumps(global_cache, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        if filled:
            print(f"[cache-fill] filled original_confidence for {filled}/{len(need)} tasks ({rule_id_for_tmp})")

    # 文字变换规则：需要 qwen25coder 生成 parameters（且只对第一个成功 k 之前的候选调用）
    TEXTUAL_RULES = {"T20", "T12", "T31", "T34", "T19"}

    # 参数生成模型默认从 config.yaml 读取
    config_path = project_root / "config.yaml"
    param_model = args.param_model
    param_base_url = args.param_base_url
    param_api_key = args.param_api_key
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
        tm = (cfg.get("target_model") or {})
        if param_model is None:
            param_model = tm.get("model")
        if param_base_url is None:
            param_base_url = tm.get("base_url")
        if param_api_key is None:
            param_api_key = tm.get("api_key", "EMPTY")
    if not param_model or not param_base_url:
        raise ValueError("param_model/param_base_url 未设置，且 config.yaml 里也找不到。")

    overall_report: List[Dict] = []

    rules_iter = args.rules
    if args.progress:
        try:
            from tqdm import tqdm  # type: ignore

            rules_iter = tqdm(
                args.rules,
                desc="rules",
                unit="rule",
                total=len(args.rules),
                dynamic_ncols=True,
                position=0,
                leave=True,
            )
        except ImportError:
            pass

    for rule_id in rules_iter:
        print(f"\n=== Evaluating rule {rule_id} ===", flush=True)

        # 1. 规则层统计 + 生成 orig/adv 结果目录
        per_rule_stats: List[RuleApplyStats] = []
        rule_results_orig = results_root / rule_id / "orig"
        rule_results_adv = results_root / rule_id / "adv"
        rule_results_orig.mkdir(parents=True, exist_ok=True)
        rule_results_adv.mkdir(parents=True, exist_ok=True)

        # 清理旧文件（防止混淆）
        for d in (rule_results_orig, rule_results_adv):
            # 用户可选择跳过 adv 清理
            if args.skip_clean_adv and d == rule_results_adv:
                continue
            for f in d.glob("*.json"):
                f.unlink()

        enum_data = enumerate(data)
        if args.progress:
            try:
                from tqdm import tqdm  # type: ignore

                max_n = len(data)
                if args.sample_limit is not None:
                    max_n = min(args.sample_limit, len(data))
                enum_data = tqdm(
                    enumerate(data),
                    total=max_n,
                    desc=f"{rule_id} transform",
                    unit="task",
                    dynamic_ncols=True,
                )
            except ImportError:
                pass

        for i, task in enum_data:
            if args.sample_limit is not None and i >= args.sample_limit:
                break
            task_id = task.get("task_id")
            code = task.get("canonical_solution", "")
            if not task_id or not code:
                continue

            # 复用：如果 adv 已存在，则跳过变换/参数生成，只在 per_rule_stats 中标记 num_success=1
            if args.reuse_existing_adv:
                adv_file = rule_results_adv / f"{task_id}.json"
                if adv_file.exists():
                    try:
                        adv_j = json.loads(adv_file.read_text(encoding="utf-8"))
                        adv_changed = adv_j.get("changed") is True or (adv_j.get("final") is not None)
                    except Exception:
                        adv_changed = False
                    try:
                        candidates = engine._get_candidates_for_transform(code, rule_id)
                        num_candidates = len(candidates)
                    except Exception:
                        num_candidates = 0
                    num_success = 1 if adv_changed else 0
                    success_tokens = [0] if num_success > 0 else []
                    per_rule_stats.append(
                        RuleApplyStats(
                            task_id=task_id,
                            rule_id=rule_id,
                            num_candidates=num_candidates,
                            num_success=num_success,
                            success_tokens=success_tokens,
                        )
                    )
                    # 不再写 orig/adv 文件（保持已有内容）
                    continue

            adv_code: Optional[str] = None
            rename_map: Dict[str, str] = {}
            params_used: Dict = {}
            selected_k: Optional[int] = None
            adv_target_line: Optional[int] = None
            adv_target_signal: str = ""

            if rule_id in TEXTUAL_RULES:
                candidates = engine._get_candidates_for_transform(code, rule_id)
                num_candidates = len(candidates)
                num_success = 0
                success_tokens: List[int] = []

                # T19：准备可写/可读信号列表，增强 prompt 约束（减少语法错误并提升误导强度）
                t19_writable_signals: Optional[List[str]] = None
                t19_readable_signals: Optional[List[str]] = None
                if rule_id == "T19":
                    try:
                        vs = analyze(code)
                        port_names = {p.name for p in vs.ports}
                        t19_writable_signals = [
                            s.name
                            for s in getattr(vs, "signals", [])
                            if getattr(s, "kind", None) in ("reg", "logic")
                            and s.name and not (s.name in port_names and getattr(s, "direction", None) == "input")
                        ]
                        # 可读：输入端口 + 所有内部信号名（用于 RHS 表达式）
                        t19_readable_signals = [
                            p.name for p in getattr(vs, "ports", []) if getattr(p, "direction", None) == "input"
                        ] + [s.name for s in getattr(vs, "signals", []) if getattr(s, "name", None)]
                    except Exception:
                        t19_writable_signals = None
                        t19_readable_signals = None

                # 只用“第一个成功 k”，且对每个尝试的 k 才调用一次 LLM
                for k in range(num_candidates):
                    try:
                        target_line, target_signal = engine.get_target_line_signal(code, rule_id, k)
                    except Exception:
                        target_line, target_signal = None, None

                    t34_old_name = None
                    if rule_id == "T34":
                        # T34 的 candidates 是字符串 old_name，不具备 start/end 偏移；target_line 可能是假的，
                        # 因此让提示词只依赖 t34_old_name。
                        target_line, target_signal = None, None
                        # T34 的候选是字符串 old_name
                        try:
                            t34_cands = candidates  # already computed
                            if 0 <= k < len(t34_cands) and isinstance(t34_cands[k], str):
                                t34_old_name = t34_cands[k]
                        except Exception:
                            t34_old_name = None

                    # 生成 parameters
                    try:
                        if rule_id in {"T20", "T12", "T31", "T34", "T19"}:
                            params_used = generate_textual_rule_parameters(
                                base_url=param_base_url,
                                model=param_model,
                                api_key=param_api_key or "EMPTY",
                                rule_id=rule_id,
                                task_prompt=task.get("prompt", ""),
                                rtl=code,
                                target_token=k,
                                target_line=target_line,
                                target_signal=target_signal,
                                t34_old_name=t34_old_name,
                                t19_writable_signals=t19_writable_signals,
                                t19_readable_signals=t19_readable_signals,
                                temperature=args.param_temperature,
                                max_tokens=args.param_max_tokens,
                            )
                        else:
                            params_used = {}
                    except Exception:
                        continue

                    # 应用变换
                    try:
                        new_code = engine.apply_transform(code, rule_id, target_token=k, **params_used)
                    except Exception:
                        continue

                    if new_code == code:
                        continue

                    # 语法/解析检查：能被 analyze 成功即可视为 transform success
                    try:
                        analyze(new_code)
                    except Exception:
                        continue

                    adv_code = new_code
                    rename_map = engine.get_last_rename_map() or {}
                    selected_k = k
                    adv_target_line = target_line
                    adv_target_signal = (target_signal or "") if target_signal is not None else ""
                    num_success = 1
                    success_tokens = [k]
                    break

                stats = RuleApplyStats(
                    task_id=task_id,
                    rule_id=rule_id,
                    num_candidates=num_candidates,
                    num_success=num_success,
                    success_tokens=success_tokens,
                )
                per_rule_stats.append(stats)

                # 只在有成功变换时生成 orig/adv 两个版本
                if adv_code is None:
                    continue
            else:
                stats = apply_rule_on_sample(rule_id, task_id, code)
                per_rule_stats.append(stats)

                # 只在有成功变换时生成 orig/adv 两个版本
                if not stats.success_tokens:
                    continue
                k = stats.success_tokens[0]
                selected_k = k
                try:
                    adv_code = engine.apply_transform(code, rule_id, target_token=k)
                    rename_map = engine.get_last_rename_map() or {}
                except Exception:
                    continue
                if adv_code == code:
                    continue
                try:
                    tl, ts = engine.get_target_line_signal(code, rule_id, k)
                    adv_target_line = tl
                    adv_target_signal = (ts or "") if ts is not None else ""
                except Exception:
                    adv_target_line = None
                    adv_target_signal = ""

            # 写 orig 版本（与 apply_rule_on_dataset.py 保持结构一致）
            rec_orig = {
                "task_id": task_id,
                "rule_id": rule_id,
                "changed": False,
                "final": code,
            }
            (rule_results_orig / f"{task_id}.json").write_text(
                json.dumps(rec_orig, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

            # 写 adv 版本（target_token 供离线导出 SFT / 复现定位，与候选索引一致）
            tok_out = selected_k if selected_k is not None else k
            rec_adv = {
                "task_id": task_id,
                "rule_id": rule_id,
                "changed": True,
                "final": adv_code,
                "rename_map": rename_map or {},
                "params_used": params_used if isinstance(params_used, dict) else {},
                "target_token": tok_out,
                "target_line": adv_target_line,
                "target_signal": adv_target_signal or "",
            }
            (rule_results_adv / f"{task_id}.json").write_text(
                json.dumps(rec_adv, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

        # 规则层 coverage/success 统计
        total_samples = len(per_rule_stats)
        applicable_samples = sum(1 for s in per_rule_stats if s.num_candidates > 0)
        success_samples = sum(1 for s in per_rule_stats if s.num_success > 0)
        total_candidates = sum(s.num_candidates for s in per_rule_stats)
        total_success = sum(s.num_success for s in per_rule_stats)

        coverage = success_samples / total_samples if total_samples else 0.0
        success_rate = (total_success / total_candidates) if total_candidates else 0.0

        # 2. 调用 evaluate.py 评估 adv（original verdict 走全局缓存）
        eval_orig_dir = eval_output_root / rule_id / "orig_eval"
        eval_adv_dir = eval_output_root / rule_id / "adv_eval"
        eval_orig_dir.mkdir(parents=True, exist_ok=True)
        eval_adv_dir.mkdir(parents=True, exist_ok=True)

        base_cmd = [
            "python",
            "evaluate.py",
            "--dataset",
            str(dataset_path),
            "--provider",
            args.provider,
            "--model",
            args.model,
            "--temperature",
            "0.0",
            "--max-tokens",
            "2048",
            "--repeat",
            str(args.repeat),
        ]
        if args.base_url:
            base_cmd += ["--base-url", args.base_url]
        if args.api_key:
            base_cmd += ["--api-key", args.api_key]

        summary_adv_path = eval_adv_dir / "summary.json"
        reuse_existing = summary_adv_path.exists()

        if not reuse_existing:
            # 对抗
            cmd_adv = base_cmd + [
                "--results",
                str(rule_results_adv),
                "--output",
                str(eval_adv_dir),
                "--modes",
                "adversarial",
            ]
            if args.progress:
                cmd_adv.append("--progress")
            _run(cmd_adv, cwd=project_root, stream=bool(args.progress))

        # success（可应用且成功变换）口径：
        # 只对 num_success > 0 的 task_id 统计 original_passed / adversarial_passed。
        success_task_ids = [s.task_id for s in per_rule_stats if getattr(s, "num_success", 0) > 0]
        success_task_ids_set = set(success_task_ids)
        denom_samples = len(success_task_ids)

        # 若 cached original_confidence 缺失，则对当前规则的 success_task_ids 运行 evaluate.py(original) 补齐
        ensure_original_confidence(success_task_ids, rule_id)

        # acc_orig：从全局缓存中按 success_task_ids 统计
        orig_passed_cnt = 0
        conf_orig_sum = 0.0
        for tid in success_task_ids:
            entry = cache_tasks.get(tid)
            if entry and entry.get("original_passed") is True:
                orig_passed_cnt += 1
            c = entry.get("original_confidence") if entry else None
            if isinstance(c, (int, float)):
                conf_orig_sum += float(c)
        acc_orig = (orig_passed_cnt / denom_samples) if denom_samples else 0.0
        conf_orig_avg = (conf_orig_sum / denom_samples) if denom_samples else 0.0

        # acc_adv / ASR：从当前 rule 的 adv_eval per-task json 统计（避免加载 giant summary results 数组）
        adv_by_tid: Dict[str, Dict] = {}
        for adv_file in eval_adv_dir.glob("*_rep*.json"):
            if not adv_file.is_file():
                continue
            # 只取 rep0：与 denom_samples 的口径一致（repeat 通常为 1）
            if not adv_file.stem.endswith("_rep0"):
                continue
            tid = adv_file.stem.split("_rep")[0]
            if tid not in success_task_ids_set:
                continue
            try:
                adv_by_tid[tid] = json.loads(adv_file.read_text(encoding="utf-8"))
            except Exception:
                continue

        adv_passed_cnt = 0
        denom = 0
        numer = 0
        conf_adv_sum = 0.0
        for tid in success_task_ids:
            adv_j = adv_by_tid.get(tid)
            if not adv_j:
                continue
            ap = adv_j.get("adversarial_passed", None)
            if ap is True:
                adv_passed_cnt += 1
            c = adv_j.get("adversarial_confidence", None)
            if isinstance(c, (int, float)):
                conf_adv_sum += float(c)

            orig_entry = cache_tasks.get(tid) or {}
            if orig_entry.get("original_passed") is True:
                denom += 1
                if ap is False:
                    numer += 1

        acc_adv = (adv_passed_cnt / denom_samples) if denom_samples else 0.0
        asr = (numer / denom) if denom else None

        conf_orig_avg = (conf_orig_sum / denom_samples) if denom_samples else 0.0
        conf_adv_avg = (conf_adv_sum / denom_samples) if denom_samples else 0.0

        # gain_conf：与 ASR 同分母——仅在 success ∩ original_passed 子集上平均 conf（缺置信度记 0 参与分母，与 conf_orig/conf_adv 全量口径一致）
        denom_op = orig_passed_cnt
        conf_orig_sum_op = 0.0
        conf_adv_sum_op = 0.0
        for tid in success_task_ids:
            entry = cache_tasks.get(tid) or {}
            if entry.get("original_passed") is not True:
                continue
            co = entry.get("original_confidence")
            if isinstance(co, (int, float)):
                conf_orig_sum_op += float(co)
            adv_j = adv_by_tid.get(tid) or {}
            ca = adv_j.get("adversarial_confidence")
            if isinstance(ca, (int, float)):
                conf_adv_sum_op += float(ca)

        conf_orig_op_avg = (conf_orig_sum_op / denom_op) if denom_op else 0.0
        conf_adv_op_avg = (conf_adv_sum_op / denom_op) if denom_op else 0.0
        # LLM confidence：score = P(NO) - P(YES)；gain_conf 为对抗前后平均 score 之差（orig_pass 子集）
        gain_conf = conf_adv_op_avg - conf_orig_op_avg
        gain = gain_conf
        strength = coverage * gain_conf if gain_conf is not None else coverage

        rule_report = {
            "rule_id": rule_id,
            "num_samples": total_samples,
            "applicable_samples": applicable_samples,
            "success_samples": success_samples,
            "total_candidates": total_candidates,
            "total_success": total_success,
            "coverage": coverage,
            "success_rate": success_rate,
            "acc_orig": acc_orig,
            "acc_adv": acc_adv,
            "conf_orig": conf_orig_avg,
            "conf_adv": conf_adv_avg,
            "conf_orig_op": conf_orig_op_avg,
            "conf_adv_op": conf_adv_op_avg,
            "denom_orig_passed": denom_op,
            "gain": gain,
            "gain_conf": gain_conf,
            "asr": asr,
            "strength": strength,
        }
        overall_report.append(rule_report)

        # 也单独写一份 per-rule 报告
        (eval_output_root / f"{rule_id}_report.json").write_text(
            json.dumps(rule_report, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # 写总体报告
    (eval_output_root / "rules_report.json").write_text(
        json.dumps(overall_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()

