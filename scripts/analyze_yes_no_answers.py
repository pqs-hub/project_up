#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""分析数据集中的yes/no判断结果"""

import json
import sys
from collections import Counter

if len(sys.argv) < 2:
    print("用法: python analyze_yes_no_answers.py <dataset.jsonl>")
    sys.exit(1)

dataset_file = sys.argv[1]

# 统计
total = 0
answer_pairs = []
rule_answers = {}

with open(dataset_file, 'r', encoding='utf-8') as f:
    for line in f:
        if not line.strip():
            continue
        
        sample = json.loads(line)
        total += 1
        
        original_ans = sample.get('judge_original_answer', 'N/A')
        transformed_ans = sample.get('judge_transformed_answer', 'N/A')
        rule = sample.get('attack_rule', 'Unknown')
        
        answer_pairs.append((original_ans, transformed_ans))
        
        if rule not in rule_answers:
            rule_answers[rule] = []
        rule_answers[rule].append((original_ans, transformed_ans))

print("=" * 60)
print("数据集yes/no判断分析")
print("=" * 60)
print(f"总样本数: {total}")

# 统计答案对
print("\n答案翻转统计:")
pair_counts = Counter(answer_pairs)
for (orig, trans), count in pair_counts.most_common():
    pct = count / total * 100
    emoji = "✅" if orig == "yes" and trans == "no" else "⚠️"
    print(f"  {emoji} {orig} → {trans}: {count} ({pct:.1f}%)")

# 按规则统计
print("\n按攻击规则统计:")
for rule, pairs in sorted(rule_answers.items()):
    yes_to_no = sum(1 for o, t in pairs if o == "yes" and t == "no")
    total_rule = len(pairs)
    pct = yes_to_no / total_rule * 100 if total_rule > 0 else 0
    print(f"  {rule}: {yes_to_no}/{total_rule} ({pct:.1f}%) yes→no")

# 检查异常情况
print("\n异常检查:")
unusual = []
for line_no, (orig, trans) in enumerate(answer_pairs, 1):
    if orig == "no":
        unusual.append(f"  样本{line_no}: 原始代码被判为no（不应该出现）")
    if trans == "yes":
        unusual.append(f"  样本{line_no}: 变换后代码被判为yes（攻击失败）")

if unusual:
    print("⚠️  发现异常样本:")
    for msg in unusual[:10]:
        print(msg)
    if len(unusual) > 10:
        print(f"  ... 还有 {len(unusual) - 10} 个异常")
else:
    print("✅ 没有发现异常样本")

print("=" * 60)
