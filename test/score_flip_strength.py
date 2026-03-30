#!/usr/bin/env python3
"""
对 sft_canonical_v_json.jsonl 中每条样本，用 verifier 分别评估：

核心指标（同时看 yes 和 no，排除"致盲攻击"干扰）：
  margin_orig   = log(p_no_orig / p_yes_orig)  （负值：倾向yes）
  margin_adv    = log(p_no_adv  / p_yes_adv)   （越正越好：模型被说服输出no）
  flip_strength = margin_adv - margin_orig       （攻击把模型从yes拉向no的力度）

辅助指标：
  p_yes_orig / p_yes_adv / delta_yes  （兼容旧版）
  p_no_adv                            （"致盲攻击"检测：p_no_adv < 0.5 说明模型变傻而非被说服）

输出：
  sft_canonical_scored.jsonl  -- 带完整信号的样本
  flip_strength_report.txt    -- 规则级统计报告（含致盲攻击比例）

用法:
  python test/score_flip_strength.py [--workers 16] [--limit 1000]
"""

import argparse
import json
import re
import sys
import difflib
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import yaml
from core.target_model import TargetModelClient

BASE = Path("/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset")


def load_config() -> dict:
    cfg_path = PROJECT_ROOT / "config.yaml"
    with open(cfg_path) as f:
        return yaml.safe_load(f)


def extract_spec_and_orig(input_text: str) -> tuple[str, str]:
    """从 SFT input 字段提取 spec 和去行号的原始代码"""
    spec_m = re.search(r"###\s*功能规范\s*\n(.*?)(?=###|```)", input_text, re.DOTALL)
    spec = spec_m.group(1).strip() if spec_m else ""

    code_m = re.search(r"```verilog\s*\n(.*?)```", input_text, re.DOTALL)
    orig_code = ""
    if code_m:
        numbered = code_m.group(1)
        lines = []
        for line in numbered.split("\n"):
            # 去掉行号前缀 "N: "
            cleaned = re.sub(r"^\s*\d+:\s?", "", line)
            lines.append(cleaned)
        orig_code = "\n".join(lines).strip()

    return spec, orig_code


import math as _math


def _safe_margin(p_no, p_yes) -> float:
    """log(p_no/p_yes)，即归一化log-odds，正值=倾向no，负值=倾向yes"""
    if p_yes is None or p_no is None:
        return None
    if p_yes <= 0 or p_no <= 0:
        return None
    return round(_math.log(p_no / p_yes), 4)


def compute_structural_features(orig_code: str, adv_code: str) -> dict:
    """计算代码结构特征：行数、长度、diff ratio"""
    orig_lines = orig_code.splitlines()
    adv_lines  = adv_code.splitlines()
    matcher = difflib.SequenceMatcher(None, orig_lines, adv_lines)
    diff_ratio = round(1.0 - matcher.ratio(), 4)  # 0=完全一样，1=完全不同
    return {
        "code_lines":      len(orig_lines),
        "code_length":     len(orig_code),
        "code_diff_ratio": diff_ratio,
    }


