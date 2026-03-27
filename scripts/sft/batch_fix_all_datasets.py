#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
批量修复所有数据集的 RTL 和 testbench 模块名匹配问题

这个脚本会：
1. 扫描 data/ 目录下所有 JSON 数据集
2. 检查每个样本的模块名是否匹配
3. 统一修复为 top_module
4. 保存修复后的数据集（添加 _fixed 后缀）
"""

import json
import re
from pathlib import Path
from typing import List, Dict, Any


def extract_rtl_module_name(rtl_code: str) -> str:
    """提取 RTL 代码中的模块名"""
    match = re.search(r'module\s+(\w+)', rtl_code)
    return match.group(1) if match else None


def extract_tb_module_name(tb_code: str) -> str:
    """提取 testbench 中实例化的模块名"""
    # 匹配各种实例化模式
    patterns = [
        r'(\w+)\s+(?:dut|uut|inst|top|u1|u_\w+)\s*\(',  # 标准实例化
        r'(\w+)\s+\w+\s*\(',  # 通用实例化
    ]
    for pattern in patterns:
        match = re.search(pattern, tb_code)
        if match:
            return match.group(1)
    return None


def fix_module_name(rtl_code: str, target_name: str = "top_module") -> str:
    """将 RTL 代码中的模块名统一改为 target_name"""
    # 替换 module 声明
    rtl_code = re.sub(r'module\s+\w+', f'module {target_name}', rtl_code, count=1)
    return rtl_code


def fix_testbench(tb_code: str, target_name: str = "top_module") -> str:
    """将 testbench 中的模块实例化统一改为 target_name"""
    # 替换模块实例化（更宽松的匹配）
    tb_code = re.sub(
        r'(\w+)\s+(dut|uut|inst|top|u1|u_\w+)\s*\(',
        f'{target_name} \\2(',
        tb_code
    )
    return tb_code


def process_dataset(
    input_path: Path, 
    output_path: Path,
    target_module: str = "top_module",
    max_check: int = 10
) -> Dict[str, Any]:
    """
    处理单个数据集文件
    
    Returns:
        统计信息字典
    """
    # 读取数据集
    with open(input_path, 'r', encoding='utf-8') as f:
        samples = json.load(f)
    
    if not isinstance(samples, list):
        return {"error": "Not a list format", "processed": 0}
    
    # 检查样本格式
    if not samples or 'canonical_solution' not in samples[0] or 'test' not in samples[0]:
        return {"error": "Missing required fields", "processed": 0}
    
    # 检查前几个样本
    mismatch_count = 0
    for sample in samples[:max_check]:
        rtl_module = extract_rtl_module_name(sample.get('canonical_solution', ''))
        tb_module = extract_tb_module_name(sample.get('test', ''))
        if rtl_module != tb_module:
            mismatch_count += 1
    
    # 修复所有样本
    fixed_samples = []
    fix_count = 0
    
    for sample in samples:
        rtl = sample.get('canonical_solution', '')
        tb = sample.get('test', '')
        
        if not rtl or not tb:
            fixed_samples.append(sample)
            continue
        
        rtl_module = extract_rtl_module_name(rtl)
        tb_module = extract_tb_module_name(tb)
        
        # 创建副本
        fixed_sample = sample.copy()
        
        # 如果模块名不一致，统一修复
        if rtl_module != target_module or tb_module != target_module:
            fixed_sample['canonical_solution'] = fix_module_name(rtl, target_module)
            fixed_sample['test'] = fix_testbench(tb, target_module)
            fix_count += 1
        
        fixed_samples.append(fixed_sample)
    
    # 验证修复
    verify_count = 0
    for sample in fixed_samples[:max_check]:
        rtl_module = extract_rtl_module_name(sample.get('canonical_solution', ''))
        tb_module = extract_tb_module_name(sample.get('test', ''))
        if rtl_module == tb_module == target_module:
            verify_count += 1
    
    # 保存修复后的数据集
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(fixed_samples, f, indent=2, ensure_ascii=False)
    
    return {
        "total": len(samples),
        "mismatch_found": mismatch_count,
        "fixed": fix_count,
        "verified": f"{verify_count}/{max_check}",
        "output": str(output_path)
    }


def main():
    print("=" * 80)
    print("批量修复所有数据集的模块名")
    print("=" * 80)
    
    data_dir = Path("data")
    
    # 定义要处理的数据集列表
    datasets_to_fix = [
        "qualified_newcot_noconfidence.json",
        "qualified_dataset.json",
        "verilog_eval.json",
        "verilog_eval_correct_only.json",
        "qualified_dataset_correct.json",
        "verilog_eval_cot_correct.json",
        "qualified_newcot_correct.json",
        "qualified_dataset_low_confidence.json",
    ]
    
    print(f"\n扫描数据集文件...")
    print(f"数据目录: {data_dir}")
    
    # 处理每个数据集
    results = []
    
    for dataset_name in datasets_to_fix:
        input_path = data_dir / dataset_name
        
        if not input_path.exists():
            print(f"\n⊘ 跳过 {dataset_name} (文件不存在)")
            continue
        
        # 生成输出文件名
        stem = input_path.stem
        if stem.endswith('_fixed'):
            print(f"\n⊘ 跳过 {dataset_name} (已经是修复版本)")
            continue
        
        output_path = data_dir / f"{stem}_fixed.json"
        
        print(f"\n处理 {dataset_name}...")
        print(f"  输入: {input_path}")
        print(f"  输出: {output_path}")
        
        try:
            stats = process_dataset(input_path, output_path)
            
            if "error" in stats:
                print(f"  ✗ 错误: {stats['error']}")
            else:
                print(f"  ✓ 完成")
                print(f"    总样本数: {stats['total']}")
                print(f"    发现不匹配: {stats['mismatch_found']}")
                print(f"    修复样本数: {stats['fixed']}")
                print(f"    验证通过: {stats['verified']}")
                
                results.append({
                    "dataset": dataset_name,
                    **stats
                })
        
        except Exception as e:
            print(f"  ✗ 处理失败: {e}")
    
    # 总结
    print("\n" + "=" * 80)
    print("批量修复完成")
    print("=" * 80)
    
    if results:
        print(f"\n成功处理 {len(results)} 个数据集:\n")
        for r in results:
            print(f"  ✓ {r['dataset']}")
            print(f"      修复: {r['fixed']}/{r['total']} 个样本")
        
        print(f"\n修复后的文件都添加了 '_fixed' 后缀")
        print(f"例如: qualified_dataset.json → qualified_dataset_fixed.json")
        
        print(f"\n使用修复后的数据集:")
        print(f"  python scripts/sft/run_beam_search_attack.py \\")
        print(f"    --dataset data/single_rule_failed_samples_fixed.json \\")
        print(f"    --output data/multi_rule_attacks.json")
    else:
        print("\n没有成功处理任何数据集")


if __name__ == "__main__":
    main()
