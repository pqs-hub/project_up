#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从qualified_dataset.json筛选出CoT判断为正确的样本
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import json
import argparse
from tqdm import tqdm
from core.target_model import TargetModelClient


def filter_cot_correct_samples(
    input_file: str,
    output_file: str,
    judge_base_url: str,
    judge_model: str,
    max_samples: int = None
):
    """筛选CoT判断为正确的样本"""
    
    # 创建判断模型客户端
    judge_client = TargetModelClient(
        base_url=judge_base_url,
        api_key="EMPTY",
        model=judge_model,
        timeout=120,  # 增加到120秒
        max_retries=3  # 失败重试3次
    )
    
    # 读取数据
    print(f"📖 读取数据: {input_file}")
    with open(input_file) as f:
        data = json.load(f)
    
    if max_samples:
        data = data[:max_samples]
    
    print(f"✅ 加载了 {len(data)} 个样本")
    print()
    
    # 筛选样本
    correct_samples = []
    stats = {
        'total': len(data),
        'correct': 0,
        'incorrect': 0,
        'error': 0
    }
    
    pbar = tqdm(data, desc="筛选样本", unit="sample", ncols=100)
    
    for sample in pbar:
        task_id = sample.get('task_id', 'unknown')
        prompt = sample.get('prompt', '')
        code = sample.get('canonical_solution', '')
        
        if not code:
            stats['error'] += 1
            continue
        
        max_retries = 10
        retry_delay = 5
        
        for attempt in range(max_retries):
            try:
                # 使用CoT判断（现在已修复输出截断问题）
                verdict = judge_client.judge(prompt, code, use_cot=True)
                
                if verdict is None:
                    if attempt < max_retries - 1:
                        pbar.write(f"⚠️  {task_id} | 判断失败，第{attempt+1}次重试...")
                        import time
                        time.sleep(retry_delay)
                        continue
                    else:
                        stats['error'] += 1
                        pbar.write(f"❌ {task_id} | 判断最终失败")
                        break
                
                if verdict.get('is_correct'):
                    # 创建增强样本（包含判断信息）
                    enriched_sample = sample.copy()
                    enriched_sample['judge_verdict'] = {
                        'is_correct': verdict.get('is_correct'),
                        'confidence': verdict.get('confidence'),
                        'cot_reasoning': verdict.get('raw_output')  # CoT推理过程
                    }
                    correct_samples.append(enriched_sample)
                    stats['correct'] += 1
                    break
                else:
                    stats['incorrect'] += 1
                    break
            
            except Exception as e:
                if attempt < max_retries - 1:
                    pbar.write(f"❌ {task_id} | 异常: {e}，第{attempt+1}次重试...")
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    stats['error'] += 1
                    pbar.write(f"❌ {task_id} | 最终失败: {e}")
                    break
        
        # 更新进度条统计
        pbar.set_postfix({
            'correct': stats['correct'],
            'incorrect': stats['incorrect'],
            'error': stats['error']
        })
    
    pbar.close()
    
    # 保存结果
    print()
    print(f"💾 保存结果到: {output_file}")
    with open(output_file, 'w') as f:
        json.dump(correct_samples, f, indent=2, ensure_ascii=False)
    
    # 打印统计
    print()
    print("=" * 60)
    print("📊 筛选统计")
    print("=" * 60)
    print(f"总样本数:        {stats['total']}")
    print(f"CoT判断正确:     {stats['correct']} ({stats['correct']/stats['total']*100:.1f}%)")
    print(f"CoT判断错误:     {stats['incorrect']} ({stats['incorrect']/stats['total']*100:.1f}%)")
    print(f"判断失败:        {stats['error']}")
    print("=" * 60)
    
    return correct_samples, stats


def main():
    parser = argparse.ArgumentParser(
        description="从qualified_dataset.json筛选出CoT判断为正确的样本"
    )
    parser.add_argument(
        "--input",
        type=str,
        default="data/qualified_dataset.json",
        help="输入文件路径"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/verilog_eval_correct_only.json",
        help="输出文件路径"
    )
    parser.add_argument(
        "--judge-base-url",
        type=str,
        default="http://localhost:8001/v1",
        help="判断模型API地址"
    )
    parser.add_argument(
        "--judge-model",
        type=str,
        default="qwen25_coder",
        help="判断模型名称"
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="最大处理样本数（用于测试）"
    )
    
    args = parser.parse_args()
    
    filter_cot_correct_samples(
        input_file=args.input,
        output_file=args.output,
        judge_base_url=args.judge_base_url,
        judge_model=args.judge_model,
        max_samples=args.max_samples
    )


if __name__ == "__main__":
    main()
