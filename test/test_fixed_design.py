#!/usr/bin/env python3
"""测试修复后的design_for_testbench函数"""

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

task = data[0]
rtl = task.get('canonical_solution', '')
testbench = task.get('test', '')

print("测试修复后的design_for_testbench...")
print(f"原始RTL模块名: RefModule")
print(f"Testbench期望: sd_card_controller")
print()

# 模拟一个简单的变换（添加注释）
transformed = rtl.replace("response <= 1'b1;", "response <= 1'b1; // Modified")

# 使用修复后的函数
tb_design = design_for_testbench(rtl, transformed)

print("生成的testbench设计:")
print(tb_design[:300])
print("...")

# 测试编译
with tempfile.TemporaryDirectory() as tmpdir:
    tmpdir_path = Path(tmpdir)
    design_path = tmpdir_path / "design.v"
    tb_path = tmpdir_path / "tb.v"
    out_path = tmpdir_path / "sim.out"
    
    design_path.write_text(tb_design)
    tb_path.write_text(testbench)
    
    # 编译
    compile_cmd = ["iverilog", "-g2012", "-o", str(out_path), str(design_path), str(tb_path)]
    result = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=10)
    
    print(f"\n编译结果: {result.returncode}")
    if result.returncode == 0:
        print("✅ 编译成功！")
        
        # 运行仿真
        run_result = subprocess.run(["vvp", str(out_path)], capture_output=True, text=True, timeout=10)
        print(f"运行结果: {run_result.returncode}")
        
        if "Test passed" in run_result.stdout:
            print("✅ Testbench通过！")
        else:
            print("❌ Testbench失败")
            print(f"输出: {run_result.stdout[-500:]}")
    else:
        print("❌ 编译失败")
        print(f"错误: {result.stderr}")
        
print("\n" + "="*60)
print("测试完成")
print("="*60)
