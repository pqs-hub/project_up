#!/usr/bin/env python3
"""
在 dataset.json 上应用固定的单条 T-rule，生成 evaluate.py 可用的攻击结果目录。

输入：
  - dataset.json：由 scripts/dataset/convert_qualified_to_dataset.py 生成，
    每条样本包含：
      {
        "task_id": "...",
        "prompt": "...",
        "canonical_solution": "<RefModule 版本 RTL>",
        "test": "<testbench>"
      }

输出：
  - results_dir 下为若干 JSON 文件，每个 task_id 一条，例如：
      {
        "task_id": "q000001",
        "rule_id": "T09",
        "changed": true,
        "final": "<应用规则后的 RTL 代码>"
      }
  - evaluate.py 会把该目录当作 --results 使用，读取其中的 "final" 作为 adversarial 代码。

注意：
  - 这里只是按固定规则在 canonical_solution 上做一次变换：
      - 若无可用候选或规则未改变代码，则 "changed": false，final=原始代码。
  - 多次堆叠、复杂度分桶等高级指标后续可以在此脚本基础上扩展。
"""

import argparse
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ast_transforms_loader import create_engine


def apply_rule_to_dataset(
    dataset_path: Path,
    rule_id: str,
    results_dir: Path,
) -> None:
    with dataset_path.open("r", encoding="utf-8") as f:
        dataset = json.load(f)

    engine = create_engine()
    if rule_id not in engine.registry:
        raise ValueError(f"未知规则 ID: {rule_id}（engine.registry 中不存在）")

    results_dir.mkdir(parents=True, exist_ok=True)

    total = 0
    changed_cnt = 0
    applicable_cnt = 0

    for task in dataset:
        task_id = task.get("task_id")
        code = task.get("canonical_solution", "")
        if not task_id or not code:
            continue
        total += 1

        # 粗略检查该规则是否有候选：用 target_token=0 调一次 get_target_line_signal
        line, sig = engine.get_target_line_signal(code, rule_id, 0)
        has_candidate = line is not None or sig is not None
        if has_candidate:
            applicable_cnt += 1
            try:
                new_code = engine.apply_transform(code, rule_id, target_token=0)
            except Exception:
                new_code = code
        else:
            new_code = code

        changed = new_code != code
        if changed:
            changed_cnt += 1

        rec = {
            "task_id": task_id,
            "rule_id": rule_id,
            "changed": changed,
            "final": new_code,
        }
        out_path = results_dir / f"{task_id}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)

    summary = {
        "rule_id": rule_id,
        "total_tasks": total,
        "applicable_tasks": applicable_cnt,
        "changed_tasks": changed_cnt,
    }
    with (results_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)

    print(
        f"规则 {rule_id}: total={total}, applicable={applicable_cnt}, "
        f"changed={changed_cnt}。结果已写入 {results_dir}"
    )


def main():
    parser = argparse.ArgumentParser(description="Apply T-rule(s) on dataset.json to generate adversarial RTL")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(PROJECT_ROOT / "data" / "qualified_dataset.json"),
        help="evaluate.py 使用的 dataset.json 路径",
    )
    parser.add_argument(
        "--rule",
        type=str,
        default=None,
        help="单条规则 ID，例如 T09、T34；与 --all-rules 二选一",
    )
    parser.add_argument(
        "--all-rules",
        action="store_true",
        help="遍历引擎中所有规则，每条规则写入 results 下的子目录 <rule_id>/",
    )
    parser.add_argument(
        "--results",
        type=str,
        default=str(PROJECT_ROOT / "results" / "qualified_by_rule"),
        help="攻击结果根目录；单规则时直接写到此目录，--all-rules 时写到此目录下的 <rule_id>/",
    )
    args = parser.parse_args()

    if not args.rule and not args.all_rules:
        parser.error("请指定 --rule <规则ID> 或 --all-rules")
    if args.rule and args.all_rules:
        parser.error("--rule 与 --all-rules 不可同时使用")

    dataset_path = Path(args.dataset)
    base_results = Path(args.results)
    engine = create_engine()
    rule_ids = list(engine.registry.keys()) if args.all_rules else [args.rule]

    for rule_id in rule_ids:
        if rule_id not in engine.registry:
            print(f"跳过未知规则: {rule_id}")
            continue
        results_dir = base_results / rule_id if args.all_rules else base_results
        apply_rule_to_dataset(
            dataset_path=dataset_path,
            rule_id=rule_id,
            results_dir=results_dir,
        )


if __name__ == "__main__":
    main()

