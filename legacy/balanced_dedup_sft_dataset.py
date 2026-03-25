#!/usr/bin/env python3
"""
平衡去重SFT数据集（方案3：分层采样）

策略：
1. 每个任务最多保留3个规则
2. 优先保留不同ASR层级的规则（高/中/低）
3. 同层级选择ASR最高的
4. 确保规则多样性
"""

import json
from pathlib import Path
from collections import defaultdict
import random

# 规则ASR分层
HIGH_ASR_RULES = ['T45', 'T19']  # ASR >= 80%
MID_ASR_RULES = ['T30', 'T12', 'T20', 'T34']  # 40% <= ASR < 80%
LOW_ASR_RULES = ['T09', 'T31', 'T41', 'T48', 'T47', 'T10', 'T07', 'T03', 'T32']  # ASR < 40%

RULE_ASR = {
    'T45': 99.1, 'T19': 90.8, 'T30': 60.5, 'T12': 56.5, 'T20': 51.6,
    'T34': 42.1, 'T09': 37.1, 'T31': 36.8, 'T41': 34.2, 'T48': 28.4,
    'T47': 28.2, 'T10': 26.2, 'T07': 22.4, 'T03': 16.7, 'T32': 14.4,
}

TRANSFORM_TO_RULE_ID = {
    'redundant_logic': 'T03', 'assign_reorder': 'T07', 'demorgan_and': 'T09',
    'demorgan_or': 'T10', 'intermediate_signal': 'T12', 'false_pattern_injection': 'T19',
    'misleading_comment': 'T20', 'constant_identity': 'T30', 'simple_intermediate': 'T31',
    'bitwidth_arithmetic': 'T32', 'universal_rename': 'T34', 'case_branch_reorder': 'T41',
    'pseudo_comb_loop': 'T45', 'dataflow_shattering': 'T47', 'anti_topological_shuffle': 'T48',
}

def extract_task_id_from_input(input_text: str) -> str:
    """从input中提取task标识"""
    if '### 功能规范' in input_text and '### 原始代码' in input_text:
        start = input_text.find('### 功能规范') + 12
        end = input_text.find('### 原始代码')
        return input_text[start:end].strip()
    return input_text[:500]

def extract_attack_name(output_text: str) -> str:
    """从output中提取attack_name"""
    try:
        json_start = output_text.find('```json\n') + 8
        json_end = output_text.find('\n```', json_start)
        attack_config = json.loads(output_text[json_start:json_end])
        return attack_config.get('attack_name', 'unknown')
    except:
        return 'unknown'

def balanced_sample_rules(samples, max_rules_per_task=3):
    """
    分层采样：每个任务最多保留max_rules_per_task个规则
    
    优先级：
    1. 每个ASR层级至少1个（如果有）
    2. 同层级选择ASR最高的
    3. 如果不够，从高ASR层级补充
    """
    
    # 按规则分组
    rule_samples = defaultdict(list)
    for sample in samples:
        attack_name = extract_attack_name(sample['output'])
        rule_id = TRANSFORM_TO_RULE_ID.get(attack_name, attack_name)
        rule_samples[rule_id].append(sample)
    
    selected = []
    selected_rules = set()
    
    # 第1步：从每个层级选1个
    for tier, tier_rules in [
        ('high', HIGH_ASR_RULES),
        ('mid', MID_ASR_RULES),
        ('low', LOW_ASR_RULES)
    ]:
        # 找到该层级中存在的规则
        available = [r for r in tier_rules if r in rule_samples and r not in selected_rules]
        
        if available and len(selected) < max_rules_per_task:
            # 选择该层级中ASR最高的
            best_rule = max(available, key=lambda r: RULE_ASR.get(r, 0))
            selected.append(rule_samples[best_rule][0])
            selected_rules.add(best_rule)
    
    # 第2步：如果还不够，按ASR从高到低补充
    if len(selected) < max_rules_per_task:
        remaining = [r for r in rule_samples.keys() if r not in selected_rules]
        remaining.sort(key=lambda r: RULE_ASR.get(r, 0), reverse=True)
        
        for rule_id in remaining:
            if len(selected) >= max_rules_per_task:
                break
            selected.append(rule_samples[rule_id][0])
            selected_rules.add(rule_id)
    
    return selected

