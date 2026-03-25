#!/usr/bin/env python3
"""从真实数据中提取每个规则的攻击成功和失败样本"""

import json
import os
import glob
from collections import defaultdict

def extract_rule_examples():
    """提取每个规则的成功和失败样本"""
    
    results_dir = '/data3/pengqingsong/LLM_attack/rule_eval/results_full_all_rules'
    metrics_dir = '/data3/pengqingsong/LLM_attack/rule_eval/metrics_conf_v2_on_fullall_adv'
    
    # 获取所有规则
    rule_dirs = [d for d in os.listdir(results_dir) if os.path.isdir(os.path.join(results_dir, d)) and d.startswith('T')]
    
    all_results = {}
    
    for rule_id in sorted(rule_dirs):
        print(f"处理规则 {rule_id}...")
        
        success_samples = []
        failure_samples = []
        
        # 读取该规则的对抗样本
        adv_dir = os.path.join(results_dir, rule_id, 'adv')
        if not os.path.exists(adv_dir):
            continue
        
        adv_files = glob.glob(os.path.join(adv_dir, '*.json'))
        
        for adv_file in adv_files[:50]:  # 每个规则最多读50个样本
            try:
                # 读取对抗代码
                with open(adv_file, 'r', encoding='utf-8') as f:
                    adv_data = json.load(f)
                
                task_id = adv_data.get('task_id', '')
                changed = adv_data.get('changed', False)
                adv_code = adv_data.get('final', '')
                
                # 读取评估结果
                eval_file = os.path.join(metrics_dir, rule_id, 'adv_eval', f'{task_id}_rep0.json')
                orig_eval_file = os.path.join(metrics_dir, rule_id, 'orig_eval', f'{task_id}_rep0.json')
                
                if not os.path.exists(eval_file) or not os.path.exists(orig_eval_file):
                    continue
                
                with open(eval_file, 'r') as f:
                    eval_data = json.load(f)
                
                with open(orig_eval_file, 'r') as f:
                    orig_eval_data = json.load(f)
                
                orig_truth = orig_eval_data.get('original_truth', None)
                adv_truth = eval_data.get('adversarial_truth', None)
                
                # 攻击成功：原始正确 AND 对抗错误 AND 代码改变
                is_success = (orig_truth == True) and (adv_truth == False) and changed
                
                # 读取原始代码
                orig_file = os.path.join(results_dir, rule_id, 'orig', f'{task_id}.json')
                orig_code = ''
                if os.path.exists(orig_file):
                    with open(orig_file, 'r') as f:
                        orig_data = json.load(f)
                        orig_code = orig_data.get('final', '')
                
                sample_info = {
                    'task_id': task_id,
                    'original_truth': orig_truth,
                    'adversarial_truth': adv_truth,
                    'changed': changed,
                    'original_code': orig_code[:500],
                    'adversarial_code': adv_code[:500]
                }
                
                if is_success:
                    success_samples.append(sample_info)
                else:
                    failure_samples.append(sample_info)
                    
            except Exception as e:
                print(f"  错误处理 {adv_file}: {e}")
                continue
        
        all_results[rule_id] = {
            'success': success_samples,
            'failure': failure_samples
        }
        
        print(f"  {rule_id}: 成功 {len(success_samples)}, 失败 {len(failure_samples)}")
    
    return all_results

def print_results(all_results):
    """打印结果"""
    print("\n" + "=" * 120)
    print("规则库真实攻击成功/失败样本分析")
    print("=" * 120)
    
    for rule_id in sorted(all_results.keys()):
        success_samples = all_results[rule_id]['success']
        failure_samples = all_results[rule_id]['failure']
        
        total = len(success_samples) + len(failure_samples)
        if total == 0:
            continue
            
        success_rate = len(success_samples) / total * 100 if total > 0 else 0
        
        print(f"\n{'='*120}")
        print(f"规则: {rule_id}")
        print(f"{'='*120}")
        print(f"总样本数: {total}")
        print(f"成功样本: {len(success_samples)} ({success_rate:.2f}%)")
        print(f"失败样本: {len(failure_samples)} ({100-success_rate:.2f}%)")
        
        # 显示成功样本
        if success_samples:
            print(f"\n✓ 攻击成功样本 (前2个):")
            for i, sample in enumerate(success_samples[:2], 1):
                print(f"\n  【成功示例 {i}】")
                print(f"  Task ID: {sample['task_id']}")
                print(f"  原始判断: {sample['original_truth']}, 对抗判断: {sample['adversarial_truth']}")
                print(f"\n  原始代码:")
                print(f"  {sample['original_code'][:300]}...")
                print(f"\n  对抗代码:")
                print(f"  {sample['adversarial_code'][:300]}...")
        
        # 显示失败样本
        if failure_samples:
            print(f"\n✗ 攻击失败样本 (前2个):")
            for i, sample in enumerate(failure_samples[:2], 1):
                print(f"\n  【失败示例 {i}】")
                print(f"  Task ID: {sample['task_id']}")
                print(f"  原始判断: {sample['original_truth']}, 对抗判断: {sample['adversarial_truth']}")
                print(f"  代码是否改变: {sample['changed']}")
                if sample['changed']:
                    print(f"\n  对抗代码:")
                    print(f"  {sample['adversarial_code'][:300]}...")

if __name__ == '__main__':
    results = extract_rule_examples()
    print_results(results)
    
    # 保存到文件
    output_file = '/data3/pengqingsong/LLM_attack/rule_examples_report.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n\n详细结果已保存到: {output_file}")
