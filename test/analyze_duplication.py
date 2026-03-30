#!/usr/bin/env python3
"""用不同策略分析重复率"""

import json
import hashlib
from pathlib import Path

def analyze_duplication_strategies():
    input_file = "/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/attack_success_samples.jsonl"
    
    # 读取样本
    samples = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                samples.append(json.loads(line))
    
    print(f"总样本数: {len(samples)}")
    
    # 策略1: 仅基于变换后代码去重
    print("\n=== 策略1: 仅基于变换后代码去重 ===")
    code_fps = set()
    code_duplicates = 0
    for sample in samples:
        code = sample.get('transformed_rtl', '')
        code_fp = hashlib.md5(''.join(code.split()).encode()).hexdigest()
        if code_fp in code_fps:
            code_duplicates += 1
        else:
            code_fps.add(code_fp)
    print(f"重复样本: {code_duplicates}")
    print(f"重复率: {code_duplicates/len(samples)*100:.2f}%")
    
    # 策略2: 基于规则+变换后代码去重
    print("\n=== 策略2: 基于规则+变换后代码去重 ===")
    rule_code_fps = set()
    rule_code_duplicates = 0
    for sample in samples:
        rule_id = sample.get('rule_id', '')
        code = sample.get('transformed_rtl', '')
        combined = f"{rule_id}|{''.join(code.split())}"
        fp = hashlib.md5(combined.encode()).hexdigest()
        if fp in rule_code_fps:
            rule_code_duplicates += 1
        else:
            rule_code_fps.add(fp)
    print(f"重复样本: {rule_code_duplicates}")
    print(f"重复率: {rule_code_duplicates/len(samples)*100:.2f}%")
    
    # 策略3: 仅基于输入去重
    print("\n=== 策略3: 仅基于输入去重 ===")
    input_fps = set()
    input_duplicates = 0
    for sample in samples:
        input_text = sample.get('input', '')
        input_fp = hashlib.md5(''.join(input_text.split()).encode()).hexdigest()
        if input_fp in input_fps:
            input_duplicates += 1
        else:
            input_fps.add(input_fp)
    print(f"重复样本: {input_duplicates}")
    print(f"重复率: {input_duplicates/len(samples)*100:.2f}%")
    
    # 分析数据来源
    print("\n=== 数据来源分析 ===")
    external_samples = 0
    original_samples = 0
    for sample in samples:
        source = sample.get('source_file', '')
        if 'external_dataset' in source:
            external_samples += 1
        else:
            original_samples += 1
    print(f"原始数据集样本: {original_samples}")
    print(f"外部数据集样本: {external_samples}")
    
    # 按规则分析重复情况
    print("\n=== 按规则分析重复率 ===")
    rule_stats = {}
    for sample in samples:
        rule_id = sample.get('rule_id', 'unknown')
        code = sample.get('transformed_rtl', '')
        code_fp = hashlib.md5(''.join(code.split()).encode()).hexdigest()
        
        if rule_id not in rule_stats:
            rule_stats[rule_id] = {'total': 0, 'duplicates': 0, 'fps': set()}
        
        rule_stats[rule_id]['total'] += 1
        if code_fp in rule_stats[rule_id]['fps']:
            rule_stats[rule_id]['duplicates'] += 1
        else:
            rule_stats[rule_id]['fps'].add(code_fp)
    
    for rule_id, stats in sorted(rule_stats.items()):
        total = stats['total']
        dups = stats['duplicates']
        rate = dups / total * 100 if total > 0 else 0
        print(f"{rule_id}: {dups}/{total} ({rate:.1f}%)")

if __name__ == "__main__":
    analyze_duplication_strategies()
