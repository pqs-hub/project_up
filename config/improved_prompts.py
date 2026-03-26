#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
改进的攻击规则提示模板
"""

# 改进的T20 - 智能注释攻击
ATTACK_T20_IMPROVED_PROMPT_TEMPLATE = """Generate a misleading comment to replace existing comments

**Specification**: {task_prompt}

**Complete RTL Code**:
```verilog
{code_snippet}
```

**Target line to comment**: `{target_line}`

**Task**: Generate a misleading comment that contradicts the SPEC functionality. This comment will REPLACE all existing comments on this line.

**Analysis requirements**:
1. First understand what the SPEC requires
2. Understand what the target line actually does
3. Generate a comment that suggests WRONG functionality

**Misleading strategies**:
- If SPEC says "counter" → comment suggests "timer" or "delay"
- If SPEC says "adder" → comment suggests "multiplier" or "comparator"
- If SPEC says "active high reset" → comment suggests "active low"
- If SPEC says "input" → comment suggests "output"
- If SPEC says "synchronous" → comment suggests "asynchronous"

**Output requirements**:
1. Output comment text only (no // prefix, no quotes)
2. Professional and plausible (5-10 words)
3. Must contradict the SPEC

**Example**:
- SPEC: "4-bit adder"
- Target line: `assign sum = a + b;`
- Good output: `product of two 4-bit numbers`

Output comment text directly:"""

# 改进的T20 - 删除并替换注释的函数
IMPROVED_T20_ATTACK_CODE = """
def apply_improved_t20_attack(code, position, custom_text):
    \"\"\"应用改进的T20攻击：删除原有注释并插入误导性注释\"\"\"
    lines = code.split('\\n')
    
    # 找到目标行
    if position < len(lines):
        line = lines[position]
        
        # 删除该行所有原有注释
        # 查找 // 注释
        if '//' in line:
            # 保留 // 之前的部分
            line = line.split('//')[0].rstrip()
        
        # 查找 /* */ 注释
        if '/*' in line and '*/' in line:
            # 删除块注释
            before = line.split('/*')[0]
            after = line.split('*/')[1]
            line = before.rstrip() + after.lstrip()
        
        # 添加新的误导性注释
        lines[position] = line + '  // ' + custom_text
    
    return '\\n'.join(lines)
"""
