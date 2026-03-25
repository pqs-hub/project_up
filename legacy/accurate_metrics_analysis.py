#!/usr/bin/env python3
"""
基于明确的指标定义，准确统计评估结果

指标定义（来自evaluate.py）：
1. original_truth: 原始代码仿真是否通过（Ground Truth）
2. adversarial_truth: 对抗代码仿真是否通过（Ground Truth）
3. original_passed: LLM对原始代码判断是否正确（passed=True表示LLM判对）
4. adversarial_passed: LLM对对抗代码判断是否正确（passed=True表示LLM判对）
5. adversarial_code: 规则是否成功应用（'YES'/'NO'）

关键指标：
- 功能等价率 = (original_truth==True AND adversarial_truth==True) / (original_truth==True)
- ASR = 在(original_truth==True AND adversarial_truth==True AND original_passed==True)的前提下，
        adversarial_passed==False的比例
"""

import json
from pathlib import Path
from collections import defaultdict

def analyze_rule(rule_id, eval_dir):
    """分析单个规则的详细指标"""
    
    if not eval_dir.exists():
        return None
    
    # 统计变量
    total = 0
    
    # Ground Truth统计
    orig_truth_true = 0  # 原始代码仿真通过
    func_equiv = 0  # 功能等价（both truth==True）
    func_broken = 0  # 功能破坏（orig==True, adv==False）
    
    # 规则应用统计
    code_yes = 0  # 规则成功应用
    code_no = 0   # 规则未应用
    
    # LLM判断统计（全量）
    orig_passed_true = 0   # LLM对原始代码判对
    orig_passed_false = 0  # LLM对原始代码判错
    orig_passed_none = 0   # 原始代码未评估
    
    adv_passed_true = 0    # LLM对对抗代码判对
    adv_passed_false = 0   # LLM对对抗代码判错
    adv_passed_none = 0    # 对抗代码未评估
    
    # ASR相关统计
    asr_denom = 0  # ASR分母：功能等价 AND 规则应用 AND LLM原始判对
    asr_numer = 0  # ASR分子：在分母基础上，LLM对抗判错
    
    # 功能等价且规则应用的样本中，LLM判断统计
    equiv_code_yes_total = 0
    equiv_code_yes_orig_passed = 0
    equiv_code_yes_adv_passed = 0
    equiv_code_yes_both_passed = 0
    equiv_code_yes_flipped = 0  # 原始判对→对抗判错
    
    # 详细样本记录
    samples = {
        'func_broken_samples': [],  # 功能破坏样本
        'asr_success_samples': [],  # ASR成功样本
        'code_no_samples': [],      # 规则未应用样本
    }
    
    for json_file in eval_dir.glob('*.json'):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            total += 1
            
            task_id = data.get('task_id')
            orig_truth = data.get('original_truth')
            adv_truth = data.get('adversarial_truth')
            orig_passed = data.get('original_passed')
            adv_passed = data.get('adversarial_passed')
            adv_code = data.get('adversarial_code', '')
            
            # Ground Truth统计
            if orig_truth == True:
                orig_truth_true += 1
                
                if adv_truth == True:
                    func_equiv += 1
                elif adv_truth == False:
                    func_broken += 1
                    if len(samples['func_broken_samples']) < 5:
                        samples['func_broken_samples'].append({
                            'task_id': task_id,
                            'adversarial_code': adv_code
                        })
            
            # 规则应用统计
            if adv_code == 'YES':
                code_yes += 1
            elif adv_code == 'NO':
                code_no += 1
                if len(samples['code_no_samples']) < 5:
                    samples['code_no_samples'].append(task_id)
            
            # LLM判断统计
            if orig_passed == True:
                orig_passed_true += 1
            elif orig_passed == False:
                orig_passed_false += 1
            else:
                orig_passed_none += 1
            
            if adv_passed == True:
                adv_passed_true += 1
            elif adv_passed == False:
                adv_passed_false += 1
            else:
                adv_passed_none += 1
            
            # ASR统计（严格定义）
            if orig_truth == True and adv_truth == True and adv_code == 'YES':
                equiv_code_yes_total += 1
                
                if orig_passed == True:
                    equiv_code_yes_orig_passed += 1
                    asr_denom += 1
                    
                    if adv_passed == False:
                        asr_numer += 1
                        equiv_code_yes_flipped += 1
                        if len(samples['asr_success_samples']) < 5:
                            samples['asr_success_samples'].append(task_id)
                
                if adv_passed == True:
                    equiv_code_yes_adv_passed += 1
                
                if orig_passed == True and adv_passed == True:
                    equiv_code_yes_both_passed += 1
        
        except Exception as e:
            continue
    
    # 计算比率
    func_equiv_rate = (func_equiv / orig_truth_true * 100) if orig_truth_true > 0 else 0
    func_broken_rate = (func_broken / orig_truth_true * 100) if orig_truth_true > 0 else 0
    code_yes_rate = (code_yes / total * 100) if total > 0 else 0
    
    asr = (asr_numer / asr_denom * 100) if asr_denom > 0 else None
    
    # LLM准确率（在功能等价且规则应用的样本上）
    llm_orig_acc = (equiv_code_yes_orig_passed / equiv_code_yes_total * 100) if equiv_code_yes_total > 0 else 0
    llm_adv_acc = (equiv_code_yes_adv_passed / equiv_code_yes_total * 100) if equiv_code_yes_total > 0 else 0
    
    return {
        'rule_id': rule_id,
        'total_samples': total,
        
        # Ground Truth
        'orig_truth_true': orig_truth_true,
        'func_equiv': func_equiv,
        'func_broken': func_broken,
        'func_equiv_rate': func_equiv_rate,
        'func_broken_rate': func_broken_rate,
        
        # 规则应用
        'code_yes': code_yes,
        'code_no': code_no,
        'code_yes_rate': code_yes_rate,
        
        # LLM判断（全量）
        'orig_passed_true': orig_passed_true,
        'orig_passed_false': orig_passed_false,
        'orig_passed_none': orig_passed_none,
        'adv_passed_true': adv_passed_true,
        'adv_passed_false': adv_passed_false,
        'adv_passed_none': adv_passed_none,
        
        # 功能等价且规则应用的子集
        'equiv_code_yes_total': equiv_code_yes_total,
        'equiv_code_yes_orig_passed': equiv_code_yes_orig_passed,
        'equiv_code_yes_adv_passed': equiv_code_yes_adv_passed,
        'equiv_code_yes_both_passed': equiv_code_yes_both_passed,
        'equiv_code_yes_flipped': equiv_code_yes_flipped,
        
        # ASR
        'asr_denom': asr_denom,
        'asr_numer': asr_numer,
        'asr': asr,
        
        # LLM准确率（在功能等价且规则应用的样本上）
        'llm_orig_acc': llm_orig_acc,
        'llm_adv_acc': llm_adv_acc,
        
        # 样本
        'samples': samples
    }

