#!/usr/bin/env python3
"""候选位置缓存测试"""

import sys
import json
import pickle
import hashlib
from pathlib import Path
from tqdm import tqdm

# 确保在项目根目录
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from core.transforms import create_engine

def get_rtl_hash(rtl):
    """计算RTL的哈希值"""
    return hashlib.md5(rtl.encode()).hexdigest()[:16]

def cache_candidates(eval_data, rules_to_test, cache_file="data/candidates_cache.pkl"):
    """缓存候选位置"""
    
    cache_dir = Path(cache_file).parent
    cache_dir.mkdir(exist_ok=True)
    
    # 加载现有缓存
    cache = {}
    if Path(cache_file).exists():
        with open(cache_file, 'rb') as f:
            cache = pickle.load(f)
        print(f"加载现有缓存: {len(cache)} 个条目")
    
    engine = create_engine()
    new_entries = 0
    
    print("计算候选位置...")
    for item in tqdm(eval_data[:100]):  # 测试前100个
        task_id = item.get('task_id', '')
        rtl = item.get('canonical_solution', '')
        rtl_hash = get_rtl_hash(rtl)
        
        if rtl_hash not in cache:
            cache[rtl_hash] = {}
        
        for rule_id in rules_to_test:
            if rule_id not in cache[rtl_hash]:
                try:
                    candidates = engine._get_candidates_for_transform(rtl, rule_id)
                    cache[rtl_hash][rule_id] = candidates
                    new_entries += 1
                except Exception as e:
                    print(f"错误 {task_id} {rule_id}: {e}")
                    cache[rtl_hash][rule_id] = []
    
    # 保存缓存
    with open(cache_file, 'wb') as f:
        pickle.dump(cache, f)
    
    print(f"缓存完成: 新增 {new_entries} 个条目")
    print(f"缓存文件: {cache_file}")
    print(f"缓存大小: {Path(cache_file).stat().st_size / 1024 / 1024:.1f} MB")

def test_cache_speed():
    """测试缓存加速效果"""
    
    # 读取测试数据
    with open('data/qualified_newcot_noconfidence.json') as f:
        eval_data = json.load(f)
    
    rules_to_test = ['T03', 'T12', 'T19']  # 测试3个规则
    
    # 第一次运行（无缓存）
    print("第一次运行（无缓存）...")
    import time
    start = time.time()
    cache_candidates(eval_data, rules_to_test, "data/test_cache_1.pkl")
    time1 = time.time() - start
    
    # 第二次运行（有缓存）
    print("\n第二次运行（有缓存）...")
    start = time.time()
    cache_candidates(eval_data, rules_to_test, "data/test_cache_2.pkl")
    time2 = time.time() - start
    
    print(f"\n性能对比:")
    print(f"  无缓存: {time1:.1f} 秒")
    print(f"  有缓存: {time2:.1f} 秒")
    print(f"  加速: {time1/time2:.1f}x")

if __name__ == "__main__":
    test_cache_speed()
