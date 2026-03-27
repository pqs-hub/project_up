#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
注册数据集到LlamaFactory

需要在LlamaFactory的data目录下创建dataset_info.json条目
"""

import json
import sys
from pathlib import Path


def register_dataset(
    llamafactory_path: str,
    dataset_name: str,
    dataset_file: str,
    description: str = ""
):
    """注册数据集到LlamaFactory"""
    
    llamafactory_path = Path(llamafactory_path)
    dataset_info_path = llamafactory_path / "data" / "dataset_info.json"
    
    # 读取现有配置
    if dataset_info_path.exists():
        with open(dataset_info_path, 'r', encoding='utf-8') as f:
            dataset_info = json.load(f)
    else:
        dataset_info = {}
    
    # 添加新数据集
    dataset_info[dataset_name] = {
        "file_name": str(dataset_file),
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
    
    # 保存
    with open(dataset_info_path, 'w', encoding='utf-8') as f:
        json.dump(dataset_info, f, indent=2, ensure_ascii=False)
    
    print(f"✅ 已注册数据集: {dataset_name}")
    print(f"  文件: {dataset_file}")
    print(f"  配置: {dataset_info_path}")
    
    return True


if __name__ == "__main__":
    print("="*70)
    print("注册Verilog攻击数据集到LlamaFactory")
    print("="*70)
    
    # 配置
    llamafactory_path = input("\n请输入LlamaFactory安装路径 [默认: ~/LLaMA-Factory]: ").strip()
    if not llamafactory_path:
        llamafactory_path = str(Path.home() / "LLaMA-Factory")
    
    llamafactory_path = Path(llamafactory_path).expanduser()
    
    if not llamafactory_path.exists():
        print(f"❌ 路径不存在: {llamafactory_path}")
        print("请先安装LlamaFactory或提供正确的路径")
        sys.exit(1)
    
    print(f"\nLlamaFactory路径: {llamafactory_path}")
    
    # 数据集配置
    project_root = Path(__file__).resolve().parents[1]
    dataset_file = project_root / "data" / "llamafactory_attack_strategy.json"
    
    if not dataset_file.exists():
        print(f"❌ 数据集文件不存在: {dataset_file}")
        print("请先运行转换脚本生成数据集")
        sys.exit(1)
    
    # 复制数据集到LlamaFactory的data目录
    target_data_dir = llamafactory_path / "data"
    target_data_dir.mkdir(exist_ok=True)
    
    target_file = target_data_dir / "verilog_attack_strategy.json"
    
    print(f"\n复制数据集文件...")
    print(f"  源: {dataset_file}")
    print(f"  目标: {target_file}")
    
    import shutil
    shutil.copy2(dataset_file, target_file)
    print("✅ 数据集文件已复制")
    
    # 注册数据集
    print(f"\n注册数据集到dataset_info.json...")
    register_dataset(
        llamafactory_path=llamafactory_path,
        dataset_name="verilog_attack_strategy",
        dataset_file="verilog_attack_strategy.json",
        description="Verilog代码混淆攻击策略数据集"
    )
    
    print("\n" + "="*70)
    print("✅ 所有步骤完成！")
    print("="*70)
    print("\n现在可以开始训练:")
    print(f"  cd {llamafactory_path}")
    print(f"  llamafactory-cli train {project_root}/configs/llamafactory/sft_attack_test.yaml")
