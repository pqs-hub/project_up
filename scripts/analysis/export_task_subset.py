#!/usr/bin/env python3
"""
从主数据集中按 task_id 列表导出一个子集：
- 写一个 dataset.json（与 evaluate.py / evaluate_rules 相同字段：task_id, prompt, canonical_solution, test）
- 将每条样本的 SPEC(prompt)、RTL、testbench 分别写入子目录中的独立文件，便于单独打开或版本管理。

示例：

  python scripts/analysis/export_task_subset.py \\
    --task-list rule_eval/unflipped_orig_pass_tasks.txt \\
    --dataset data/qualified_dataset.normalized.json \\
    --out-dir data/unflipped_orig_pass_subset
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path


def main() -> None:
    ap = argparse.ArgumentParser(description="按 task_id 列表导出 dataset.json + 分文件 SPEC/RTL/TB")
    ap.add_argument("--task-list", required=True, help="每行一个 task_id 的文本文件")
    ap.add_argument("--dataset", required=True, help="完整 dataset.json 路径")
    ap.add_argument(
        "--out-dir",
        required=True,
        help="输出根目录（将创建 spec/ rtl/ testbench/ 与 dataset.json）",
    )
    ap.add_argument(
        "--encoding",
        default="utf-8",
        help="文本文件编码（默认 utf-8）",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    list_path = root / args.task_list
    dataset_path = root / args.dataset
    out_dir = root / args.out_dir

    ids: list[str] = []
    for line in list_path.read_text(encoding=args.encoding).splitlines():
        tid = line.strip()
        if tid and not tid.startswith("#"):
            ids.append(tid)
    id_set = set(ids)

    data = json.loads(dataset_path.read_text(encoding=args.encoding))
    if not isinstance(data, list):
        raise SystemExit("dataset 顶层必须是 JSON 数组")

    by_id = {str(t.get("task_id")): t for t in data if t.get("task_id")}
    missing = sorted(id_set - set(by_id.keys()))
    if missing:
        raise SystemExit(f"以下 task_id 在数据集中不存在（共 {len(missing)} 个）: {missing[:20]}{'...' if len(missing) > 20 else ''}")

    spec_dir = out_dir / "spec"
    rtl_dir = out_dir / "rtl"
    tb_dir = out_dir / "testbench"
    for d in (spec_dir, rtl_dir, tb_dir):
        d.mkdir(parents=True, exist_ok=True)

    subset: list[dict] = []
    for tid in ids:
        item = by_id[tid]
        prompt = item.get("prompt") or ""
        rtl = item.get("canonical_solution") or ""
        test = item.get("test") or ""

        (spec_dir / f"{tid}.txt").write_text(prompt, encoding=args.encoding)
        (rtl_dir / f"{tid}.v").write_text(rtl, encoding=args.encoding)
        (tb_dir / f"{tid}.v").write_text(test, encoding=args.encoding)

        subset.append(
            {
                "task_id": tid,
                "prompt": prompt,
                "canonical_solution": rtl,
                "test": test,
            }
        )

    out_json = out_dir / "dataset.json"
    out_json.write_text(json.dumps(subset, ensure_ascii=False, indent=2), encoding=args.encoding)

    print(f"已导出 {len(subset)} 条样本 -> {out_dir}")
    print(f"  - {out_json}")
    print(f"  - {spec_dir}/<task_id>.txt")
    print(f"  - {rtl_dir}/<task_id>.v")
    print(f"  - {tb_dir}/<task_id>.v")


if __name__ == "__main__":
    main()
