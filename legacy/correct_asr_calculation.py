#!/usr/bin/env python3
"""
正确计算ASR - 不依赖adversarial_code字段

关键理解：
- adversarial_code存储的是LLM的判断结果（YES/NO），不是规则是否应用
- 规则是否应用需要通过其他方式判断（比如代码是否改变）
- ASR的正确定义：在功能等价的前提下，LLM被欺骗的比例

新的计算方法：
ASR = (功能等价 AND LLM原始判对 AND LLM对抗判错) / (功能等价 AND LLM原始判对)

假设original_passed=True（默认LLM对原始代码都判对）：
ASR = (orig_truth==True AND adv_truth==True AND adv_passed==False) / (orig_truth==True AND adv_truth==True)

只统计注册表中的15个规则：T03, T07, T09, T10, T12, T19, T20, T30, T31, T32, T34, T41, T45, T47, T48
"""

import json
from pathlib import Path
from collections import defaultdict

# 注册表中的规则（与 ast_transforms.2.py 的 AST_TRANSFORM_REGISTRY 保持一致）
REGISTRY_RULES = {
    'T03', 'T07', 'T09', 'T10', 'T12', 
    'T19', 'T20', 'T30', 'T31', 'T32', 
    'T34', 'T41', 'T45', 'T47', 'T48'
}

def analyze_rule_correctly(rule_id, eval_dir):
    """正确分析规则的ASR"""
    
    if not eval_dir.exists():
        return None
    
    # 功能等价的样本
    func_equiv_total = 0
    func_equiv_llm_correct = 0  # adversarial_passed=True
    func_equiv_llm_wrong = 0    # adversarial_passed=False （攻击成功！）
    func_equiv_llm_none = 0     # adversarial_passed=None
    
    # 功能破坏的样本
    func_broken_total = 0
    func_broken_llm_correct = 0
    func_broken_llm_wrong = 0
    
    # 原始代码就错的样本
    orig_wrong_total = 0
    
    # 攻击成功样本
    attack_success_samples = []
    
    # LLM判断分布（功能等价）
    equiv_llm_says_yes = 0  # adversarial_code='YES'
    equiv_llm_says_no = 0   # adversarial_code='NO'
    
    for json_file in eval_dir.glob('*.json'):
        try:
            with open(json_file, 'r') as f:
                data = json.load(f)
            
            task_id = data.get('task_id')
            orig_truth = data.get('original_truth')
            adv_truth = data.get('adversarial_truth')
            adv_passed = data.get('adversarial_passed')
            adv_code = data.get('adversarial_code', '')
            adv_confidence = data.get('adversarial_confidence')
            
            # 原始代码错误
            if orig_truth != True:
                orig_wrong_total += 1
                continue
            
            # 功能等价
            if adv_truth == True:
                func_equiv_total += 1
                
                # 统计LLM说什么
                if adv_code == 'YES':
                    equiv_llm_says_yes += 1
                elif adv_code == 'NO':
                    equiv_llm_says_no += 1
                
                # 统计LLM判断是否正确
                if adv_passed == True:
                    func_equiv_llm_correct += 1
                elif adv_passed == False:
                    func_equiv_llm_wrong += 1
                    if len(attack_success_samples) < 20:
                        attack_success_samples.append({
                            'task_id': task_id,
                            'adv_code': adv_code,
                            'confidence': adv_confidence
                        })
                else:
                    func_equiv_llm_none += 1
            
            # 功能破坏
            elif adv_truth == False:
                func_broken_total += 1
                if adv_passed == True:
                    func_broken_llm_correct += 1
                elif adv_passed == False:
                    func_broken_llm_wrong += 1
        
        except Exception as e:
            continue
    
    # 计算ASR（假设original_passed=True）
    asr_denom = func_equiv_total  # 功能等价的样本
    asr_numer = func_equiv_llm_wrong  # LLM对抗判错
    asr = (asr_numer / asr_denom * 100) if asr_denom > 0 else None
    
    return {
        'rule_id': rule_id,
        
        # 功能等价
        'func_equiv_total': func_equiv_total,
        'func_equiv_llm_correct': func_equiv_llm_correct,
        'func_equiv_llm_wrong': func_equiv_llm_wrong,
        'func_equiv_llm_none': func_equiv_llm_none,
        'equiv_llm_says_yes': equiv_llm_says_yes,
        'equiv_llm_says_no': equiv_llm_says_no,
        
        # 功能破坏
        'func_broken_total': func_broken_total,
        'func_broken_llm_correct': func_broken_llm_correct,
        'func_broken_llm_wrong': func_broken_llm_wrong,
        
        # 原始错误
        'orig_wrong_total': orig_wrong_total,
        
        # ASR
        'asr_denom': asr_denom,
        'asr_numer': asr_numer,
        'asr': asr,
        
        # 样本
        'attack_success_samples': attack_success_samples
    }

