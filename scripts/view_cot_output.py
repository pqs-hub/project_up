#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查看攻击数据集中的CoT推理输出"""

import json
import sys

if len(sys.argv) < 2:
    print("用法: python view_cot_output.py <dataset.jsonl> [样本索引]")
    sys.exit(1)

dataset_file = sys.argv[1]
sample_idx = int(sys.argv[2]) if len(sys.argv) > 2 else 0

# 加载数据集
samples = []
with open(dataset_file, 'r', encoding='utf-8') as f:
    for line in f:
        if line.strip():
            samples.append(json.loads(line))

if not samples:
    print("数据集为空")
    sys.exit(1)

if sample_idx >= len(samples):
    print(f"样本索引超出范围，数据集共有 {len(samples)} 个样本")
    sys.exit(1)

sample = samples[sample_idx]

print("=" * 80)
print(f"样本 #{sample_idx + 1}/{len(samples)}: {sample.get('task_id', 'Unknown')}")
print("=" * 80)

print(f"\n📋 任务: {sample.get('task_id')}")
print(f"🎯 攻击规则: {sample.get('attack_rule')}")
print(f"📊 攻击参数: {json.dumps(sample.get('attack_params', {}), ensure_ascii=False)}")
print(f"✅ Testbench通过: {sample.get('testbench_passed')}")
print(f"🎭 判断模型被欺骗: {sample.get('judge_fooled')}")
print(f"📈 置信度: {sample.get('judge_confidence', 0):.4f}")
print(f"🔵 原始代码判断: {sample.get('judge_original_answer', 'N/A')}")
print(f"🔴 变换后代码判断: {sample.get('judge_transformed_answer', 'N/A')}")

print("\n" + "=" * 80)
print("📝 功能规范")
print("=" * 80)
print(sample.get('prompt', '')[:300])
if len(sample.get('prompt', '')) > 300:
    print("...")

print("\n" + "=" * 80)
print("🔵 原始代码（前200字符）")
print("=" * 80)
print(sample.get('original_code', '')[:200])
if len(sample.get('original_code', '')) > 200:
    print("...")

print("\n" + "=" * 80)
print("🔴 变换后代码（前200字符）")
print("=" * 80)
print(sample.get('transformed_code', '')[:200])
if len(sample.get('transformed_code', '')) > 200:
    print("...")

print("\n" + "=" * 80)
print("💭 判断模型CoT推理 - 原始代码")
print("=" * 80)
cot_original = sample.get('judge_cot_original', '')
if cot_original:
    print(cot_original)
else:
    print("（未记录）")

print("\n" + "=" * 80)
print("💭 判断模型CoT推理 - 变换后代码")
print("=" * 80)
cot_transformed = sample.get('judge_cot_transformed', '')
if cot_transformed:
    print(cot_transformed)
else:
    print("（未记录）")

print("\n" + "=" * 80)
print("🔍 CoT对比分析")
print("=" * 80)

if cot_original and cot_transformed:
    orig_lines = cot_original.split('\n')
    trans_lines = cot_transformed.split('\n')
    
    print(f"原始代码推理行数: {len(orig_lines)}")
    print(f"变换后代码推理行数: {len(trans_lines)}")
    
    # 提取关键差异
    orig_lower = cot_original.lower()
    trans_lower = cot_transformed.lower()
    
    keywords = ['错误', 'error', '不正确', 'incorrect', '误导', 'misleading', 
                '注释', 'comment', '混淆', 'confusing']
    
    print("\n关键词出现情况:")
    for keyword in keywords:
        orig_count = orig_lower.count(keyword)
        trans_count = trans_lower.count(keyword)
        if orig_count > 0 or trans_count > 0:
            print(f"  '{keyword}': 原始{orig_count}次, 变换后{trans_count}次")
else:
    print("CoT输出未完整记录")

print("\n" + "=" * 80)
print(f"查看更多样本: python {sys.argv[0]} {dataset_file} <索引>")
print(f"可用索引范围: 0-{len(samples)-1}")
print("=" * 80)
