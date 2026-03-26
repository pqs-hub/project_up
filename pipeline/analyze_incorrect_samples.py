#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
分析被判为错误的样本
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import json
import random
from core.target_model import TargetModelClient


def analyze_incorrect_samples(
    input_file: str,
    judge_base_url: str,
    judge_model: str,
    num_samples: int = 10
):
    """随机抽取样本进行详细分析"""
    
    # 创建判断模型客户端
    judge_client = TargetModelClient(
        base_url=judge_base_url,
        api_key="EMPTY",
        model=judge_model
    )
    
    # 读取数据
    print(f"📖 读取数据: {input_file}")
    with open(input_file) as f:
        data = json.load(f)
    
    # 随机抽样
    samples = random.sample(data, min(num_samples, len(data)))
    
    print(f"🎲 随机抽取 {len(samples)} 个样本进行分析")
    print()
    
    incorrect_samples = []
    
    for i, sample in enumerate(samples):
        task_id = sample.get('task_id', 'unknown')
        prompt = sample.get('prompt', '')
        code = sample.get('canonical_solution', '')
        
        print(f"=" * 80)
        print(f"样本 {i+1}/{len(samples)}: {task_id}")
        print(f"=" * 80)
        
        # 使用CoT判断
        verdict = judge_client.judge(prompt, code, use_cot=True)
        
        if verdict:
            is_correct = verdict.get('is_correct')
            confidence = verdict.get('confidence')
            cot_reasoning = verdict.get('raw_output', '')
            
            print(f"判断结果: {'✅ 正确' if is_correct else '❌ 错误'}")
            print(f"置信度: {confidence}")
            print()
            print(f"功能规范（前200字符）:")
            print(f"  {prompt[:200]}...")
            print()
            print(f"代码:")
            print("  " + "\n  ".join(code.split('\n')[:15]))
            if len(code.split('\n')) > 15:
                print("  ...")
            print()
            print(f"CoT推理过程:")
            print("  " + "\n  ".join(cot_reasoning.split('\n')))
            print()
            
            if not is_correct:
                incorrect_samples.append({
                    'task_id': task_id,
                    'confidence': confidence,
                    'prompt': prompt[:100],
                    'reasoning': cot_reasoning
                })
        else:
            print("⚠️  判断失败")
        
        print()
    
    # 总结
    print("=" * 80)
    print("📊 分析总结")
    print("=" * 80)
    print(f"抽样数量: {len(samples)}")
    print(f"判断为错误: {len(incorrect_samples)} ({len(incorrect_samples)/len(samples)*100:.1f}%)")
    print()
    
    if incorrect_samples:
        print("被判为错误的样本:")
        for item in incorrect_samples:
            print(f"\n  - {item['task_id']} (置信度: {item['confidence']})")
            print(f"    {item['prompt']}...")
            print(f"    原因简述: {item['reasoning'].split('FINAL_ANSWER')[0][-200:]}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", default="data/qualified_dataset.json")
    parser.add_argument("--judge-base-url", default="http://localhost:8001/v1")
    parser.add_argument("--judge-model", default="qwen25_coder")
    parser.add_argument("--num-samples", type=int, default=10)
    
    args = parser.parse_args()
    
    analyze_incorrect_samples(
        input_file=args.input,
        judge_base_url=args.judge_base_url,
        judge_model=args.judge_model,
        num_samples=args.num_samples
    )
