#!/usr/bin/env python3
"""
SFT数据集查看工具

用法:
    python view_sft_samples.py --rule T45 --num 5
    python view_sft_samples.py --task q007000
    python view_sft_samples.py --random 10
"""

import json
import random
import argparse
from pathlib import Path
from typing import List, Dict

def load_dataset(path: Path) -> List[Dict]:
    """加载SFT数据集"""
    with open(path, 'r') as f:
        return json.load(f)

def filter_by_rule(dataset: List[Dict], rule_id: str) -> List[Dict]:
    """按规则ID筛选"""
    return [s for s in dataset if s['metadata']['rule_id'] == rule_id]

def filter_by_task(dataset: List[Dict], task_id: str) -> List[Dict]:
    """按任务ID筛选"""
    return [s for s in dataset if s['metadata']['task_id'] == task_id]

def display_sample(sample: Dict, index: int = None):
    """显示单个样本"""
    print("=" * 100)
    if index is not None:
        print(f"样本 #{index}")
    print("=" * 100)
    
    meta = sample['metadata']
    print(f"\n【元数据】")
    print(f"  规则ID: {meta['rule_id']}")
    print(f"  任务ID: {meta['task_id']}")
    print(f"  LLM错误输出: {meta['llm_wrong_output']}")
    print(f"  正确答案: {sample['output']}")
    print(f"  置信度: {meta['adversarial_confidence']:.4f}")
    
    print(f"\n【Instruction】")
    print(sample['instruction'][:300] + '...' if len(sample['instruction']) > 300 else sample['instruction'])
    
    print(f"\n【Input - 规范部分】")
    input_text = sample['input']
    spec_end = input_text.find('\n\nHere is a')
    if spec_end > 0:
        spec = input_text[:spec_end]
        print(spec[:500] + '...' if len(spec) > 500 else spec)
    
    print(f"\n【对抗代码】")
    if 'adversarial_code' in sample:
        code = sample['adversarial_code']
        print(code if len(code) < 1000 else code[:1000] + '\n...')
    else:
        # 从input中提取
        code_start = input_text.find('```verilog\n')
        code_end = input_text.find('\n```', code_start)
        if code_start > 0 and code_end > 0:
            code = input_text[code_start + 11:code_end]
            print(code if len(code) < 1000 else code[:1000] + '\n...')
    
    if 'original_code' in sample:
        print(f"\n【原始代码长度】{len(sample['original_code'])} 字符")
        print(f"【对抗代码长度】{len(sample.get('adversarial_code', ''))} 字符")
        if 'testbench' in sample:
            print(f"【Testbench长度】{len(sample['testbench'])} 字符")
    
    print()

def main():
    parser = argparse.ArgumentParser(description='查看SFT数据集样本')
    parser.add_argument('--data', type=str, default='data/sft_attack_success.json',
                        help='数据集文件路径')
    parser.add_argument('--rule', type=str, help='按规则ID筛选（如T45）')
    parser.add_argument('--task', type=str, help='按任务ID筛选（如q007000）')
    parser.add_argument('--random', type=int, help='随机显示N个样本')
    parser.add_argument('--num', type=int, default=5, help='显示样本数量（默认5）')
    parser.add_argument('--stats', action='store_true', help='只显示统计信息')
    
    args = parser.parse_args()
    
    # 加载数据集
    print(f"加载数据集: {args.data}")
    dataset = load_dataset(Path(args.data))
    print(f"✓ 加载了 {len(dataset)} 个样本\n")
    
    # 统计信息
    if args.stats or (not args.rule and not args.task and not args.random):
        print("=" * 100)
        print("数据集统计")
        print("=" * 100)
        
        # 按规则统计
        from collections import Counter
        rule_counts = Counter(s['metadata']['rule_id'] for s in dataset)
        task_counts = Counter(s['metadata']['task_id'] for s in dataset)
        
        print(f"\n总样本数: {len(dataset):,}")
        print(f"涵盖规则数: {len(rule_counts)}")
        print(f"涵盖任务数: {len(task_counts)}")
        
        print(f"\n各规则样本分布:")
        for rule_id, count in sorted(rule_counts.items()):
            pct = count / len(dataset) * 100
            print(f"  {rule_id}: {count:,} ({pct:.1f}%)")
        
        if args.stats:
            return
    
    # 筛选
    if args.rule:
        dataset = filter_by_rule(dataset, args.rule)
        print(f"筛选规则 {args.rule}: {len(dataset)} 个样本\n")
    
    if args.task:
        dataset = filter_by_task(dataset, args.task)
        print(f"筛选任务 {args.task}: {len(dataset)} 个样本\n")
    
    if not dataset:
        print("没有符合条件的样本")
        return
    
    # 显示样本
    if args.random:
        samples = random.sample(dataset, min(args.random, len(dataset)))
        print(f"随机显示 {len(samples)} 个样本:\n")
    else:
        samples = dataset[:args.num]
        print(f"显示前 {len(samples)} 个样本:\n")
    
    for i, sample in enumerate(samples, 1):
        display_sample(sample, i)

if __name__ == '__main__':
    main()
