#!/usr/bin/env python3
import json

# 检查新生成的数据集
print("检查新生成的数据集:")
print("="*80)

with_params = 0
without_params = 0

with open('data/sft_attack_success_registry.jsonl', 'r') as f:
    for i, line in enumerate(f):
        if i >= 200:
            break
        
        sample = json.loads(line)
        output = sample['output']
        
        try:
            json_start = output.find('```json\n') + 8
            json_end = output.find('\n```', json_start)
            attack_config = json.loads(output[json_start:json_end])
            
            if 'parameters' in attack_config and attack_config['parameters']:
                with_params += 1
                if with_params <= 10:
                    print(f"\n样本 {i+1} (有参数):")
                    print(f"  attack_name: {attack_config.get('attack_name')}")
                    print(f"  target_line: {attack_config.get('target_line')}")
                    print(f"  target_signal: {attack_config.get('target_signal')}")
                    print(f"  parameters: {attack_config.get('parameters')}")
            else:
                without_params += 1
                if without_params <= 3:
                    print(f"\n样本 {i+1} (无参数):")
                    print(f"  attack_name: {attack_config.get('attack_name')}")
                    print(f"  JSON: {json.dumps(attack_config, ensure_ascii=False)}")
        except Exception as e:
            print(f"解析样本 {i+1} 失败: {e}")

print(f"\n统计（前200个样本）:")
print(f"  有参数: {with_params}")
print(f"  无参数: {without_params}")
