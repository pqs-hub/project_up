#!/usr/bin/env python3
"""
打印所有规则的攻击成功率统计
"""

import json

def print_all_rules_stats(stats_file='rule_eval/metrics_conf_v2_on_fullall_adv_stats.json'):
    # 读取统计结果
    with open(stats_file, 'r') as f:
        stats = json.load(f)

    print('=' * 120)
    print('所有规则攻击成功率统计（基于 metrics_conf_v2_on_fullall_adv）')
    print('=' * 120)
    print()

    # 按规则ID排序
    rules = sorted(stats['per_rule_stats'].items())

    # 表头
    header = f"{'规则':<8} {'总样本':>10} {'原始正确':>10} {'攻击成功':>10} {'GT成功率':>10} {'LLM通过':>10} {'LLM失败':>10} {'LLM攻击成功':>12} {'LLM成功率':>12}"
    print(header)
    print('=' * 120)

    for rule, s in rules:
        gt_rate = s['attack_success'] / s['original_correct'] * 100 if s['original_correct'] > 0 else 0
        llm_rate = s['llm_attack_success'] / s['original_correct'] * 100 if s['original_correct'] > 0 else 0
        
        print(f"{rule:<8} {s['total']:>10,} {s['original_correct']:>10,} {s['attack_success']:>10,} "
              f"{gt_rate:>9.1f}% {s['adversarial_passed']:>10,} {s['adversarial_failed']:>10,} "
              f"{s['llm_attack_success']:>12,} {llm_rate:>11.1f}%")

    print('=' * 120)
    total_llm_success = sum(s['llm_attack_success'] for s in stats['per_rule_stats'].values())
    total_adv_passed = sum(s['adversarial_passed'] for s in stats['per_rule_stats'].values())
    total_adv_failed = sum(s['adversarial_failed'] for s in stats['per_rule_stats'].values())
    
    print(f"{'总计':<8} {stats['total_samples']:>10,} {stats['total_original_correct']:>10,} "
          f"{stats['total_attack_success']:>10,} "
          f"{stats['attack_success_rate']*100:>9.1f}% "
          f"{total_adv_passed:>10,} "
          f"{total_adv_failed:>10,} "
          f"{total_llm_success:>12,} "
          f"{total_llm_success/stats['total_original_correct']*100:>11.1f}%")
    print()
    print()

    # 分类统计
    print('=' * 100)
    print('规则分类统计')
    print('=' * 100)
    print()

    # 1. 按Ground Truth成功率分类
    print('【按Ground Truth攻击成功率分类】')
    print()
    high_gt = [(r, s) for r, s in rules if s['original_correct'] > 0 and s['attack_success'] / s['original_correct'] > 0.4]
    medium_gt = [(r, s) for r, s in rules if s['original_correct'] > 0 and 0.1 < s['attack_success'] / s['original_correct'] <= 0.4]
    low_gt = [(r, s) for r, s in rules if s['original_correct'] > 0 and 0 < s['attack_success'] / s['original_correct'] <= 0.1]
    zero_gt = [(r, s) for r, s in rules if s['attack_success'] == 0]

    print(f'高成功率（>40%）: {len(high_gt)} 个规则')
    for r, s in sorted(high_gt, key=lambda x: x[1]['attack_success']/x[1]['original_correct'], reverse=True):
        rate = s['attack_success'] / s['original_correct'] * 100
        print(f"  {r}: {rate:>5.1f}% ({s['attack_success']:>5,} / {s['original_correct']:>6,})")
    print()

    print(f'中成功率（10%-40%）: {len(medium_gt)} 个规则')
    for r, s in sorted(medium_gt, key=lambda x: x[1]['attack_success']/x[1]['original_correct'], reverse=True):
        rate = s['attack_success'] / s['original_correct'] * 100
        print(f"  {r}: {rate:>5.1f}% ({s['attack_success']:>5,} / {s['original_correct']:>6,})")
    print()

    print(f'低成功率（0%-10%）: {len(low_gt)} 个规则')
    for r, s in sorted(low_gt, key=lambda x: x[1]['attack_success']/x[1]['original_correct'], reverse=True):
        rate = s['attack_success'] / s['original_correct'] * 100
        print(f"  {r}: {rate:>5.1f}% ({s['attack_success']:>5,} / {s['original_correct']:>6,})")
    print()

    print(f'零成功率（0%）: {len(zero_gt)} 个规则')
    for r, s in zero_gt:
        print(f"  {r}: 0.0% (0 / {s['original_correct']:>6,})")
    print()
    print()

    # 2. 按LLM成功率分类
    print('【按LLM攻击成功率分类】')
    print()
    high_llm = [(r, s) for r, s in rules if s['original_correct'] > 0 and s['llm_attack_success'] / s['original_correct'] > 0.5]
    medium_llm = [(r, s) for r, s in rules if s['original_correct'] > 0 and 0.2 < s['llm_attack_success'] / s['original_correct'] <= 0.5]
    low_llm = [(r, s) for r, s in rules if s['original_correct'] > 0 and s['llm_attack_success'] / s['original_correct'] <= 0.2]

    print(f'高LLM成功率（>50%）: {len(high_llm)} 个规则')
    for r, s in sorted(high_llm, key=lambda x: x[1]['llm_attack_success']/x[1]['original_correct'], reverse=True):
        rate = s['llm_attack_success'] / s['original_correct'] * 100
        print(f"  {r}: {rate:>5.1f}% ({s['llm_attack_success']:>6,} / {s['original_correct']:>6,})")
    print()

    print(f'中LLM成功率（20%-50%）: {len(medium_llm)} 个规则')
    for r, s in sorted(medium_llm, key=lambda x: x[1]['llm_attack_success']/x[1]['original_correct'], reverse=True):
        rate = s['llm_attack_success'] / s['original_correct'] * 100
        print(f"  {r}: {rate:>5.1f}% ({s['llm_attack_success']:>6,} / {s['original_correct']:>6,})")
    print()

    print(f'低LLM成功率（<20%）: {len(low_llm)} 个规则')
    for r, s in sorted(low_llm, key=lambda x: x[1]['llm_attack_success']/x[1]['original_correct'], reverse=True):
        rate = s['llm_attack_success'] / s['original_correct'] * 100
        print(f"  {r}: {rate:>5.1f}% ({s['llm_attack_success']:>6,} / {s['original_correct']:>6,})")

if __name__ == '__main__':
    print_all_rules_stats()
