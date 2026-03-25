#!/usr/bin/env python3
"""测试统一后的COT提示词"""

import sys
sys.path.insert(0, '/data3/pengqingsong/LLM_attack')

from taget_model import TargetModelClient

# 创建客户端
client = TargetModelClient(
    base_url="http://localhost:8000/v1",
    api_key="EMPTY",
    model="test-model"
)

# 测试spec和rtl
spec = "设计一个2选1多路选择器"
rtl = "module mux(input a, input b, input sel, output y); assign y = sel ? b : a; endmodule"

print("=" * 70)
print("统一后的COT提示词测试")
print("=" * 70)

print("\n【System Prompt (非COT)】")
print(client.system_prompt)
print("\n预期：只回答yes/no，不要其他内容")

print("\n" + "-" * 70)
print("【System Prompt (启用COT)】")
print(client.system_prompt_cot)
print("\n预期：允许推理，但最后一行必须是FINAL_ANSWER: yes/no")

print("\n" + "=" * 70)
print("【完整对话示例 - 非COT】")
print("=" * 70)
msg_no_cot = client._build_user_message(spec, rtl, use_cot=False)
print(f"System: {client.system_prompt}")
print(f"\nUser: {msg_no_cot}")
print("\n期望回复: yes")

print("\n" + "=" * 70)
print("【完整对话示例 - 启用COT】")
print("=" * 70)
msg_cot = client._build_user_message(spec, rtl, use_cot=True)
print(f"System: {client.system_prompt_cot}")
print(f"\nUser: {msg_cot}")
print("\n期望回复示例:")
print("1. 接口核对：输入a, b, sel，输出y - ✓")
print("2. 组合逻辑：sel=1时选b，sel=0时选a - ✓")
print("3. 边界条件：无特殊边界 - ✓")
print("\nFINAL_ANSWER: yes")

print("\n" + "=" * 60)
print("答案解析测试")
print("=" * 60)

test_cases = [
    ("yes", True),
    ("no", False),
    ("FINAL_ANSWER: yes", True),
    ("FINAL_ANSWER: no", False),
    ("经过核对，接口匹配，逻辑正确。\nFINAL_ANSWER: yes", True),
    ("接口不匹配，sel信号缺失。\nFINAL_ANSWER: no", False),
    ("1. 接口核对：✓\n2. 组合逻辑：✓\n3. 边界条件：✓\n\nFINAL_ANSWER: yes", True),
]

for text, expected in test_cases:
    result = client._extract_yes_no(text)
    status = "✓" if result == expected else "✗"
    print(f"{status} '{text[:50]}...' => {result} (期望: {expected})")

print("\n✅ COT提示词修改完成！")
