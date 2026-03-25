#!/usr/bin/env python3
"""
自动将数据集注册到LLaMA-Factory
"""

import json
from pathlib import Path


def register_datasets():
    """注册数据集到LLaMA-Factory的dataset_info.json"""
    
    # LLaMA-Factory的dataset_info.json路径
    dataset_info_path = Path('/data3/pengqingsong/finetune/LLaMA-Factory/data/dataset_info.json')
    
    # 新数据集配置路径
    new_datasets_path = Path('/data3/pengqingsong/finetune/LLaMA-Factory/data/obfuscation_datasets.json')
    
    print("="*80)
    print("注册数据集到LLaMA-Factory")
    print("="*80)
    
    # 读取现有配置
    print(f"\n📂 读取现有配置: {dataset_info_path}")
    with open(dataset_info_path, 'r', encoding='utf-8') as f:
        dataset_info = json.load(f)
    print(f"  现有数据集数量: {len(dataset_info)}")
    
    # 读取新数据集配置
    print(f"\n📂 读取新数据集配置: {new_datasets_path}")
    with open(new_datasets_path, 'r', encoding='utf-8') as f:
        new_datasets = json.load(f)
    print(f"  新数据集数量: {len(new_datasets)}")
    
    # 检查是否已存在
    existing = [name for name in new_datasets if name in dataset_info]
    if existing:
        print(f"\n⚠️  以下数据集已存在，将被覆盖:")
        for name in existing:
            print(f"  - {name}")
    
    # 合并配置
    print(f"\n🔄 合并配置...")
    dataset_info.update(new_datasets)
    
    # 保存
    print(f"\n💾 保存到: {dataset_info_path}")
    with open(dataset_info_path, 'w', encoding='utf-8') as f:
        json.dump(dataset_info, f, indent=2, ensure_ascii=False)
    
    print(f"\n✅ 注册完成！")
    print(f"  总数据集数量: {len(dataset_info)}")
    print(f"\n新注册的数据集:")
    for name in new_datasets:
        print(f"  - {name}")
    
    print("\n" + "="*80)
    print("可以开始训练了！")
    print("="*80)
    print("\n快速开始:")
    print("  cd /data3/pengqingsong/finetune/LLaMA-Factory")
    print("  llamafactory-cli train \\")
    print("      /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_test.yaml")
    print()


if __name__ == '__main__':
    register_datasets()
