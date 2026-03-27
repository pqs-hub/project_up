#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析和转换攻击数据集

功能：
1. 统计数据集基本信息
2. 分析规则分布
3. 转换为SFT训练格式
4. 数据质量检查
"""

import argparse
import json
from pathlib import Path
from collections import Counter, defaultdict
from typing import List, Dict

# 攻击规则代码到英文名称的映射
RULE_NAME_MAPPING = {
    'T03': 'Redundant Logic',
    'T07': 'Assign Reorder',
    'T09': 'DeMorgan AND',
    'T10': 'DeMorgan OR',
    'T12': 'Intermediate Signal',
    'T19': 'False Pattern',
    'T20': 'Flexible Misleading Comment',
    'T30': 'Constant Identity',
    'T31': 'Simple Intermediate',
    'T32': 'Bitwidth Arithmetic',
    'T34': 'Internal Signal Rename',
    'T41': 'Case Reorder',
    'T45': 'Pseudo Loop',
    'T47': 'Dataflow Shatter',
    'T48': 'Anti-Topological',
}

# 反向映射：英文名称到规则代码
RULE_CODE_MAPPING = {v: k for k, v in RULE_NAME_MAPPING.items()}


def get_rule_code(rule_name: str) -> str:
    """将英文规则名称映射回TX代码"""
    return RULE_CODE_MAPPING.get(rule_name, rule_name)


def get_rule_name(rule_code: str) -> str:
    """将TX代码映射为英文规则名称"""
    return RULE_NAME_MAPPING.get(rule_code, rule_code)


def load_dataset(file_path: str) -> List[Dict]:
    """加载JSONL数据集"""
    samples = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line:
                samples.append(json.loads(line))
    return samples


def analyze_dataset(samples: List[Dict]) -> Dict:
    """分析数据集统计信息"""
    stats = {
        'total_samples': len(samples),
        'rule_distribution': Counter(),
        'avg_confidence': 0.0,
        'testbench_pass_rate': 0.0,
        'tasks': set(),
    }
    
    total_confidence = 0.0
    testbench_passed = 0
    
    for sample in samples:
        # 规则分布
        rule = sample.get('attack_rule', 'unknown')
        stats['rule_distribution'][rule] += 1
        
        # 置信度
        confidence = sample.get('judge_confidence', 0.0)
        total_confidence += confidence
        
        # Testbench通过率
        if sample.get('testbench_passed', False):
            testbench_passed += 1
        
        # 任务ID
        task_id = sample.get('task_id', '')
        if task_id:
            stats['tasks'].add(task_id)
    
    if len(samples) > 0:
        stats['avg_confidence'] = total_confidence / len(samples)
        stats['testbench_pass_rate'] = testbench_passed / len(samples)
    
    stats['unique_tasks'] = len(stats['tasks'])
    stats['tasks'] = list(stats['tasks'])  # 转换为列表以便JSON序列化
    
    return stats


def print_analysis(stats: Dict):
    """打印分析结果"""
    print("=" * 60)
    print("数据集分析报告")
    print("=" * 60)
    print(f"总样本数: {stats['total_samples']}")
    print(f"唯一任务数: {stats['unique_tasks']}")
    print(f"平均置信度: {stats['avg_confidence']:.4f}")
    print(f"Testbench通过率: {stats['testbench_pass_rate']:.2%}")
    
    print("\n规则分布:")
    for rule, count in sorted(stats['rule_distribution'].items(), key=lambda x: -x[1]):
        pct = count / stats['total_samples'] * 100
        print(f"  {rule}: {count} ({pct:.1f}%)")
    
    print("\n样本任务覆盖:")
    print(f"  涵盖 {stats['unique_tasks']} 个不同的任务")
    print("=" * 60)


def convert_to_sft_format(samples: List[Dict]) -> List[Dict]:
    """转换为SFT训练格式"""
    sft_samples = []
    
    for sample in samples:
        # 构建instruction
        instruction = "请对以下Verilog代码进行混淆攻击，使其功能保持不变但难以被AI理解。"
        
        # 构建input
        input_text = f"""### 功能规范
{sample['prompt']}

