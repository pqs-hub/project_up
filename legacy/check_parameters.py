#!/usr/bin/env python3
"""检查数据集中的参数"""

import json
from pathlib import Path

def check_dataset_parameters(jsonl_path):
    """检查数据集中的参数"""
    
    print(f"检查数据集: {jsonl_path}")
    print("="*80)
    
    samples_with_params = []
    samples_without_params = []
    
    with open(jsonl_path, 'r') as f:
        for i, line in enumerate(f):
            if i >= 100:  # 只检查前100个
                break
            
            sample = json.loads(line)
            output = sample['output']
            
            try:
                json_start = output.find('```json\n') + 8
                json_end = output.find('\n```', json_start)
                attack_config = json.loads(output[json_start:json_end])
                
                if 'parameters' in attack_config and attack_config['parameters']:
                    samples_with_params.append({
                        'index': i+1,
                        'attack_name': attack_config.get('attack_name'),
                        'target_line': attack_config.get('target_line'),
                        'target_signal': attack_config.get('target_signal'),
                        'parameters': attack_config.get('parameters')
                    })
                else:
                    samples_without_params.append({
                        'index': i+1,
                        'attack_name': attack_config.get('attack_name')
                    })
            except Exception as e:
                print(f"解析样本 {i+1} 失败: {e}")
    
    print(f"\n统计（前100个样本）:")
    print(f"  有参数的样本: {len(samples_with_params)}")
    print(f"  无参数的样本: {len(samples_without_params)}")
    
    if samples_with_params:
        print(f"\n有参数的样本示例（前5个）:")
        for sample in samples_with_params[:5]:
            print(f"\n样本 {sample['index']}:")
            print(f"  attack_name: {sample['attack_name']}")
            print(f"  target_line: {sample['target_line']}")
            print(f"  target_signal: {sample['target_signal']}")
            print(f"  parameters: {sample['parameters']}")
    
    return samples_with_params, samples_without_params

if __name__ == '__main__':
    print("检查现有数据集:")
    check_dataset_parameters('data/sft_from_eval_highquality.jsonl')
    
    print("\n" + "="*80)
    print("\n检查新生成的数据集:")
    check_dataset_parameters('data/sft_attack_success_balanced.jsonl')
