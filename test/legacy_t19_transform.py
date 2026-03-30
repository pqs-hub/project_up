#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
旧框架的T19变换函数（仅在endmodule前插入）
用于对比评估攻击效果
"""
import re
from typing import Optional

# 7种固定的死代码模式
T19_FALSE_PATTERNS = [
    (
        "  always @(*) begin\n"
        "    if (1'b0) begin\n"
        "    end\n"
        "  end\n"
        "\n"
    ),
    (
        "  always @(*) begin\n"
        "    if (1'b0) ; else ;\n"
        "  end\n"
        "\n"
    ),
    (
        "  always @(*) case (1'b0)\n"
        "    1'b1: ;\n"
        "    default: ;\n"
        "  endcase\n"
        "\n"
    ),
    (
        "  always @(*) begin\n"
        "    if (1'b1) if (1'b0) ;\n"
        "  end\n"
        "\n"
    ),
    (
        "  initial begin\n"
        "    if (1'b0) ;\n"
        "  end\n"
        "\n"
    ),
    (
        "  always @(*) begin\n"
        "    case (1'b0)\n"
        "      1'b1: ;\n"
        "      default: ;\n"
        "    endcase\n"
        "  end\n"
        "\n"
    ),
    (
        "  always @(*) begin\n"
        "    if (1'b0) begin end else if (1'b0) begin end\n"
        "  end\n"
        "\n"
    ),
]


def legacy_t19_transform(
    code: str,
    target_token: Optional[int] = None,
    custom_dead_stmts: Optional[str] = None,
) -> str:
    """旧框架的T19变换：固定在endmodule前插入死代码
    
    Args:
        code: 原始Verilog代码
        target_token: 选择固定模式索引（0-6）
        custom_dead_stmts: LLM生成的自定义死代码语句
    
    Returns:
        变换后的代码
    """
    endmodule_m = re.search(r'\bendmodule\b', code)
    if not endmodule_m:
        return code
    
    insert_pos = endmodule_m.start()
    patterns = T19_FALSE_PATTERNS
    idx = 0 if target_token is None else 0
    if target_token is not None and 0 <= target_token < len(patterns):
        idx = target_token

    # 1) 优先使用自定义死代码语句（不可达分支包装）
    if custom_dead_stmts is not None:
        dead = str(custom_dead_stmts).strip()
        if dead:
            # 安全过滤：避免 LLM 生成外层结构关键字
            banned = ("always", "initial", "module", "endmodule")
            low = dead.lower()
            if any(b in low for b in banned):
                return code

            # 将自定义语句作为 if(1'b0) 分支内容插入
            indented_lines = []
            for line in dead.splitlines():
                line = line.rstrip()
                if not line:
                    continue
                indented_lines.append("      " + line)
            dead_body = "\n".join(indented_lines) if indented_lines else "      ;"

            false_block = (
                "  always @(*) begin\n"
                "    if (1'b0) begin\n"
                f"{dead_body}\n"
                "    end\n"
                "  end\n"
                "\n"
            )
            return code[:insert_pos] + false_block + code[insert_pos:]

    # 2) 否则回退到固定模板
    false_block = patterns[idx]
    
    return code[:insert_pos] + false_block + code[insert_pos:]
