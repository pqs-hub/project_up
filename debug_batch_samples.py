#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量调试样本
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(PROJECT_ROOT))

from core.target_model import TargetModelClient

def test_batch_samples():
    print("🔍 批量调试样本...")
    
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
    
    # 测试前10个样本
    success_count = 0
    fail_count = 0
    none_count = 0
    
    for i, sample in enumerate(data[:10]):
        task_id = sample.get('task_id', 'unknown')
        spec = sample.get('prompt', '')
        rtl = sample.get('canonical_solution', '')
        
        print(f"\n📝 样本 {i+1}/10: {task_id}")
        
        try:
            result = client.judge(spec, rtl, use_cot=True)
            
            if result is None:
                print(f"❌ 返回None")
                none_count += 1
            elif result.get('is_correct'):
                print(f"✅ 判断为正确")
                success_count += 1
            else:
                print(f"❌ 判断为错误")
                fail_count += 1
                
        except Exception as e:
            print(f"💥 异常: {e}")
            fail_count += 1
    
    print(f"\n📊 统计结果:")
    print(f"✅ 成功: {success_count}")
    print(f"❌ 错误: {fail_count}")
    print(f"⚠️  None: {none_count}")

if __name__ == "__main__":
    test_batch_samples()
