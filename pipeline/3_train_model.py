#!/usr/bin/env python3
"""
Step 3: 使用SFT数据集训练模型（LoRA）

封装LLaMA-Factory训练流程
"""
import argparse
import os
import subprocess
import sys
from pathlib import Path

def run(args):
    """运行模型训练"""
    print("="*60)
    print("  Step 3: 训练模型（LoRA微调）")
    print("="*60)
    print()
    
    # 参数
    dataset = Path(args.dataset)
    base_model = Path(args.base_model)
    output_dir = Path(args.output) if args.output else Path("models/checkpoints/obfuscation_lora")
    gpus = args.gpus
    gpu_list = [gpu.strip() for gpu in gpus.split(',') if gpu.strip()]
    config_file = Path(args.config) if args.config else None
    
    # 验证输入
    if not dataset.exists():
        print(f"❌ 数据集不存在: {dataset}")
        return 1
    
    if not base_model.exists():
        print(f"❌ 基础模型不存在: {base_model}")
        return 1
    
    print(f"数据集: {dataset}")
    print(f"基础模型: {base_model}")
    print(f"输出目录: {output_dir}")
    print(f"使用GPU: {gpus}")
    print()
    
    # 设置环境变量
    env = os.environ.copy()
    env['CUDA_VISIBLE_DEVICES'] = gpus
    
    # 构建训练命令
    use_multi_gpu = len(gpu_list) > 1

    if config_file and config_file.exists():
        # 使用配置文件
        print(f"使用配置文件: {config_file}")
        if use_multi_gpu:
            cmd = [
                "torchrun",
                "--nproc_per_node", str(len(gpu_list)),
                "-m", "llamafactory.cli",
                "train",
                str(config_file.absolute())
            ]
        else:
            cmd = [
                "llamafactory-cli", "train",
                str(config_file.absolute())
            ]
    else:
        # 使用命令行参数（简化版）
        print("使用默认LoRA配置")
        llamafactory_dir = Path.home() / "finetune" / "LLaMA-Factory"
        if not llamafactory_dir.exists():
            llamafactory_dir = Path("/data3/pengqingsong/finetune/LLaMA-Factory")
        
        default_cfg = f"{llamafactory_dir}/configs/lora_config.yaml"
        if use_multi_gpu:
            cmd = [
                "torchrun",
                "--nproc_per_node", str(len(gpu_list)),
                "-m", "llamafactory.cli",
                "train",
                default_cfg
            ]
        else:
            cmd = [
                "llamafactory-cli", "train",
                default_cfg  # 需要预先配置
            ]
    
    # 创建输出目录
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 运行训练
    try:
        print("开始训练...")
        print(f"命令: {' '.join(cmd)}")
        print()
        
        result = subprocess.run(
            cmd,
            env=env,
            cwd=str(output_dir.parent),
            check=True
        )
        
        print()
        print("="*60)
        print("  ✅ 训练完成！")
        print("="*60)
        print(f"模型保存在: {output_dir}")
        return 0
        
    except subprocess.CalledProcessError as e:
        print(f"❌ 训练失败: {e}")
        return 1

def main():
    parser = argparse.ArgumentParser(description="训练对抗样本生成模型（LoRA）")
    parser.add_argument('--dataset', required=True, help='SFT数据集路径')
    parser.add_argument('--base-model', required=True, help='基础模型路径')
    parser.add_argument('--output', help='输出目录（默认: models/checkpoints/obfuscation_lora）')
    parser.add_argument('--gpus', default='0,1,2,3', help='使用的GPU编号')
    parser.add_argument('--config', help='训练配置文件（YAML）')
    
    args = parser.parse_args()
    sys.exit(run(args))

if __name__ == '__main__':
    main()
