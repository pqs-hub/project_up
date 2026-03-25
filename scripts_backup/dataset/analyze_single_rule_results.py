#!/usr/bin/env python3
"""
统计单规则攻击结果
"""

import os
import json
from collections import defaultdict

def analyze_single_rule_results(base_dir='rule_eval/metrics_conf_v2_on_fullall_adv'):
    """分析单规则攻击结果"""
    
    rule_dirs = sorted([d for d in os.listdir(base_dir) 
                        if os.path.isdir(os.path.join(base_dir, d)) and d.startswith('T')])
    
    print('=== 单规则攻击成功样本统计（基于ground truth） ===')
    print()
    
    stats = {}
    total_samples = 0
    total_original_correct = 0
    total_attack_success = 0
    
    for rule in rule_dirs:
        adv_eval_dir = os.path.join(base_dir, rule, 'adv_eval')
        
        if not os.path.exists(adv_eval_dir):
            continue
        
        json_files = [f for f in os.listdir(adv_eval_dir) if f.endswith('.json')]
        
        rule_stats = {
            'total': len(json_files),
            'original_correct': 0,      # original_truth == True
            'attack_success': 0,         # original_truth == True && adversarial_truth == False
            'adversarial_passed': 0,     # adversarial_passed == True
            'adversarial_failed': 0,     # adversarial_passed == False
            'has_adv_code': 0,          # adversarial_code 非空
            'llm_attack_success': 0,    # adversarial_passed == False (LLM判断失败)
        }
        
        for json_file in json_files:
            try:
                with open(os.path.join(adv_eval_dir, json_file), 'r') as f:
                    data = json.load(f)
                
                # 原始代码正确
                if data.get('original_truth') == True:
                    rule_stats['original_correct'] += 1
                    
                    # 攻击成功（原始正确 -> 对抗错误）
                    if data.get('adversarial_truth') == False:
                        rule_stats['attack_success'] += 1
                
                # LLM判断对抗代码通过
                if data.get('adversarial_passed') == True:
                    rule_stats['adversarial_passed'] += 1
                elif data.get('adversarial_passed') == False:
                    rule_stats['adversarial_failed'] += 1
                    # LLM攻击成功（LLM判断对抗代码错误）
                    if data.get('original_truth') == True:
                        rule_stats['llm_attack_success'] += 1
                
                # 有对抗代码
                adv_code = data.get('adversarial_code', '')
                if adv_code and adv_code != '':
                    rule_stats['has_adv_code'] += 1
            
            except Exception as e:
                print(f"Error reading {json_file}: {e}")
        
        stats[rule] = rule_stats
        total_samples += rule_stats['total']
        total_original_correct += rule_stats['original_correct']
        total_attack_success += rule_stats['attack_success']
    
    # 打印总体统计
    print(f'总样本数: {total_samples:,}')
    print(f'原始代码正确: {total_original_correct:,} ({total_original_correct/total_samples*100:.1f}%)')
    print(f'攻击成功（ground truth）: {total_attack_success:,} ({total_attack_success/total_samples*100:.1f}%)')
    print()
    
    # 打印详细表格
    print('=' * 110)
    print(f'{"规则":<8} {"总样本":>10} {"原始正确":>10} {"攻击成功":>10} {"成功率":>10} {"LLM通过":>10} {"LLM失败":>10} {"LLM攻击成功":>12}')
    print('=' * 110)
    
    for rule in rule_dirs:
        if rule not in stats:
            continue
        s = stats[rule]
        success_rate = s['attack_success'] / s['original_correct'] * 100 if s['original_correct'] > 0 else 0
        llm_success_rate = s['llm_attack_success'] / s['original_correct'] * 100 if s['original_correct'] > 0 else 0
        print(f'{rule:<8} {s["total"]:>10,} {s["original_correct"]:>10,} {s["attack_success"]:>10,} '
              f'{success_rate:>9.1f}% {s["adversarial_passed"]:>10,} {s["adversarial_failed"]:>10,} '
              f'{s["llm_attack_success"]:>10,} ({llm_success_rate:.1f}%)')
    
    print('=' * 110)
    total_llm_success = sum(s['llm_attack_success'] for s in stats.values())
    print(f'{"总计":<8} {total_samples:>10,} {total_original_correct:>10,} {total_attack_success:>10,} '
          f'{total_attack_success/total_original_correct*100:>9.1f}% '
          f'{sum(s["adversarial_passed"] for s in stats.values()):>10,} '
          f'{sum(s["adversarial_failed"] for s in stats.values()):>10,} '
          f'{total_llm_success:>10,} ({total_llm_success/total_original_correct*100:.1f}%)')
    print()
    
    # 保存统计结果
    output = {
        'total_samples': total_samples,
        'total_original_correct': total_original_correct,
        'total_attack_success': total_attack_success,
        'attack_success_rate': total_attack_success / total_original_correct if total_original_correct > 0 else 0,
        'per_rule_stats': stats
    }
    
    output_file = f'{base_dir}_stats.json'
    with open(output_file, 'w') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f'统计结果已保存到: {output_file}')
    
    return stats

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='统计单规则攻击结果')
    parser.add_argument('--eval-dir', default='rule_eval/metrics_conf_v2_on_fullall_adv',
                        help='评估结果目录')
    args = parser.parse_args()
    
    analyze_single_rule_results(args.eval_dir)
