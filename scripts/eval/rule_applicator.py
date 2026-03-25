#!/usr/bin/env python3
"""
单规则应用器：在单个样本上统计某条 T-rule 的候选数和成功变换数。

用法示例（快速 sanity check）：

    python scripts/eval/rule_applicator.py --rule T09 --dataset data/qualified_dataset.json --sample-limit 100
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional
import sys

# 确保可以从项目根目录导入 ast_transforms_loader 等模块
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from ast_transforms_loader import create_engine  # 加载 ast_transforms.2.py


engine = create_engine()


@dataclass
class RuleApplyStats:
    task_id: str
    rule_id: str
    num_candidates: int
    num_success: int
    success_tokens: List[int]


def apply_rule_on_sample(rule_id: str, task_id: str, code: str) -> RuleApplyStats:
    """
    在单个样本上应用一条规则，统计候选与成功变换情况。

    - 候选列表统一通过 engine._get_candidates_for_transform 获取
    - 成功变换要求：apply_transform 后代码发生变化，且 analyze(new_code) 不抛异常
    """
    from ast_transforms_2 import analyze  # 通过 loader 已经注入到 sys.modules

    candidates = engine._get_candidates_for_transform(code, rule_id)
    num_candidates = len(candidates)

    num_success = 0
    success_tokens: List[int] = []

    for k in range(num_candidates):
        try:
            new_code = engine.apply_transform(code, rule_id, target_token=k)
        except Exception:
            continue
        if new_code == code:
            continue

        # 语法检查：能被 analyze 正常解析即可视为成功
        try:
            analyze(new_code)
        except Exception:
            continue

        num_success += 1
        success_tokens.append(k)

    return RuleApplyStats(
        task_id=task_id,
        rule_id=rule_id,
        num_candidates=num_candidates,
        num_success=num_success,
        success_tokens=success_tokens,
    )


def _cli() -> None:
    parser = argparse.ArgumentParser(description="单规则在数据集上的 coverage / success 统计（不跑 LLM）")
    parser.add_argument("--rule", required=True, help="规则 ID，例如 T09")
    parser.add_argument("--dataset", required=True, help="dataset.json 路径，例如 data/qualified_dataset.json")
    parser.add_argument("--output", help="输出统计 JSON 路径（可选）")
    parser.add_argument("--sample-limit", type=int, default=None, help="最多评估多少条样本")
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    data = json.loads(dataset_path.read_text(encoding="utf-8"))

    stats_list: List[RuleApplyStats] = []

    for i, task in enumerate(data):
        if args.sample_limit is not None and i >= args.sample_limit:
            break
        task_id = task.get("task_id")
        code = task.get("canonical_solution", "")
        if not task_id or not code:
            continue
        stats = apply_rule_on_sample(args.rule, task_id, code)
        stats_list.append(stats)

    total = len(stats_list)
    applicable = sum(1 for s in stats_list if s.num_candidates > 0)
    success_tasks = sum(1 for s in stats_list if s.num_success > 0)
    total_candidates = sum(s.num_candidates for s in stats_list)
    total_success = sum(s.num_success for s in stats_list)

    coverage = success_tasks / total if total else 0.0
    success_rate = (total_success / total_candidates) if total_candidates else 0.0

    summary = {
        "rule_id": args.rule,
        "num_samples": total,
        "applicable_samples": applicable,
        "success_samples": success_tasks,
        "total_candidates": total_candidates,
        "total_success": total_success,
        "coverage": coverage,
        "success_rate": success_rate,
        "details": [asdict(s) for s in stats_list],
    }

    if args.output:
        Path(args.output).write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    else:
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _cli()