def score_sample(client: TargetModelClient, sample: dict) -> dict:
    spec, orig_code = extract_spec_and_orig(sample["input"])
    adv_code = sample.get("transformed_rtl", "")

    result = dict(sample)
    # 初始化所有信号字段
    for k in ("p_yes_orig", "p_no_orig", "margin_orig",
              "p_yes_adv",  "p_no_adv",  "margin_adv",
              "flip_strength", "delta_yes", "adv_is_correct",
              "blinding_attack"):
        result[k] = None

    if not spec or not orig_code or not adv_code:
        result["score_error"] = "missing_fields"
        return result

    # --- 评估原始代码 ---
    v_orig = client.judge(spec, orig_code)
    if v_orig is not None:
        result["p_yes_orig"] = v_orig.get("p_yes", v_orig.get("confidence"))
        result["p_no_orig"]  = v_orig.get("p_no")
        result["margin_orig"] = (
            v_orig.get("margin")
            or _safe_margin(result["p_no_orig"], result["p_yes_orig"])
        )

    # --- 评估攻击后代码 ---
    v_adv = client.judge(spec, adv_code)
    if v_adv is not None:
        result["p_yes_adv"]    = v_adv.get("p_yes", v_adv.get("confidence"))
        result["p_no_adv"]     = v_adv.get("p_no")
        result["adv_is_correct"] = v_adv.get("is_correct")
        result["margin_adv"] = (
            v_adv.get("margin")
            or _safe_margin(result["p_no_adv"], result["p_yes_adv"])
        )

    # --- 计算核心指标 ---
    if result["margin_orig"] is not None and result["margin_adv"] is not None:
        # flip_strength: margin 的变化量，越大说明攻击把模型从yes拉向no越有力
        result["flip_strength"] = round(result["margin_adv"] - result["margin_orig"], 4)

    if result["p_yes_orig"] is not None and result["p_yes_adv"] is not None:
        result["delta_yes"] = round(result["p_yes_orig"] - result["p_yes_adv"], 4)

    # --- 致盲攻击检测 ---
    if result["p_no_adv"] is not None:
        result["blinding_attack"] = bool(result["p_no_adv"] < 0.5)

    # --- 结构特征 ---
    if orig_code and adv_code:
        result.update(compute_structural_features(orig_code, adv_code))

    return result


