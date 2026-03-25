#!/usr/bin/env python3
"""
Verilog混淆攻击框架 - 统一入口

完整流程:
1. 生成对抗样本（规则库调用 + 参数生成）
2. 构建SFT数据集
3. 训练模型（LoRA）
4. 合并LoRA权重
5. 评估模型（支持GPU选择、vLLM部署、CoT可选）
"""
import argparse
import sys
import subprocess
from pathlib import Path

def run_pipeline_step(script_path: Path, args: list):
    """运行pipeline步骤"""
    cmd = [sys.executable, str(script_path)] + args
    result = subprocess.run(cmd)
    return result.returncode

def main():
    parser = argparse.ArgumentParser(
        description="Verilog Obfuscation Attack Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例用法:

  # 生成对抗样本
  python main.py attack --input data/raw/verilog_eval.json --output data/attacks/

  # 构建SFT数据集
  python main.py build-sft --attacks data/attacks/ --output data/sft/obfuscation.jsonl

  # 训练模型
  python main.py train --dataset data/sft/obfuscation.jsonl \\
                       --base-model /path/to/model --gpus 0,3,4,5

  # 合并LoRA
  python main.py merge --lora models/checkpoints/obfuscation_lora \\
                       --base-model /path/to/model \\
                       --output models/merged/obfuscation_model

  # 评估模型
  python main.py eval --model models/merged/obfuscation_model \\
                      --eval-data data/eval/verilog_eval.json \\
                      --attack-gpus 0,1 --judge-gpus 2,3 --use-cot

  # 完整流程（暂未实现）
  python main.py full --config configs/pipeline.yaml
        """
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Pipeline步骤')
    
    # === Step 1: 生成对抗样本 ===
    parser_attack = subparsers.add_parser('attack', help='生成对抗样本')
    parser_attack.add_argument('--input', required=True, help='输入数据集')
    parser_attack.add_argument('--output', required=True, help='输出目录')
    parser_attack.add_argument('--rules', nargs='+', help='规则ID列表')
    parser_attack.add_argument('--max-samples', type=int, help='最大样本数')
    
    # === Step 2: 构建SFT数据集 ===
    parser_sft = subparsers.add_parser('build-sft', help='构建SFT数据集')
    parser_sft.add_argument('--attacks', required=True, help='攻击结果目录')
    parser_sft.add_argument('--output', required=True, help='输出SFT数据集')
    parser_sft.add_argument('--balance', action='store_true', help='平衡数据集')
    
    # === Step 3: 训练模型 ===
    parser_train = subparsers.add_parser('train', help='训练模型（LoRA）')
    parser_train.add_argument('--dataset', required=True, help='SFT数据集')
    parser_train.add_argument('--base-model', required=True, help='基础模型路径')
    parser_train.add_argument('--output', help='输出目录')
    parser_train.add_argument('--gpus', default='0,1,2,3', help='GPU编号')
    parser_train.add_argument('--config', help='训练配置文件（YAML）')
    
    # === Step 4: 合并LoRA ===
    parser_merge = subparsers.add_parser('merge', help='合并LoRA权重')
    parser_merge.add_argument('--lora', required=True, help='LoRA checkpoint路径')
    parser_merge.add_argument('--base-model', required=True, help='基础模型路径')
    parser_merge.add_argument('--output', required=True, help='输出目录')
    
    # === Step 5: 评估模型 ===
    parser_eval = subparsers.add_parser('eval', help='评估攻击模型')
    parser_eval.add_argument('--model', required=True, help='攻击模型路径')
    parser_eval.add_argument('--eval-data', required=True, help='评估数据集')
    parser_eval.add_argument('--attack-gpus', default='0', help='攻击模型GPU')
    parser_eval.add_argument('--judge-gpus', default='1', help='判断模型GPU')
    parser_eval.add_argument('--use-cot', action='store_true', help='判断模型使用CoT')
    parser_eval.add_argument('--max-samples', type=int, default=100, help='最大样本数')
    parser_eval.add_argument('--n-per-task', type=int, default=5, help='每个任务采样数')
    parser_eval.add_argument('--output', required=True, help='结果输出路径')
    
    # === 完整流程 ===
    parser_full = subparsers.add_parser('full', help='运行完整pipeline')
    parser_full.add_argument('--config', required=True, help='Pipeline配置文件（YAML）')
    
    # === GPU状态 ===
    parser_gpu = subparsers.add_parser('gpu', help='查看GPU状态')
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return 0
    
    # 执行对应命令
    project_root = Path(__file__).parent
    
    if args.command == 'attack':
        script = project_root / 'pipeline' / '1_generate_attacks.py'
        script_args = [
            '--input', args.input,
            '--output', args.output,
        ]
        if args.rules:
            script_args += ['--rules'] + args.rules
        if args.max_samples:
            script_args += ['--max-samples', str(args.max_samples)]
        return run_pipeline_step(script, script_args)
    
    elif args.command == 'build-sft':
        script = project_root / 'pipeline' / '2_build_sft_dataset.py'
        script_args = [
            '--attacks', args.attacks,
            '--output', args.output,
        ]
        if args.balance:
            script_args.append('--balance')
        return run_pipeline_step(script, script_args)
    
    elif args.command == 'train':
        script = project_root / 'pipeline' / '3_train_model.py'
        script_args = [
            '--dataset', args.dataset,
            '--base-model', args.base_model,
            '--gpus', args.gpus,
        ]
        if args.output:
            script_args += ['--output', args.output]
        if args.config:
            script_args += ['--config', args.config]
        return run_pipeline_step(script, script_args)
    
    elif args.command == 'merge':
        script = project_root / 'pipeline' / '4_merge_lora.py'
        script_args = [
            '--lora', args.lora,
            '--base-model', args.base_model,
            '--output', args.output,
        ]
        return run_pipeline_step(script, script_args)
    
    elif args.command == 'eval':
        script = project_root / 'pipeline' / '5_evaluate_model.py'
        script_args = [
            '--model', args.model,
            '--eval-file', args.eval_data,
            '--attack-base-url', f'http://localhost:8002/v1',  # 需要先启动vLLM
            '--max-samples', str(args.max_samples),
            '--n-per-task', str(args.n_per_task),
            '--output', args.output,
        ]
        # TODO: 自动启动vLLM服务
        print("提示: 评估前请先手动启动vLLM服务")
        print(f"  攻击模型: GPU {args.attack_gpus}, 端口 8002")
        print(f"  判断模型: GPU {args.judge_gpus}, 端口 8001")
        if args.use_cot:
            print(f"  判断模型使用 CoT")
        return run_pipeline_step(script, script_args)
    
    elif args.command == 'full':
        print("完整pipeline功能开发中...")
        return 1
    
    elif args.command == 'gpu':
        from utils.gpu_utils import print_gpu_status
        print_gpu_status()
        return 0
    
    else:
        parser.print_help()
        return 1

if __name__ == '__main__':
    sys.exit(main())
