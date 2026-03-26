#!/usr/bin/env python3
"""
从 data/unflipped_orig_pass_subset/ 目录构建 verilog_eval.json 数据集
"""

import json
import os
from pathlib import Path

def build_eval_dataset():
    """构建评估数据集"""
    
    data_root = Path("/mnt/public/pqs/Veri_atack/project_up/data/unflipped_orig_pass_subset")
    output_path = Path("/mnt/public/pqs/Veri_atack/project_up/data/verilog_eval.json")
    
    if not data_root.exists():
        print(f"❌ 数据目录不存在: {data_root}")
        return
    
    # 获取所有RTL文件
    rtl_dir = data_root / "rtl"
    spec_dir = data_root / "spec" 
    test_dir = data_root / "testbench"
    
    rtl_files = list(rtl_dir.glob("*.v"))
    print(f"找到 {len(rtl_files)} 个RTL文件")
    
    eval_data = []
    
    for rtl_file in rtl_files[:50]:  # 先取50个文件作为测试
        task_id = rtl_file.stem
        
        # 对应的规范和测试台文件
        spec_file = spec_dir / f"{task_id}.txt"
        test_file = test_dir / f"{task_id}.v"
        
        if not spec_file.exists() or not test_file.exists():
            print(f"⚠️  跳过 {task_id}: 缺少规范或测试台文件")
            continue
            
        try:
            # 读取文件内容
            with open(rtl_file, 'r', encoding='utf-8') as f:
                rtl_code = f.read().strip()
            
            with open(spec_file, 'r', encoding='utf-8') as f:
                spec = f.read().strip()
                
            with open(test_file, 'r', encoding='utf-8') as f:
                test = f.read().strip()
            
            # 构建数据项
            eval_item = {
                "task_id": task_id,
                "prompt": spec,
                "canonical_solution": rtl_code,
                "test": test
            }
            
            eval_data.append(eval_item)
            print(f"✅ 添加 {task_id}")
            
        except Exception as e:
            print(f"❌ 处理 {task_id} 时出错: {e}")
    
    # 保存数据集
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(eval_data, f, ensure_ascii=False, indent=2)
    
    print(f"\n🎉 数据集构建完成！")
    print(f"📊 总样本数: {len(eval_data)}")
    print(f"💾 输出文件: {output_path}")

if __name__ == "__main__":
    build_eval_dataset()
