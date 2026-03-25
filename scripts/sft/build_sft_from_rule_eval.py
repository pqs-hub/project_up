#!/usr/bin/env python3
"""
从全量 rule_eval 产物构建与 filter_and_convert_sft 对齐的高质量 SFT jsonl。

口径（与 union_asr_report / ASR 一致）：
  original_passed==True（orig_verdict_cache）
  AND adversarial_passed==False（metrics/<T>/adv_eval/<tid>_rep0.json）
  AND results/<T>/adv/<tid>.json 存在、changed、final 与 canonical_solution 不同

混合粒度（mix）：
  - Head 规则（ASR 成功条数最多的前 head_top_k 条）：每个 task_id 至多保留 1 条，
    在该题所有「Head 规则上的成功」中选 adversarial_confidence 最大者。
  - Tail 规则：保留每个 (task_id, rule_id) 至多一条。

默认（推荐训练）：均衡模式 — 每规则先 uniform cap，再 equalize-to-min（各规则条数拉齐到
最少规则的量）。旧版 Head/Tail 不同上限易偏斜，需显式传 --legacy-head-tail-caps。

依赖：data/filter_and_convert_sft.build_sft_sample、ast_transforms_loader.create_engine
"""
from __future__ import annotations

import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "data"))

import ast_transforms_loader as ast_loader

from filter_and_convert_sft import build_sft_sample

RULE_DIR_RE = re.compile(r"^T\d")


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _norm_code(s: str) -> str:
    if not s:
        return ""
    s = s.replace("\r\n", "\n")
    return s


def _code_equal(a: str, b: str) -> bool:
    a, b = _norm_code(a), _norm_code(b)
    if a == b:
        return True
    # 宽松：逐行去尾部空白
    la = "\n".join(line.rstrip() for line in a.split("\n"))
    lb = "\n".join(line.rstrip() for line in b.split("\n"))
    return la == lb


def _load_cache_tasks(cache_path: Path, cache_key: Optional[str]) -> Tuple[Dict[str, Any], str]:
    blob = _load_json(cache_path)
    if cache_key:
        if cache_key not in blob:
            raise SystemExit(f"cache 中无分区: {cache_key!r}")
        key = cache_key
    else:
        keys = [k for k in blob if k != "tasks" and isinstance(blob.get(k), dict)]
        if len(keys) != 1:
            raise SystemExit(
                "请用 --cache-key 指定分区；候选:\n  " + "\n  ".join(keys[:12])
            )
        key = keys[0]
    section = blob[key]
    tasks = section.get("tasks") or {}
    if not isinstance(tasks, dict):
        raise SystemExit("cache 分区内无 tasks 对象")
    return tasks, key


def _iter_adv_eval_entries(metrics_root: Path) -> List[Tuple[str, str, Path]]:
    """返回 (rule_id, task_id, adv_json_path)。"""
    out: List[Tuple[str, str, Path]] = []
    for rule_dir in sorted(metrics_root.iterdir()):
        if not rule_dir.is_dir() or not RULE_DIR_RE.match(rule_dir.name):
            continue
        adv_eval = rule_dir / "adv_eval"
        if not adv_eval.is_dir():
            continue
        for f in adv_eval.glob("*_rep0.json"):
            stem = f.stem
            if "_rep" not in stem:
                continue
            tid = stem.split("_rep")[0]
            out.append((rule_dir.name, tid, f))
    return out


def _infer_target_token(
    engine,
    rtl: str,
    rule_id: str,
    params_used: Dict[str, Any],
    expected_final: str,
    stored: Optional[int],
) -> Optional[int]:
    if stored is not None:
        return stored
    tries: List[Optional[int]] = []
    try:
        cands = engine._get_candidates_for_transform(rtl, rule_id)
        if cands:
            tries = list(range(len(cands)))
        else:
            tries = [None]
    except Exception:
        tries = [None]

    pu = dict(params_used or {})
    for k in tries:
        try:
            out = engine.apply_transform(rtl, rule_id, target_token=k, **pu)
            if _code_equal(out, expected_final):
                return k
        except Exception:
            continue
    for k in range(32):
        if k in tries:
            continue
        try:
            out = engine.apply_transform(rtl, rule_id, target_token=k, **pu)
            if _code_equal(out, expected_final):
                return k
        except Exception:
            continue
    return None


