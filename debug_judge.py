#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试判断请求
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(PROJECT_ROOT))

from core.target_model import TargetModelClient

def test_judge():
    print("🔍 调试判断请求...")
    
    # 创建客户端
    client = TargetModelClient(
        base_url="http://localhost:8001/v1",
        api_key="EMPTY",
        model="qwen25_coder",
        timeout=120,
        max_retries=3
    )
    
    # 简单测试
    spec = "实现一个NOT门"
    rtl = """module RefModule(
    input in,
    output out
);
    assign out = ~in;
endmodule"""
    
    print("📝 测试规范:")
    print(spec)
    print("\n🔧 测试代码:")
    print(rtl)
    print("\n🚀 开始判断...")
    
    try:
        result = client.judge(spec, rtl, use_cot=True)
        print(f"✅ 判断成功: {result}")
    except Exception as e:
        print(f"❌ 判断失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_judge()
