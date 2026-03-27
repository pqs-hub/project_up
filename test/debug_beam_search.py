#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试束搜索引擎 - 详细日志模式

这个脚本用于诊断束搜索引擎为什么没有真正执行
"""

import sys
import logging
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 设置 DEBUG 日志级别
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s'
)

from pipeline.adversarial_collector_v2 import AdversarialCollectorV2
from core.target_model import TargetModelClient
import json


def main():
    print("=" * 70)
    print("束搜索引擎调试 - 详细日志模式")
    print("=" * 70)
    
    # 初始化客户端
    print("\n[1/4] 初始化目标模型客户端...")
    target_client = TargetModelClient(
        base_url="http://localhost:8001/v1",
        api_key="EMPTY",
        model="Qwen/Qwen2.5-Coder-7B-Instruct",
        timeout=120
    )
    
    # 初始化收集器
    print("[2/4] 初始化束搜索收集器...")
    collector = AdversarialCollectorV2(
        target_model_client=target_client,
        beam_width=3,
        max_depth=3
    )
    
    # 载入数据集（使用修复后的版本）
    print("[3/4] 载入数据集...")
    dataset_path = PROJECT_ROOT / "data" / "single_rule_failed_samples_fixed.json"
    with open(dataset_path, 'r', encoding='utf-8') as f:
        samples = json.load(f)
    
    # 只处理第一个样本，详细观察
    sample = samples[0]
    print(f"\n[4/4] 处理样本: {sample['task_id']}")
    print(f"  初始置信度: {sample.get('judge_verdict', {}).get('confidence', 'N/A')}")
    print(f"  代码长度: {len(sample['canonical_solution'])} 字符")
    print(f"  Testbench 长度: {len(sample['test'])} 字符")
    
    print("\n" + "=" * 70)
    print("开始束搜索（详细日志）...")
    print("=" * 70 + "\n")
    
    # 运行束搜索
    results = collector.process_sample(sample)
    
    print("\n" + "=" * 70)
    print("调试完成")
    print("=" * 70)
    print(f"\n结果: {len(results)} 个成功的攻击路径")
    
    if results:
        print("\n成功!")
        for i, r in enumerate(results, 1):
            print(f"  路径 {i}:")
            print(f"    深度: {r['search_depth']}")
            print(f"    规则链: {' → '.join([s['rule'] for s in r['attack_chain']])}")
    else:
        print("\n未找到成功的攻击路径")
        print("\n可能的原因:")
        print("  1. 探测动作返回空（检查 '_probe_valid_actions' 日志）")
        print("  2. 变换执行失败（检查 '_execute_step' 日志）")
        print("  3. TB 验证失败（检查 iverilog 相关日志）")
        print("  4. 模型服务未响应（检查 HTTP 请求日志）")


if __name__ == "__main__":
    main()
