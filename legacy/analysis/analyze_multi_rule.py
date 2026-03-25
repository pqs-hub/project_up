#!/usr/bin/env python3
"""分析数据集中同一样本被多个规则攻击的情况"""

import json
from collections import defaultdict
from pathlib import Path

def analyze_multi_rule_problem():
    """分析同一个样本是否有多个不同的规则"""
    
    # 从评估结果直接统计
    eval_base = Path('rule_eval/metrics_conf_v2_on_fullall_adv')
    
    # 统计每个task_id被哪些规则成功攻击
    task_to_rules = defaultdict(set)
    
    REGISTRY_RULES = {
        'T03', 'T07', 'T09', 'T10', 'T12', 
        'T19', 'T20', 'T30', 'T31', 'T32', 
        'T34', 'T41', 'T45', 'T47', 'T48'
    }
    
    for rule_id in sorted(REGISTRY_RULES):
        eval_dir = eval_base / rule_id / 'adv_eval'
        
        if not eval_dir.exists():
            continue
        
        for json_file in eval_dir.glob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    eval_data = json.load(f)
                
                task_id = eval_data.get('task_id')
                orig_truth = eval_data.get('original_truth')
                adv_truth = eval_data.get('adversarial_truth')
                adv_passed = eval_data.get('adversarial_passed')
                
                # 攻击成功
                if orig_truth == True and adv_truth == True and adv_passed == False:
                    task_to_rules[task_id].add(rule_id)
            
            except Exception as e:
                continue
    
    # 统计分析
    print("="*80)
    print("数据集分析：同一样本的多规则问题")
    print("="*80)
    
    total_tasks = len(task_to_rules)
    total_samples = sum(len(rules) for rules in task_to_rules.values())
    
    print(f"\n独特任务数: {total_tasks:,}")
    print(f"总攻击成功样本: {total_samples:,}")
    print(f"平均每个任务: {total_samples / total_tasks:.2f} 个成功规则")
    
    # 按规则数量分组
    rule_count_dist = defaultdict(int)
    for task_id, rules in task_to_rules.items():
        rule_count_dist[len(rules)] += 1
    
    print("\n每个任务被多少个规则成功攻击:")
    print("-" * 60)
    for count in sorted(rule_count_dist.keys()):
        num_tasks = rule_count_dist[count]
        pct = num_tasks / total_tasks * 100
        print(f"  {count} 个规则: {num_tasks:,} 个任务 ({pct:.1f}%)")
    
    # 找出被最多规则攻击的任务
    multi_rule_tasks = [(task_id, rules) for task_id, rules in task_to_rules.items() if len(rules) > 1]
    multi_rule_tasks.sort(key=lambda x: len(x[1]), reverse=True)
    
    print(f"\n⚠️  被多个规则攻击的任务: {len(multi_rule_tasks):,} 个 ({len(multi_rule_tasks)/total_tasks*100:.1f}%)")
    
    if multi_rule_tasks:
        print("\nTop 10 被攻击最多的任务:")
        print("-" * 60)
        for i, (task_id, rules) in enumerate(multi_rule_tasks[:10], 1):
            print(f"  {i}. {task_id}: {len(rules)} 个规则 - {sorted(rules)}")
    
    # 分析问题
    print("\n" + "="*80)
    print("问题分析")
    print("="*80)
    
    single_rule_tasks = sum(1 for rules in task_to_rules.values() if len(rules) == 1)
    
    print(f"\n✅ 只被1个规则攻击: {single_rule_tasks:,} 个任务 ({single_rule_tasks/total_tasks*100:.1f}%)")
    print(f"⚠️  被多个规则攻击: {len(multi_rule_tasks):,} 个任务 ({len(multi_rule_tasks)/total_tasks*100:.1f}%)")
    
    # 计算冲突样本数
    conflict_samples = sum(len(rules) for task_id, rules in multi_rule_tasks)
    print(f"\n冲突样本数（同一任务的多个规则）: {conflict_samples:,} / {total_samples:,} ({conflict_samples/total_samples*100:.1f}%)")
    
    return task_to_rules, multi_rule_tasks

def show_conflict_examples(task_to_rules):
    """显示冲突样本的具体例子"""
    
    print("\n" + "="*80)
    print("冲突样本示例")
    print("="*80)
    
    # 加载原始数据集
    dataset_path = Path('data/qualified_dataset.json')
    with open(dataset_path, 'r') as f:
        dataset = json.load(f)
    dataset_dict = {task['task_id']: task for task in dataset}
    
    # 找几个被多个规则攻击的任务
    multi_rule_tasks = [(task_id, rules) for task_id, rules in task_to_rules.items() if len(rules) > 2]
    multi_rule_tasks.sort(key=lambda x: len(x[1]), reverse=True)
    
    for i, (task_id, rules) in enumerate(multi_rule_tasks[:3], 1):
        task = dataset_dict.get(task_id)
        if not task:
            continue
        
        print(f"\n示例 {i}: {task_id}")
        print(f"被 {len(rules)} 个规则成功攻击: {sorted(rules)}")
        print(f"\n代码（前300字符）:")
        code = task.get('canonical_solution', '')
        print(code[:300] + '...' if len(code) > 300 else code)

if __name__ == '__main__':
    task_to_rules, multi_rule_tasks = analyze_multi_rule_problem()
    show_conflict_examples(task_to_rules)