def main():
    print("="*100)
    print("正确计算ASR（仅统计注册表中的15个规则）")
    print("="*100)
    print("\nASR定义：在功能等价的前提下，LLM被欺骗的比例")
    print("ASR = (功能等价 AND LLM对抗判错) / 功能等价")
    print("\n假设：LLM对所有原始代码都判对（original_passed=True）")
    print(f"\n统计规则：{sorted(REGISTRY_RULES)}\n")
    
    eval_base = Path('rule_eval/metrics_conf_v2_on_fullall_adv')
    
    # 获取所有规则，但只处理注册表中的规则
    all_rules = [d.name for d in eval_base.iterdir() if d.is_dir() and d.name.startswith('T')]
    rules = sorted([r for r in all_rules if r in REGISTRY_RULES])
    
    skipped_rules = sorted(set(all_rules) - REGISTRY_RULES)
    if skipped_rules:
        print(f"跳过未在注册表中的规则：{skipped_rules}")
    
    all_results = []
    
    for rule_id in rules:
        eval_dir = eval_base / rule_id / 'adv_eval'
        result = analyze_rule_correctly(rule_id, eval_dir)
        
        if result:
            all_results.append(result)
    
    # 按ASR排序
    all_results_with_asr = [r for r in all_results if r['asr'] is not None and r['asr'] > 0]
    all_results_with_asr.sort(key=lambda x: x['asr'], reverse=True)
    
    # 打印ASR排行
    print("="*100)
    print("ASR（攻击成功率）排行榜")
    print("="*100)
    print(f"\n{'规则':<8} {'功能等价':<10} {'LLM判对':<10} {'LLM判错':<10} {'ASR':<10} {'评级':<10}")
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
        
        print(f"{r['rule_id']:<8} {r['asr_denom']:<10} "
              f"{r['func_equiv_llm_correct']:<10} "
              f"{r['asr_numer']:<10} {r['asr']:>6.1f}%    {rating:<10}")
    
    # 零ASR规则
    zero_asr = [r for r in all_results if r['asr'] == 0]
    if zero_asr:
        print(f"\n零ASR规则: {len(zero_asr)} 个")
        print(f"  {', '.join([r['rule_id'] for r in zero_asr])}")
    
    # LLM判断详细分析
    print("\n" + "="*100)
    print("LLM判断详细分析（功能等价样本）")
    print("="*100)
    print(f"\n{'规则':<8} {'功能等价':<10} {'LLM说YES':<10} {'LLM说NO':<10} "
          f"{'判对':<10} {'判错':<10} {'ASR':<10}")
    print("-"*100)
    
    for r in all_results:
        if r['func_equiv_total'] > 0:
            print(f"{r['rule_id']:<8} {r['func_equiv_total']:<10} "
                  f"{r['equiv_llm_says_yes']:<10} {r['equiv_llm_says_no']:<10} "
                  f"{r['func_equiv_llm_correct']:<10} {r['func_equiv_llm_wrong']:<10} "
                  f"{r['asr'] if r['asr'] is not None else 0:>6.1f}%")
    
    # 攻击成功样本展示
    print("\n" + "="*100)
    print("攻击成功样本展示")
    print("="*100)
    
    for r in all_results_with_asr[:10]:
        if r['attack_success_samples']:
            print(f"\n{r['rule_id']} (ASR={r['asr']:.1f}%):")
            for i, s in enumerate(r['attack_success_samples'][:5], 1):
                print(f"  {i}. {s['task_id']}: LLM说\"{s['adv_code']}\", "
                      f"confidence={s['confidence']:.4f}")
    
    # 总体统计
    print("\n" + "="*100)
    print("总体统计")
    print("="*100)
    
    total_func_equiv = sum(r['func_equiv_total'] for r in all_results)
    total_func_equiv_correct = sum(r['func_equiv_llm_correct'] for r in all_results)
    total_func_equiv_wrong = sum(r['func_equiv_llm_wrong'] for r in all_results)
    total_func_broken = sum(r['func_broken_total'] for r in all_results)
    total_orig_wrong = sum(r['orig_wrong_total'] for r in all_results)
    
    overall_asr = (total_func_equiv_wrong / total_func_equiv * 100) if total_func_equiv > 0 else 0
    
    print(f"\n功能等价样本: {total_func_equiv:,}")
    print(f"  - LLM判对: {total_func_equiv_correct:,} ({total_func_equiv_correct/total_func_equiv*100:.1f}%)")
    print(f"  - LLM判错（攻击成功）: {total_func_equiv_wrong:,} ({total_func_equiv_wrong/total_func_equiv*100:.1f}%)")
    print(f"\n功能破坏样本: {total_func_broken:,}")
    print(f"原始代码错误: {total_orig_wrong:,}")
    print(f"\n总体ASR: {overall_asr:.2f}%")
    
    # 保存结果
    output_file = 'rule_eval/correct_asr_calculation.json'
    with open(output_file, 'w') as f:
        json.dump(all_results, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细结果已保存到: {output_file}")

if __name__ == '__main__':
    main()
