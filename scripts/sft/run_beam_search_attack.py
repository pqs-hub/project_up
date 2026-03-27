#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
束搜索攻击数据收集运行脚本

快速启动语义锚定束搜索攻击引擎，生成高质量的多规则攻击数据。
"""

import sys
import argparse
from pathlib import Path

# 添加项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.adversarial_collector_v2 import AdversarialCollectorV2, logger
from core.target_model import TargetModelClient
import json


def main():
    parser = argparse.ArgumentParser(description="束搜索攻击数据收集器")
    
    parser.add_argument("--dataset", type=str, required=True, help="输入数据集路径")
    parser.add_argument("--output", type=str, default="data/gold_multi_rule_attacks.json", help="输出路径")
    parser.add_argument("--limit", type=int, default=None, help="限制处理样本数")
    parser.add_argument("--confidence-threshold", type=float, default=0.8, help="置信度阈值")
    parser.add_argument("--beam-width", type=int, default=3, help="束搜索宽度")
    parser.add_argument("--max-depth", type=int, default=3, help="最大搜索深度")
    parser.add_argument("--base-url", type=str, default="http://localhost:8001/v1", help="模型 API URL")
    parser.add_argument("--model", type=str, default="Qwen/Qwen2.5-Coder-7B-Instruct", help="模型名称")
    parser.add_argument("--timeout", type=int, default=120, help="请求超时时间")
    parser.add_argument("--workers", type=int, default=1, help="并行 worker 数量")
    
    args = parser.parse_args()
    
    # 创建日志目录
    (PROJECT_ROOT / "logs").mkdir(exist_ok=True)
    
    # 初始化客户端和收集器
    logger.info("初始化目标模型客户端...")
    target_client = TargetModelClient(
        base_url=args.base_url,
        api_key="EMPTY",
        model=args.model,
        timeout=args.timeout
    )
    
    logger.info(f"初始化束搜索收集器 (宽度={args.beam_width}, 深度={args.max_depth})...")
    collector = AdversarialCollectorV2(
        target_model_client=target_client,
        beam_width=args.beam_width,
        max_depth=args.max_depth,
        max_workers=args.workers
    )
    
    # 载入数据集
    logger.info(f"载入数据集: {args.dataset}")
    with open(args.dataset, 'r', encoding='utf-8') as f:
        samples = json.load(f)
    logger.info(f"载入 {len(samples)} 个样本")
    
    # 过滤高置信度样本
    if samples and 'judge_verdict' in samples[0]:
        filtered = [s for s in samples if s.get('judge_verdict', {}).get('confidence', 0) > args.confidence_threshold]
        logger.info(f"过滤后得到 {len(filtered)} 个高置信度样本 (阈值 > {args.confidence_threshold})")
    else:
        filtered = samples
        logger.warning("数据集无 judge_verdict 字段，使用所有样本")
    
    if args.limit:
        filtered = filtered[:args.limit]
        logger.info(f"限制处理 {len(filtered)} 个样本")
    
    # 执行束搜索
    logger.info("=" * 60)
    logger.info("开始束搜索攻击数据收集...")
    logger.info("=" * 60)
    
    results = collector.process_dataset(filtered, save_path=Path(args.output))
    
    # 统计
    logger.info("=" * 60)
    logger.info(f"收集完成！成功攻击数: {len(results)}")
    logger.info(f"成功率: {len(results) / len(filtered) * 100:.2f}%")
    logger.info(f"结果保存至: {args.output}")
    
    depth_stats = {}
    for r in results:
        depth = r.get('search_depth', 0)
        depth_stats[depth] = depth_stats.get(depth, 0) + 1
    
    if depth_stats:
        logger.info("\n各深度成功攻击统计:")
        for depth in sorted(depth_stats.keys()):
            logger.info(f"  深度 {depth}: {depth_stats[depth]} 个")
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
