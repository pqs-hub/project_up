#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析攻击规则的冗余性

检查低使用率规则的样本是否冗余（即同一任务已被其他规则成功攻击）
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

def load_dataset(file_path):
    """加载JSONL数据集"""
    samples = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples

def analyze_redundancy(samples):
    """分析规则冗余性"""
    # 按任务分组：task_id -> [rule1, rule2, ...]
    task_rules = defaultdict(set)
    
    # 规则样本映射：rule -> [(task_id, sample_idx), ...]
    rule_samples = defaultdict(list)
    
    for idx, sample in enumerate(samples):
        task_id = sample.get('task_id', '')
        rule = sample.get('attack_rule', 'unknown')
        
        task_rules[task_id].add(rule)
        rule_samples[rule].append((task_id, idx))
    
    # 统计每个规则的样本数
    rule_counts = {rule: len(samples_list) for rule, samples_list in rule_samples.items()}
    
    # 按样本数排序规则
    sorted_rules = sorted(rule_counts.items(), key=lambda x: x[1], reverse=True)
    
    print("=" * 70)
    print("规则冗余性分析")
    print("=" * 70)
    print(f"\n总样本数: {len(samples)}")
    print(f"总任务数: {len(task_rules)}\n")
    
    # 分析每个规则的冗余性
    print("规则详细分析:")
    print("-" * 70)
    print(f"{'规则':<6} {'样本数':<8} {'唯一任务':<10} {'冗余任务':<10} {'冗余率':<10}")
    print("-" * 70)
    
    redundancy_info = {}
    
    for rule, count in sorted_rules:
        # 该规则攻击成功的任务
        rule_tasks = [task_id for task_id, _ in rule_samples[rule]]
        unique_tasks = set(rule_tasks)
        
        # 检查这些任务是否也被其他规则攻击成功
        redundant_tasks = set()
        unique_contribution_tasks = set()
        
        for task_id in unique_tasks:
            # 获取该任务被哪些规则攻击成功
            rules_for_task = task_rules[task_id]
            
            if len(rules_for_task) > 1:
                # 该任务被多个规则攻击成功，当前规则是冗余的
                redundant_tasks.add(task_id)
            else:
                # 该任务只被当前规则攻击成功
                unique_contribution_tasks.add(task_id)
        
        redundancy_rate = len(redundant_tasks) / len(unique_tasks) * 100 if unique_tasks else 0
        
        redundancy_info[rule] = {
            'total_samples': count,
            'unique_tasks': len(unique_tasks),
            'redundant_tasks': len(redundant_tasks),
            'redundant_tasks_set': redundant_tasks,  # 保存集合
            'unique_contribution': len(unique_contribution_tasks),
            'redundancy_rate': redundancy_rate
        }
        
        print(f"{rule:<6} {count:<8} {len(unique_tasks):<10} {len(redundant_tasks):<10} {redundancy_rate:>6.1f}%")
    
    print("-" * 70)
    
    # 分析低使用率规则
    print("\n" + "=" * 70)
    print("低使用率规则（<100样本）分析")
    print("=" * 70)
    
    low_usage_rules = [rule for rule, count in sorted_rules if count < 100]
    
    total_low_samples = sum(rule_counts[rule] for rule in low_usage_rules)
    total_low_unique_contribution = sum(redundancy_info[rule]['unique_contribution'] for rule in low_usage_rules)
    
    print(f"\n低使用率规则: {low_usage_rules}")
    print(f"总样本数: {total_low_samples}")
    print(f"唯一贡献任务数: {total_low_unique_contribution}")
    print(f"可删除样本数: {total_low_samples - total_low_unique_contribution}")
    
    for rule in low_usage_rules:
        info = redundancy_info[rule]
        print(f"\n{rule}:")
        print(f"  - 总样本: {info['total_samples']}")
        print(f"  - 唯一贡献任务: {info['unique_contribution']} (不可删除)")
        print(f"  - 冗余任务: {info['redundant_tasks']} (可删除)")
        print(f"  - 如果删除该规则，会失去 {info['unique_contribution']} 个任务的覆盖")
    
    # 计算如果删除所有冗余样本的影响
    print("\n" + "=" * 70)
    print("删除冗余样本的影响")
    print("=" * 70)
    
    total_redundant_samples = 0
    tasks_lost = set()
    
    for rule in low_usage_rules:
        # 计算该规则有多少冗余样本
        for task_id, sample_idx in rule_samples[rule]:
            if task_id in redundancy_info[rule]['redundant_tasks_set']:
                total_redundant_samples += 1
        
        # 如果完全删除该规则
        tasks_lost.update([task_id for task_id, _ in rule_samples[rule] 
                          if len(task_rules[task_id]) == 1])
    
    print(f"\n删除低使用率规则的所有冗余样本:")
    print(f"  - 可删除样本数: {total_redundant_samples}")
    print(f"  - 保留样本数: {len(samples) - total_redundant_samples}")
    print(f"  - 不影响任务覆盖（仍覆盖 {len(task_rules)} 个任务）")
    
    print(f"\n如果完全删除低使用率规则:")
    print(f"  - 会删除样本数: {total_low_samples}")
    print(f"  - 会失去任务数: {len(tasks_lost)}")
    print(f"  - 保留任务数: {len(task_rules) - len(tasks_lost)}")
    print(f"  - 任务覆盖率: {(len(task_rules) - len(tasks_lost)) / len(task_rules) * 100:.2f}%")
    
    print("\n" + "=" * 70)
    
    return redundancy_info

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python analyze_rule_redundancy.py <数据集路径>")
        sys.exit(1)
    
    dataset_path = sys.argv[1]
    print(f"加载数据集: {dataset_path}")
    samples = load_dataset(dataset_path)
    print(f"加载了 {len(samples)} 个样本\n")
    
    analyze_redundancy(samples)
