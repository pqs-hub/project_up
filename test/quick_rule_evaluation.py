#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快速评估15个规则对数据集的攻击效果
不依赖判断模型API，只测试规则的基本可用性：
- 代码变换成功率
- Testbench通过率（如果有）
"""

import sys
import json
from pathlib import Path
from collections import defaultdict
from tqdm import tqdm

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ast_transforms_loader import create_engine
from Testbench_valid import TestbenchRunner

# 15个规则列表
ALL_RULES = ['T03', 'T07', 'T09', 'T10', 'T12', 'T19', 'T20', 'T30', 'T31', 'T32', 'T34', 'T41', 'T45', 'T47', 'T48']


def load_dataset(path: str):
    """加载数据集"""
    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    # 转换为标准格式
    samples = []
    for item in data:
        if 'canonical_solution' in item:
            samples.append({
                'task_id': item['task_id'],
                'spec': item.get('prompt', ''),
                'rtl': item['canonical_solution'],
                'testbench': item.get('test', '')
            })
    
    return samples


def evaluate_rule(engine, testbench_runner, samples, rule_id, max_samples=None):
    """评估单个规则"""
    stats = {
        'rule_id': rule_id,
        'total_samples': 0,
        'transform_success': 0,
        'transform_failed': 0,
        'testbench_passed': 0,
        'testbench_failed': 0,
        'testbench_skipped': 0,
    }
    
    test_samples = samples[:max_samples] if max_samples else samples
    stats['total_samples'] = len(test_samples)
    
    for sample in tqdm(test_samples, desc=f"Testing {rule_id}", leave=False):
        rtl = sample['rtl']
        testbench = sample.get('testbench', '')
        
        # 尝试应用规则
        try:
            # 对于不同位置尝试target_token=0（第一个候选位置）
            transformed = engine.apply_transform(
                code=rtl,
                transform_id=rule_id,
                target_token=0
            )
            
            # 检查是否成功变换
            if transformed and transformed != rtl:
                stats['transform_success'] += 1
                
                # 如果有testbench，尝试验证
                if testbench and testbench_runner:
                    try:
                        result = testbench_runner.run(transformed, testbench)
                        if result['passed']:
                            stats['testbench_passed'] += 1
                        else:
                            stats['testbench_failed'] += 1
                    except Exception:
                        stats['testbench_skipped'] += 1
                else:
                    stats['testbench_skipped'] += 1
            else:
                stats['transform_failed'] += 1
                
        except Exception as e:
            stats['transform_failed'] += 1
    
    return stats


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='快速评估规则攻击效果')
    parser.add_argument('--dataset', default='data/verilog_eval.json', help='数据集路径')
    parser.add_argument('--max-samples', type=int, default=50, help='每个规则最多测试多少样本')
    parser.add_argument('--rules', default=None, help='要测试的规则（逗号分隔），默认全部15个')
    parser.add_argument('--enable-testbench', action='store_true', help='启用testbench验证（较慢）')
    parser.add_argument('--output', default='test/rule_evaluation_results.json', help='结果输出路径')
    
    args = parser.parse_args()
    
    # 确定要测试的规则
    if args.rules:
        rules_to_test = args.rules.split(',')
    else:
        rules_to_test = ALL_RULES
    
    print(f"加载数据集: {args.dataset}")
    samples = load_dataset(args.dataset)
    print(f"数据集样本数: {len(samples)}")
    print(f"要测试的规则: {', '.join(rules_to_test)}")
    print(f"每个规则测试样本数: {min(args.max_samples, len(samples))}")
    
    # 初始化引擎
    print("\n初始化混淆引擎...")
    engine = create_engine()
    
    # 初始化testbench
    testbench_runner = None
    if args.enable_testbench:
        print("启用testbench验证（这会显著增加评估时间）...")
        testbench_runner = TestbenchRunner(simulator='iverilog', timeout=10)
    
    # 评估所有规则
    print("\n开始评估...\n")
    all_results = []
    
    for rule_id in rules_to_test:
        print(f"\n{'='*60}")
        print(f"评估规则: {rule_id}")
        print(f"{'='*60}")
        
        stats = evaluate_rule(engine, testbench_runner, samples, rule_id, args.max_samples)
        all_results.append(stats)
        
        # 打印统计
        print(f"\n规则 {rule_id} 统计:")
        print(f"  总样本数: {stats['total_samples']}")
        print(f"  变换成功: {stats['transform_success']} ({stats['transform_success']/stats['total_samples']*100:.1f}%)")
        print(f"  变换失败: {stats['transform_failed']} ({stats['transform_failed']/stats['total_samples']*100:.1f}%)")
        
        if args.enable_testbench:
            print(f"  Testbench通过: {stats['testbench_passed']}")
            print(f"  Testbench失败: {stats['testbench_failed']}")
            print(f"  Testbench跳过: {stats['testbench_skipped']}")
    
    # 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump({
            'config': {
                'dataset': args.dataset,
                'max_samples': args.max_samples,
                'total_dataset_size': len(samples),
                'rules_tested': rules_to_test,
                'testbench_enabled': args.enable_testbench
            },
            'results': all_results
        }, f, indent=2, ensure_ascii=False)
    
    print(f"\n\n{'='*60}")
    print("评估完成！")
    print(f"结果已保存到: {output_path}")
    print(f"{'='*60}\n")
    
    # 打印汇总表格
    print("\n规则攻击效果汇总:")
    print(f"{'规则':<8} {'总样本':<8} {'成功':<8} {'失败':<8} {'成功率':<10}")
    print("-" * 50)
    
    for stats in all_results:
        success_rate = stats['transform_success'] / stats['total_samples'] * 100
        print(f"{stats['rule_id']:<8} {stats['total_samples']:<8} {stats['transform_success']:<8} "
              f"{stats['transform_failed']:<8} {success_rate:>6.1f}%")
    
    # 计算平均成功率
    avg_success_rate = sum(s['transform_success'] for s in all_results) / sum(s['total_samples'] for s in all_results) * 100
    print("-" * 50)
    print(f"{'平均':<8} {sum(s['total_samples'] for s in all_results):<8} "
          f"{sum(s['transform_success'] for s in all_results):<8} "
          f"{sum(s['transform_failed'] for s in all_results):<8} {avg_success_rate:>6.1f}%")


if __name__ == '__main__':
    main()
