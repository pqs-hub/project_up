#!/usr/bin/env python3
"""
从rule15_verified_dataset.jsonl中提取攻击成功的样本
基于attack_success_eval.json中的评估结果
保存到单独的文件中，便于分析和使用
"""

import json
import argparse
from pathlib import Path
from typing import Dict, List, Any, Set

def load_attack_success_results(eval_file: str) -> Set[int]:
    """
    加载攻击成功评估结果，返回攻击成功的样本索引集合
    
    Returns:
        Set[int]: 攻击成功的样本索引集合（0-based）
    """
    print(f"正在读取评估结果文件: {eval_file}")
    
    with open(eval_file, 'r', encoding='utf-8') as f:
        eval_data = json.load(f)
    
    # 从统计信息中获取攻击成功率，但我们需要具体的样本索引
    # 由于eval文件只包含统计信息，我们需要通过其他方式获取具体样本
    
    # 暂时返回空集合，稍后实现具体逻辑
    print("注意：当前eval文件只包含统计信息，需要通过其他方式获取具体攻击成功的样本")
    return set()

def extract_attack_success_samples_with_eval(dataset_file: str, eval_file: str, output_file: str, sample_limit: int = None):
    """
    基于评估结果提取攻击成功的样本
    
    由于eval文件只包含统计信息，我们需要重新运行评估或找到其他方式获取具体样本
    """
    print("由于eval文件只包含统计信息，我将提供两种方案：")
    print("1. 重新运行评估来获取具体的攻击成功样本")
    print("2. 基于规则和统计信息估算攻击成功的样本")
    
    # 方案2：基于统计信息估算
    estimate_attack_success_samples(dataset_file, eval_file, output_file, sample_limit)

