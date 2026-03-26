#!/usr/bin/env python3
"""调试单个攻击为什么失败"""

import sys
import json
from pathlib import Path

# 确保在项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.attack_engine import create_engine
from config.prompts import LLM_PARAM_RULES

# 读取一个测试任务
with open('data/qualified_newcot_noconfidence.json') as f:
    data = json.load(f)

task = data[0]
task_id = task.get('task_id', '')
spec = task.get('prompt', '')
rtl = task.get('canonical_solution', '')

print(f"测试任务: {task_id}")
print(f"SPEC长度: {len(spec)}")
print(f"RTL长度: {len(rtl)}")
print()

engine = create_engine()

# 测试几个规则
test_rules = ['T03', 'T12', 'T19', 'T20']

for rule_id in test_rules:
    print(f"\n{'='*60}")
    print(f"测试规则: {rule_id}")
    print(f"{'='*60}")
    
    try:
        # 1. 获取候选
        candidates = engine._get_candidates_for_transform(rtl, rule_id)
        print(f"✅ 候选数: {len(candidates)}")
        
        if len(candidates) == 0:
            print(f"❌ 没有候选位置，跳过")
            continue
        
        # 2. 测试第一个位置的变换
        target_token = 0
        print(f"\n尝试位置: {target_token}")
        
        # 3. 准备参数
        params = {'target_token': target_token}
        
        if rule_id in LLM_PARAM_RULES:
            print(f"⚠️  {rule_id} 需要LLM参数生成")
            # 这里不实际生成，看是否影响变换
        
        # 4. 应用变换
        transformed = engine.apply_transform(rtl, rule_id, **params)
        
        if not transformed:
            print(f"❌ 变换返回空")
            continue
            
        if transformed == rtl:
            print(f"❌ 变换后代码未改变")
            continue
        
        print(f"✅ 变换成功！")
        print(f"   原代码长度: {len(rtl)}")
        print(f"   变换后长度: {len(transformed)}")
        print(f"   差异: {len(transformed) - len(rtl)} bytes")
        
        # 显示差异（前200字符）
        if len(transformed) > len(rtl):
            diff_start = 0
            for i, (a, b) in enumerate(zip(rtl, transformed)):
                if a != b:
                    diff_start = max(0, i - 50)
                    break
            print(f"\n差异预览（位置{diff_start}）:")
            print(transformed[diff_start:diff_start+200])
        
    except Exception as e:
        print(f"❌ 错误: {e}")
        import traceback
        traceback.print_exc()

print("\n" + "="*60)
print("调试完成")
print("="*60)
