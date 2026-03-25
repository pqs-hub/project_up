#!/usr/bin/env python3
"""
去重SFT数据集 - 每个任务只保留一个最佳规则

策略：
1. 对于每个task，选择ASR最高的规则
2. 如果ASR相同，选择置信度最高的
3. 确保每个任务只有一个训练样本
"""

import json
from pathlib import Path
from collections import defaultdict

# 规则ASR排序（从高到低）
RULE_ASR = {
    'T45': 99.1,  # 假性组合逻辑环
    'T19': 90.8,  # 虚假模式注入
    'T30': 60.5,  # 常量恒等变换
    'T12': 56.5,  # 中间信号注入
    'T20': 51.6,  # 误导性注释
    'T34': 42.1,  # 通用重命名
    'T09': 37.1,  # 德摩根AND
    'T31': 36.8,  # 简单中间信号
    'T41': 34.2,  # Case分支重排
    'T48': 28.4,  # 逆向拓扑重排
    'T47': 28.2,  # 数据流破碎
    'T10': 26.2,  # 德摩根OR
    'T07': 22.4,  # 赋值重排
    'T03': 16.7,  # 冗余逻辑注入
    'T32': 14.4,  # 位宽算术变换
}

TRANSFORM_TO_RULE_ID = {
    'redundant_logic': 'T03',
    'assign_reorder': 'T07',
    'demorgan_and': 'T09',
    'demorgan_or': 'T10',
    'intermediate_signal': 'T12',
    'false_pattern_injection': 'T19',
    'misleading_comment': 'T20',
    'constant_identity': 'T30',
    'simple_intermediate': 'T31',
    'bitwidth_arithmetic': 'T32',
    'universal_rename': 'T34',
    'case_branch_reorder': 'T41',
    'pseudo_comb_loop': 'T45',
    'dataflow_shattering': 'T47',
    'anti_topological_shuffle': 'T48',
}

def extract_task_id_from_input(input_text: str) -> str:
    """从input中提取task标识（用前500字符）"""
    # 提取功能规范部分作为task的唯一标识
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

def deduplicate_by_best_rule(input_path: Path, output_path: Path):
    """去重：每个任务只保留ASR最高的规则"""
    
    print("="*80)
    print("去重SFT数据集 - 每个任务只保留最佳规则")
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
    
    # 为每个任务选择最佳规则
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
            # 多个规则，选择ASR最高的
            best_sample = None
            best_asr = -1
            
            for sample in samples:
                attack_name = extract_attack_name(sample['output'])
                rule_id = TRANSFORM_TO_RULE_ID.get(attack_name, attack_name)
                asr = RULE_ASR.get(rule_id, 0)
                
                if asr > best_asr:
                    best_asr = asr
                    best_sample = sample
            
            if best_sample:
                deduplicated.append(best_sample)
                attack_name = extract_attack_name(best_sample['output'])
                rule_id = TRANSFORM_TO_RULE_ID.get(attack_name, attack_name)
                rule_selection_count[rule_id] += 1
    
    # 保存去重后的数据集
    print(f"\n保存到: {output_path}")
    with open(output_path, 'w', encoding='utf-8') as f:
        for sample in deduplicated:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    print(f"✓ 保存了 {len(deduplicated)} 个样本")
    
    # 统计
    print("\n" + "="*80)
    print("去重统计")
    print("="*80)
    print(f"\n原始样本数: {sum(len(v) for v in task_samples.values()):,}")
    print(f"去重后样本数: {len(deduplicated):,}")
    print(f"减少: {sum(len(v) for v in task_samples.values()) - len(deduplicated):,} ({(1 - len(deduplicated) / sum(len(v) for v in task_samples.values())) * 100:.1f}%)")
    
    print(f"\n去重后各规则分布:")
    print("-" * 60)
    for rule_id in sorted(rule_selection_count.keys(), key=lambda x: RULE_ASR.get(x, 0), reverse=True):
        count = rule_selection_count[rule_id]
        asr = RULE_ASR.get(rule_id, 0)
        pct = count / len(deduplicated) * 100
        print(f"  {rule_id} (ASR={asr:5.1f}%): {count:5,} 样本 ({pct:5.1f}%)")
    
    print("\n✅ 去重完成！每个任务现在只有一个规则")
    
    # 计算文件大小
    import os
    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\n文件大小: {file_size:.2f} MB")

if __name__ == '__main__':
    input_path = Path('data/sft_attack_success_registry.jsonl')
    output_path = Path('data/sft_attack_success_dedup.jsonl')
    
    deduplicate_by_best_rule(input_path, output_path)
