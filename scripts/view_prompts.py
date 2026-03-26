#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查看所有当前使用的Prompts"""

import sys
from pathlib import Path

# 添加项目根目录到路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from config.prompts import (
    JUDGE_SYSTEM_PROMPT,
    JUDGE_SYSTEM_PROMPT_COT,
    ATTACK_T19_DEAD_CODE_PROMPT_TEMPLATE,
    ATTACK_T20_COMMENT_PROMPT_TEMPLATE,
    ATTACK_T34_RENAME_PROMPT_TEMPLATE,
    LLM_PARAM_RULES,
)


def print_section(title, content, width=80):
    """打印一个章节"""
    print("=" * width)
    print(f" {title}")
    print("=" * width)
    print(content)
    print()


def main():
    print("\n" + "🎨 " * 20)
    print(" " * 20 + "Prompts配置查看器")
    print("🎨 " * 20 + "\n")
    
    # 判断模型Prompts
    print_section(
        "1️⃣  判断模型 - 非CoT模式",
        JUDGE_SYSTEM_PROMPT
    )
    
    print_section(
        "2️⃣  判断模型 - CoT模式",
        JUDGE_SYSTEM_PROMPT_COT
    )
    
    # 攻击规则Prompts
    print_section(
        "3️⃣  攻击规则 T19 - 死代码生成（专业版）",
        ATTACK_T19_DEAD_CODE_PROMPT_TEMPLATE
    )
    
    print_section(
        "4️⃣  攻击规则 T20 - 误导性注释（专业版）",
        ATTACK_T20_COMMENT_PROMPT_TEMPLATE
    )
    
    print_section(
        "5️⃣  攻击规则 T34 - 对抗性重命名（专业版）",
        ATTACK_T34_RENAME_PROMPT_TEMPLATE
    )
    
    # LLM参数规则配置
    print("=" * 80)
    print(" 6️⃣  LLM参数规则配置")
    print("=" * 80)
    for rule_id, config in LLM_PARAM_RULES.items():
        print(f"  {rule_id}:")
        print(f"    参数名: {config['param_name']}")
        print(f"    Prompt长度: {len(config['prompt_template'])} 字符")
    print()
    
    # 统计信息
    print("=" * 80)
    print(" 📊 统计信息")
    print("=" * 80)
    print(f"  判断模型Prompts: 2个")
    print(f"  攻击规则Prompts: {len(LLM_PARAM_RULES)}个")
    print(f"  总Prompt数: {2 + len(LLM_PARAM_RULES)}个")
    print()
    
    # 使用提示
    print("=" * 80)
    print(" 💡 使用提示")
    print("=" * 80)
    print("  • 修改Prompts: 编辑 config/prompts.py")
    print("  • 详细说明: 查看 config/README_prompts.md")
    print("  • 效果对比: python scripts/analyze_failures.py")
    print("=" * 80)
    print()


if __name__ == "__main__":
    main()
