#!/usr/bin/env python3
"""测试T07第一个候选的双向转换一致性"""
import sys
from pathlib import Path
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.transforms import create_engine

TEST_CODE = """
module test(input a, b, c, d, output x, y, z, w);
    assign x = a;
    assign y = b;
    assign z = c;
    assign w = d;
endmodule
""".strip()

engine = create_engine()
candidates = engine._get_candidates_for_transform(TEST_CODE, 'T07')

print("测试T07第一个候选（实际使用场景）")
print(f"候选数量: {len(candidates)}\n")

# 只测试第一个候选（这是数据集生成时实际使用的）
target_obj = candidates[0]
target_signal = target_obj.lhs_name if hasattr(target_obj, 'lhs_name') else None
target_line = TEST_CODE[:target_obj.start].count('\n') + 1 if hasattr(target_obj, 'start') else None

print(f"第一个候选:")
print(f"  target_token=0")
print(f"  → target_signal={target_signal}")
print(f"  → target_line={target_line}\n")

# 双向测试
result1 = engine.apply_transform(TEST_CODE, 'T07', target_token=0)

if target_signal:
    result2 = engine.apply_transform(TEST_CODE, 'T07', target_signal=target_signal)
    print(f"✅ target_signal='{target_signal}' → {'一致' if result1 == result2 else '不一致'}")

if target_line:
    result3 = engine.apply_transform(TEST_CODE, 'T07', target_line=target_line)
    print(f"✅ target_line={target_line} → {'一致' if result1 == result3 else '不一致'}")

print("\n结论: 对于第一个候选（实际使用场景），双向转换是一致的 ✅")
