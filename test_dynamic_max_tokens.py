#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试动态max_tokens功能
"""

import sys
import json
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(PROJECT_ROOT))

from core.target_model import TargetModelClient

def test_dynamic_max_tokens():
    print("🔍 测试动态max_tokens功能...")
    
    # 创建客户端
    client = TargetModelClient(
        base_url="http://localhost:8001/v1",
        api_key="EMPTY",
        model="qwen25_coder",
        timeout=120,
        max_retries=3
    )
    
    # 读取样本
    with open('data/qualified_dataset.json') as f:
        data = json.load(f)
    
    # 找几个不同长度的样本测试
    samples = [
        data[0],   # q000000 - 605字符
        data[1],   # q000001 - 380字符
        data[2],   # q000002 - 444字符
    ]
    
    for i, sample in enumerate(samples):
        task_id = sample.get('task_id', 'unknown')
        spec = sample.get('prompt', '')
        rtl = sample.get('canonical_solution', '')
        
        print(f"\n📝 样本 {i+1}: {task_id}")
        print(f"📏 规范长度: {len(spec)} 字符")
        print(f"📏 代码长度: {len(rtl)} 字符")
        
        try:
            result = client.judge(spec, rtl, use_cot=True)
            
            if result is None:
                print(f"❌ 返回None")
            elif result.get('is_correct'):
                print(f"✅ 判断为正确 (置信度: {result.get('confidence', 'N/A')})")
            else:
                print(f"❌ 判断为错误 (置信度: {result.get('confidence', 'N/A')})")
                
            # 显示CoT长度
            cot_output = result.get('raw_output', '') if result else ''
            print(f"📄 CoT输出长度: {len(cot_output)} 字符")
            
        except Exception as e:
            print(f"💥 异常: {e}")

if __name__ == "__main__":
    test_dynamic_max_tokens()
