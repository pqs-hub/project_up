#!/usr/bin/env python3
"""测试双输出功能"""

import sys
import json
from pathlib import Path

# 确保在项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# 创建测试样本
test_samples = [
    {
        'task_id': 'test001',
        'status': 'success',
        'attack_rule': 'T03',
        'position_index': 0,
        'testbench_passed': True,
        'judge_fooled': True,
        'prompt': 'test prompt',
        'original_code': 'module test(); endmodule',
        'transformed_code': 'module test(); // modified endmodule',
    },
    {
        'task_id': 'test002',
        'status': 'testbench_passed_judge_not_fooled',
        'attack_rule': 'T19',
        'position_index': 1,
        'testbench_passed': True,
        'judge_fooled': False,
        'prompt': 'test prompt 2',
        'original_code': 'module test2(); endmodule',
        'transformed_code': 'module test2(); // dead code endmodule',
    },
    {
        'task_id': 'test003',
        'status': 'success',
        'attack_rule': 'T20',
        'position_index': 0,
        'testbench_passed': True,
        'judge_fooled': True,
        'prompt': 'test prompt 3',
        'original_code': 'module test3(); endmodule',
        'transformed_code': 'module test3(); // modified endmodule',
    }
]

# 创建输出目录
output_dir = Path('test/output')
output_dir.mkdir(exist_ok=True)

# 保存到两个文件
success_file = output_dir / 'attack_success.jsonl'
testbench_passed_file = output_dir / 'testbench_passed.jsonl'

success_count = 0
testbench_passed_count = 0

for sample in test_samples:
    if sample['status'] == 'success':
        with open(success_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
        success_count += 1
        print(f"✅ 保存攻击成功样本: {sample['task_id']}")
    elif sample['status'] == 'testbench_passed_judge_not_fooled':
        with open(testbench_passed_file, 'a', encoding='utf-8') as f:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
        testbench_passed_count += 1
        print(f"⚠️  保存testbench通过样本: {sample['task_id']}")

print(f"\n保存完成:")
print(f"  攻击成功样本: {success_count} -> {success_file}")
print(f"  Testbench通过样本: {testbench_passed_count} -> {testbench_passed_file}")

# 验证文件内容
print(f"\n验证文件内容:")
if success_file.exists():
    with open(success_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    print(f"  {success_file.name}: {len(lines)} 行")
    for i, line in enumerate(lines):
        sample = json.loads(line)
        print(f"    行{i+1}: {sample['task_id']} - {sample['status']}")

if testbench_passed_file.exists():
    with open(testbench_passed_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
    print(f"  {testbench_passed_file.name}: {len(lines)} 行")
    for i, line in enumerate(lines):
        sample = json.loads(line)
        print(f"    行{i+1}: {sample['task_id']} - {sample['status']}")

print("\n✅ 双输出功能测试完成！")