def _collect_asr_rows(
    metrics_root: Path,
    results_root: Path,
    tasks: Dict[str, Any],
    task_rtl: Dict[str, str],
    allowed_rules: set,
) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    for rule_id, tid, adv_path in _iter_adv_eval_entries(metrics_root):
        if rule_id not in allowed_rules:
            continue
        entry = tasks.get(tid)
        if not entry or entry.get("original_passed") is not True:
            continue
        adv_blob = _load_json(adv_path)
        if adv_blob.get("adversarial_passed") is not False:
            continue
        rtl = task_rtl.get(tid) or ""
        res_path = results_root / rule_id / "adv" / f"{tid}.json"
        if not res_path.is_file():
            continue
        res = _load_json(res_path)
        if res.get("changed") is not True:
            continue
        final = res.get("final") or ""
        if not final or _code_equal(final, rtl):
            continue
        conf = adv_blob.get("adversarial_confidence")
        if not isinstance(conf, (int, float)):
            conf = float("-inf")
        tl = res.get("target_line")
        ts = res.get("target_signal")
        rows.append(
            {
                "task_id": tid,
                "rule_id": rule_id,
                "adversarial_confidence": float(conf),
                "final": final,
                "params_used": res.get("params_used") if isinstance(res.get("params_used"), dict) else {},
                "target_token": res.get("target_token"),
                "target_line": tl if tl is not None else None,
                "target_signal": ts if isinstance(ts, str) else None,
            }
        )
    return rows


def _apply_mix(
    rows: List[Dict[str, Any]],
    head_rules: set,
) -> List[Dict[str, Any]]:
    by_tid_head: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    tail_rows: List[Dict[str, Any]] = []
    for r in rows:
        rid = r["rule_id"]
        if rid in head_rules:
            by_tid_head[r["task_id"]].append(r)
        else:
            tail_rows.append(r)

    picked: List[Dict[str, Any]] = []
    for tid, lst in by_tid_head.items():
        best = max(lst, key=lambda x: x["adversarial_confidence"])
        picked.append(best)
    picked.extend(tail_rows)
    return picked


def _cap_per_rule(
    rows: List[Dict[str, Any]],
    head_rules: set,
    head_max: int,
    tail_max: int,
    seed: int,
) -> List[Dict[str, Any]]:
    rng = random.Random(seed)
    by_rule: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_rule[r["rule_id"]].append(r)
    out: List[Dict[str, Any]] = []
    for rid, lst in by_rule.items():
        cap = head_max if rid in head_rules else tail_max
        rng.shuffle(lst)
        out.extend(lst[:cap])
    rng.shuffle(out)
    return out


def _cap_uniform(
    rows: List[Dict[str, Any]],
    cap: int,
    seed: int,
) -> List[Dict[str, Any]]:
    """每条规则同一上限，便于 attack_name 分布更均匀（训练推荐）。"""
    rng = random.Random(seed)
    by_rule: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_rule[r["rule_id"]].append(r)
    out: List[Dict[str, Any]] = []
    for _rid, lst in by_rule.items():
        rng.shuffle(lst)
        out.extend(lst[:cap])
    rng.shuffle(out)
    return out


def _equalize_to_min_per_rule(
    rows: List[Dict[str, Any]], seed: int
) -> Tuple[List[Dict[str, Any]], int]:
    """
    各规则随机下采样到同一数量 m = min(各规则当前条数)，使 attack_name 分布完全均匀
    （受限于 ASR 成功最少的规则；无样本的规则不参与）。
    """
    rng = random.Random(seed)
    by_rule: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in rows:
        by_rule[r["rule_id"]].append(r)
    nonempty = [lst for lst in by_rule.values() if lst]
    if not nonempty:
        return [], 0
    m = min(len(lst) for lst in nonempty)
    out: List[Dict[str, Any]] = []
    for lst in by_rule.values():
        if not lst:
            continue
        rng.shuffle(lst)
        out.extend(lst[:m])
    rng.shuffle(out)
    return out, m


