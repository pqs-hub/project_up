#!/usr/bin/env python3
"""从qualified数据中提取每个规则的成功和失败样本"""

import json
import os
from collections import defaultdict
import glob

def load_qualified_samples():
    """加载qualified样本"""
    qualified_dir = '/data3/pengqingsong/LLM_attack/results/qualified_by_rule'
    
    # 按规则分组
    rule_samples = defaultdict(lambda: {'success': [], 'failure': []})
    
    # 遍历所有qualified文件
    for filepath in glob.glob(os.path.join(qualified_dir, '*.json')):
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            task_id = data.get('task_id', 'Unknown')
            rule_id = data.get('rule_id', 'Unknown')
            changed = data.get('changed', False)
            
            # 读取对应的评估结果
            eval_file = f'/data3/pengqingsong/LLM_attack/rule_eval/metrics/{rule_id}/orig_eval/{task_id}_rep0.json'
            adv_eval_file = f'/data3/pengqingsong/LLM_attack/rule_eval/metrics/{rule_id}/adv_eval/{task_id}_rep0.json'
            
            orig_truth = None
            adv_truth = None
            
            if os.path.exists(eval_file):
                with open(eval_file, 'r') as f:
                    eval_data = json.load(f)
                    orig_truth = eval_data.get('original_truth', None)
            
            if os.path.exists(adv_eval_file):
                with open(adv_eval_file, 'r') as f:
                    adv_eval_data = json.load(f)
                    adv_truth = adv_eval_data.get('adversarial_truth', None)
            
            # 攻击成功：原始正确 AND 对抗错误
            is_success = (orig_truth == True) and (adv_truth == False) and changed
            
            sample_info = {
                'task_id': task_id,
                'original_truth': orig_truth,
                'adversarial_truth': adv_truth,
                'changed': changed,
                'code': data.get('final', '')[:500]  # 只保留前500字符
            }
            
            if is_success:
                rule_samples[rule_id]['success'].append(sample_info)
            else:
                rule_samples[rule_id]['failure'].append(sample_info)
                
        except Exception as e:
            print(f"Error processing {filepath}: {e}")
            continue
    
    return rule_samples

def print_rule_examples():
    """打印每个规则的示例"""
    rule_samples = load_qualified_samples()
    
    print("=" * 100)
    print("规则库攻击成功/失败样本分析")
    print("=" * 100)
    
    # 按规则ID排序
    for rule_id in sorted(rule_samples.keys()):
        if rule_id == 'Unknown':
            continue
            
        success_samples = rule_samples[rule_id]['success']
        failure_samples = rule_samples[rule_id]['failure']
        
        total = len(success_samples) + len(failure_samples)
        if total == 0:
            continue
            
        success_rate = len(success_samples) / total * 100 if total > 0 else 0
        
        print(f"\n{'='*100}")
        print(f"规则: {rule_id}")
        print(f"{'='*100}")
        print(f"总样本数: {total}")
        print(f"成功样本: {len(success_samples)} ({success_rate:.2f}%)")
        print(f"失败样本: {len(failure_samples)} ({100-success_rate:.2f}%)")
        
        # 显示成功样本
        if success_samples:
            print(f"\n✓ 攻击成功样本 (前2个):")
            for i, sample in enumerate(success_samples[:2], 1):
                print(f"\n  示例 {i}:")
                print(f"  Task ID: {sample['task_id']}")
                print(f"  原始判断: {sample['original_truth']}, 对抗判断: {sample['adversarial_truth']}")
                print(f"  代码片段:\n{sample['code'][:300]}...")
        
        # 显示失败样本
        if failure_samples:
            print(f"\n✗ 攻击失败样本 (前2个):")
            for i, sample in enumerate(failure_samples[:2], 1):
                print(f"\n  示例 {i}:")
                print(f"  Task ID: {sample['task_id']}")
                print(f"  原始判断: {sample['original_truth']}, 对抗判断: {sample['adversarial_truth']}")
                print(f"  代码是否改变: {sample['changed']}")
                if sample['code']:
                    print(f"  代码片段:\n{sample['code'][:300]}...")

if __name__ == '__main__':
    print_rule_examples()
