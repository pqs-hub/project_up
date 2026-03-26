#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试所有规则的位置参数支持（target_token, target_line, target_signal）
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.transforms import create_engine

# 测试用的简单Verilog代码
TEST_CODE = """
module test(
    input clk,
    input rst,
    input [7:0] data_in,
    output reg [7:0] data_out,
    output valid
);
    wire [7:0] temp;
    reg enable;
    
    assign temp = data_in & 8'hFF;
    assign valid = enable;
    
    always @(posedge clk) begin
        if (rst)
            data_out <= 8'h00;
        else
            data_out <= temp;
    end
    
    always @(*) begin
        enable = (data_in > 8'h10);
    end
endmodule
""".strip()


def test_rule(rule_id, test_name, **kwargs):
    """测试单个规则"""
    print(f"\n{'='*60}")
    print(f"测试 {rule_id} - {test_name}")
    print(f"参数: {kwargs}")
    print(f"{'='*60}")
    
    engine = create_engine()
    
    try:
        result = engine.apply_transform(TEST_CODE, rule_id, **kwargs)
        
        if result == TEST_CODE:
            print("⚠️  结果: 代码未变化（可能是正常的，取决于规则）")
            return False
        else:
            print("✅ 结果: 代码已变换")
            # 显示变化的部分（前200字符）
            if len(result) > len(TEST_CODE):
                print(f"   新增了 {len(result) - len(TEST_CODE)} 个字符")
            print(f"   预览: {result[:200]}...")
            return True
    except Exception as e:
        print(f"❌ 错误: {type(e).__name__}: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_all_rules():
    """测试所有修改过的规则"""
    results = {}
    
    # ===== T03 测试 =====
    print("\n" + "="*60)
    print("T03 - Redundant Logic")
    print("="*60)
    
    results['T03_token'] = test_rule('T03', 'target_token=0', 
        target_token=0, name_prefix="_tap_")
    
    results['T03_line'] = test_rule('T03', 'target_line=3 (clk端口)', 
        target_line=3, name_prefix="_mon_")
    
    results['T03_signal'] = test_rule('T03', 'target_signal=data_in', 
        target_signal="data_in", name_prefix="_check_")
    
    # ===== T07 测试 =====
    print("\n" + "="*60)
    print("T07 - Assign Reorder")
    print("="*60)
    
    results['T07_token'] = test_rule('T07', 'target_token=0', 
        target_token=0)
    
    results['T07_line'] = test_rule('T07', 'target_line=11 (temp赋值)', 
        target_line=11)
    
    results['T07_signal'] = test_rule('T07', 'target_signal=temp', 
        target_signal="temp")
    
    # ===== T19 测试 =====
    print("\n" + "="*60)
    print("T19 - Dead Code Injection")
    print("="*60)
    
    results['T19_token'] = test_rule('T19', 'target_token=0', 
        target_token=0, custom_dead_stmts="dummy = 1'b0;")
    
    results['T19_line'] = test_rule('T19', 'target_line=15 (第一个always后)', 
        target_line=15, custom_dead_stmts="flag = 1'b1;")
    
    # ===== T20 测试 =====
    print("\n" + "="*60)
    print("T20 - Misleading Comment")
    print("="*60)
    
    results['T20_token'] = test_rule('T20', 'target_token=0', 
        target_token=0, custom_text="Wrong description")
    
    results['T20_line'] = test_rule('T20', 'target_line=11', 
        target_line=11, custom_text="This is incorrect")
    
    # ===== T34 测试 =====
    print("\n" + "="*60)
    print("T34 - Internal Signal Rename")
    print("="*60)
    
    results['T34_token'] = test_rule('T34', 'target_token=0', 
        target_token=0, custom_map={"enable": "disable"})
    
    results['T34_line'] = test_rule('T34', 'target_line=9 (enable声明)', 
        target_line=9, custom_map={"enable": "inactive"})
    
    results['T34_signal'] = test_rule('T34', 'target_signal=enable', 
        target_signal="enable", custom_map={"enable": "busy"})
    
    # ===== T45 测试 =====
    print("\n" + "="*60)
    print("T45 - Pseudo Combinational Loop")
    print("="*60)
    
    results['T45_token'] = test_rule('T45', 'target_token=0', 
        target_token=0)
    
    results['T45_line'] = test_rule('T45', 'target_line=11', 
        target_line=11)
    
    results['T45_signal'] = test_rule('T45', 'target_signal=temp', 
        target_signal="temp")
    
    # ===== 测试其他规则是否仍然工作 =====
    print("\n" + "="*60)
    print("其他规则基本测试（确保没破坏）")
    print("="*60)
    
    # T09, T10, T12等使用装饰器的规则
    results['T09_basic'] = test_rule('T09', 'basic test', target_token=0)
    results['T12_basic'] = test_rule('T12', 'basic test', target_token=0, wire_name="cond_wire")
    results['T31_basic'] = test_rule('T31', 'basic test', target_token=0, wire_name="buf_wire")
    results['T32_basic'] = test_rule('T32', 'basic test', target_token=0, offset=2)
    
    # ===== 总结 =====
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed
    
    print(f"\n总测试数: {total}")
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败/未变化: {failed}")
    
    if failed > 0:
        print("\n失败的测试:")
        for test_name, result in results.items():
            if not result:
                print(f"  - {test_name}")
    
    print("\n详细结果:")
    for test_name, result in results.items():
        status = "✅" if result else "❌"
        print(f"  {status} {test_name}")
    
    return failed == 0


def test_position_resolution():
    """测试位置解析是否正确"""
    print("\n" + "="*60)
    print("位置解析测试")
    print("="*60)
    
    engine = create_engine()
    
    # 测试T19的候选位置数量
    try:
        candidates = engine.get_target_line_signal(TEST_CODE, 'T19')
        print(f"✅ T19候选位置数: {len(candidates)}")
        
        # 显示每个位置
        for idx, cand in enumerate(candidates):
            if hasattr(cand, 'start'):
                line = TEST_CODE[:cand.start].count('\n') + 1
                print(f"   位置{idx}: 行{line}")
    except Exception as e:
        print(f"❌ T19候选位置查询失败: {e}")
    
    # 测试T07的候选对数
    try:
        candidates = engine.get_target_line_signal(TEST_CODE, 'T07')
        print(f"✅ T07可交换assign对数: {len(candidates)}")
    except Exception as e:
        print(f"❌ T07候选查询失败: {e}")
    
    # 测试T03的候选端口数
    try:
        candidates = engine.get_target_line_signal(TEST_CODE, 'T03')
        print(f"✅ T03候选端口数: {len(candidates)}")
    except Exception as e:
        print(f"❌ T03候选查询失败: {e}")


if __name__ == "__main__":
    print("="*60)
    print("位置参数支持测试")
    print("="*60)
    print(f"\n测试代码:\n{TEST_CODE}\n")
    
    # 运行位置解析测试
    test_position_resolution()
    
    # 运行所有规则测试
    all_passed = test_all_rules()
    
    # 退出码
    sys.exit(0 if all_passed else 1)
