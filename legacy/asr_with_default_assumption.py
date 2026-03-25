#!/usr/bin/env python3
"""
假设original_passed默认为True来计算ASR

ASR定义：
在功能等价（original_truth==True AND adversarial_truth==True）且
规则成功应用（adversarial_code=='YES'）且
LLM原始判对（original_passed==True，默认假设为True）的前提下，
LLM对抗判错（adversarial_passed==False）的比例
"""

import json
from pathlib import Path
from collections import defaultdict

def analyze_rule_with_assumption(rule_id, eval_dir):
    """假设original_passed=True来分析规则"""
    
    if not eval_dir.exists():
        return None
    
    # ASR统计
    asr_denom = 0  # 功能等价 AND 规则应用 AND original_passed==True（假设）
    asr_numer = 0  # 在分母基础上，adversarial_passed==False
    
    # 详细分类
    func_equiv_code_yes = 0  # 功能等价且规则应用
    func_equiv_code_yes_adv_passed_true = 0   # LLM对抗判对
    func_equiv_code_yes_adv_passed_false = 0  # LLM对抗判错（攻击成功）
    func_equiv_code_yes_adv_passed_none = 0   # LLM对抗未评估
    
    # 功能等价但规则未应用
    func_equiv_code_no = 0
    
    # 功能破坏
    func_broken = 0
    func_broken_code_yes = 0
    func_broken_code_no = 0
    
    # 样本记录
    attack_success_samples = []  # ASR成功样本
    
    for json_file in eval_dir.glob('*.json'):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            task_id = data.get('task_id')
            orig_truth = data.get('original_truth')
            adv_truth = data.get('adversarial_truth')
            adv_passed = data.get('adversarial_passed')
            adv_code = data.get('adversarial_code', '')
            
            # 只处理原始代码仿真通过的样本
            if orig_truth != True:
                continue
            
            # 功能等价
            if adv_truth == True:
                if adv_code == 'YES':
                    func_equiv_code_yes += 1
                    
                    # 假设original_passed=True，计入ASR分母
                    asr_denom += 1
                    
                    if adv_passed == False:
                        asr_numer += 1
                        func_equiv_code_yes_adv_passed_false += 1
                        if len(attack_success_samples) < 10:
                            attack_success_samples.append({
                                'task_id': task_id,
                                'adversarial_confidence': data.get('adversarial_confidence')
                            })
                    elif adv_passed == True:
                        func_equiv_code_yes_adv_passed_true += 1
                    else:
                        func_equiv_code_yes_adv_passed_none += 1
                
                elif adv_code == 'NO':
                    func_equiv_code_no += 1
            
            # 功能破坏
            elif adv_truth == False:
                func_broken += 1
                if adv_code == 'YES':
                    func_broken_code_yes += 1
                elif adv_code == 'NO':
                    func_broken_code_no += 1
        
        except Exception as e:
            continue
    
    # 计算ASR
    asr = (asr_numer / asr_denom * 100) if asr_denom > 0 else None
    
    return {
        'rule_id': rule_id,
        
        # 功能等价且规则应用
        'func_equiv_code_yes': func_equiv_code_yes,
        'func_equiv_code_yes_adv_passed_true': func_equiv_code_yes_adv_passed_true,
        'func_equiv_code_yes_adv_passed_false': func_equiv_code_yes_adv_passed_false,
        'func_equiv_code_yes_adv_passed_none': func_equiv_code_yes_adv_passed_none,
        
        # 功能等价但规则未应用
        'func_equiv_code_no': func_equiv_code_no,
        
        # 功能破坏
        'func_broken': func_broken,
        'func_broken_code_yes': func_broken_code_yes,
        'func_broken_code_no': func_broken_code_no,
        
        # ASR
        'asr_denom': asr_denom,
        'asr_numer': asr_numer,
        'asr': asr,
        
        # 样本
        'attack_success_samples': attack_success_samples
    }

