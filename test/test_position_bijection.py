#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
测试位置参数的双向转换一致性
验证: target_token ↔ (target_signal, target_line) 是一一对应的
"""
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.transforms import create_engine

# 测试代码（包含多种结构以触发所有规则）
TEST_CODE = """
module counter(
    input clk,
    input rst,
    input [7:0] data_in,
    input [1:0] mode,
    output reg [7:0] count,
    output reg [7:0] result,
    output valid
);
    wire [7:0] temp;
    wire [7:0] sum;
    wire is_equal;
    reg enable;
    
    assign temp = data_in & 8'hFF;
    assign valid = enable | 1'b0;
    assign sum = data_in + 8'h01;
    assign is_equal = (data_in == 8'hAA);
    
    always @(posedge clk) begin
        if (rst)
            count <= 8'h00;
        else
            count <= count + 1;
    end
    
    always @(*) begin
        case (mode)
            2'b00: result = 8'h00;
            2'b01: result = 8'h10;
            2'b10: result = 8'h20;
            default: result = 8'hFF;
        endcase
    end
endmodule
""".strip()


def test_bidirectional_conversion(rule_id, rule_name):
    """测试单个规则的双向转换一致性"""
    print(f"\n{'='*60}")
    print(f"测试 {rule_id} - {rule_name}")
    print(f"{'='*60}")
    
    engine = create_engine()
    
    try:
        # 获取候选列表（使用私有方法，仅用于测试）
        candidates = engine._get_candidates_for_transform(TEST_CODE, rule_id)
        
        if not candidates:
            print("⚠️  无候选位置，跳过")
            return True
        
        print(f"📊 候选数量: {len(candidates)}")
        
        # 测试每个候选位置的双向转换
        all_passed = True
        
        for idx in range(len(candidates)):
            target_obj = candidates[idx]
            
            # ===== 第一步：从target_token提取语义信息 =====
            extracted_signal = None
            extracted_line = None
            
            # 提取signal
            if hasattr(target_obj, 'name'):
                extracted_signal = target_obj.name
            elif hasattr(target_obj, 'lhs_name'):
                extracted_signal = target_obj.lhs_name
            
            # 提取line
            if hasattr(target_obj, 'start') and target_obj.start is not None:
                extracted_line = TEST_CODE[:target_obj.start].count('\n') + 1
            elif hasattr(target_obj, 'offset') and target_obj.offset is not None:
                extracted_line = TEST_CODE[:target_obj.offset].count('\n') + 1
            
            print(f"\n  候选 {idx}:")
            print(f"    target_token={idx}")
            print(f"    → target_signal={extracted_signal}")
            print(f"    → target_line={extracted_line}")
            
            # ===== 第二步：使用语义信息转换回target_token =====
            
            # 测试signal转换
            if extracted_signal:
                result1 = engine.apply_transform(TEST_CODE, rule_id, 
                    target_signal=extracted_signal)
                result2 = engine.apply_transform(TEST_CODE, rule_id, 
                    target_token=idx)
                
                if result1 == result2:
                    print(f"    ✅ target_signal='{extracted_signal}' → 结果一致")
                else:
                    print(f"    ❌ target_signal='{extracted_signal}' → 结果不一致！")
                    all_passed = False
            
            # 测试line转换
            if extracted_line:
                result1 = engine.apply_transform(TEST_CODE, rule_id, 
                    target_line=extracted_line)
                result2 = engine.apply_transform(TEST_CODE, rule_id, 
                    target_token=idx)
                
                if result1 == result2:
                    print(f"    ✅ target_line={extracted_line} → 结果一致")
                else:
                    print(f"    ❌ target_line={extracted_line} → 结果不一致！")
                    all_passed = False
        
        return all_passed
        
    except Exception as e:
        print(f"❌ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("="*60)
    print("位置参数双向转换一致性测试")
    print("="*60)
    print(f"\n测试目标：验证 target_token ↔ (target_signal, target_line)")
    print(f"测试代码:\n{TEST_CODE}\n")
    
    # 测试所有15个规则
    test_cases = [
        ('T03', 'Redundant Logic'),
        ('T07', 'Assign Reorder'),
        ('T09', 'DeMorgan AND'),
        ('T10', 'DeMorgan OR'),
        ('T12', 'Intermediate Signal'),
        ('T19', 'Dead Code Injection'),
        ('T20', 'Misleading Comment'),
        ('T30', 'Constant Identity'),
        ('T31', 'Simple Intermediate'),
        ('T32', 'Bitwidth Arithmetic'),
        ('T34', 'Internal Signal Rename'),
        ('T41', 'Case Reorder'),
        ('T45', 'Pseudo Comb Loop'),
        ('T47', 'Dataflow Shatter'),
        ('T48', 'Anti-Topological'),
    ]
    
    results = {}
    for rule_id, rule_name in test_cases:
        results[rule_id] = test_bidirectional_conversion(rule_id, rule_name)
    
    # 总结
    print("\n" + "="*60)
    print("测试总结")
    print("="*60)
    
    total = len(results)
    passed = sum(1 for v in results.values() if v)
    failed = total - passed
    
    print(f"\n总测试规则数: {total}")
    print(f"✅ 通过: {passed}")
    print(f"❌ 失败: {failed}")
    
    if failed > 0:
        print("\n失败的规则:")
        for rule_id, result in results.items():
            if not result:
                print(f"  - {rule_id}")
    
    print("\n详细结果:")
    for rule_id, result in results.items():
        status = "✅" if result else "❌"
        print(f"  {status} {rule_id}")
    
    if failed == 0:
        print("\n🎉 所有转换都是一致的！target_token ↔ (target_signal, target_line) 完美对应！")
    else:
        print("\n⚠️  存在转换不一致的情况，需要修复！")
    
    return failed == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
