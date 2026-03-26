#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
调试返回None的样本
"""

import sys
import json
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(PROJECT_ROOT))

def debug_none_sample():
    print("🔍 调试返回None的样本...")
    
    # 读取样本
    with open('data/qualified_dataset.json') as f:
        data = json.load(f)
    
    # 测试q000001（返回None的样本）
    sample = data[1]  # q000001
    task_id = sample.get('task_id', 'unknown')
    spec = sample.get('prompt', '')
    rtl = sample.get('canonical_solution', '')
    
    print(f"📝 样本ID: {task_id}")
    
    # 构建请求
    user_message = (
        f"[功能规范]\\n{spec}\\n\\n"
        f"[RTL代码]\\n```verilog\\n{rtl}\\n```\\n\\n"
        f"问题：该RTL代码是否正确实现了功能规范？\\n请逐步核对，最后一行必须是：FINAL_ANSWER: yes 或 FINAL_ANSWER: no"
    )
    
    system_prompt = "你是 Verilog 代码验证专家。请先进行简洁的逐步核对（接口、组合/时序行为、边界条件），然后在最后一行严格输出：FINAL_ANSWER: yes 或 FINAL_ANSWER: no。"
    
    payload = {
        "model": "qwen25_coder",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,
        "max_tokens": 256,
        "logprobs": True,
        "top_logprobs": 20,
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer EMPTY",
    }
    
    print("🚀 发送请求...")
    
    try:
        resp = requests.post(
            "http://localhost:8001/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        
        if resp.status_code != 200:
            print(f"❌ HTTP错误: {resp.status_code}")
            print(resp.text[:500])
            return
        
        data = resp.json()
        choice = (data.get("choices") or [None])[0]
        if not choice:
            print("❌ 没有choices")
            return
        
        content = ((choice.get("message") or {}).get("content") or "").strip()
        
        print(f"✅ 原始输出长度: {len(content)} 字符")
        print(f"📄 原始输出:")
        print("=" * 80)
        print(content)
        print("=" * 80)
        
        # 测试解析
        import re
        low = content.strip().lower()
        
        print(f"\n🔍 调试解析:")
        print(f"包含'final': {'final' in low}")
        print(f"包含'yes': {'yes' in low}")
        print(f"包含'no': {'no' in low}")
        
        # 查找所有可能的格式
        patterns = [
            r"final_answer\s*:\s*(yes|no)",
            r"final\s+answer\s*:\s*(yes|no)",
            r"final_answer\s*=\s*(yes|no)",
            r"\b(yes|no)\b"
        ]
        
        for pattern in patterns:
            m = re.search(pattern, low)
            if m:
                print(f"✅ 匹配模式 '{pattern}': {m.group(1)}")
            else:
                print(f"❌ 未匹配模式 '{pattern}'")
        
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    debug_none_sample()
