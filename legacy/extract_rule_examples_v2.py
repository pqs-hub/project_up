#!/usr/bin/env python3
"""从qualified数据中提取每个规则的成功和失败样本"""

import json
import os
from collections import defaultdict
import glob

def analyze_rule_samples():
    """分析每个规则的成功和失败样本"""
    base_dir = '/data3/pengqingsong/LLM_attack/results/qualified_by_rule'
    
    # 获取所有规则目录
    rule_dirs = [d for d in os.listdir(base_dir) if os.path.isdir(os.path.join(base_dir, d)) and d.startswith('T')]
    
    results = {}
    
    for rule_id in sorted(rule_dirs):
        rule_dir = os.path.join(base_dir, rule_id)
        
        success_samples = []
        failure_samples = []
        
        # 读取该规则下的所有样本
        json_files = glob.glob(os.path.join(rule_dir, '*.json'))
        
        for filepath in json_files[:100]:  # 只读取前100个样本
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                
                task_id = data.get('task_id', 'Unknown')
                changed = data.get('changed', False)
                
                # 读取评估结果
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
                
                # 攻击成功：原始正确 AND 对抗错误 AND 代码改变
                is_success = (orig_truth == True) and (adv_truth == False) and changed
                
                sample_info = {
                    'task_id': task_id,
                    'original_truth': orig_truth,
                    'adversarial_truth': adv_truth,
                    'changed': changed,
                    'code': data.get('final', '')[:400]
                }
                
                if is_success:
                    success_samples.append(sample_info)
                else:
                    failure_samples.append(sample_info)
                    
            except Exception as e:
                continue
        
        results[rule_id] = {
            'success': success_samples,
            'failure': failure_samples
        }
    
    # 打印结果
    print("=" * 100)
    print("规则库攻击成功/失败样本分析")
    print("=" * 100)
    
    for rule_id in sorted(results.keys()):
        success_samples = results[rule_id]['success']
        failure_samples = results[rule_id]['failure']
        
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
                print(f"  代码片段:\n{sample['code'][:250]}...")
        
        # 显示失败样本
        if failure_samples:
            print(f"\n✗ 攻击失败样本 (前2个):")
            for i, sample in enumerate(failure_samples[:2], 1):
                print(f"\n  示例 {i}:")
                print(f"  Task ID: {sample['task_id']}")
                print(f"  原始判断: {sample['original_truth']}, 对抗判断: {sample['adversarial_truth']}")
                print(f"  代码是否改变: {sample['changed']}")

if __name__ == '__main__':
    analyze_rule_samples()
