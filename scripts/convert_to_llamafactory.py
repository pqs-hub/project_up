#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
将清洗后的SFT数据集转换为LLaMA-Factory的ShareGPT格式
"""

import json
import sys
from pathlib import Path


def convert_to_sharegpt(input_file: str, output_file: str, system_prompt: str = None):
    """
    转换为LLaMA-Factory的ShareGPT格式
    
    输入格式:
    {
        "instruction": "...",
        "input": "...",
        "output": "..."
    }
    
    输出格式:
    {
        "messages": [
            {"role": "system", "content": "..."},
            {"role": "user", "content": "..."},
            {"role": "assistant", "content": "..."}
        ]
    }
    """
    
    print(f"转换数据集: {input_file} -> {output_file}")
    
    if system_prompt is None:
        system_prompt = "你是一个Verilog代码混淆专家，能够选择合适的混淆规则来增加代码的AI理解难度，同时保持功能不变。"
    
    sharegpt_data = []
    
    with open(input_file, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            
            sample = json.loads(line)
            
            # 合并instruction和input（LlamaFactory中系统提示词和用户输入分离更清晰）
            user_content = f"{sample['instruction']}\n\n{sample['input']}"
            
            # 转换为ShareGPT格式
            messages = [
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": user_content
                },
                {
                    "role": "assistant",
                    "content": sample['output']
                }
            ]
            
            sharegpt_data.append({
                "messages": messages
            })
            
            if (i + 1) % 1000 == 0:
                print(f"  已处理 {i + 1} 个样本...")
    
    # 保存为JSON格式（不是JSONL）
    output_path = Path(output_file)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(sharegpt_data, f, ensure_ascii=False, indent=2)
    
    print(f"✅ 转换完成: {len(sharegpt_data)} 个样本")
    print(f"  输出文件: {output_file}")
    
    return len(sharegpt_data)


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("用法: python convert_to_llamafactory.py <输入JSONL> <输出JSON>")
        print("\n示例:")
        print("  python convert_to_llamafactory.py data/sft_attack_strategy_cleaned.jsonl data/llamafactory_attack_strategy.json")
        sys.exit(1)
    
    input_file = sys.argv[1]
    output_file = sys.argv[2]
    
    convert_to_sharegpt(input_file, output_file)
