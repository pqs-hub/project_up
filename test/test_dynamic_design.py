#!/usr/bin/env python3
"""测试动态提取模块名的design_for_testbench函数"""

import sys
import json
import tempfile
import subprocess
from pathlib import Path

# 确保在项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 导入修复后的函数
import importlib.util
spec = importlib.util.spec_from_file_location("gen_module", project_root / "pipeline" / "6_generate_attack_dataset.py")
gen_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen_module)

design_for_testbench = gen_module.design_for_testbench

# 读取测试数据
with open('data/qualified_newcot_noconfidence.json') as f:
    data = json.load(f)

print("测试动态模块名提取...")
print("="*60)

# 测试几个不同的任务
test_tasks = [0, 10, 50, 100]  # 不同的任务索引

for idx in test_tasks:
    if idx >= len(data):
        break
        
    task = data[idx]
    task_id = task.get('task_id', '')
    rtl = task.get('canonical_solution', '')
    testbench = task.get('test', '')
    
    print(f"\n任务 {idx}: {task_id}")
    
    # 提取testbench期望的模块名
    import re
    dut_match = re.search(r'(\w+)\s+dut\s*\(', testbench)
    expected_name = dut_match.group(1) if dut_match else "未找到"
    
    print(f"  Testbench期望: {expected_name}")
    
    # 模拟一个简单的变换
    transformed = rtl.replace(";", "; // Modified")
    
    # 使用改进后的函数
    tb_design = design_for_testbench(rtl, transformed, testbench)
    
    # 验证模块名是否正确
    module_match = re.search(r'module\s+(\w+)\s*\(', tb_design)
    actual_name = module_match.group(1) if module_match else "未找到"
    
    print(f"  生成模块名: {actual_name}")
    print(f"  匹配: {'✅' if actual_name == expected_name else '❌'}")
    
    # 快速编译测试（只测试前2个）
    if idx < 2:
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)
            design_path = tmpdir_path / "design.v"
            tb_path = tmpdir_path / "tb.v"
            out_path = tmpdir_path / "sim.out"
            
            design_path.write_text(tb_design)
            tb_path.write_text(testbench)
            
            # 编译
            compile_cmd = ["iverilog", "-g2012", "-o", str(out_path), str(design_path), str(tb_path)]
            result = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=5)
            
            if result.returncode == 0:
                print(f"  编译: ✅")
            else:
                print(f"  编译: ❌ - {result.stderr[:100]}")

print("\n" + "="*60)
print("测试完成")
print("="*60)
