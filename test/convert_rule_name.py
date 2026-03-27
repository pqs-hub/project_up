#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
规则名称转换工具

用法:
    python convert_rule_name.py T20
    python convert_rule_name.py "Flexible Misleading Comment"
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import importlib.util
spec = importlib.util.spec_from_file_location(
    "analyze_module", 
    PROJECT_ROOT / "pipeline" / "7_analyze_attack_dataset.py"
)
analyze_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(analyze_module)


def main():
    if len(sys.argv) < 2:
        print("用法:")
        print("  python convert_rule_name.py T20")
        print('  python convert_rule_name.py "Flexible Misleading Comment"')
        sys.exit(1)
    
    input_value = sys.argv[1]
    
    # 判断是代码还是名称
    if input_value.startswith('T') and len(input_value) <= 3:
        # 代码 -> 名称
        result = analyze_module.get_rule_name(input_value)
        if result == input_value:
            print(f"❌ 未找到规则代码: {input_value}")
        else:
            print(f"✅ {input_value} -> {result}")
    else:
        # 名称 -> 代码
        result = analyze_module.get_rule_code(input_value)
        if result == input_value:
            print(f"❌ 未找到规则名称: {input_value}")
        else:
            print(f"✅ {input_value} -> {result}")


if __name__ == "__main__":
    main()
