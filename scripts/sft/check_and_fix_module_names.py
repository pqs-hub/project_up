#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查并修复数据集中 RTL 和 testbench 的模块名匹配问题
"""

import json
import re
from pathlib import Path


def extract_rtl_module_name(rtl_code: str) -> str:
    """提取 RTL 代码中的模块名"""
    match = re.search(r'module\s+(\w+)', rtl_code)
    return match.group(1) if match else None


def extract_tb_module_name(tb_code: str) -> str:
    """提取 testbench 中实例化的模块名"""
    # 匹配 module_name dut(...) 或 module_name uut(...) 等模式
    match = re.search(r'(\w+)\s+(?:dut|uut|inst|top|u1|u_\w+)\s*\(', tb_code)
    return match.group(1) if match else None


def fix_module_name(rtl_code: str, target_name: str = "top_module") -> str:
    """将 RTL 代码中的模块名统一改为 target_name"""
    # 替换 module 声明
    rtl_code = re.sub(r'module\s+\w+', f'module {target_name}', rtl_code)
    # 替换 endmodule 之前可能的模块名引用（如果有）
    return rtl_code


def fix_testbench(tb_code: str, target_name: str = "top_module") -> str:
    """将 testbench 中的模块实例化统一改为 target_name"""
    # 替换模块实例化
    tb_code = re.sub(
        r'(\w+)\s+(dut|uut|inst|top|u1|u_\w+)\s*\(',
        f'{target_name} \\2(',
        tb_code
    )
    return tb_code


def main():
    print("=" * 70)
    print("检查并修复 RTL 和 testbench 模块名匹配")
    print("=" * 70)
    
    # 读取数据集
    input_file = Path("data/single_rule_failed_samples.json")
    output_file = Path("data/single_rule_failed_samples_fixed.json")
    
    print(f"\n[1/4] 读取数据集: {input_file}")
    with open(input_file, 'r', encoding='utf-8') as f:
        samples = json.load(f)
    print(f"  总样本数: {len(samples)}")
    
    # 检查匹配情况
    print(f"\n[2/4] 检查模块名匹配情况...")
    mismatch_count = 0
    mismatch_samples = []
    
    for i, sample in enumerate(samples[:20], 1):  # 先检查前 20 个
        rtl_module = extract_rtl_module_name(sample['canonical_solution'])
        tb_module = extract_tb_module_name(sample['test'])
        
        if rtl_module != tb_module:
            mismatch_count += 1
            mismatch_samples.append(i - 1)
            if mismatch_count <= 5:  # 只显示前 5 个
                print(f"  样本 {i} ({sample['task_id']}):")
                print(f"    RTL: {rtl_module}")
                print(f"    TB:  {tb_module}")
                print(f"    ✗ 不匹配")
    
    print(f"\n  前 20 个样本中有 {mismatch_count} 个模块名不匹配")
    
    # 修复所有样本
    print(f"\n[3/4] 修复模块名...")
    target_module_name = "top_module"  # 统一使用 top_module
    
    fixed_samples = []
    fix_count = 0
    
    for sample in samples:
        rtl_module = extract_rtl_module_name(sample['canonical_solution'])
        tb_module = extract_tb_module_name(sample['test'])
        
        # 创建副本
        fixed_sample = sample.copy()
        
        # 如果模块名不一致，统一修复
        if rtl_module != target_module_name or tb_module != target_module_name:
            fixed_sample['canonical_solution'] = fix_module_name(
                sample['canonical_solution'], 
                target_module_name
            )
            fixed_sample['test'] = fix_testbench(
                sample['test'], 
                target_module_name
            )
            fix_count += 1
        
        fixed_samples.append(fixed_sample)
    
    print(f"  修复了 {fix_count} 个样本")
    
    # 验证修复
    print(f"\n[4/4] 验证修复结果...")
    verify_count = 0
    for i, sample in enumerate(fixed_samples[:20]):
        rtl_module = extract_rtl_module_name(sample['canonical_solution'])
        tb_module = extract_tb_module_name(sample['test'])
        if rtl_module == tb_module == target_module_name:
            verify_count += 1
    
    print(f"  前 20 个样本验证通过: {verify_count}/20")
    
    # 保存修复后的数据集
    print(f"\n保存修复后的数据集到: {output_file}")
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(fixed_samples, f, indent=2, ensure_ascii=False)
    
    print("\n" + "=" * 70)
    print("完成！")
    print("=" * 70)
    print(f"\n统计:")
    print(f"  总样本数: {len(samples)}")
    print(f"  修复样本数: {fix_count}")
    print(f"  输出文件: {output_file}")
    print(f"\n使用修复后的数据集:")
    print(f"  python scripts/sft/run_beam_search_attack.py \\")
    print(f"    --dataset {output_file} \\")
    print(f"    --output data/multi_rule_attacks.json \\")
    print(f"    --limit 10")


if __name__ == "__main__":
    main()