def main():
    print("="*100)
    print("基于明确定义的准确指标统计")
    print("="*100)
    
    eval_base = Path('rule_eval/metrics_conf_v2_on_fullall_adv')
    
    # 获取所有规则
    rules = sorted([d.name for d in eval_base.iterdir() if d.is_dir() and d.name.startswith('T')])
    print(f"\n找到 {len(rules)} 个规则: {', '.join(rules)}")
    
    all_results = []
    
    for rule_id in rules:
        eval_dir = eval_base / rule_id / 'adv_eval'
        result = analyze_rule(rule_id, eval_dir)
        
        if result:
            all_results.append(result)
    
    # 按ASR排序
    all_results_with_asr = [r for r in all_results if r['asr'] is not None]
    all_results_with_asr.sort(key=lambda x: x['asr'], reverse=True)
    
    # 打印详细表格
    print("\n" + "="*100)
    print("详细统计表")
    print("="*100)
    
    print(f"\n{'规则':<8} {'总样本':<8} {'原始通过':<10} {'功能等价':<10} {'等价率':<8} "
          f"{'规则应用':<10} {'应用率':<8}")
    print("-"*100)
    
    for r in all_results:
        print(f"{r['rule_id']:<8} {r['total_samples']:<8} {r['orig_truth_true']:<10} "
              f"{r['func_equiv']:<10} {r['func_equiv_rate']:>6.1f}%  "
              f"{r['code_yes']:<10} {r['code_yes_rate']:>6.1f}%")
    
    # ASR统计表
    print("\n" + "="*100)
    print("ASR（攻击成功率）统计")
    print("="*100)
    print("\nASR定义：在功能等价、规则应用、LLM原始判对的前提下，LLM对抗判错的比例")
    print(f"\n{'规则':<8} {'等价+应用':<12} {'LLM原始判对':<14} {'LLM对抗判错':<14} {'ASR':<10} {'评级':<10}")
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
        
        print(f"{r['rule_id']:<8} {r['equiv_code_yes_total']:<12} {r['asr_denom']:<14} "
              f"{r['asr_numer']:<14} {r['asr']:>6.1f}%    {rating:<10}")
    
    # 无ASR的规则
    no_asr_rules = [r for r in all_results if r['asr'] is None]
    if no_asr_rules:
        print(f"\n无ASR数据的规则（LLM原始判对数为0）:")
        for r in no_asr_rules:
            print(f"  {r['rule_id']}: 等价+应用={r['equiv_code_yes_total']}, "
                  f"LLM原始判对={r['asr_denom']}")
    
    # LLM准确率对比
    print("\n" + "="*100)
    print("LLM准确率对比（仅在功能等价且规则应用的样本上）")
    print("="*100)
    print(f"\n{'规则':<8} {'样本数':<10} {'原始准确率':<12} {'对抗准确率':<12} {'准确率下降':<12}")
    print("-"*100)
    
    for r in all_results:
        if r['equiv_code_yes_total'] > 0:
            acc_drop = r['llm_orig_acc'] - r['llm_adv_acc']
            print(f"{r['rule_id']:<8} {r['equiv_code_yes_total']:<10} "
                  f"{r['llm_orig_acc']:>6.1f}%      {r['llm_adv_acc']:>6.1f}%      "
                  f"{acc_drop:>6.1f}%")
    
    # 功能破坏分析
    print("\n" + "="*100)
    print("功能破坏分析")
    print("="*100)
    print(f"\n{'规则':<8} {'原始通过':<10} {'功能破坏':<10} {'破坏率':<10} {'其中code=NO':<12}")
    print("-"*100)
    
    for r in sorted(all_results, key=lambda x: x['func_broken_rate'], reverse=True):
        if r['func_broken'] > 0:
            # 统计功能破坏中code=NO的比例
            code_no_in_broken = 0
            for sample in r['samples']['func_broken_samples']:
                if sample['adversarial_code'] == 'NO':
                    code_no_in_broken += 1
            
            print(f"{r['rule_id']:<8} {r['orig_truth_true']:<10} {r['func_broken']:<10} "
                  f"{r['func_broken_rate']:>6.1f}%    "
                  f"{code_no_in_broken}/{min(5, r['func_broken'])}")
    
    # 总体统计
    print("\n" + "="*100)
    print("总体统计")
    print("="*100)
    
    total_samples = sum(r['total_samples'] for r in all_results)
    total_orig_true = sum(r['orig_truth_true'] for r in all_results)
    total_func_equiv = sum(r['func_equiv'] for r in all_results)
    total_func_broken = sum(r['func_broken'] for r in all_results)
    total_code_yes = sum(r['code_yes'] for r in all_results)
    total_equiv_code_yes = sum(r['equiv_code_yes_total'] for r in all_results)
    total_asr_denom = sum(r['asr_denom'] for r in all_results)
    total_asr_numer = sum(r['asr_numer'] for r in all_results)
    
    overall_func_equiv_rate = (total_func_equiv / total_orig_true * 100) if total_orig_true > 0 else 0
    overall_func_broken_rate = (total_func_broken / total_orig_true * 100) if total_orig_true > 0 else 0
    overall_asr = (total_asr_numer / total_asr_denom * 100) if total_asr_denom > 0 else 0
    
    print(f"\n总样本数: {total_samples:,}")
    print(f"原始代码仿真通过: {total_orig_true:,}")
    print(f"  - 功能等价: {total_func_equiv:,} ({overall_func_equiv_rate:.1f}%)")
    print(f"  - 功能破坏: {total_func_broken:,} ({overall_func_broken_rate:.1f}%)")
    print(f"\n规则成功应用: {total_code_yes:,}")
    print(f"功能等价且规则应用: {total_equiv_code_yes:,}")
    print(f"\nASR统计:")
    print(f"  - 分母（功能等价+规则应用+LLM原始判对）: {total_asr_denom:,}")
    print(f"  - 分子（LLM对抗判错）: {total_asr_numer:,}")
    print(f"  - 总体ASR: {overall_asr:.2f}%")
    
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
    
    # 保存结果
    output_file = 'rule_eval/accurate_metrics_analysis.json'
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细结果已保存到: {output_file}")

if __name__ == '__main__':
    main()