def load_checkpoint(ckpt_path: Path) -> dict:
    """key: sample_idx (str) -> scored result"""
    if not ckpt_path.exists():
        return {}
    data = {}
    with open(ckpt_path) as f:
        for line in f:
            if line.strip():
                s = json.loads(line)
                data[str(s["_ckpt_idx"])] = s
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers",    type=int, default=16)
    parser.add_argument("--limit",      type=int, default=0, help="0=全部")
    parser.add_argument("--input",      type=str,
                        default=str(BASE / "sft_clean_v_json.fixed.jsonl"),
                        help="评估全量样本；canonical样本用 sft_canonical_v_json.jsonl")
    parser.add_argument("--output",     type=str,
                        default=str(BASE / "sft_all_scored.jsonl"))
    parser.add_argument("--report",     type=str,
                        default=str(BASE / "flip_strength_report.txt"))
    parser.add_argument("--checkpoint", type=str,
                        default=str(BASE / "score_checkpoint.jsonl"),
                        help="断点续传文件，中断后重运行自动跳过已完成项")
    parser.add_argument("--save-every", type=int, default=200,
                        help="每 N 条写入一次checkpoint")
    args = parser.parse_args()

    cfg = load_config()["target_model"]
    client = TargetModelClient(
        base_url=cfg["base_url"],
        api_key=cfg.get("api_key", "EMPTY"),
        model=cfg["model"],
        timeout=cfg.get("timeout", 60),
        max_retries=cfg.get("max_retries", 3),
    )

    samples = []
    with open(args.input) as f:
        for i, line in enumerate(f):
            if args.limit and i >= args.limit:
                break
            if line.strip():
                samples.append(json.loads(line))

    # 加载断点，跳过已完成的
    ckpt_path = Path(args.checkpoint)
    checkpoint = load_checkpoint(ckpt_path)
    scored = [None] * len(samples)
    for k, v in checkpoint.items():
        idx = int(k)
        if idx < len(scored):
            scored[idx] = v

    todo_indices = [i for i in range(len(samples)) if scored[i] is None]
    print(f"待评估样本: {len(samples)} 条，已完成: {len(checkpoint)}，"
          f"待处理: {len(todo_indices)}， workers={args.workers}")

    ckpt_file = open(ckpt_path, "a")  # 追加模式
    done = 0
    pending_writes = {}  # idx -> result

    try:
        with ThreadPoolExecutor(max_workers=args.workers) as ex:
            fut_to_idx = {ex.submit(score_sample, client, samples[i]): i
                          for i in todo_indices}
            for fut in as_completed(fut_to_idx):
                idx = fut_to_idx[fut]
                try:
                    res = fut.result()
                except Exception as e:
                    res = {**samples[idx], "score_error": str(e)}
                res["_ckpt_idx"] = idx
                scored[idx] = res
                pending_writes[idx] = res
                done += 1

                # 每 save_every 条刷入checkpoint
                if done % args.save_every == 0 or done == len(todo_indices):
                    for _, r in sorted(pending_writes.items()):
                        ckpt_file.write(json.dumps(r, ensure_ascii=False) + "\n")
                    ckpt_file.flush()
                    pending_writes.clear()
                    print(f"  {len(checkpoint) + done}/{len(samples)} 已完成，已写checkpoint")
    finally:
        # 确保剩余结果写入
        if pending_writes:
            for _, r in sorted(pending_writes.items()):
                ckpt_file.write(json.dumps(r, ensure_ascii=False) + "\n")
            ckpt_file.flush()
        ckpt_file.close()

    # 写最终输出
    with open(args.output, "w") as f:
        for s in scored:
            if s:
                out = {k: v for k, v in s.items() if k != "_ckpt_idx"}
                f.write(json.dumps(out, ensure_ascii=False) + "\n")

    # --- 规则级统计 ---
    import statistics

    rule_stats = defaultdict(lambda: {
        "n": 0,
        "flip_strength_list": [], "margin_adv_list": [],
        "delta_yes_list": [], "p_yes_orig_list": [], "p_no_adv_list": [],
        "n_blinding": 0,
    })
    n_no_signal = 0

    for s in scored:
        if not s:
            continue
        rid = s.get("rule_id", "?")
        st = rule_stats[rid]
        st["n"] += 1

        fs = s.get("flip_strength")
        if fs is not None:
            st["flip_strength_list"].append(fs)
        else:
            n_no_signal += 1

        for key, lst in [
            ("margin_adv",  "margin_adv_list"),
            ("delta_yes",   "delta_yes_list"),
            ("p_yes_orig",  "p_yes_orig_list"),
            ("p_no_adv",    "p_no_adv_list"),
        ]:
            v = s.get(key)
            if v is not None:
                st[lst].append(v)

        if s.get("blinding_attack"):
            st["n_blinding"] += 1

    hdr = (f"{'规则':<6} {'n':>5} {'avg_flip':>9} {'med_flip':>9} "
           f"{'avg_margin_adv':>15} {'avg_p_orig':>11} "
           f"{'p_no_adv>=0.5(%)':>17} {'blind(%)':>9}")
    sep = "-" * len(hdr)

    lines = ["flip_strength 规则级统计报告（核心指标: flip_strength = margin_adv - margin_orig）",
             "=" * len(hdr),
             f"总样本: {len(samples)}  无法计算flip_strength: {n_no_signal}",
             "",
             "致盲攻击定义: 攻击后 p_no_adv < 0.5（模型变傻而非被说服输出no）",
             "", hdr, sep]

    for rid in sorted(rule_stats):
        st = rule_stats[rid]
        fsl = st["flip_strength_list"]
        if not fsl:
            lines.append(f"{rid:<6} {st['n']:>5}" + "  N/A" * 6)
            continue

        avg_fs  = sum(fsl) / len(fsl)
        med_fs  = statistics.median(fsl)
        mal     = st["margin_adv_list"]
        avg_ma  = sum(mal) / len(mal) if mal else float("nan")
        pol     = st["p_yes_orig_list"]
        avg_po  = sum(pol) / len(pol) if pol else float("nan")
        pnal    = st["p_no_adv_list"]
        pct_ok  = sum(1 for v in pnal if v >= 0.5) / len(pnal) * 100 if pnal else float("nan")
        pct_bl  = st["n_blinding"] / st["n"] * 100

        lines.append(
            f"{rid:<6} {st['n']:>5} {avg_fs:>9.3f} {med_fs:>9.3f} "
            f"{avg_ma:>15.3f} {avg_po:>11.4f} "
            f"{pct_ok:>16.1f}% {pct_bl:>8.1f}%"
        )

    report_text = "\n".join(lines)
    with open(args.report, "w") as f:
        f.write(report_text)
    print("\n" + report_text)
    print(f"\n评分结果: {args.output}")
    print(f"报告: {args.report}")


if __name__ == "__main__":
    main()
