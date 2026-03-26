#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
查看CoT的完整输出过程
"""

import sys
import json
import requests
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[0]
sys.path.insert(0, str(PROJECT_ROOT))

def show_cot_output():
    print("🔍 查看CoT输出过程...")
    
    # 读取样本
    with open('data/qualified_dataset.json') as f:
        data = json.load(f)
    
    # 选择一个样本进行详细分析
    sample = data[1]  # q000001
    task_id = sample.get('task_id', 'unknown')
    spec = sample.get('prompt', '')
    rtl = sample.get('canonical_solution', '')
    
    print(f"📝 样本ID: {task_id}")
    print(f"📏 规范长度: {len(spec)} 字符")
    print(f"📏 代码长度: {len(rtl)} 字符")
    print()
    
    # 显示完整规范（前300字符）
    print("📄 功能规范（前300字符）:")
    print("=" * 80)
    print(spec[:300] + ("..." if len(spec) > 300 else ""))
    print("=" * 80)
    print()
    
    # 显示完整代码
    print("🔧 RTL代码:")
    print("=" * 80)
    print(rtl)
    print("=" * 80)
    print()
    
    # 构建CoT请求
    user_message = (
        f"[功能规范]\\n{spec}\\n\\n"
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
    print(f"📏 请求长度: {len(user_message)} 字符")
    print()
    
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
        
        print(f"✅ CoT输出长度: {len(content)} 字符")
        print()
        print("📄 CoT完整输出:")
        print("=" * 80)
        print(content)
        print("=" * 80)
        print()
        
        # 分析输出
        print("🔍 输出分析:")
        print(f"包含'FINAL_ANSWER': {'FINAL_ANSWER' in content}")
        print(f"包含'final_answer': {'final_answer' in content}")
        print(f"包含'yes': {'yes' in content}")
        print(f"包含'no': {'no' in content}")
        print()
        
        # 检查是否被截断
        if len(content) == 409:
            print("⚠️  输出被截断到409字符！")
            print("这是vLLM的硬编码限制。")
        
        # 尝试解析
        import re
        low = content.strip().lower()
        m = re.search(r"final_answer\s*:\s*(yes|no)", low)
        if m:
            print(f"✅ 解析成功: {m.group(1)}")
        else:
            print("❌ 解析失败：未找到FINAL_ANSWER格式")
            
            # 显示可能的结尾
            print(f"📄 输出结尾（最后50字符）:")
            print("=" * 50)
            print(content[-50:])
            print("=" * 50)
        
    except Exception as e:
        print(f"❌ 请求失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    show_cot_output()
