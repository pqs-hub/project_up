#!/usr/bin/env python3
"""调试Testbench为什么失败"""

import sys
import json
from pathlib import Path
import tempfile

# 确保在项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.attack_engine import create_engine
from Testbench_valid import TestbenchRunner

# 读取一个测试任务
with open('data/qualified_newcot_noconfidence.json') as f:
    data = json.load(f)

task = data[0]
task_id = task.get('task_id', '')
spec = task.get('prompt', '')
rtl = task.get('canonical_solution', '')
testbench = task.get('test', '')

print(f"测试任务: {task_id}")
print(f"RTL长度: {len(rtl)}")
print(f"Testbench长度: {len(testbench)}")
print()

# 1. 检查testbench runner
tb_runner = TestbenchRunner()
print(f"Testbench available: {tb_runner.available}")
print(f"Simulator: {tb_runner.simulator}")
print()

# 2. 测试原始代码的testbench
print("测试原始代码的testbench...")
try:
    result = tb_runner.run(rtl, testbench)
    print(f"原始代码testbench结果:")
    print(f"  passed: {result.get('passed')}")
    print(f"  error: {result.get('error', 'None')}")
    if result.get('output'):
        print(f"  output: {result.get('output')[:200]}...")
except Exception as e:
    print(f"原始代码testbench错误: {e}")

print()

# 3. 测试一个简单的攻击
engine = create_engine()
try:
    candidates = engine._get_candidates_for_transform(rtl, 'T03')
    print(f"T03候选数: {len(candidates)}")
    
    if len(candidates) > 0:
        # 应用变换
        transformed = engine.apply_transform(rtl, 'T03', target_token=0)
        
        if transformed and transformed != rtl:
            print(f"✅ T03变换成功")
            print(f"变换后长度: {len(transformed)}")
            
            # 测试变换后代码的testbench
            print("\n测试变换后代码的testbench...")
            try:
                result = tb_runner.run(transformed, testbench)
                print(f"变换后代码testbench结果:")
                print(f"  passed: {result.get('passed')}")
                print(f"  error: {result.get('error', 'None')}")
                if result.get('output'):
                    print(f"  output: {result.get('output')[:200]}...")
            except Exception as e:
                print(f"变换后代码testbench错误: {e}")
        else:
            print(f"❌ T03变换失败")
    else:
        print(f"❌ T03没有候选")
        
except Exception as e:
    print(f"攻击测试错误: {e}")
    import traceback
    traceback.print_exc()

print("\n" + "="*60)
print("检查iverilog安装...")
print("="*60)

import subprocess
try:
    result = subprocess.run(["iverilog", "-V"], capture_output=True, text=True, timeout=5)
    print(f"iverilog版本: {result.stdout}")
    if result.stderr:
        print(f"iverilog错误: {result.stderr}")
except Exception as e:
    print(f"iverilog不可用: {e}")

print("\n" + "="*60)
print("手动测试一个简单Verilog...")
print("="*60)

# 创建一个简单的测试
simple_design = """
module simple_counter(
    input clk,
    input rst,
    output reg [3:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 4'b0;
        else
            count <= count + 1'b1;
    end
endmodule
"""

simple_tb = """
module tb();
    reg clk, rst;
    wire [3:0] count;
    
    simple_counter uut(.clk(clk), .rst(rst), .count(count));
    
    initial begin
        clk = 0;
        rst = 1;
        #10 rst = 0;
        #100;
        $display("Test passed");
        $finish;
    end
    
    always #5 clk = ~clk;
endmodule
"""

try:
    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        design_path = tmpdir_path / "design.v"
        tb_path = tmpdir_path / "tb.v"
        out_path = tmpdir_path / "sim.out"
        
        design_path.write_text(simple_design)
        tb_path.write_text(simple_tb)
        
        # 编译
        compile_cmd = ["iverilog", "-g2012", "-o", str(out_path), str(design_path), str(tb_path)]
        result = subprocess.run(compile_cmd, capture_output=True, text=True, timeout=10)
        
        print(f"编译结果: {result.returncode}")
        if result.stdout:
            print(f"编译输出: {result.stdout}")
        if result.stderr:
            print(f"编译错误: {result.stderr}")
        
        if result.returncode == 0:
            # 运行
            run_result = subprocess.run(["vvp", str(out_path)], capture_output=True, text=True, timeout=10)
            print(f"运行结果: {run_result.returncode}")
            print(f"运行输出: {run_result.stdout}")
            if run_result.stderr:
                print(f"运行错误: {run_result.stderr}")
                
except Exception as e:
    print(f"简单测试错误: {e}")
    import traceback
    traceback.print_exc()
