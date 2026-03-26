#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析数据集中的失败样本"""

import json
import sys
from collections import Counter, defaultdict

if len(sys.argv) < 2:
    print("用法: python analyze_failures.py <dataset.jsonl>")
    sys.exit(1)

dataset_file = sys.argv[1]

# 统计
total = 0
status_counts = Counter()
rule_status = defaultdict(lambda: Counter())

with open(dataset_file, 'r', encoding='utf-8') as f:
    for line in f:
        if not line.strip():
            continue
        
        sample = json.loads(line)
        total += 1
        
        status = sample.get('status', 'unknown')
        rule = sample.get('attack_rule', 'Unknown')
        
        status_counts[status] += 1
        rule_status[rule][status] += 1

print("=" * 60)
print("数据集失败分析")
print("=" * 60)
print(f"总样本数: {total}")

# 状态分布
print("\n样本状态分布:")
for status, count in status_counts.most_common():
    pct = count / total * 100
    emoji = "✅" if status == "success" else "❌"
    print(f"  {emoji} {status}: {count} ({pct:.1f}%)")

# 按规则统计
print("\n按攻击规则统计:")
for rule in sorted(rule_status.keys()):
    counts = rule_status[rule]
    total_rule = sum(counts.values())
    success = counts.get('success', 0)
    attack_failed = counts.get('attack_failed', 0)
    testbench_failed = counts.get('testbench_failed', 0)
    
    print(f"\n  {rule} (总计{total_rule}):")
    print(f"    成功: {success} ({success/total_rule*100:.1f}%)")
    if attack_failed > 0:
        print(f"    攻击失败: {attack_failed} ({attack_failed/total_rule*100:.1f}%)")
    if testbench_failed > 0:
        print(f"    testbench失败: {testbench_failed} ({testbench_failed/total_rule*100:.1f}%)")

# 提取失败原因
print("\n" + "=" * 60)
print("失败原因分析")
print("=" * 60)

failure_reasons = Counter()
with open(dataset_file, 'r', encoding='utf-8') as f:
    for line in f:
        if not line.strip():
            continue
        sample = json.loads(line)
        if sample.get('status') != 'success' and 'failure_reason' in sample:
            failure_reasons[sample['failure_reason']] += 1

if failure_reasons:
    for reason, count in failure_reasons.most_common():
        print(f"  • {reason}: {count}次")
else:
    print("  （所有样本都成功或无失败原因记录）")

print("=" * 60)