def main():
    print("="*100)
    print("假设original_passed=True来计算ASR")
    print("="*100)
    print("\n假设：LLM对所有原始代码的判断都是正确的（original_passed=True）")
    print("ASR = 在功能等价且规则应用的前提下，LLM对抗判错的比例\n")
    
    eval_base = Path('rule_eval/metrics_conf_v2_on_fullall_adv')
    
    # 获取所有规则
    rules = sorted([d.name for d in eval_base.iterdir() if d.is_dir() and d.name.startswith('T')])
    
    all_results = []
    
    for rule_id in rules:
        eval_dir = eval_base / rule_id / 'adv_eval'
        result = analyze_rule_with_assumption(rule_id, eval_dir)
        
        if result:
            all_results.append(result)
    
    # 按ASR排序
    all_results_with_asr = [r for r in all_results if r['asr'] is not None]
    all_results_with_asr.sort(key=lambda x: x['asr'], reverse=True)
    
    # 打印ASR统计表
    print("="*100)
    print("ASR（攻击成功率）排行榜")
    print("="*100)
    print(f"\n{'规则':<8} {'功能等价+应用':<14} {'LLM对抗判对':<14} {'LLM对抗判错':<14} {'ASR':<10} {'评级':<10}")
    print("-"*100)
    
    for r in all_results_with_asr:
        rating = ""
        if r['asr'] >= 50:
            rating = "🔥 极强"
        elif r['asr'] >= 30:
            rating = "✅ 强"
        elif r['asr'] >= 10:
            rating = "⚠️ 中等"
        elif r['asr'] > 0:
            rating = "💡 弱"
        else:
            rating = "❌ 无效"
        
        print(f"{r['rule_id']:<8} {r['asr_denom']:<14} "
              f"{r['func_equiv_code_yes_adv_passed_true']:<14} "
              f"{r['asr_numer']:<14} {r['asr']:>6.1f}%    {rating:<10}")
    
    # 详细分类统计
    print("\n" + "="*100)
    print("详细分类统计")
    print("="*100)
    print(f"\n{'规则':<8} {'等价+应用':<12} {'判对':<8} {'判错':<8} {'未评估':<8} "
          f"{'等价+未应用':<12} {'破坏':<8}")
    print("-"*100)
    
    for r in all_results:
        print(f"{r['rule_id']:<8} {r['func_equiv_code_yes']:<12} "
              f"{r['func_equiv_code_yes_adv_passed_true']:<8} "
              f"{r['func_equiv_code_yes_adv_passed_false']:<8} "
              f"{r['func_equiv_code_yes_adv_passed_none']:<8} "
              f"{r['func_equiv_code_no']:<12} {r['func_broken']:<8}")
    
    # 规则分类
    print("\n" + "="*100)
    print("规则分类")
    print("="*100)
    
    high_asr = [r for r in all_results_with_asr if r['asr'] >= 30]
    medium_asr = [r for r in all_results_with_asr if 10 <= r['asr'] < 30]
    low_asr = [r for r in all_results_with_asr if 0 < r['asr'] < 10]
    zero_asr = [r for r in all_results_with_asr if r['asr'] == 0]
    
    print(f"\n🔥 高ASR规则 (≥30%): {len(high_asr)} 个")
    if high_asr:
        for r in high_asr:
            print(f"  {r['rule_id']}: ASR={r['asr']:.1f}%, "
                  f"攻击成功={r['asr_numer']}/{r['asr_denom']}")
            if r['attack_success_samples']:
                print(f"    样本: {', '.join([s['task_id'] for s in r['attack_success_samples'][:5]])}")
    
    print(f"\n✅ 中等ASR规则 (10-30%): {len(medium_asr)} 个")
    if medium_asr:
        for r in medium_asr:
            print(f"  {r['rule_id']}: ASR={r['asr']:.1f}%, "
                  f"攻击成功={r['asr_numer']}/{r['asr_denom']}")
    
    print(f"\n💡 低ASR规则 (0-10%): {len(low_asr)} 个")
    if low_asr:
        for r in low_asr:
            print(f"  {r['rule_id']}: ASR={r['asr']:.1f}%, "
                  f"攻击成功={r['asr_numer']}/{r['asr_denom']}")
    
    print(f"\n❌ 零ASR规则: {len(zero_asr)} 个")
    if zero_asr:
        print(f"  {', '.join([r['rule_id'] for r in zero_asr])}")
    
    # 总体统计
    print("\n" + "="*100)
    print("总体统计")
    print("="*100)
    
    total_func_equiv_code_yes = sum(r['func_equiv_code_yes'] for r in all_results)
    total_asr_denom = sum(r['asr_denom'] for r in all_results)
    total_asr_numer = sum(r['asr_numer'] for r in all_results)
    total_adv_passed_true = sum(r['func_equiv_code_yes_adv_passed_true'] for r in all_results)
    total_func_equiv_code_no = sum(r['func_equiv_code_no'] for r in all_results)
    total_func_broken = sum(r['func_broken'] for r in all_results)
    
    overall_asr = (total_asr_numer / total_asr_denom * 100) if total_asr_denom > 0 else 0
    
    print(f"\n功能等价且规则应用: {total_func_equiv_code_yes:,}")
    print(f"  - LLM对抗判对: {total_adv_passed_true:,} ({total_adv_passed_true/total_func_equiv_code_yes*100:.1f}%)")
    print(f"  - LLM对抗判错（攻击成功）: {total_asr_numer:,} ({total_asr_numer/total_func_equiv_code_yes*100:.1f}%)")
    print(f"\n功能等价但规则未应用: {total_func_equiv_code_no:,}")
    print(f"功能破坏: {total_func_broken:,}")
    print(f"\n总体ASR: {overall_asr:.2f}%")
    print(f"  分母（假设original_passed=True）: {total_asr_denom:,}")
    print(f"  分子（adversarial_passed=False）: {total_asr_numer:,}")
    
    # 保存结果
    output_file = 'rule_eval/asr_with_default_assumption.json'
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细结果已保存到: {output_file}")
    
    # 生成攻击成功样本汇总
    print("\n" + "="*100)
    print("攻击成功样本汇总")
    print("="*100)
    
    all_attack_samples = []
    for r in all_results:
        if r['attack_success_samples']:
            for sample in r['attack_success_samples']:
                all_attack_samples.append({
                    'rule_id': r['rule_id'],
                    'task_id': sample['task_id'],
                    'adversarial_confidence': sample['adversarial_confidence']
                })
    
    print(f"\n总共找到 {total_asr_numer:,} 个攻击成功样本")
    print(f"前10个样本:")
    for i, sample in enumerate(all_attack_samples[:10], 1):
        print(f"  {i}. {sample['rule_id']}/{sample['task_id']} "
              f"(confidence={sample['adversarial_confidence']:.4f})")
    
    # 保存攻击成功样本
    attack_samples_file = 'rule_eval/attack_success_samples.json'
    with open(attack_samples_file, 'w') as f:
        json.dump(all_attack_samples, f, indent=2, ensure_ascii=False)
    
    print(f"\n所有攻击成功样本已保存到: {attack_samples_file}")

if __name__ == '__main__':
    main()
