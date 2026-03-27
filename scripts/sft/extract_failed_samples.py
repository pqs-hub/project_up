#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
提取单规则攻击失败的样本

从原始数据集中提取那些单规则攻击未成功的样本，用于多规则束搜索攻击
"""

import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


def main():
    # 文件路径
    original_dataset = PROJECT_ROOT / "data" / "qualified_newcot_noconfidence.json"
    success_dataset = PROJECT_ROOT / "data" / "attack_dataset_20260326_1816.jsonl"
    output_failed = PROJECT_ROOT / "data" / "single_rule_failed_samples.json"
    
    print("=" * 70)
    print("提取单规则攻击失败的样本")
    print("=" * 70)
    
    # 1. 读取原始数据集
    print(f"\n[1/4] 读取原始数据集: {original_dataset}")
    with open(original_dataset, 'r', encoding='utf-8') as f:
        original_samples = json.load(f)
    print(f"  原始样本数: {len(original_samples)}")
    
    # 2. 读取成功攻击的数据
    print(f"\n[2/4] 读取成功攻击数据: {success_dataset}")
    success_task_ids = set()
    with open(success_dataset, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data = json.loads(line)
                success_task_ids.add(data['task_id'])
    print(f"  成功攻击的 task_id 数: {len(success_task_ids)}")
    
    # 3. 提取失败的样本
    print(f"\n[3/4] 提取单规则攻击失败的样本...")
    failed_samples = [
        sample for sample in original_samples
        if sample['task_id'] not in success_task_ids
    ]
    print(f"  失败样本数: {len(failed_samples)}")
    print(f"  成功率: {len(success_task_ids) / len(original_samples) * 100:.2f}%")
    
    # 4. 保存失败样本
    print(f"\n[4/4] 保存失败样本到: {output_failed}")
    with open(output_failed, 'w', encoding='utf-8') as f:
        json.dump(failed_samples, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 70)
    print("完成！")
    print("=" * 70)
    print(f"\n统计信息:")
    print(f"  原始样本: {len(original_samples)}")
    print(f"  单规则成功: {len(success_task_ids)}")
    print(f"  单规则失败: {len(failed_samples)}")
    print(f"  成功率: {len(success_task_ids) / len(original_samples) * 100:.2f}%")
    print(f"\n输出文件: {output_failed}")
    print(f"\n下一步: 对这些失败样本运行束搜索攻击")
    print(f"  python scripts/sft/run_beam_search_attack.py \\")
    print(f"    --dataset {output_failed} \\")
    print(f"    --output data/multi_rule_attacks.json \\")
    print(f"    --beam-width 3 \\")
    print(f"    --max-depth 3")


if __name__ == "__main__":
    main()
