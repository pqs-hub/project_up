#!/usr/bin/env python3
"""
对指定 task_id 列表，汇总它们在已生成的对抗结果里「有哪些变体规则」。

默认读取：
  rule_eval/results_full_all_rules/<rule_id>/adv/<task_id>.json
该文件在 evaluate_rules.py 中由变换器输出（final 字段为变换后的 RTL）。

输出：
  - 一个 JSON：task_id -> {rules:[...], changed:[...]}（按规则出现情况）
  - 一个 JSON：rule_id -> count（该规则对多少个 task 生成了 adv 结果）

可选：
  - --dump-rtl：把每个 (rule_id, task_id) 的 final RTL 导出到 out_dir/rtl/<rule_id>/<task_id>.v
    （文件数量可能较大）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def main() -> None:
    ap = argparse.ArgumentParser(description="汇总 task 子集的变体规则集合")
    ap.add_argument(
        "--task-list",
        required=True,
        help="文本文件：每行一个 task_id（如 q000005）",
    )
    ap.add_argument(
        "--results-root",
        default="rule_eval/results_full_all_rules",
        help="evaluate_rules 生成的 results_full_all_rules 根目录",
    )
    ap.add_argument(
        "--out-dir",
        required=True,
        help="输出目录（将创建 variants_summary.json 等文件）",
    )
    ap.add_argument(
        "--dump-rtl",
        action="store_true",
        help="额外导出 final RTL（大量小文件）",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    task_list_path = root / args.task_list
    results_root = root / args.results_root
    out_dir = root / args.out_dir

    if not task_list_path.exists():
        raise SystemExit(f"task-list 不存在: {task_list_path}")
    if not results_root.exists():
        raise SystemExit(f"results-root 不存在: {results_root}")

    ids: List[str] = []
    for line in task_list_path.read_text(encoding="utf-8").splitlines():
        tid = line.strip()
        if not tid or tid.startswith("#"):
            continue
        ids.append(tid)
    ids_set = set(ids)

    # discover rule dirs
    rule_dirs: List[Tuple[str, Path]] = []
    for p in sorted(results_root.iterdir()):
        if not p.is_dir():
            continue
        rule_id = p.name
        adv_dir = p / "adv"
        if adv_dir.is_dir():
            rule_dirs.append((rule_id, adv_dir))
    if not rule_dirs:
        raise SystemExit(f"在 {results_root} 下未发现任何 */adv 目录")

    # Initialize
    by_task: Dict[str, Dict[str, Any]] = {}
    rule_counts: Dict[str, int] = {rid: 0 for rid, _ in rule_dirs}

    if args.dump_rtl:
        rtl_root = out_dir / "rtl"
        rtl_root.mkdir(parents=True, exist_ok=True)

    for tid in ids:
        rules_hit: List[str] = []
        changed_hit: List[bool] = []
        for rid, adv_dir in rule_dirs:
            f = adv_dir / f"{tid}.json"
            if not f.exists():
                continue
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                # 文件损坏也要保留 rule_id
                rules_hit.append(rid)
                changed_hit.append(False)
                continue
            rules_hit.append(rid)
            changed_hit.append(bool(j.get("changed", True)))

            if args.dump_rtl:
                final_rtl = j.get("final") or ""
                if final_rtl:
                    (rtl_root / rid).mkdir(parents=True, exist_ok=True)
                    (rtl_root / rid / f"{tid}.v").write_text(final_rtl, encoding="utf-8")

        by_task[tid] = {
            "task_id": tid,
            "rules": rules_hit,
            "changed": changed_hit,
            "num_variants": len(rules_hit),
        }
        for rid in by_task[tid]["rules"]:
            rule_counts[rid] = rule_counts.get(rid, 0) + 1

    out_dir.mkdir(parents=True, exist_ok=True)
    variants_summary_path = out_dir / "variants_summary.json"
    variants_summary_path.write_text(json.dumps(by_task, ensure_ascii=False, indent=2), encoding="utf-8")

    rule_counts_path = out_dir / "variants_rule_counts.json"
    rule_counts_path.write_text(
        json.dumps(
            {k: rule_counts[k] for k in sorted(rule_counts.keys())},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    # quick human-readable sample
    sample_tid = ids[0] if ids else None
    if sample_tid:
        print(f"输出：{variants_summary_path}")
        print(f"输出：{rule_counts_path}")
        print(f"样本示例 task={sample_tid}: rules={by_task[sample_tid]['rules']}")
    else:
        print(f"输出：{variants_summary_path}")
        print(f"输出：{rule_counts_path}")


if __name__ == "__main__":
    main()

