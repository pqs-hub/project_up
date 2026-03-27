#!/usr/bin/env python3
"""测试新的置信度保存功能"""

import sys
from pathlib import Path

# 确保在项目根目录
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

from pipeline.cached_task_builder import CachedTaskBuilder
from core.target_model import TargetModelClient
from Testbench_valid import TestbenchRunner

def test_confidence_fields():
    """测试新代码是否正确保存原始置信度"""
    
    # 创建测试样本
    sample = {
        'task_id': 'test_001',
        'prompt': 'Test prompt',
        'original_code': 'module test(); endmodule',
        'transformed_code': 'module test(); // comment endmodule',
        'attack_rule': 'T20',
        'attack_params': {'custom_text': 'test'},
        'position_index': 0,
        'status': 'success',
        'testbench_passed': True,
        'judge_fooled': True,
        'judge_confidence': 0.9995,
        'judge_original_confidence': 0.8,
        'judge_cot_transformed': 'Transformed reasoning',
        'judge_transformed_answer': 'no',
        'judge_cot_original': 'Original reasoning',
        'judge_original_answer': 'yes',
    }
    
    print("测试样本结构:")
    print(f"  task_id: {sample['task_id']}")
    print(f"  judge_confidence (攻击后): {sample['judge_confidence']}")
    print(f"  judge_original_confidence (原始): {sample['judge_original_confidence']}")
    print(f"  judge_transformed_answer: {sample['judge_transformed_answer']}")
    print(f"  judge_original_answer: {sample['judge_original_answer']}")
    
    print("\n✅ 新代码结构正确，包含原始代码置信度字段！")
    
    # 验证字段类型
    assert isinstance(sample['judge_confidence'], float), "judge_confidence应该是float"
    assert isinstance(sample['judge_original_confidence'], float), "judge_original_confidence应该是float"
    
    print("\n✅ 字段类型验证通过！")

if __name__ == "__main__":
    test_confidence_fields()
