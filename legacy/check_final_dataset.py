#!/usr/bin/env python3
"""最终检查数据集参数"""

import json

def check_dataset(path, name):
    print(f"\n{'='*80}")
    print(f"检查: {name}")
    print(f"文件: {path}")
    print('='*80)
    
    with_params = 0
    without_params = 0
    param_examples = {}
    
    with open(path, 'r') as f:
        for i, line in enumerate(f):
            if i >= 200:  # 只检查前200个
                break
            
            sample = json.loads(line)
            output = sample['output']
            
            try:
                json_start = output.find('```json\n') + 8
                json_end = output.find('\n```', json_start)
                attack_config = json.loads(output[json_start:json_end])
                
                attack_name = attack_config.get('attack_name')
                has_params = 'parameters' in attack_config and attack_config['parameters']
                
                if has_params:
                    with_params += 1
                    if attack_name not in param_examples:
                        param_examples[attack_name] = attack_config
                else:
                    without_params += 1
            except Exception as e:
                pass
    
    print(f"\n统计（前200个样本）:")
    print(f"  有参数: {with_params}")
    print(f"  无参数: {without_params}")
    print(f"  有参数占比: {with_params / 200 * 100:.1f}%")
    
    print(f"\n参数示例（不同规则）:")
    for attack_name, config in sorted(param_examples.items())[:10]:
        print(f"\n  {attack_name}:")
        print(f"    target_line: {config.get('target_line')}")
        print(f"    target_signal: {config.get('target_signal')}")
        print(f"    parameters: {config.get('parameters')}")

# 检查现有数据集
check_dataset('data/sft_from_eval_highquality.jsonl', '现有数据集（参考）')

# 检查新生成的数据集
check_dataset('data/sft_attack_success_balanced.jsonl', '新生成平衡数据集 ⭐')

print(f"\n{'='*80}")
print("✅ 数据集参数检查完成")
print('='*80)
