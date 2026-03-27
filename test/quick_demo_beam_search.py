#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
束搜索攻击引擎快速演示

这个脚本展示如何使用 AdversarialCollectorV2 对单个样本进行攻击
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.adversarial_collector_v2 import AdversarialCollectorV2
from core.target_model import TargetModelClient
import json


def create_demo_sample():
    """创建一个演示样本 - 简单的 4-bit 加法器"""
    return {
        "task_id": "demo_adder",
        "prompt": """Design a 4-bit adder module.
Module should have:
- Two 4-bit inputs: a, b
- One 4-bit output: sum
- One carry output: cout
Calculate sum = a + b""",
        
        "canonical_solution": """module top_module(
    input [3:0] a,
    input [3:0] b,
    output [3:0] sum,
    output cout
);
    assign {cout, sum} = a + b;
endmodule""",
        
        "test": """module testbench;
    reg [3:0] a, b;
    wire [3:0] sum;
    wire cout;
    
    top_module dut(a, b, sum, cout);
    
    initial begin
        // Test case 1: 0 + 0
        a = 4'd0; b = 4'd0; #10;
        if (sum !== 4'd0 || cout !== 0) $display("FAIL");
        
        // Test case 2: 5 + 3
        a = 4'd5; b = 4'd3; #10;
        if (sum !== 4'd8 || cout !== 0) $display("FAIL");
        
        // Test case 3: 15 + 1 (overflow)
        a = 4'd15; b = 4'd1; #10;
        if (sum !== 4'd0 || cout !== 1) $display("FAIL");
        
        // Test case 4: 8 + 8 (overflow)
        a = 4'd8; b = 4'd8; #10;
        if (sum !== 4'd0 || cout !== 1) $display("FAIL");
        
        $display("PASS");
        $finish;
    end
endmodule""",
        
        "judge_verdict": {
            "is_correct": True,
            "confidence": 0.95
        }
    }


def main():
    print("=" * 70)
    print("束搜索攻击引擎 - 快速演示")
    print("=" * 70)
    
    # 1. 创建演示样本
    print("\n[1/4] 创建演示样本...")
    sample = create_demo_sample()
    print(f"  任务: {sample['task_id']}")
    print(f"  原始置信度: {sample['judge_verdict']['confidence']}")
    
    # 2. 初始化目标模型客户端
    print("\n[2/4] 初始化目标模型客户端...")
    print("  注意: 需要先启动模型服务，例如:")
    print("  vllm serve Qwen/Qwen2.5-Coder-7B-Instruct --port 8001")
    
    target_client = TargetModelClient(
        base_url="http://localhost:8001/v1",
        api_key="EMPTY",
        model="Qwen/Qwen2.5-Coder-7B-Instruct",
        timeout=120
    )
    
    # 3. 创建束搜索收集器
    print("\n[3/4] 创建束搜索收集器...")
    collector = AdversarialCollectorV2(
        target_model_client=target_client,
        beam_width=3,    # 使用 3 个分支
        max_depth=3,     # 搜索 3 层深度
        max_workers=1    # 单线程处理
    )
    print("  配置: 宽度=3, 深度=3")
    
    # 4. 执行束搜索攻击
    print("\n[4/4] 执行束搜索攻击...")
    print("-" * 70)
    
    try:
        results = collector.process_sample(sample)
        
        print("-" * 70)
        print(f"\n攻击完成！找到 {len(results)} 条成功路径\n")
        
        if results:
            for i, result in enumerate(results, 1):
                print(f"路径 {i}:")
                print(f"  搜索深度: {result['search_depth']}")
                print(f"  置信度变化: {result['original_confidence']:.3f} → {result['final_confidence']:.3f}")
                print(f"  攻击链长度: {len(result['attack_chain'])} 步")
                print(f"  使用的规则: {' → '.join([s['rule'] for s in result['attack_chain']])}")
                print()
                
                # 显示攻击链详情
                print("  攻击链详情:")
                for j, step in enumerate(result['attack_chain'], 1):
                    print(f"    步骤 {j}: {step['rule']} @ line {step['line']}, signal '{step['signal']}'")
                print()
            
            # 保存结果
            output_file = PROJECT_ROOT / "test" / "output" / "demo_beam_search_result.json"
            output_file.parent.mkdir(parents=True, exist_ok=True)
            
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(results, f, indent=2, ensure_ascii=False)
            
            print(f"结果已保存到: {output_file}")
            
        else:
            print("未找到成功的攻击路径")
            print("可能的原因:")
            print("  1. 目标模型太强，难以欺骗")
            print("  2. 样本太简单，没有足够的攻击面")
            print("  3. 搜索深度/宽度不够")
            print("\n建议:")
            print("  - 增加 beam_width 和 max_depth")
            print("  - 尝试更复杂的样本")
            
    except Exception as e:
        print(f"\n错误: {e}")
        print("\n常见问题:")
        print("  1. 确保模型服务已启动 (http://localhost:8001)")
        print("  2. 确保安装了 iverilog (用于 testbench 验证)")
        print("  3. 检查网络连接和防火墙设置")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 70)
    print("演示完成")
    print("=" * 70)


if __name__ == "__main__":
    main()
