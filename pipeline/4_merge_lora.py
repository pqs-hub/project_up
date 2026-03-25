#!/usr/bin/env python3
"""
Step 4: 合并LoRA权重到基础模型

封装LLaMA-Factory导出流程
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

def run(args):
    """运行LoRA合并"""
    print("="*60)
    print("  Step 4: 合并LoRA权重")
    print("="*60)
    print()
    
    # 参数
    lora_path = Path(args.lora)
    base_model = Path(args.base_model)
    output_dir = Path(args.output)
    
    # 验证输入
    if not lora_path.exists():
        print(f"❌ LoRA checkpoint不存在: {lora_path}")
        return 1
    
    if not base_model.exists():
        print(f"❌ 基础模型不存在: {base_model}")
        return 1
    
    print(f"LoRA checkpoint: {lora_path}")
    print(f"基础模型: {base_model}")
    print(f"输出目录: {output_dir}")
    print()
    
    # 创建临时配置文件
    config_content = f"""### LoRA模型导出配置

### 基础模型
model_name_or_path: {base_model}
trust_remote_code: true

### LoRA适配器路径
adapter_name_or_path: {lora_path}

### 模板
template: qwen

### 微调类型
finetuning_type: lora

### 导出配置
export_dir: {output_dir}
export_size: 2
export_device: auto
export_legacy_format: false
"""
    
    temp_config = Path("/tmp/lora_export_config.yaml")
    temp_config.write_text(config_content)
    
    # 构建合并命令
    cmd = [
        "llamafactory-cli", "export",
        str(temp_config)
    ]
    
    # 运行合并
    try:
        print("开始合并LoRA权重...")
        print(f"命令: {' '.join(cmd)}")
        print()
        
        result = subprocess.run(
            cmd,
            check=True
        )
        
        print()
        print("="*60)
        print("  ✅ LoRA合并完成！")
        print("="*60)
        print(f"合并后的模型保存在: {output_dir}")
        
        # 清理临时配置
        temp_config.unlink()
        return 0
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 合并失败: {e}")
        if temp_config.exists():
            temp_config.unlink()
        return 1

def main():
    parser = argparse.ArgumentParser(description="合并LoRA权重到基础模型")
    parser.add_argument('--lora', required=True, help='LoRA checkpoint路径')
    parser.add_argument('--base-model', required=True, help='基础模型路径')
    parser.add_argument('--output', required=True, help='输出目录')
    
    args = parser.parse_args()
    sys.exit(run(args))

if __name__ == '__main__':
    main()
