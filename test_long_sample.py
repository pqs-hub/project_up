#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试长规范样本的CoT输出
"""

import sys
import json
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(PROJECT_ROOT))

def test_long_sample():
    print("🔍 测试长规范样本的CoT输出...")
    
    # 读取样本
    with open('data/qualified_dataset.json') as f:
        data = json.load(f)
    
    # 选择长规范样本
    sample = data[0]  # q000000 - 605字符
    task_id = sample.get('task_id', 'unknown')
    spec = sample.get('prompt', '')
    rtl = sample.get('canonical_solution', '')
    
    print(f"📝 样本ID: {task_id}")
    print(f"📏 规范长度: {len(spec)} 字符")
    print()
    
    # 构建CoT请求（带智能截断）
    if len(spec) > 800:
        spec_processed = spec[:400] + "..." + spec[-100:]
        print(f"✂️  规范被截断: {len(spec)} → {len(spec_processed)} 字符")
    else:
        spec_processed = spec
        print(f"📄 规范无需截断")
    
    user_message = (
        f"[功能规范]\\n{spec_processed}\\n\\n"
        f"[RTL代码]\\n```verilog\\n{rtl}\\n```\\n\\n"
        f"问题：该RTL代码是否正确实现了功能规范？\\n简述：接口、逻辑、边界。最后：FINAL_ANSWER: yes/no。"
    )
    
    system_prompt = "你是 Verilog 代码验证专家。请简洁核对：1.接口 2.逻辑 3.边界。最后一行输出：FINAL_ANSWER: yes/no。"
    
    payload = {
        "model": "qwen25_coder",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        "temperature": 0.0,
        "max_tokens": 2048,
        "logprobs": True,
        "top_logprobs": 20,
    }
    
    headers = {
        "Content-Type": "application/json",
        "Authorization": "Bearer EMPTY",
    }
    
    print("🚀 发送CoT请求...")
    
    try:
        resp = requests.post(
            "http://localhost:8001/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        
        if resp.status_code != 200:
            print(f"❌ HTTP错误: {resp.status_code}")
            return
        
        data = resp.json()
        choice = (data.get("choices") or [None])[0]
        if not choice:
            print("❌ 没有choices")
            return
        
        content = ((choice.get("message") or {}).get("content") or "").strip()
        
        print(f"✅ CoT输出长度: {len(content)} 字符")
        print()
        
        # 检查是否包含FINAL_ANSWER
        if "FINAL_ANSWER" in content:
            print("✅ 包含FINAL_ANSWER")
            # 提取答案
            import re
            m = re.search(r"FINAL_ANSWER:\s*(yes|no)", content)
            if m:
                print(f"🎯 判断结果: {m.group(1)}")
        else:
            print("❌ 不包含FINAL_ANSWER")
            print(f"📄 输出结尾: {content[-100:]}")
        
        print()
        print("📄 CoT输出:")
        print("=" * 80)
        print(content)
        print("=" * 80)
        
    except Exception as e:
        print(f"❌ 请求失败: {e}")

if __name__ == "__main__":
    test_long_sample()
