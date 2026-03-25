#!/usr/bin/env python3
"""
将SFT数据集转换为LLaMA-Factory格式
"""

import json
from pathlib import Path


def convert_to_sharegpt_format(input_file: str, output_file: str):
    """
    转换为LLaMA-Factory的sharegpt格式
    
    输入格式 (Alpaca):
    {
        "instruction": "...",
        "input": "...",
        "output": "...",
        "history": []
    }
    
    输出格式 (ShareGPT):
    {
        "messages": [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ]
    }
    """
    
    print(f"转换数据集: {input_file} -> {output_file}")
    
    sharegpt_data = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            if not line.strip():
                continue
            
            sample = json.loads(line)
            
            # 转换为ShareGPT格式
            messages = [
                {
                    "role": "system",
                    "content": sample['instruction']
                },
                {
                    "role": "user",
                    "content": sample['input']
                },
                {
                    "role": "assistant",
                    "content": sample['output']
                }
            ]
            
            sharegpt_data.append({
                "messages": messages
            })
            
            if (i + 1) % 10000 == 0:
                print(f"  已处理 {i + 1} 个样本...")
    
    # 保存为JSON格式（不是JSONL）
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(sharegpt_data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ 转换完成: {len(sharegpt_data)} 个样本")
    print(f"  输出文件: {output_file}")
    
    return len(sharegpt_data)


def main():
    # 定义数据集
    datasets = {
        'obfuscation_balanced': {
            'input': 'data/sft_attack_success_balanced.jsonl',
            'output': '/data3/pengqingsong/finetune/LLaMA-Factory/data/obfuscation_balanced.json',
            'description': '平衡去重版本（推荐）'
        },
        'obfuscation_dedup': {
            'input': 'data/sft_attack_success_dedup.jsonl',
            'output': '/data3/pengqingsong/finetune/LLaMA-Factory/data/obfuscation_dedup.json',
            'description': '完全去重版本'
        },
        'obfuscation_full': {
            'input': 'data/sft_attack_success_registry.jsonl',
            'output': '/data3/pengqingsong/finetune/LLaMA-Factory/data/obfuscation_full.json',
            'description': '完整版本（有冲突）'
        }
    }
    
    print("="*80)
    print("转换数据集为LLaMA-Factory格式")
    print("="*80)
    
    dataset_info = {}
    
    for name, config in datasets.items():
        input_file = config['input']
        output_file = config['output']
        
        if not Path(input_file).exists():
            print(f"\n⚠️  跳过 {name}: 输入文件不存在")
            continue
        
        print(f"\n{config['description']}")
        count = convert_to_sharegpt_format(input_file, output_file)
        
        # 添加到dataset_info
        dataset_info[name] = {
            "file_name": Path(output_file).name,
            "formatting": "sharegpt",
            "columns": {
                "messages": "messages"
            },
            "tags": {
                "role_tag": "role",
                "content_tag": "content",
                "user_tag": "user",
                "assistant_tag": "assistant",
                "system_tag": "system"
            }
        }
    
    # 保存dataset_info配置
    dataset_info_path = '/data3/pengqingsong/finetune/LLaMA-Factory/data/obfuscation_datasets.json'
    with open(dataset_info_path, 'w', encoding='utf-8') as f:
        json.dump(dataset_info, f, ensure_ascii=False, indent=2)
    
    print("\n" + "="*80)
    print(f"✓ 所有数据集转换完成！")
    print(f"\nDataset配置已保存到: {dataset_info_path}")
    print("\n请将以下内容添加到 LLaMA-Factory/data/dataset_info.json:")
    print("-"*80)
    print(json.dumps(dataset_info, ensure_ascii=False, indent=2))
    print("-"*80)


if __name__ == '__main__':
    main()
