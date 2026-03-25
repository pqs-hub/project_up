#!/usr/bin/env python3
"""
SFT训练脚本 - 使用Hugging Face Transformers
训练Verilog代码混淆模型
"""

import argparse
import json
import os
from pathlib import Path
from typing import Dict, List

import torch
from transformers import (
    AutoTokenizer,
    AutoModelForCausalLM,
    TrainingArguments,
    Trainer,
    DataCollatorForLanguageModeling
)
from datasets import Dataset


def load_jsonl_dataset(file_path: str) -> List[Dict]:
    """加载JSONL格式的SFT数据集"""
    data = []
    with open(file_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                data.append(json.loads(line))
    return data


def format_instruction_prompt(sample: Dict) -> str:
    """
    格式化为instruction-following格式
    
    示例格式（Qwen/Alpaca风格）:
    <|im_start|>system
    {instruction}<|im_end|>
    <|im_start|>user
    {input}<|im_end|>
    <|im_start|>assistant
    {output}<|im_end|>
    """
    instruction = sample.get('instruction', '')
    input_text = sample.get('input', '')
    output_text = sample.get('output', '')
    
    # Qwen2.5格式
    prompt = f"""<|im_start|>system
{instruction}<|im_end|>
<|im_start|>user
{input_text}<|im_end|>
<|im_start|>assistant
{output_text}<|im_end|>"""
    
    return prompt


def prepare_dataset(data: List[Dict], tokenizer, max_length: int = 2048):
    """准备训练数据集"""
    
    def tokenize_function(examples):
        # 格式化prompt
        prompts = [format_instruction_prompt(ex) for ex in examples['data']]
        
        # Tokenize
        tokenized = tokenizer(
            prompts,
            max_length=max_length,
            truncation=True,
            padding=False,
            return_tensors=None
        )
        
        # 创建labels（与input_ids相同，用于causal LM训练）
        tokenized['labels'] = tokenized['input_ids'].copy()
        
        return tokenized
    
    # 转换为Hugging Face Dataset
    dataset = Dataset.from_dict({'data': data})
    tokenized_dataset = dataset.map(
        tokenize_function,
        batched=True,
        remove_columns=['data'],
        desc="Tokenizing dataset"
    )
    
    return tokenized_dataset


def main():
    parser = argparse.ArgumentParser(description='训练Verilog代码混淆SFT模型')
    
    # 数据参数
    parser.add_argument('--data', type=str, required=True,
                        help='训练数据路径（JSONL格式）')
    parser.add_argument('--max_length', type=int, default=2048,
                        help='最大序列长度')
    
    # 模型参数
    parser.add_argument('--model', type=str, 
                        default='Qwen/Qwen2.5-Coder-7B-Instruct',
                        help='基础模型名称或路径')
    parser.add_argument('--output_dir', type=str, 
                        default='./obfuscation_model',
                        help='模型输出目录')
    
    # 训练参数
    parser.add_argument('--epochs', type=int, default=3,
                        help='训练轮数')
    parser.add_argument('--batch_size', type=int, default=4,
                        help='每设备训练batch size')
    parser.add_argument('--gradient_accumulation_steps', type=int, default=4,
                        help='梯度累积步数')
    parser.add_argument('--learning_rate', type=float, default=2e-5,
                        help='学习率')
    parser.add_argument('--warmup_steps', type=int, default=100,
                        help='warmup步数')
    parser.add_argument('--logging_steps', type=int, default=10,
                        help='日志记录步数')
    parser.add_argument('--save_steps', type=int, default=500,
                        help='模型保存步数')
    
    # 其他参数
    parser.add_argument('--fp16', action='store_true',
                        help='使用FP16混合精度训练')
    parser.add_argument('--bf16', action='store_true',
                        help='使用BF16混合精度训练')
    
    args = parser.parse_args()
    
    print("="*80)
    print("SFT训练 - Verilog代码混淆模型")
    print("="*80)
    
    # 加载数据
    print(f"\n📂 加载数据: {args.data}")
    data = load_jsonl_dataset(args.data)
    print(f"✓ 加载了 {len(data)} 个训练样本")
    
    # 加载tokenizer
    print(f"\n🔧 加载tokenizer: {args.model}")
    tokenizer = AutoTokenizer.from_pretrained(
        args.model,
        trust_remote_code=True,
        padding_side='right'
    )
    
    # 设置pad_token（如果没有）
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    
    # 准备数据集
    print(f"\n📊 准备数据集...")
    train_dataset = prepare_dataset(data, tokenizer, args.max_length)
    print(f"✓ 数据集准备完成: {len(train_dataset)} 样本")
    
    # 加载模型
    print(f"\n🤖 加载模型: {args.model}")
    model = AutoModelForCausalLM.from_pretrained(
        args.model,
        trust_remote_code=True,
        torch_dtype=torch.bfloat16 if args.bf16 else (torch.float16 if args.fp16 else torch.float32),
        device_map='auto'
    )
    
    # 启用gradient checkpointing节省显存
    model.gradient_checkpointing_enable()
    
    # 训练参数
    print(f"\n⚙️  配置训练参数...")
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        warmup_steps=args.warmup_steps,
        logging_steps=args.logging_steps,
        save_steps=args.save_steps,
        save_total_limit=3,
        fp16=args.fp16,
        bf16=args.bf16,
        optim="adamw_torch",
        gradient_checkpointing=True,
        logging_dir=f"{args.output_dir}/logs",
        report_to="none",  # 不使用wandb等
        remove_unused_columns=False,
    )
    
    print(f"""
训练配置:
  - 输出目录: {args.output_dir}
  - 训练轮数: {args.epochs}
  - Batch size: {args.batch_size}
  - 梯度累积: {args.gradient_accumulation_steps}
  - 有效batch size: {args.batch_size * args.gradient_accumulation_steps}
  - 学习率: {args.learning_rate}
  - 最大长度: {args.max_length}
  - 混合精度: {'BF16' if args.bf16 else ('FP16' if args.fp16 else 'FP32')}
    """)
    
    # Data collator
    data_collator = DataCollatorForLanguageModeling(
        tokenizer=tokenizer,
        mlm=False  # Causal LM, not masked LM
    )
    
    # 创建Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        data_collator=data_collator,
    )
    
    # 开始训练
    print("\n🚀 开始训练...")
    print("="*80)
    trainer.train()
    
    # 保存最终模型
    print("\n💾 保存最终模型...")
    trainer.save_model(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    
    print(f"\n✅ 训练完成！模型保存在: {args.output_dir}")
    print("="*80)


if __name__ == '__main__':
    main()
