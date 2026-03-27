#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析数据集中一个输入对应多个输出的情况
检查是否需要数据清洗
"""

import json
import sys
from pathlib import Path
from collections import defaultdict, Counter


def analyze_input_output_distribution(dataset_path):
    """分析输入输出分布"""
    
    # 加载数据
    samples = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    
    print(f"加载了 {len(samples)} 个样本\n")
    
    # 分析1: 同一任务的多个攻击样本
    task_attacks = defaultdict(list)
    for idx, sample in enumerate(samples):
        task_id = sample.get('task_id', '')
        rule = sample.get('attack_rule', '')
        params = json.dumps(sample.get('attack_params', {}), sort_keys=True)
        
        task_attacks[task_id].append({
            'index': idx,
            'rule': rule,
            'params': params,
            'original_code': sample.get('original_code', ''),
            'transformed_code': sample.get('transformed_code', '')
        })
    
    # 统计每个任务的攻击数量
    attack_counts = Counter()
    for task_id, attacks in task_attacks.items():
        attack_counts[len(attacks)] += 1
    
    print("=" * 70)
    print("分析1: 同一任务的攻击样本数量分布")
    print("=" * 70)
    print(f"\n总任务数: {len(task_attacks)}")
    print(f"总样本数: {len(samples)}")
    print(f"平均每任务样本数: {len(samples) / len(task_attacks):.2f}\n")
    
    print("任务攻击数量分布:")
    print("-" * 70)
    for count in sorted(attack_counts.keys()):
        tasks = attack_counts[count]
        pct = tasks / len(task_attacks) * 100
        print(f"  {count:3d} 个攻击样本: {tasks:5d} 个任务 ({pct:5.2f}%)")
    print("-" * 70)
    
    # 找出攻击样本最多的任务
    max_attacks_task = max(task_attacks.items(), key=lambda x: len(x[1]))
    print(f"\n攻击样本最多的任务: {max_attacks_task[0]}")
    print(f"  样本数: {len(max_attacks_task[1])}")
    print(f"  使用的规则: {set(a['rule'] for a in max_attacks_task[1])}")
    
    # 分析2: 完全相同的输入对应不同的输出
    input_outputs = defaultdict(list)
    for idx, sample in enumerate(samples):
        input_key = sample.get('original_code', '')
        output = sample.get('transformed_code', '')
        rule = sample.get('attack_rule', '')
        
        input_outputs[input_key].append({
            'index': idx,
            'output': output,
            'rule': rule,
            'task_id': sample.get('task_id', '')
        })
    
    # 统计同一输入的不同输出数量
    multiple_outputs = {k: v for k, v in input_outputs.items() if len(v) > 1}
    
    print("\n" + "=" * 70)
    print("分析2: 同一原始代码的不同输出分布")
    print("=" * 70)
    print(f"\n唯一输入数: {len(input_outputs)}")
    print(f"有多个输出的输入数: {len(multiple_outputs)}")
    print(f"多输出比例: {len(multiple_outputs) / len(input_outputs) * 100:.2f}%\n")
    
    output_counts = Counter(len(v) for v in input_outputs.values())
    print("每个输入的输出数量分布:")
    print("-" * 70)
    for count in sorted(output_counts.keys()):
        inputs = output_counts[count]
        pct = inputs / len(input_outputs) * 100
        print(f"  {count:3d} 个输出: {inputs:5d} 个输入 ({pct:5.2f}%)")
    print("-" * 70)
    
    # 分析3: 同一任务+同一规则的重复样本
    task_rule_samples = defaultdict(list)
    for idx, sample in enumerate(samples):
        task_id = sample.get('task_id', '')
        rule = sample.get('attack_rule', '')
        key = f"{task_id}_{rule}"
        
        task_rule_samples[key].append({
            'index': idx,
            'params': sample.get('attack_params', {}),
            'transformed_code': sample.get('transformed_code', '')
        })
    
    duplicates = {k: v for k, v in task_rule_samples.items() if len(v) > 1}
    
    print("\n" + "=" * 70)
    print("分析3: 同一任务+同一规则的重复样本")
    print("=" * 70)
    print(f"\n任务-规则组合数: {len(task_rule_samples)}")
    print(f"有重复的组合数: {len(duplicates)}")
    
    if duplicates:
        print(f"重复比例: {len(duplicates) / len(task_rule_samples) * 100:.2f}%\n")
        
        # 显示几个示例
        print("重复样本示例（前5个）:")
        print("-" * 70)
        for i, (key, samples_list) in enumerate(list(duplicates.items())[:5]):
            task_id, rule = key.rsplit('_', 1)
            print(f"\n{i+1}. 任务 {task_id} + 规则 {rule}: {len(samples_list)} 个样本")
            
            # 检查参数和输出是否相同
            params_set = set(json.dumps(s['params'], sort_keys=True) for s in samples_list)
            outputs_set = set(s['transformed_code'] for s in samples_list)
            
            print(f"   不同参数数: {len(params_set)}")
            print(f"   不同输出数: {len(outputs_set)}")
            
            if len(params_set) > 1:
                print(f"   → 同一规则使用了不同参数")
            if len(outputs_set) > 1:
                print(f"   → 产生了不同的变换结果")
    else:
        print("✅ 没有发现同一任务+同一规则的重复样本")
    
    # 给出建议
    print("\n" + "=" * 70)
    print("数据清洗建议")
    print("=" * 70)
    
    multiple_task_ratio = (len(task_attacks) - attack_counts[1]) / len(task_attacks) * 100
    
    print(f"\n1. 多样本任务占比: {multiple_task_ratio:.2f}%")
    if multiple_task_ratio > 50:
        print("   ⚠️  超过一半的任务有多个攻击样本")
        print("   建议: 考虑数据清洗策略")
    else:
        print("   ✅ 大部分任务只有单个攻击样本，问题不严重")
    
    print(f"\n2. 多输出输入占比: {len(multiple_outputs) / len(input_outputs) * 100:.2f}%")
    if len(multiple_outputs) / len(input_outputs) > 0.5:
        print("   ⚠️  同一输入对应多个输出的情况较多")
        print("   建议: 需要清洗")
    else:
        print("   ✅ 大部分输入只有一个输出")
    
    print("\n清洗策略建议:")
    print("-" * 70)
    print("策略A: 每个任务只保留1个最优样本")
    print("  - 优先选择高置信度的样本")
    print("  - 优先选择常用规则（T20, T45等）")
    print(f"  - 预计保留: {len(task_attacks)} 个样本")
    print(f"  - 删除: {len(samples) - len(task_attacks)} 个样本")
    
    print("\n策略B: 每个任务每个规则只保留1个样本")
    print("  - 允许同一任务使用不同规则")
    print("  - 同一规则只保留参数最优的")
    print(f"  - 预计保留: {len(task_rule_samples)} 个样本")
    print(f"  - 删除: {len(samples) - len(task_rule_samples)} 个样本")
    
    print("\n策略C: 保留所有样本（当前状态）")
    print("  - 优点: 数据多样性最高")
    print("  - 缺点: 可能导致模型对同一任务输出不稳定")
    print(f"  - 当前样本数: {len(samples)}")
    
    print("\n推荐策略: 策略B（平衡多样性和稳定性）")
    print("=" * 70)
    
    return {
        'total_samples': len(samples),
        'total_tasks': len(task_attacks),
        'multiple_outputs_ratio': len(multiple_outputs) / len(input_outputs),
        'duplicates': len(duplicates)
    }


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("用法: python analyze_input_output_distribution.py <数据集路径>")
        sys.exit(1)
    
    dataset_path = sys.argv[1]
    analyze_input_output_distribution(dataset_path)
