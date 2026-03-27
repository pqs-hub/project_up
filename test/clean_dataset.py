#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据集清洗工具

策略B: 每个任务每个规则只保留1个最优样本
- 允许同一任务使用不同规则（保持多样性）
- 同一规则只保留置信度最高的样本
"""

import json
import sys
from pathlib import Path
from collections import defaultdict


def clean_dataset(input_path, output_path, strategy='B'):
    """清洗数据集"""
    
    # 加载数据
    samples = []
    with open(input_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    
    print(f"加载了 {len(samples)} 个样本")
    
    if strategy == 'A':
        # 策略A: 每个任务只保留1个最优样本
        cleaned_samples = clean_strategy_a(samples)
    elif strategy == 'B':
        # 策略B: 每个任务每个规则只保留1个样本（推荐）
        cleaned_samples = clean_strategy_b(samples)
    else:
        print(f"未知策略: {strategy}")
        return
    
    # 保存清洗后的数据
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in cleaned_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    print(f"\n清洗完成！")
    print(f"原始样本数: {len(samples)}")
    print(f"清洗后样本数: {len(cleaned_samples)}")
    print(f"删除样本数: {len(samples) - len(cleaned_samples)}")
    print(f"保留比例: {len(cleaned_samples) / len(samples) * 100:.2f}%")
    print(f"\n已保存到: {output_path}")


def clean_strategy_a(samples):
    """策略A: 每个任务只保留1个最优样本"""
    
    # 规则优先级（基于成功率）
    rule_priority = {
        'T20': 1, 'T45': 2, 'T03': 3, 'T32': 4, 'T19': 5,
        'T07': 6, 'T48': 7, 'T31': 8, 'T34': 9, 'T41': 10,
        'T09': 11, 'T30': 12, 'T10': 13, 'T12': 14, 'T47': 15
    }
    
    task_best = {}
    
    for sample in samples:
        task_id = sample.get('task_id', '')
        if not task_id:
            continue
        
        # 计算样本得分
        confidence = sample.get('judge_confidence', 0)
        rule = sample.get('attack_rule', '')
        rule_score = 20 - rule_priority.get(rule, 20)  # 优先规则得分高
        
        score = confidence * 100 + rule_score  # 置信度为主，规则为辅
        
        if task_id not in task_best or score > task_best[task_id]['score']:
            task_best[task_id] = {
                'sample': sample,
                'score': score
            }
    
    cleaned_samples = [item['sample'] for item in task_best.values()]
    
    print(f"\n策略A: 每个任务只保留1个最优样本")
    print(f"保留的唯一任务数: {len(cleaned_samples)}")
    
    return cleaned_samples


def clean_strategy_b(samples):
    """策略B: 每个任务每个规则只保留1个样本（推荐）"""
    
    # 按 (task_id, rule) 分组
    task_rule_samples = defaultdict(list)
    
    for idx, sample in enumerate(samples):
        task_id = sample.get('task_id', '')
        rule = sample.get('attack_rule', '')
        
        if not task_id or not rule:
            continue
        
        key = (task_id, rule)
        task_rule_samples[key].append({
            'index': idx,
            'sample': sample,
            'confidence': sample.get('judge_confidence', 0)
        })
    
    # 每组只保留置信度最高的
    cleaned_samples = []
    
    for key, samples_list in task_rule_samples.items():
        # 按置信度排序，取最高的
        best = max(samples_list, key=lambda x: x['confidence'])
        cleaned_samples.append(best['sample'])
    
    # 统计
    task_ids = set(s.get('task_id', '') for s in cleaned_samples)
    rules = set(s.get('attack_rule', '') for s in cleaned_samples)
    
    print(f"\n策略B: 每个任务每个规则只保留1个样本")
    print(f"保留的任务-规则组合数: {len(cleaned_samples)}")
    print(f"涵盖的唯一任务数: {len(task_ids)}")
    print(f"涵盖的规则数: {len(rules)}")
    
    # 统计规则分布
    from collections import Counter
    rule_counts = Counter(s.get('attack_rule', '') for s in cleaned_samples)
    print(f"\n清洗后的规则分布:")
    for rule, count in sorted(rule_counts.items(), key=lambda x: -x[1])[:10]:
        print(f"  {rule}: {count}")
    
    return cleaned_samples


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python clean_dataset.py <输入文件> <输出文件> [策略A/B]")
        print("\n策略说明:")
        print("  A - 每个任务只保留1个最优样本（最激进）")
        print("  B - 每个任务每个规则只保留1个样本（推荐，默认）")
        print("\n示例:")
        print("  python clean_dataset.py input.jsonl output_clean.jsonl B")
        sys.exit(1)
    
    input_path = sys.argv[1]
    output_path = sys.argv[2]
    strategy = sys.argv[3] if len(sys.argv) > 3 else 'B'
    
    clean_dataset(input_path, output_path, strategy)
