#!/usr/bin/env python3
"""测试改进的T20攻击效果"""

import sys
from pathlib import Path

# 确保在项目根目录
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from core.transforms import ast_flexible_comment

def test_improved_t20():
    """测试改进的T20攻击"""
    
    # 测试代码（带原有注释）
    code = """module RefModule(
    input clk,
    input rst,
    output reg [3:0] count  // 4-bit counter output
);

always @(posedge clk) begin
    if (rst) begin
        count <= 4'b0000;  // Reset to zero
    end else begin
        count <= {~count[0], count[3:1]};
    end
end

endmodule"""
    
    print("原始代码:")
    print(code)
    print("\n" + "="*50 + "\n")
    
    # 应用改进的T20攻击
    transformed = ast_flexible_comment(
        code,
        target_token=2,  # 第三个插入点（output reg行）
        custom_text="asynchronous reset, active low"
    )
    
    print("攻击后代码:")
    print(transformed)
    print("\n" + "="*50 + "\n")
    
    # 检查原有注释是否被删除
    if "4-bit counter output" in transformed:
        print("❌ 原有注释未被删除")
    else:
        print("✅ 原有注释已被删除")
    
    if "asynchronous reset, active low" in transformed:
        print("✅ 新的误导性注释已添加")
    else:
        print("❌ 新的误导性注释未添加")

if __name__ == "__main__":
    test_improved_t20()
