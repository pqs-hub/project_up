#!/usr/bin/env python3
"""分析每个规则的成功和失败样本"""

import json
import os
from collections import defaultdict

def load_jsonl(filepath):
    """加载 JSONL 文件"""
    data = []
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data

def analyze_rule_samples():
    """分析每个规则的成功和失败样本"""
    
    # 读取 metadata 文件（包含规则和评估结果）
    metadata_file = '/data3/pengqingsong/LLM_attack/data/adversarial_dataset.metadata.jsonl'
    
    if not os.path.exists(metadata_file):
        print(f"文件不存在: {metadata_file}")
        return
    
    metadata = load_jsonl(metadata_file)
    
    # 按规则分组
    rule_samples = defaultdict(lambda: {'success': [], 'failure': []})
    
    for item in metadata:
        rule_id = item.get('rule_id', 'Unknown')
        task_id = item.get('task_id', 'Unknown')
        
        # 判断是否成功（原始正确，对抗错误）
        orig_truth = item.get('original_truth', False)
        adv_truth = item.get('adversarial_truth', False)
        
        # 攻击成功：原始正确 AND 对抗错误
        is_success = orig_truth and not adv_truth
        
        sample_info = {
            'task_id': task_id,
            'original_truth': orig_truth,
            'adversarial_truth': adv_truth,
            'variant_id': item.get('variant_id', 'Unknown')
        }
        
        if is_success:
            rule_samples[rule_id]['success'].append(sample_info)
        else:
            rule_samples[rule_id]['failure'].append(sample_info)
    
    # 输出结果
    print("=" * 80)
    print("规则库攻击成功/失败样本分析")
    print("=" * 80)
    
    # 按规则ID排序
    for rule_id in sorted(rule_samples.keys()):
        if rule_id == 'Unknown':
            continue
            
        success_samples = rule_samples[rule_id]['success']
        failure_samples = rule_samples[rule_id]['failure']
        
        total = len(success_samples) + len(failure_samples)
        success_rate = len(success_samples) / total * 100 if total > 0 else 0
        
        print(f"\n{'='*80}")
        print(f"规则: {rule_id}")
        print(f"{'='*80}")
        print(f"总样本数: {total}")
        print(f"成功样本: {len(success_samples)} ({success_rate:.2f}%)")
        print(f"失败样本: {len(failure_samples)} ({100-success_rate:.2f}%)")
        
        # 显示前3个成功样本
        if success_samples:
            print(f"\n✓ 成功样本示例 (前3个):")
            for i, sample in enumerate(success_samples[:3], 1):
                print(f"  {i}. Task: {sample['task_id']}, Variant: {sample['variant_id']}")
        
        # 显示前3个失败样本
        if failure_samples:
            print(f"\n✗ 失败样本示例 (前3个):")
            for i, sample in enumerate(failure_samples[:3], 1):
                print(f"  {i}. Task: {sample['task_id']}, Variant: {sample['variant_id']}")
                print(f"     原始: {sample['original_truth']}, 对抗: {sample['adversarial_truth']}")
    
    # 保存详细结果到JSON
    output_file = '/data3/pengqingsong/LLM_attack/rule_samples_analysis.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(dict(rule_samples), f, indent=2, ensure_ascii=False)
    
    print(f"\n\n详细结果已保存到: {output_file}")

if __name__ == '__main__':
    analyze_rule_samples()
