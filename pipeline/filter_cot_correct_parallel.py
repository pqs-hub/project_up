#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从qualified_dataset.json筛选出CoT判断为正确的样本（并行版本）
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import json
import argparse
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from core.target_model import TargetModelClient


def judge_sample(sample, judge_client):
    """判断单个样本并返回增强信息（重试直到成功）"""
    task_id = sample.get('task_id', 'unknown')
    prompt = sample.get('prompt', '')
    code = sample.get('canonical_solution', '')
    
    if not code:
        return None, 'no_code'
    
    max_retries = 10  # 最大重试次数
    retry_delay = 10  # 重试间隔（秒）
    
    for attempt in range(max_retries):
        try:
            verdict = judge_client.judge(prompt, code, use_cot=True)
            
            if verdict is None:
                print(f"⚠️  {task_id} | 判断失败，第{attempt+1}次重试...")
                if attempt < max_retries - 1:
                    import time
                    time.sleep(retry_delay)
                    continue
                else:
                    # 最后一次失败，抛出异常让外层处理
                    raise Exception("判断API连续失败")
            
            # 成功获得判断结果
            if verdict.get('is_correct'):
                # 判断为正确
                enriched_sample = sample.copy()
                enriched_sample['judge_verdict'] = {
                    'is_correct': verdict.get('is_correct'),
                    'confidence': verdict.get('confidence'),
                    'cot_reasoning': verdict.get('raw_output')
                }
                return enriched_sample, 'correct'
            else:
                # 判断为错误
                return None, 'incorrect'
        
        except Exception as e:
            print(f"❌ {task_id} | 异常: {e}，第{attempt+1}次重试...")
            if attempt < max_retries - 1:
                import time
                time.sleep(retry_delay)
                continue
            else:
                # 最后一次失败
                return None, f'exception: {e}'
    
    # 理论上不会到这里
    return None, 'max_retries_exceeded'


def filter_cot_correct_samples_parallel(
    input_file: str,
    output_file: str,
    judge_base_url: str,
    judge_model: str,
    max_samples: int = None,
    num_workers: int = 4
):
    """并行筛选CoT判断为正确的样本"""
    
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
    print(f"🚀 使用 {num_workers} 个并行worker")
    print()
    
    # 筛选样本
    correct_samples = []
    stats = {
        'total': len(data),
        'correct': 0,
        'incorrect': 0,
        'judge_failed': 0,
        'exception': 0
    }
    
    # 使用线程池并行处理
    with ThreadPoolExecutor(max_workers=num_workers) as executor:
        # 提交所有任务
        futures = {
            executor.submit(judge_sample, sample, judge_client): sample
            for sample in data
        }
        
        # 使用tqdm显示进度
        pbar = tqdm(
            as_completed(futures),
            total=len(futures),
            desc="筛选样本",
            unit="sample",
            ncols=100
        )
        
        for future in pbar:
            try:
                result, status = future.result()
                
                if status == 'correct' and result:
                    correct_samples.append(result)
                    stats['correct'] += 1
                elif status == 'incorrect':
                    stats['incorrect'] += 1
                elif status == 'judge_failed':
                    stats['judge_failed'] += 1
                elif status.startswith('exception'):
                    stats['exception'] += 1
                    sample = futures[future]
                    task_id = sample.get('task_id', 'unknown')
                    pbar.write(f"❌ {task_id} | {status}")
                
            except Exception as e:
                stats['exception'] += 1
                sample = futures[future]
                task_id = sample.get('task_id', 'unknown')
                pbar.write(f"❌ {task_id} | 处理异常: {e}")
            
            # 更新进度条统计
            valid_total = stats['correct'] + stats['incorrect']
            pbar.set_postfix({
                'ok': stats['correct'],
                'wrong': stats['incorrect'],
                'failed': stats['judge_failed'],
                'rate': f"{stats['correct']/valid_total*100:.1f}%" if valid_total > 0 else "0%"
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
    print(f"总样本数:          {stats['total']}")
    print(f"✅ 判断为正确:     {stats['correct']} ({stats['correct']/stats['total']*100:.1f}%)")
    print(f"❌ 判断为错误:     {stats['incorrect']} ({stats['incorrect']/stats['total']*100:.1f}%)")
    print(f"⚠️  API调用失败:   {stats['judge_failed']} ({stats['judge_failed']/stats['total']*100:.1f}%)")
    print(f"💥 异常错误:       {stats['exception']}")
    print()
    valid_total = stats['correct'] + stats['incorrect']
    if valid_total > 0:
        print(f"📈 有效样本中正确率: {stats['correct']/valid_total*100:.1f}% ({stats['correct']}/{valid_total})")
    print("=" * 60)
    
    return correct_samples, stats


def main():
    parser = argparse.ArgumentParser(
        description="从qualified_dataset.json筛选出CoT判断为正确的样本（并行版本）"
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
    parser.add_argument(
        "--num-workers",
        type=int,
        default=8,
        help="并行worker数量（建议=GPU数量×2）"
    )
    
    args = parser.parse_args()
    
    filter_cot_correct_samples_parallel(
        input_file=args.input,
        output_file=args.output,
        judge_base_url=args.judge_base_url,
        judge_model=args.judge_model,
        max_samples=args.max_samples,
        num_workers=args.num_workers
    )


if __name__ == "__main__":
    main()
