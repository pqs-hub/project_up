#!/usr/bin/env python3
"""
分析高功能改变率规则的具体行为
"""

import os
import json

def analyze_rule_behavior(rule_id, eval_dir='rule_eval/metrics_conf_v2_on_fullall_adv'):
    """分析规则的具体行为"""
    
    adv_eval_dir = os.path.join(eval_dir, rule_id, 'adv_eval')
    
    if not os.path.exists(adv_eval_dir):
        print(f"规则 {rule_id} 的评估目录不存在")
        return
    
    # 读取前几个样本
    json_files = sorted([f for f in os.listdir(adv_eval_dir) if f.endswith('.json')])[:10]
    
    print(f"\n{'='*80}")
    print(f"规则 {rule_id} 样本分析")
    print(f"{'='*80}\n")
    
    function_changed = 0
    function_unchanged = 0
    
    for json_file in json_files:
        with open(os.path.join(adv_eval_dir, json_file), 'r') as f:
            data = json.load(f)
        
        original_truth = data.get('original_truth')
        adversarial_truth = data.get('adversarial_truth')
        
        if original_truth == True:
            if adversarial_truth == False:
                function_changed += 1
                status = "功能改变 ❌"
            else:
                function_unchanged += 1
                status = "功能不变 ✅"
            
            print(f"样本 {data['task_id']}: {status}")
            print(f"  original_truth: {original_truth}")
            print(f"  adversarial_truth: {adversarial_truth}")
            
            # 如果有代码，显示一部分
            if data.get('adversarial_code') and data['adversarial_code'] != 'YES':
                adv_code = data['adversarial_code']
                if len(adv_code) > 200:
                    print(f"  对抗代码片段: {adv_code[:200]}...")
                else:
                    print(f"  对抗代码: {adv_code}")
            print()
    
    print(f"\n前10个样本统计:")
    print(f"  功能改变: {function_changed}")
    print(f"  功能不变: {function_unchanged}")
    print(f"  改变率: {function_changed/(function_changed+function_unchanged)*100:.1f}%")

if __name__ == '__main__':
    # 分析高功能改变率的规则
    high_change_rules = ['T47', 'T38', 'T31', 'T11', 'T37']
    
    for rule in high_change_rules:
        analyze_rule_behavior(rule)
