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
    
    # 加载原始代码数据集 - 从qualified_dataset.json中获取
    print("加载原始代码数据集...")
    original_code_map = {}
    spec_map = {}
    
    qualified_dataset_file = '/data3/pengqingsong/LLM_attack/data/qualified_dataset.json'
    if os.path.exists(qualified_dataset_file):
        with open(qualified_dataset_file, 'r', encoding='utf-8') as f:
            dataset = json.load(f)
            for item in dataset:
                task_id = item.get('task_id', '')
                canonical_solution = item.get('canonical_solution', '')
                prompt = item.get('prompt', '')
                if task_id and canonical_solution:
                    original_code_map[task_id] = canonical_solution
                    spec_map[task_id] = prompt
    
    print(f"加载了 {len(original_code_map)} 个原始代码样本和规范")
    
    # 获取有评估数据的规则
    rule_dirs = [d for d in os.listdir(metrics_dir) if os.path.isdir(os.path.join(metrics_dir, d)) and d.startswith('T')]
    
    all_results = {}
    
    for rule_id in sorted(rule_dirs):
        print(f"处理规则 {rule_id}...")
        
        success_samples = []
        failure_samples = []
        
        # 读取该规则的对抗样本
        adv_dir = os.path.join(results_dir, rule_id, 'adv')
        if not os.path.exists(adv_dir):
            print(f"  跳过 {rule_id}: 没有对抗样本目录")
            continue
        
        adv_files = glob.glob(os.path.join(adv_dir, '*.json'))
        
        for adv_file in adv_files[:100]:  # 每个规则最多读100个样本
            try:
                # 读取对抗代码
                with open(adv_file, 'r', encoding='utf-8') as f:
                    adv_data = json.load(f)
                
                task_id = adv_data.get('task_id', '')
                changed = adv_data.get('changed', False)
                adv_code = adv_data.get('final', '')
                
                # 读取评估结果
                eval_file = os.path.join(metrics_dir, rule_id, 'adv_eval', f'{task_id}_rep0.json')
                
                if not os.path.exists(eval_file):
                    continue
                
                with open(eval_file, 'r') as f:
                    eval_data = json.load(f)
                
                orig_truth = eval_data.get('original_truth', None)
                adv_truth = eval_data.get('adversarial_truth', None)
                
                # 攻击成功：原始正确 AND 对抗错误 AND 代码改变
                is_success = (orig_truth == True) and (adv_truth == False) and changed
                
                # 读取原始代码和spec - 从数据集中获取
                orig_code = original_code_map.get(task_id, '')
                spec = spec_map.get(task_id, '')
                
                # 如果数据集中没有，尝试从orig目录读取
                if not orig_code:
                    orig_file = os.path.join(results_dir, rule_id, 'orig', f'{task_id}.json')
                    if os.path.exists(orig_file):
                        with open(orig_file, 'r') as f:
                            orig_data = json.load(f)
                            orig_code = orig_data.get('final', '')
                
                sample_info = {
                    'task_id': task_id,
                    'original_truth': orig_truth,
                    'adversarial_truth': adv_truth,
                    'changed': changed,
                    'spec': spec,
                    'original_code': orig_code,
                    'adversarial_code': adv_code
                }
                
                if is_success:
                    success_samples.append(sample_info)
                else:
                    failure_samples.append(sample_info)
                    
            except Exception as e:
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
                
                # 显示功能规范（完整）
                if sample.get('spec'):
                    print(f"\n  功能规范:")
                    print(f"  {sample['spec']}")
                
                # 显示完整原始代码
                print(f"\n  原始代码:")
                print(f"  {sample['original_code']}")
                
                # 显示完整对抗代码
                print(f"\n  对抗代码:")
                print(f"  {sample['adversarial_code']}")
        
        # 显示失败样本
        if failure_samples:
            print(f"\n✗ 攻击失败样本 (前2个):")
            for i, sample in enumerate(failure_samples[:2], 1):
                print(f"\n  【失败示例 {i}】")
                print(f"  Task ID: {sample['task_id']}")
                print(f"  原始判断: {sample['original_truth']}, 对抗判断: {sample['adversarial_truth']}")
                print(f"  代码是否改变: {sample['changed']}")
                
                # 显示功能规范（完整）
                if sample.get('spec'):
                    print(f"\n  功能规范:")
                    print(f"  {sample['spec']}")
                
                # 显示完整原始代码
                if sample['original_code']:
                    print(f"\n  原始代码:")
                    print(f"  {sample['original_code']}")
                
                # 显示完整对抗代码
                if sample['changed'] and sample['adversarial_code']:
                    print(f"\n  对抗代码:")
                    print(f"  {sample['adversarial_code']}")

if __name__ == '__main__':
    results = extract_rule_examples()
    print_results(results)
    
    # 保存到文件
    output_file = '/data3/pengqingsong/LLM_attack/rule_examples_report.json'
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    print(f"\n\n详细结果已保存到: {output_file}")