def balanced_deduplicate(input_path: Path, output_path: Path, max_rules_per_task=3):
    """平衡去重：每个任务最多保留N个规则，按ASR分层采样"""
    
    print("="*80)
    print(f"平衡去重SFT数据集（每任务最多{max_rules_per_task}个规则）")
    print("="*80)
    
    # 按任务分组
    task_samples = defaultdict(list)
    
    print(f"\n加载数据: {input_path}")
    with open(input_path, 'r') as f:
        for line in f:
            sample = json.loads(line)
            task_id = extract_task_id_from_input(sample['input'])
            task_samples[task_id].append(sample)
    
    print(f"✓ 加载了 {sum(len(v) for v in task_samples.values())} 个样本")
    print(f"✓ 涵盖 {len(task_samples)} 个独特任务")
    
    # 统计冲突
    multi_rule_tasks = {k: v for k, v in task_samples.items() if len(v) > 1}
    print(f"\n⚠️  有冲突的任务: {len(multi_rule_tasks)} ({len(multi_rule_tasks)/len(task_samples)*100:.1f}%)")
    
    # 为每个任务进行分层采样
    deduplicated = []
    rule_selection_count = defaultdict(int)
    
    for task_id, samples in task_samples.items():
        if len(samples) == 1:
            # 只有一个规则，直接保留
            deduplicated.append(samples[0])
            attack_name = extract_attack_name(samples[0]['output'])
            rule_id = TRANSFORM_TO_RULE_ID.get(attack_name, attack_name)
            rule_selection_count[rule_id] += 1
        else:
            # 多个规则，分层采样
            selected = balanced_sample_rules(samples, max_rules_per_task)
            deduplicated.extend(selected)
            
            for sample in selected:
                attack_name = extract_attack_name(sample['output'])
                rule_id = TRANSFORM_TO_RULE_ID.get(attack_name, attack_name)
                rule_selection_count[rule_id] += 1
    
    # 保存
    print(f"\n保存到: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in deduplicated:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    print(f"✓ 保存了 {len(deduplicated)} 个样本")
    
    # 统计
    print("\n" + "="*80)
    print("平衡去重统计")
    print("="*80)
    print(f"\n原始样本数: {sum(len(v) for v in task_samples.values()):,}")
    print(f"去重后样本数: {len(deduplicated):,}")
    print(f"减少: {sum(len(v) for v in task_samples.values()) - len(deduplicated):,} ({(1 - len(deduplicated) / sum(len(v) for v in task_samples.values())) * 100:.1f}%)")
    
    print(f"\n去重后各规则分布:")
    print("-" * 80)
    
    # 按层级显示
    print("\n📈 高ASR规则 (>= 80%):")
    for rule_id in sorted(HIGH_ASR_RULES, key=lambda x: RULE_ASR.get(x, 0), reverse=True):
        count = rule_selection_count.get(rule_id, 0)
        if count > 0:
            asr = RULE_ASR.get(rule_id, 0)
            pct = count / len(deduplicated) * 100
            print(f"  {rule_id} (ASR={asr:5.1f}%): {count:5,} 样本 ({pct:5.1f}%)")
    
    print("\n📊 中ASR规则 (40% - 80%):")
    for rule_id in sorted(MID_ASR_RULES, key=lambda x: RULE_ASR.get(x, 0), reverse=True):
        count = rule_selection_count.get(rule_id, 0)
        if count > 0:
            asr = RULE_ASR.get(rule_id, 0)
            pct = count / len(deduplicated) * 100
            print(f"  {rule_id} (ASR={asr:5.1f}%): {count:5,} 样本 ({pct:5.1f}%)")
    
    print("\n📉 低ASR规则 (< 40%):")
    for rule_id in sorted(LOW_ASR_RULES, key=lambda x: RULE_ASR.get(x, 0), reverse=True):
        count = rule_selection_count.get(rule_id, 0)
        if count > 0:
            asr = RULE_ASR.get(rule_id, 0)
            pct = count / len(deduplicated) * 100
            print(f"  {rule_id} (ASR={asr:5.1f}%): {count:5,} 样本 ({pct:5.1f}%)")
    
    # 多样性分析
    print("\n" + "="*80)
    print("规则多样性分析")
    print("="*80)
    
    total_rules = len([r for r in rule_selection_count if rule_selection_count[r] > 0])
    print(f"\n包含的规则数: {total_rules} / 15")
    
    high_count = sum(rule_selection_count.get(r, 0) for r in HIGH_ASR_RULES)
    mid_count = sum(rule_selection_count.get(r, 0) for r in MID_ASR_RULES)
    low_count = sum(rule_selection_count.get(r, 0) for r in LOW_ASR_RULES)
    
    print(f"\n层级分布:")
    print(f"  高ASR规则: {high_count:,} ({high_count/len(deduplicated)*100:.1f}%)")
    print(f"  中ASR规则: {mid_count:,} ({mid_count/len(deduplicated)*100:.1f}%)")
    print(f"  低ASR规则: {low_count:,} ({low_count/len(deduplicated)*100:.1f}%)")
    
    print("\n✅ 平衡去重完成！规则分布更均衡")
    
    # 计算文件大小
    import os
    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\n文件大小: {file_size:.2f} MB")

if __name__ == '__main__':
    input_path = Path('data/sft_attack_success_registry.jsonl')
    output_path = Path('data/sft_attack_success_balanced.jsonl')
    
    # 每个任务最多保留3个规则
    balanced_deduplicate(input_path, output_path, max_rules_per_task=3)
