#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试攻击规则名称和代码的双向映射
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

# 导入analyze脚本
import importlib.util
spec = importlib.util.spec_from_file_location(
    "analyze_module", 
    PROJECT_ROOT / "pipeline" / "7_analyze_attack_dataset.py"
)
analyze_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze_module)

RULE_NAME_MAPPING = analyze_module.RULE_NAME_MAPPING
RULE_CODE_MAPPING = analyze_module.RULE_CODE_MAPPING
get_rule_code = analyze_module.get_rule_code
get_rule_name = analyze_module.get_rule_name


def test_bidirectional_mapping():
    """测试双向映射"""
    print("=" * 70)
    print("攻击规则名称和代码的双向映射测试")
    print("=" * 70)
    
    # 测试所有规则的双向转换
    print("\n### 代码 -> 英文名称 -> 代码")
    print("-" * 70)
    all_passed = True
    for code, name in sorted(RULE_NAME_MAPPING.items()):
        # 正向转换
        converted_name = get_rule_name(code)
        # 反向转换
        converted_code = get_rule_code(name)
        
        # 验证双向转换一致性
        passed = (converted_name == name and converted_code == code)
        status = "✓" if passed else "✗"
        
        print(f"{status} {code} -> {name:35} -> {converted_code}")
        
        if not passed:
            all_passed = False
    
    print("-" * 70)
    if all_passed:
        print("✅ 所有映射测试通过！")
    else:
        print("❌ 部分映射测试失败！")
    
    # 测试反向映射字典的完整性
    print("\n### 映射表统计")
    print(f"正向映射（代码->名称）: {len(RULE_NAME_MAPPING)} 条")
    print(f"反向映射（名称->代码）: {len(RULE_CODE_MAPPING)} 条")
    
    # 显示反向映射表
    print("\n### 反向映射表（英文名称 -> 代码）")
    print("-" * 70)
    for name, code in sorted(RULE_CODE_MAPPING.items()):
        print(f"{name:35} -> {code}")
    print("-" * 70)
    
    return all_passed


def test_inference_scenario():
    """模拟推理场景：模型输出英文名称，需要转回代码执行"""
    print("\n" + "=" * 70)
    print("模拟推理场景")
    print("=" * 70)
    
    # 模拟模型输出
    model_outputs = [
        "Flexible Misleading Comment",
        "Pseudo Loop",
        "Redundant Logic",
        "Bitwidth Arithmetic",
        "Unknown Rule"  # 测试未知规则
    ]
    
    print("\n模型输出英文名称 -> 执行代码转换:")
    print("-" * 70)
    for output in model_outputs:
        code = get_rule_code(output)
        is_valid = code in RULE_NAME_MAPPING
        status = "✓" if is_valid else "⚠"
        print(f"{status} '{output}' -> '{code}' {'(有效)' if is_valid else '(未知规则)'}")
    print("-" * 70)


if __name__ == "__main__":
    # 运行测试
    success = test_bidirectional_mapping()
    test_inference_scenario()
    
    # 返回状态码
    sys.exit(0 if success else 1)
