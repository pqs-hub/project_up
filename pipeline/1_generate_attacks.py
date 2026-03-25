#!/usr/bin/env python3
"""
基于 data/qualified_dataset.json（或任意 evaluate.py 风格 dataset.json），
对每个样本应用指定的单条 T-rule，生成 evaluate.py 所需的攻击结果目录。

输出（--results 目录下每个 task_id 一个 JSON）格式示例：
{
  "task_id": "q000001",
  "final": "<应用某条规则后的 RTL 代码>",
  "transform_id": "T09",
  "target_token": 0,
  "target_line": 42,
  "target_signal": "some_sig",
  "changed": true
}

之后可运行：
  python evaluate.py --results <results_dir> --dataset data/qualified_dataset.json \\
    --provider local --model <served_model_name> --base-url http://localhost:8001/v1 \\
    --output eval_results/qualified_T09
"""

import argparse
import json
import random
from pathlib import Path
from typing import Dict, Any, List

from ast_transforms_loader import create_engine


PROJECT_ROOT = Path(__file__).resolve().parents[2]


def load_dataset(path: Path) -> List[Dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError("dataset.json 顶层必须是列表")
    return data


def choose_candidate_token(engine, code: str, transform_id: str, strategy: str = "first") -> int | None:
    """
    简单选择候选 target_token：
    - first: 选第一个
    - random: 随机选一个
    """
    # engine._get_candidates_for_transform 是私有方法，这里只用公开 API：get_target_line_signal
    # 通过逐个尝试 target_token 直到返回 (line, signal) 非 (None, None) 来近似获得候选数。
    # 为控制开销，设置一个上限。
    max_probe = 64
    valid_indices = []
    for idx in range(max_probe):
        line, sig = engine.get_target_line_signal(code, transform_id, idx)
        if line is None and sig is None:
            break
        valid_indices.append(idx)
    if not valid_indices:
        return None
    if strategy == "random":
        return random.choice(valid_indices)
    return valid_indices[0]


def generate_attacks_for_rule(
    dataset_path: Path,
    results_dir: Path,
    transform_id: str,
    limit: int | None = None,
    token_strategy: str = "first",
) -> None:
    engine = create_engine()
    if transform_id not in engine.registry:
        raise ValueError(f"未知规则 ID: {transform_id}")

    tasks = load_dataset(dataset_path)
    if limit is not None:
        tasks = tasks[:limit]

    results_dir.mkdir(parents=True, exist_ok=True)

    count_total = 0
    count_changed = 0
    for task in tasks:
        task_id = task.get("task_id")
        rtl = task.get("canonical_solution", "")
        if not task_id or not rtl:
            continue
        count_total += 1

        try:
            token = choose_candidate_token(engine, rtl, transform_id, strategy=token_strategy)
        except Exception:
            token = None

        changed = False
        final_code = rtl
        target_line = None
        target_signal = None

        if token is not None:
            # 记录下候选对应的行/信号，便于后续分析
            tl, ts = engine.get_target_line_signal(rtl, transform_id, token)
            target_line = tl
            target_signal = ts
            try:
                obf = engine.apply_transform(rtl, transform_id, target_token=token)
            except Exception:
                obf = rtl
            if obf != rtl:
                changed = True
                final_code = obf

        if changed:
            count_changed += 1

        rec = {
            "task_id": task_id,
            "final": final_code,
            "transform_id": transform_id,
            "target_token": token,
            "target_line": target_line,
            "target_signal": target_signal,
            "changed": changed,
        }
        out_path = results_dir / f"{task_id}.json"
        with out_path.open("w", encoding="utf-8") as f:
            json.dump(rec, f, indent=2, ensure_ascii=False)

    summary = {
        "transform_id": transform_id,
        "num_tasks": count_total,
        "num_changed": count_changed,
    }
    with (results_dir / "summary.json").open("w", encoding="utf-8") as f:
        json.dump(summary, f, indent=2, ensure_ascii=False)
    print(f"[{transform_id}] 总任务数: {count_total}, 成功变换: {count_changed}, 结果目录: {results_dir}")


def main():
    parser = argparse.ArgumentParser(description="Generate per-rule adversarial RTL from qualified_dataset.json")
    parser.add_argument(
        "--dataset",
        type=str,
        default=str(PROJECT_ROOT / "data" / "qualified_dataset.json"),
        help="evaluate.py 风格的数据集（由 convert_qualified_to_dataset.py 生成）",
    )
    parser.add_argument(
        "--results",
        type=str,
        required=True,
        help="攻击结果输出目录（供 evaluate.py --results 使用）",
    )
    parser.add_argument(
        "--rule",
        type=str,
        required=True,
        help="待评估的规则 ID（如 T09, EXPR_DEMORGAN_AND 等）",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="最多处理多少个样本（默认全部）",
    )
    parser.add_argument(
        "--token-strategy",
        type=str,
        default="first",
        choices=["first", "random"],
        help="在多个候选位置中选择 target_token 的策略",
    )
    args = parser.parse_args()

    dataset_path = Path(args.dataset)
    results_dir = Path(args.results)
    generate_attacks_for_rule(
        dataset_path=dataset_path,
        results_dir=results_dir,
        transform_id=args.rule,
        limit=args.limit,
        token_strategy=args.token_strategy,
    )


if __name__ == "__main__":
    main()

