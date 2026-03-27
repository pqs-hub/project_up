#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
T19信号提取功能测试脚本
验证修复后的信号提取逻辑是否正常工作
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import json
import logging
import yaml
import importlib.util

# 动态导入包含数字的模块
spec = importlib.util.spec_from_file_location(
    "gen_module", 
    PROJECT_ROOT / "pipeline" / "6_generate_attack_dataset.py"
)
gen_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen_module)

AttackDatasetGenerator = gen_module.AttackDatasetGenerator
create_attack_client = gen_module.create_attack_client

from core.target_model import TargetModelClient
from Testbench_valid import TestbenchRunner

logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def test_signal_extraction():
    """测试T19的信号提取功能"""
    
    print("="*80)
    print("T19 信号提取功能测试")
    print("="*80)
    
    # 加载配置
    config_path = PROJECT_ROOT / "config.yaml"
    if not config_path.exists():
        config_path = PROJECT_ROOT / "configs" / "config.yaml"
    
    with open(config_path, 'r', encoding='utf-8') as f:
        config = yaml.safe_load(f)
    
    # 创建judge客户端（用于测试，可以是dummy）
    tm_cfg = config.get("judge_model", {})
    judge_client = TargetModelClient(
        base_url=tm_cfg.get("base_url", "http://localhost:8001/v1"),
        api_key=tm_cfg.get("api_key", "EMPTY"),
        model=tm_cfg.get("model", "Qwen2.5-Coder-7B"),
        timeout=tm_cfg.get("timeout", 60),
    )
    
    # 创建攻击模型客户端
    print("\n检查LLM服务器连接...")
    try:
        attack_client = create_attack_client(
            base_url="http://localhost:8002/v1",
            api_key="EMPTY",
            model="obfuscation_merged"
        )
        print("✅ LLM服务器连接成功")
    except Exception as e:
        print(f"⚠️  LLM服务器未启动或连接失败: {e}")
        print("将继续测试信号提取逻辑...")
        attack_client = None
    
    # 创建testbench runner
    tb_runner = TestbenchRunner(simulator="iverilog", timeout=30)
    
    # 创建生成器
    generator = AttackDatasetGenerator(
        judge_client=judge_client,
        attack_client=attack_client,
        tb_runner=tb_runner,
        enable_llm_params=True,
        use_cot=True
    )
    
    # 加载测试数据（只取前10个）
    eval_file = PROJECT_ROOT / "data" / "qualified_dataset.json"
    if not eval_file.exists():
        # 尝试从testbench_passed中加载
        eval_file = PROJECT_ROOT / "data" / "attack_dataset_testbench_passed.jsonl"
        if not eval_file.exists():
            print(f"❌ 测试数据不存在")
            return
        
        # 从JSONL加载
        data = []
        with open(eval_file, 'r', encoding='utf-8') as f:
            for line in f:
                if len(data) >= 10:
                    break
                sample = json.loads(line)
                # 转换格式为测试所需
                data.append({
                    'task_id': sample.get('task_id'),
                    'prompt': sample.get('prompt'),
                    'canonical_solution': sample.get('original_code')
                })
    else:
        with open(eval_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            data = data[:10]
    
    test_samples = data
    print(f"\n加载了 {len(test_samples)} 个测试样本")
    
    # 测试每个样本的信号提取
    stats = {
        'total': 0,
        'signal_extracted': 0,
        'signal_failed': 0,
        'writable_signals': [],
        'readable_signals': [],
        'llm_called': 0,
        'llm_success': 0,
        'llm_failed': 0,
    }
    
    print("\n" + "="*80)
    print("开始测试信号提取...")
    print("="*80)
    
    for idx, sample in enumerate(test_samples, 1):
        task_id = sample.get('task_id', f'test_{idx}')
        spec = sample.get('prompt', '')
        code = sample.get('canonical_solution', '')
        
        print(f"\n--- 样本 {idx}/{len(test_samples)}: {task_id} ---")
        print(f"代码长度: {len(code)} 字符")
        
        stats['total'] += 1
        
        # 测试信号提取
        import re
        
        # 提取可写信号
        writable = []
        for match in re.finditer(r'\breg\s+(?:\[[^\]]+\]\s*)?(\w+)', code):
            writable.append(match.group(1))
        
        # 提取可读信号
        readable = []
        for match in re.finditer(r'\binput\s+(?:wire\s+)?(?:\[[^\]]+\]\s*)?(\w+)', code):
            readable.append(match.group(1))
        readable.extend(writable)
        for match in re.finditer(r'\bwire\s+(?:\[[^\]]+\]\s*)?(\w+)\s*[;=]', code):
            readable.append(match.group(1))
        
        writable = list(set(writable))
        readable = list(set(readable))
        
        if writable:
            stats['signal_extracted'] += 1
            writable_str = ', '.join(writable[:10])
            readable_str = ', '.join(readable[:15])
            print(f"✅ 信号提取成功")
            print(f"   可写信号 ({len(writable)}): {writable_str}")
            print(f"   可读信号 ({len(readable)}): {readable_str}")
            
            stats['writable_signals'].append(len(writable))
            stats['readable_signals'].append(len(readable))
            
            # 如果LLM可用，测试LLM生成
            if attack_client:
                print(f"   正在调用LLM生成参数...")
                stats['llm_called'] += 1
                try:
                    llm_param = generator.generate_llm_param('T19', code, spec)
                    if llm_param:
                        stats['llm_success'] += 1
                        print(f"   ✅ LLM生成成功: {llm_param[:100]}")
                    else:
                        stats['llm_failed'] += 1
                        print(f"   ❌ LLM生成失败（返回None）")
                except Exception as e:
                    stats['llm_failed'] += 1
                    print(f"   ❌ LLM调用异常: {e}")
        else:
            stats['signal_failed'] += 1
            print(f"❌ 未找到可写信号")
    
    # 输出统计结果
    print("\n" + "="*80)
    print("测试结果统计")
    print("="*80)
    print(f"\n信号提取:")
    print(f"  总样本数: {stats['total']}")
    print(f"  ✅ 提取成功: {stats['signal_extracted']} ({stats['signal_extracted']/stats['total']*100:.1f}%)")
    print(f"  ❌ 提取失败: {stats['signal_failed']} ({stats['signal_failed']/stats['total']*100:.1f}%)")
    
    if stats['writable_signals']:
        avg_writable = sum(stats['writable_signals']) / len(stats['writable_signals'])
        avg_readable = sum(stats['readable_signals']) / len(stats['readable_signals'])
        print(f"\n信号数量统计:")
        print(f"  平均可写信号数: {avg_writable:.1f}")
        print(f"  平均可读信号数: {avg_readable:.1f}")
    
    if attack_client and stats['llm_called'] > 0:
        print(f"\nLLM生成测试:")
        print(f"  总调用次数: {stats['llm_called']}")
        print(f"  ✅ 生成成功: {stats['llm_success']} ({stats['llm_success']/stats['llm_called']*100:.1f}%)")
        print(f"  ❌ 生成失败: {stats['llm_failed']} ({stats['llm_failed']/stats['llm_called']*100:.1f}%)")
        
        print(f"\n📊 关键指标:")
        if stats['llm_called'] > 0:
            success_rate = stats['llm_success'] / stats['llm_called'] * 100
            print(f"  LLM参数生成成功率: {success_rate:.1f}%")
            
            if success_rate > 20:
                print(f"  ✅ 成功率达标！(目标 >20%)")
            else:
                print(f"  ⚠️  成功率偏低 (目标 >20%)")
    else:
        print(f"\n⚠️  未测试LLM生成（服务器未连接）")
        print(f"  提示: 启动LLM服务器后重新测试以验证完整功能")
    
    print("\n" + "="*80)
    print("✅ 测试完成！")
    print("="*80)
    
    return stats

if __name__ == "__main__":
    test_signal_extraction()
