#!/usr/bin/env python3
"""测试原始代码置信度是否正确保存"""

import sys
from pathlib import Path

# 确保在项目根目录
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import json

def test_confidence_fields():
    """测试样本中是否包含原始代码置信度"""
    
    # 检查攻击成功文件
    attack_file = "data/attack_dataset_20260326_1746.jsonl"
    testbench_file = "data/attack_dataset_testbench_passed.jsonl"
    
    print("检查攻击成功样本...")
    if Path(attack_file).exists():
        with open(attack_file, 'r') as f:
            for i, line in enumerate(f):
                if i >= 3:  # 只检查前3个样本
                    break
                sample = json.loads(line)
                print(f"\n样本 {i+1}:")
                print(f"  task_id: {sample.get('task_id')}")
                print(f"  judge_confidence (攻击后): {sample.get('judge_confidence')}")
                print(f"  judge_original_confidence (原始): {sample.get('judge_original_confidence')}")
                
                if 'judge_original_confidence' not in sample:
                    print("  ❌ 缺少原始代码置信度！")
                else:
                    print("  ✅ 包含原始代码置信度")
    else:
        print(f"文件不存在: {attack_file}")
    
    print("\n检查testbench通过样本...")
    if Path(testbench_file).exists():
        with open(testbench_file, 'r') as f:
            for i, line in enumerate(f):
                if i >= 3:  # 只检查前3个样本
                    break
                sample = json.loads(line)
                print(f"\n样本 {i+1}:")
                print(f"  task_id: {sample.get('task_id')}")
                print(f"  judge_confidence (攻击后): {sample.get('judge_confidence')}")
                print(f"  judge_original_confidence (原始): {sample.get('judge_original_confidence')}")
                
                if 'judge_original_confidence' not in sample:
                    print("  ❌ 缺少原始代码置信度！")
                else:
                    print("  ✅ 包含原始代码置信度")
    else:
        print(f"文件不存在: {testbench_file}")

if __name__ == "__main__":
    test_confidence_fields()