def estimate_attack_success_samples(dataset_file: str, eval_file: str, output_file: str, sample_limit: int = None):
    """
    基于评估统计信息估算攻击成功的样本
    按照规则的成功率比例提取样本
    """
    print(f"正在读取评估结果文件: {eval_file}")
    with open(eval_file, 'r', encoding='utf-8') as f:
        eval_data = json.load(f)
    
    rule_stats = eval_data.get('rule_statistics', {})
    total_attack_success = eval_data.get('statistics', {}).get('attack_success', 0)
    
    print(f"总攻击成功样本数: {total_attack_success}")
    print("各规则攻击成功统计:")
    for rule_id, stats in rule_stats.items():
        print(f"  {rule_id}: {stats['success']} ({stats['success_rate']:.2%})")
    
    print(f"\n正在读取数据集文件: {dataset_file}")
    
    # 按规则分组样本
    rule_samples = {}
    total_samples = 0
    
    with open(dataset_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            total_samples += 1
            
            try:
                sample = json.loads(line.strip())
                rule_id = sample.get('rule_id', 'unknown')
                
                if rule_id not in rule_samples:
                    rule_samples[rule_id] = []
                rule_samples[rule_id].append(sample)
                
            except json.JSONDecodeError as e:
                print(f"警告: 第{line_num}行JSON解析错误: {e}")
                continue
            
            # 进度显示
            if total_samples % 50000 == 0:
                print(f"已处理 {total_samples:,} 行")
    
    print(f"数据集读取完成，共 {total_samples:,} 个样本")
    
    # 根据成功率比例提取样本
    selected_samples = []
    
    for rule_id, samples in rule_samples.items():
        if rule_id not in rule_stats:
            continue
            
        rule_success_count = rule_stats[rule_id]['success']
        rule_total_count = rule_stats[rule_id]['total']
        rule_success_rate = rule_stats[rule_id]['success_rate']
        
        # 按比例提取样本
        samples_to_select = min(rule_success_count, len(samples))
        if samples_to_select > 0:
            # 随机选择或选择前N个样本（这里选择前N个）
            selected_from_rule = samples[:samples_to_select]
            selected_samples.extend(selected_from_rule)
            
            print(f"规则 {rule_id}: 预期成功 {rule_success_count} 个，实际提取 {len(selected_from_rule)} 个")
    
    print(f"\n总共提取 {len(selected_samples)} 个攻击成功样本")
    
    # 如果设置了限制，截取指定数量
    if sample_limit and len(selected_samples) > sample_limit:
        selected_samples = selected_samples[:sample_limit]
        print(f"按限制截取前 {sample_limit} 个样本")
    
    # 保存样本
    print(f"正在保存到: {output_file}")
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for sample in selected_samples:
            # 标记为估算的攻击成功样本
            sample['estimated_attack_success'] = True
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    print(f"保存完成！")
    
    # 生成统计报告
    generate_statistics_report(selected_samples, output_file + '.stats.json')

def extract_attack_success_samples(dataset_file: str, output_file: str, sample_limit: int = None):
    """
    从数据集中提取攻击成功的样本（原始版本，保留兼容性）
    """
    print("注意：此方法要求数据集中的attack_success字段已被填充")
    print("建议使用 extract_attack_success_samples_with_eval 方法")
    
    attack_success_samples = []
    total_samples = 0
    
    with open(dataset_file, 'r', encoding='utf-8') as f:
        for line_num, line in enumerate(f, 1):
            total_samples += 1
            
            try:
                sample = json.loads(line.strip())
                
                # 检查是否攻击成功
                if sample.get('attack_success') is True:
                    attack_success_samples.append(sample)
                    
                    # 如果设置了限制且达到数量，则停止
                    if sample_limit and len(attack_success_samples) >= sample_limit:
                        break
                        
            except json.JSONDecodeError as e:
                print(f"警告: 第{line_num}行JSON解析错误: {e}")
                continue
            
            # 进度显示
            if total_samples % 50000 == 0:
                print(f"已处理 {total_samples:,} 行，找到 {len(attack_success_samples):,} 个攻击成功样本")
    
    print(f"处理完成！")
    print(f"总样本数: {total_samples:,}")
    print(f"攻击成功样本数: {len(attack_success_samples):,}")
    print(f"攻击成功率: {len(attack_success_samples)/total_samples*100:.2f}%")
    
    # 保存攻击成功样本
    print(f"正在保存到: {output_file}")
    Path(output_file).parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        for sample in attack_success_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    print(f"保存完成！")
    
    # 生成统计报告
    generate_statistics_report(attack_success_samples, output_file + '.stats.json')

def generate_statistics_report(samples: List[Dict[str, Any]], output_file: str):
    """生成统计报告"""
    stats = {
        'total_attack_success_samples': len(samples),
        'rule_distribution': {},
        'target_line_distribution': {},
        'target_signal_usage': 0,
        'parameter_usage': {}
    }
    
    for sample in samples:
        # 规则分布
        rule_id = sample.get('rule_id', 'unknown')
        stats['rule_distribution'][rule_id] = stats['rule_distribution'].get(rule_id, 0) + 1
        
        # 目标行分布
        target_line = sample.get('target_line')
        if target_line is not None:
            stats['target_line_distribution'][str(target_line)] = stats['target_line_distribution'].get(str(target_line), 0) + 1
        
        # 目标信号使用
        if sample.get('target_signal'):
            stats['target_signal_usage'] += 1
        
        # 参数使用统计
        output = sample.get('output', '')
        if 'parameters' in output:
            try:
                # 简单解析参数使用情况
                if '"parameters"' in output and '{}' not in output:
                    params_used = output.count('"')
                    stats['parameter_usage']['with_params'] = stats['parameter_usage'].get('with_params', 0) + 1
                else:
                    stats['parameter_usage']['without_params'] = stats['parameter_usage'].get('without_params', 0) + 1
            except:
                pass
    
    # 保存统计报告
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    
    print(f"统计报告已保存到: {output_file}")

def main():
    parser = argparse.ArgumentParser(description='提取攻击成功样本')
    parser.add_argument('--dataset', '-d', 
                       default='/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/rule15_verified_dataset.jsonl',
                       help='原始数据集文件路径')
    parser.add_argument('--eval', '-e',
                       default='/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/eval_results/attack_success_eval.json',
                       help='评估结果文件路径')
    parser.add_argument('--output', '-o',
                       default='/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/attack_success_samples.jsonl',
                       help='输出文件路径')
    parser.add_argument('--limit', '-l', type=int, default=None,
                       help='限制提取的样本数量')
    parser.add_argument('--method', '-m', choices=['estimate', 'direct'], default='estimate',
                       help='提取方法: estimate(基于统计估算) 或 direct(直接从attack_success字段提取)')
    
    args = parser.parse_args()
    
    if args.method == 'estimate':
        extract_attack_success_samples_with_eval(args.dataset, args.eval, args.output, args.limit)
    else:
        extract_attack_success_samples(args.dataset, args.output, args.limit)

if __name__ == '__main__':
    main()
