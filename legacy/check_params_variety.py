#!/usr/bin/env python3
import json
from collections import defaultdict

# 检查不同规则的参数多样性
rule_params = defaultdict(set)
rule_samples = defaultdict(list)

with open('data/sft_attack_success_registry.jsonl', 'r') as f:
    for i, line in enumerate(f):
        sample = json.loads(line)
        output = sample['output']
        
        try:
            json_start = output.find('```json\n') + 8
            json_end = output.find('\n```', json_start)
            attack_config = json.loads(output[json_start:json_end])
            
            attack_name = attack_config.get('attack_name')
            params = attack_config.get('parameters', {})
            
            # 将参数转为可哈希的字符串
            params_str = json.dumps(params, sort_keys=True)
            rule_params[attack_name].add(params_str)
            
            if len(rule_samples[attack_name]) < 5:
                rule_samples[attack_name].append({
                    'index': i+1,
                    'params': params
                })
        except Exception as e:
            pass

print('各规则的参数多样性分析:')
print('='*80)

for rule in sorted(rule_params.keys()):
    unique_params = len(rule_params[rule])
    print(f'\n{rule}:')
    print(f'  独特参数组合数: {unique_params}')
    print(f'  示例参数:')
    for i, sample in enumerate(rule_samples[rule][:5], 1):
        print(f'    示例{i} (样本{sample["index"]}): {sample["params"]}')