### 原始代码
```verilog
{sample['original_code']}
```"""
        
        # 获取攻击规则的英文名称
        rule_code = sample['attack_rule']
        rule_name = RULE_NAME_MAPPING.get(rule_code, rule_code)
        
        # 构建output（攻击策略）
        output = {
            "attack_name": rule_name,
            "parameters": sample.get('attack_params', {})
        }
        
        sft_sample = {
            "instruction": instruction,
            "input": input_text,
            "output": json.dumps(output, ensure_ascii=False)
        }
        
        sft_samples.append(sft_sample)
    
    return sft_samples


def convert_to_alpaca_format(samples: List[Dict]) -> List[Dict]:
    """转换为Alpaca格式（包含变换后代码）"""
    alpaca_samples = []
    
    for sample in samples:
        # 获取攻击规则的英文名称
        rule_code = sample['attack_rule']
        rule_name = RULE_NAME_MAPPING.get(rule_code, rule_code)
        
        alpaca_sample = {
            "instruction": "对以下Verilog代码进行混淆，保持功能不变但增加AI理解难度。",
            "input": sample['original_code'],
            "output": sample['transformed_code'],
            "metadata": {
                "attack_rule": rule_name,
                "rule_code": rule_code,  # 保留原始代码以便追溯
                "params": sample.get('attack_params', {}),
                "task_id": sample.get('task_id', ''),
            }
        }
        alpaca_samples.append(alpaca_sample)
    
    return alpaca_samples


def check_quality(samples: List[Dict]) -> Dict:
    """数据质量检查"""
    issues = {
        'missing_fields': [],
        'duplicate_transforms': [],
        'low_confidence': [],
        'tb_failed': [],
    }
    
    seen_transforms = defaultdict(list)
    
    for idx, sample in enumerate(samples):
        # 检查必需字段
        required_fields = ['task_id', 'prompt', 'original_code', 'transformed_code', 'attack_rule']
        missing = [f for f in required_fields if f not in sample or not sample[f]]
        if missing:
            issues['missing_fields'].append({
                'index': idx,
                'task_id': sample.get('task_id', 'unknown'),
                'missing': missing
            })
        
        # 检查重复变换
        key = (sample.get('original_code', ''), sample.get('transformed_code', ''))
        seen_transforms[key].append(idx)
        
        # 检查低置信度
        confidence = sample.get('judge_confidence', 1.0)
        if confidence < 0.5:
            issues['low_confidence'].append({
                'index': idx,
                'task_id': sample.get('task_id', 'unknown'),
                'confidence': confidence
            })
        
        # 检查testbench失败
        if not sample.get('testbench_passed', True):
            issues['tb_failed'].append({
                'index': idx,
                'task_id': sample.get('task_id', 'unknown'),
            })
    
    # 标记重复项
    for key, indices in seen_transforms.items():
        if len(indices) > 1:
            issues['duplicate_transforms'].append({
                'indices': indices,
                'count': len(indices)
            })
    
    return issues


def print_quality_report(issues: Dict):
    """打印质量报告"""
    print("\n" + "=" * 60)
    print("数据质量检查报告")
    print("=" * 60)
    
    total_issues = sum(len(v) for v in issues.values())
    
    if total_issues == 0:
        print("✅ 未发现质量问题")
    else:
        print(f"⚠️  发现 {total_issues} 个潜在问题：\n")
        
        if issues['missing_fields']:
            print(f"❌ 缺失字段: {len(issues['missing_fields'])} 个样本")
            for item in issues['missing_fields'][:3]:
                print(f"   - 样本 {item['index']} ({item['task_id']}): 缺少 {item['missing']}")
            if len(issues['missing_fields']) > 3:
                print(f"   ... 还有 {len(issues['missing_fields']) - 3} 个")
        
        if issues['duplicate_transforms']:
            print(f"\n⚠️  重复变换: {len(issues['duplicate_transforms'])} 组")
            for item in issues['duplicate_transforms'][:3]:
                print(f"   - 样本 {item['indices']} 重复 ({item['count']}次)")
            if len(issues['duplicate_transforms']) > 3:
                print(f"   ... 还有 {len(issues['duplicate_transforms']) - 3} 组")
        
        if issues['low_confidence']:
            print(f"\n⚠️  低置信度: {len(issues['low_confidence'])} 个样本")
            for item in issues['low_confidence'][:3]:
                print(f"   - 样本 {item['index']} ({item['task_id']}): {item['confidence']:.2f}")
            if len(issues['low_confidence']) > 3:
                print(f"   ... 还有 {len(issues['low_confidence']) - 3} 个")
        
        if issues['tb_failed']:
            print(f"\n❌ Testbench失败: {len(issues['tb_failed'])} 个样本")
    
    print("=" * 60)


def main():
    parser = argparse.ArgumentParser(description="分析和转换攻击数据集")
    parser.add_argument("input", type=str, help="输入JSONL文件路径")
    parser.add_argument("--stats", action="store_true", help="显示统计信息")
    parser.add_argument("--quality", action="store_true", help="运行质量检查")
    parser.add_argument("--to-sft", type=str, default=None, help="转换为SFT格式并保存")
    parser.add_argument("--to-alpaca", type=str, default=None, help="转换为Alpaca格式并保存")
    parser.add_argument("--filter-rules", type=str, default=None, help="只保留指定规则（逗号分隔）")
    parser.add_argument("--min-confidence", type=float, default=0.0, help="最低置信度过滤")
    
    args = parser.parse_args()
    
    # 加载数据集
    print(f"加载数据集: {args.input}")
    samples = load_dataset(args.input)
    print(f"加载了 {len(samples)} 个样本")
    
    # 过滤
    if args.filter_rules:
        rules = [r.strip() for r in args.filter_rules.split(',')]
        samples = [s for s in samples if s.get('attack_rule') in rules]
        print(f"过滤后保留 {len(samples)} 个样本（规则: {rules}）")
    
    if args.min_confidence > 0:
        samples = [s for s in samples if s.get('judge_confidence', 0) >= args.min_confidence]
        print(f"过滤后保留 {len(samples)} 个样本（置信度 >= {args.min_confidence}）")
    
    # 统计分析
    if args.stats or (not args.to_sft and not args.to_alpaca and not args.quality):
        stats = analyze_dataset(samples)
        print_analysis(stats)
    
    # 质量检查
    if args.quality:
        issues = check_quality(samples)
        print_quality_report(issues)
    
    # 转换为SFT格式
    if args.to_sft:
        sft_samples = convert_to_sft_format(samples)
        output_path = Path(args.to_sft)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for sample in sft_samples:
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')
        
        print(f"\n✅ SFT格式数据已保存: {output_path} ({len(sft_samples)} 个样本)")
    
    # 转换为Alpaca格式
    if args.to_alpaca:
        alpaca_samples = convert_to_alpaca_format(samples)
        output_path = Path(args.to_alpaca)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_path, 'w', encoding='utf-8') as f:
            for sample in alpaca_samples:
                f.write(json.dumps(sample, ensure_ascii=False) + '\n')
        
        print(f"\n✅ Alpaca格式数据已保存: {output_path} ({len(alpaca_samples)} 个样本)")


if __name__ == "__main__":
    main()
