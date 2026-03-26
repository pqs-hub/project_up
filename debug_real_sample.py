#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试真实样本
"""

import sys
import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(PROJECT_ROOT))

from core.target_model import TargetModelClient

def test_real_sample():
    print("🔍 调试真实样本...")
    
    # 创建客户端
    client = TargetModelClient(
        base_url="http://localhost:8001/v1",
        api_key="EMPTY",
        model="qwen25_coder",
        timeout=120,
        max_retries=3
    )
    
    # 读取真实样本
    with open('data/qualified_dataset.json') as f:
        data = json.load(f)
    
    sample = data[0]  # q000000
    task_id = sample.get('task_id', 'unknown')
    spec = sample.get('prompt', '')
    rtl = sample.get('canonical_solution', '')
    
    print(f"📝 样本ID: {task_id}")
    print(f"📏 规范长度: {len(spec)} 字符")
    print(f"📏 代码长度: {len(rtl)} 字符")
    print(f"📄 规范前200字符:")
    print(spec[:200] + "...")
    print(f"\n🔧 代码前200字符:")
    print(rtl[:200] + "...")
    print(f"\n🚀 开始判断...")
    
    try:
        result = client.judge(spec, rtl, use_cot=True)
        print(f"✅ 判断成功: {result}")
    except Exception as e:
        print(f"❌ 判断失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_real_sample()