def main() -> int:
    ap = argparse.ArgumentParser(description="从 rule_eval 构建 ASR 对齐的高质量 SFT")
    ap.add_argument(
        "--dataset",
        type=Path,
        default=PROJECT_ROOT / "data" / "qualified_dataset.normalized.json",
    )
    ap.add_argument(
        "--metrics-root",
        type=Path,
        default=PROJECT_ROOT / "rule_eval" / "metrics_conf_v2_on_fullall_adv",
    )
    ap.add_argument(
        "--results-root",
        type=Path,
        default=PROJECT_ROOT / "rule_eval" / "results",
    )
    ap.add_argument(
        "--orig-cache",
        type=Path,
        default=PROJECT_ROOT / "rule_eval" / "orig_verdict_cache_conf_v2.json",
    )
    ap.add_argument("--cache-key", type=str, default=None)
    ap.add_argument(
        "--union-report",
        type=Path,
        default=PROJECT_ROOT
        / "rule_eval"
        / "metrics_conf_v2_on_fullall_adv"
        / "union_asr_report.json",
        help="若存在且未传 --cache-key，则读取其中的 cache_key_used",
    )
    ap.add_argument(
        "--output",
        type=Path,
        default=PROJECT_ROOT / "data" / "sft_from_eval_highquality.jsonl",
    )
    ap.add_argument(
        "--manifest",
        type=Path,
        default=PROJECT_ROOT / "data" / "sft_from_eval_build_manifest.json",
    )
    ap.add_argument("--head-top-k", type=int, default=5, help="按 ASR 成功条数取前 K 条规则为 Head（仅 legacy 策略）")
    ap.add_argument("--head-max-per-rule", type=int, default=1200)
    ap.add_argument("--tail-max-per-rule", type=int, default=600)
    ap.add_argument(
        "--legacy-head-tail-caps",
        action="store_false",
        dest="balanced",
        help="关闭默认均衡：改用 Head(前K规则上限高)/Tail 两套 per-rule cap（旧行为，规则分布易偏斜）",
    )
    ap.set_defaults(balanced=True)
    ap.add_argument(
        "--uniform-max-per-rule",
        type=int,
        default=500,
        help="默认均衡模式下每规则随机保留上限（默认 500）；之后会再按各规则最小条数截齐除非 --no-equalize-to-min",
    )
    ap.add_argument(
        "--no-equalize-to-min",
        action="store_true",
        help="默认均衡模式下不再将各规则下采样到同一数量（仅保留 uniform cap，长尾规则仍可能更少）",
    )
    ap.add_argument(
        "--equalize-to-min",
        action="store_true",
        help="与 --legacy-head-tail-caps 联用：在 Head/Tail cap 之后再按各规则最小条数截齐",
    )
    ap.add_argument("--max-total", type=int, default=None, help="全局再随机截断到此条数")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument(
        "--resolve-target-token",
        action="store_true",
        help="对磁盘 adv 中缺失的 target_token 枚举 k 对齐 final（慢；重跑 evaluate_rules 写入 target_token 后可省略）",
    )
    ap.add_argument(
        "--require-analyze",
        action="store_true",
        help="对磁盘上的 final 再跑 analyze，失败则丢弃",
    )
    args = ap.parse_args()

    cache_key = args.cache_key
    if cache_key is None and args.union_report.is_file():
        ur = _load_json(args.union_report)
        cache_key = ur.get("cache_key_used")
    tasks, used_key = _load_cache_tasks(args.orig_cache, cache_key)

    engine = ast_loader.create_engine()
    allowed_rules = set(engine.registry.keys())

    data = _load_json(args.dataset)
    if not isinstance(data, list):
        raise SystemExit("dataset 须为 JSON 数组")
    id2task = {t["task_id"]: t for t in data if t.get("task_id")}
    task_rtl = {tid: (id2task[tid].get("canonical_solution") or "") for tid in id2task}

    print("收集 ASR 成功行（join cache + adv_eval + results/adv）...")
    rows = _collect_asr_rows(
        args.metrics_root,
        args.results_root,
        tasks,
        task_rtl,
        allowed_rules,
    )
    raw_asr_hits = len(rows)
    print(f"  原始命中: {raw_asr_hits} 条")

    if args.require_analyze:
        analyze = ast_loader.analyze
        kept = []
        for r in rows:
            try:
                analyze(r["final"])
                kept.append(r)
            except Exception:
                continue
        print(f"  analyze 过滤后: {len(kept)} 条")
        rows = kept

    by_rule_ct = Counter(r["rule_id"] for r in rows)
    head_rules = {r for r, _ in by_rule_ct.most_common(args.head_top_k)}
    print(f"  Head 规则 (top-{args.head_top_k}): {sorted(head_rules)}")

    mixed = _apply_mix(rows, head_rules)
    print(f"  mix 去重后: {len(mixed)} 条")

    equalize_min_m = 0
    did_equalize_to_min = False
    if args.balanced:
        capped = _cap_uniform(mixed, args.uniform_max_per_rule, args.seed)
        after_per_rule_cap_count = len(capped)
        print(
            f"  均匀 cap（每规则≤{args.uniform_max_per_rule}）后: {after_per_rule_cap_count} 条"
        )
        if not args.no_equalize_to_min:
            capped, equalize_min_m = _equalize_to_min_per_rule(capped, args.seed + 2)
            did_equalize_to_min = True
            after_per_rule_cap_count = len(capped)
            n_rules_eq = len({r["rule_id"] for r in capped})
            print(
                f"  equalize-to-min: 每规则 {equalize_min_m} 条 × {n_rules_eq} 规则 → {after_per_rule_cap_count} 条"
            )
    else:
        capped = _cap_per_rule(
            mixed, head_rules, args.head_max_per_rule, args.tail_max_per_rule, args.seed
        )
        after_per_rule_cap_count = len(capped)
        print(f"  per-rule cap 后: {after_per_rule_cap_count} 条")
        if args.equalize_to_min:
            capped, equalize_min_m = _equalize_to_min_per_rule(capped, args.seed + 2)
            did_equalize_to_min = True
            after_per_rule_cap_count = len(capped)
            n_rules_eq = len({r["rule_id"] for r in capped})
            print(
                f"  equalize-to-min: 每规则 {equalize_min_m} 条 × {n_rules_eq} 规则 → {after_per_rule_cap_count} 条"
            )

    if args.max_total is not None and len(capped) > args.max_total:
        rng = random.Random(args.seed + 1)
        rng.shuffle(capped)
        capped = capped[: args.max_total]
        print(f"  max-total 截断后: {len(capped)} 条")

    out_lines: List[Dict[str, Any]] = []
    missing_task = 0
    resolve_ok = 0
    for i, r in enumerate(capped):
        tid = r["task_id"]
        task = id2task.get(tid)
        if not task:
            missing_task += 1
            continue
        spec = task.get("prompt") or ""
        rtl = task.get("canonical_solution") or ""
        training_sample = {
            "input": (
                f"**功能规范**：\n{spec}\n\n"
                f"**原始代码**：\n```verilog\n{rtl}\n```"
            ),
        }
        tt = r.get("target_token")
        if tt is not None and not isinstance(tt, int):
            try:
                tt = int(tt)
            except (TypeError, ValueError):
                tt = None
        if tt is None and args.resolve_target_token:
            tt = _infer_target_token(
                engine,
                rtl,
                r["rule_id"],
                r["params_used"],
                r["final"],
                None,
            )
        if tt is not None or r.get("target_line") is not None:
            resolve_ok += 1
        meta: Dict[str, Any] = {
            "transform_id": r["rule_id"],
            "target_token": tt,
            "parameters": r["params_used"] or {},
        }

        # Prefer the exact engine-resolved (target_line, target_signal).
        # This avoids relying on heuristic get_line_number() which may drift from the engine's candidate ordering.
        tl = r.get("target_line")
        ts = r.get("target_signal")
        if tl is not None:
            meta["target_line"] = tl
        if isinstance(ts, str) and ts.strip():
            meta["target_signal"] = ts.strip()

        if tt is not None and (meta.get("target_line") is None or not meta.get("target_signal")):
            try:
                tl2, ts2 = engine.get_target_line_signal(rtl, r["rule_id"], tt)
                if tl is None and tl2 is not None:
                    meta["target_line"] = tl2
                if (not ts or not str(ts).strip()) and ts2:
                    meta["target_signal"] = ts2
            except Exception:
                # Keep whatever we already have (may be None), build_sft_sample has fallbacks for legacy data.
                pass
        try:
            item = build_sft_sample(training_sample, meta)
            out_lines.append(item)
        except Exception as e:
            print(f"  跳过 {tid} {r['rule_id']}: build_sft_sample {e}", file=sys.stderr)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        for item in out_lines:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    pr: Counter = Counter()
    with open(args.output, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                o = json.loads(line).get("output", "")
                m = re.search(r'"attack_name"\s*:\s*"([^"]+)"', o)
                if m:
                    pr[m.group(1)] += 1
            except json.JSONDecodeError:
                pass

    manifest = {
        "cache_key": used_key,
        "dataset": str(args.dataset),
        "metrics_root": str(args.metrics_root),
        "results_root": str(args.results_root),
        "head_top_k": args.head_top_k,
        "head_rules": sorted(head_rules),
        "head_max_per_rule": args.head_max_per_rule,
        "tail_max_per_rule": args.tail_max_per_rule,
        "max_total": args.max_total,
        "seed": args.seed,
        "raw_asr_hits": raw_asr_hits,
        "rows_after_optional_analyze": len(rows),
        "mix_rows": len(mixed),
        "after_per_rule_cap": after_per_rule_cap_count,
        "after_max_total": len(capped),
        "written": len(out_lines),
        "missing_task": missing_task,
        "target_token_resolved": resolve_ok,
        "balanced": args.balanced,
        "uniform_max_per_rule": args.uniform_max_per_rule if args.balanced else None,
        "no_equalize_to_min": args.no_equalize_to_min,
        "equalize_to_min": did_equalize_to_min,
        "equalize_min_per_rule": equalize_min_m,
        "legacy_equalize_flag": args.equalize_to_min,
        "per_rule_raw_asr": dict(by_rule_ct.most_common()),
        "per_rule_written": dict(pr),
    }

    args.manifest.parent.mkdir(parents=True, exist_ok=True)
    args.manifest.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"已写入 {args.output} ({len(out_lines)} 条)")
    print(f"manifest: {args.manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
