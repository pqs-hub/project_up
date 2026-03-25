#!/usr/bin/env python3
"""测试攻击场景应用"""

import sys
sys.path.insert(0, '/data3/pengqingsong/LLM_attack')

from ast_transforms_loader import load_ast_transforms

# 测试代码
test_code = """module test(input a, input b, input sel, output y);
    assign y = sel ? b : a;
endmodule"""

# 加载AST变换
ast_transforms = load_ast_transforms()

# 测试场景
scenario = {
    "description": "语义劫持（注释+重命名）",
    "rules": ["T20", "T34"],
    "params": [
        {"custom_text": "// UART Serial Communication Controller"},
        {"custom_map": {}, "fallback_prefix": "uart_"}
    ]
}

print("=" * 70)
print("攻击场景应用测试")
print("=" * 70)

print("\n【原始代码】")
print(test_code)

# 应用攻击
result = test_code
for rule_id, params in zip(scenario["rules"], scenario["params"]):
    transform = ast_transforms.AST_TRANSFORM_REGISTRY.get(rule_id)
    if transform:
        print(f"\n【应用规则 {rule_id}】")
        output = transform.apply_func(result, **params)
        # 处理元组返回值
        if isinstance(output, tuple):
            result = output[0]
        else:
            result = output
        print(result[:200] + "..." if len(result) > 200 else result)
    else:
        print(f"\n✗ 规则 {rule_id} 不存在")

print("\n" + "=" * 70)
if result != test_code:
    print("✅ 攻击场景应用成功！代码已被修改")
else:
    print("✗ 攻击场景未产生变化")
