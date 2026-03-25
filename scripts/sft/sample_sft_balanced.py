#!/usr/bin/env python3
"""
从 SFT 数据集中按 attack_name 均匀抽样，得到分布更均衡的子集。
通过对每个规则做上限采样（cap），削弱头部规则占比，保留所有规则。
"""
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SFT = PROJECT_ROOT / "data" / "sft_dataset_final.jsonl"
DEFAULT_OUT = PROJECT_ROOT / "data" / "sft_dataset_balanced.jsonl"


def extract_attack_name(output: str) -> Optional[str]:
    m = re.search(r'"attack_name"\s*:\s*"([^"]+)"', output)
    return m.group(1).strip() if m else None


def main():
    parser = argparse.ArgumentParser(description="从 SFT 中按 attack_name 均匀抽样")
    parser.add_argument("--input", type=str, default=str(DEFAULT_SFT), help="输入 jsonl 路径")
    parser.add_argument("--output", type=str, default=str(DEFAULT_OUT), help="输出 jsonl 路径")
    parser.add_argument("--max-per-rule", type=int, default=1500, help="每个 attack_name 最多保留条数（超出则随机抽样）；越小分布越均匀，如 500/300")
    parser.add_argument("--min-per-rule", type=int, default=0, help="少于该条数的规则整类丢弃（0 表示不丢弃）")
    parser.add_argument("--target-per-rule", type=int, default=None, help="若指定，则等价于 --max-per-rule 设为该值（用于强调「目标每类条数」）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    parser.add_argument("--no-shuffle", action="store_true", help="不打乱顺序，按规则顺序写出")
    args = parser.parse_args()

    inp_path = Path(args.input)
    out_path = Path(args.output)
    if not inp_path.exists():
        print(f"未找到输入: {inp_path}")
        return 1

    max_per = args.target_per_rule if args.target_per_rule is not None else args.max_per_rule
    if args.target_per_rule is not None:
        print(f"使用 --target-per-rule {args.target_per_rule}，即每规则最多保留 {max_per} 条")

    random.seed(args.seed)

    # 按 attack_name 分组
    by_rule = defaultdict(list)
    no_attack = 0
    with open(inp_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            name = extract_attack_name(d.get("output", ""))
            if not name:
                no_attack += 1
                continue
            by_rule[name].append(d)

    before = {k: len(v) for k, v in by_rule.items()}
    total_before = sum(before.values())
    print(f"原始: {total_before} 条, {len(by_rule)} 种规则, 无 attack_name: {no_attack} 条")

    # 过滤过少的规则
    if args.min_per_rule > 0:
        by_rule = {k: v for k, v in by_rule.items() if len(v) >= args.min_per_rule}
        dropped = set(before.keys()) - set(by_rule.keys())
        if dropped:
            print(f"因 --min-per-rule {args.min_per_rule} 丢弃规则: {dropped}")

    # 每个规则最多留 max_per 条（随机抽样）
    sampled = []
    for name, items in by_rule.items():
        n = len(items)
        if n <= max_per:
            chosen = items
        else:
            chosen = random.sample(items, max_per)
        sampled.extend(chosen)

    if not args.no_shuffle:
        random.shuffle(sampled)

    after = Counter(extract_attack_name(d.get("output", "")) for d in sampled)
    total_after = len(sampled)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for d in sampled:
            f.write(json.dumps(d, ensure_ascii=False) + "\n")

    print(f"均衡后: {total_after} 条, {len(after)} 种规则")
    print(f"已写入: {out_path}")
    print("\n--- 均衡后 attack_name 分布（前 20）---")
    for name, count in after.most_common(20):
        pct = 100 * count / total_after
        print(f"  {count:5d} ({pct:5.2f}%)  {name}")
    if len(after) > 20:
        print(f"  ... 共 {len(after)} 种")
    return 0


if __name__ == "__main__":
    sys.exit(main())
