#!/usr/bin/env python3
"""缓存任务构建器，避免重复计算候选位置"""

import sys
from pathlib import Path

# 确保在项目根目录
project_root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(project_root))

import json
import hashlib
import time
from typing import Dict, List, Tuple
import pickle

class CachedTaskBuilder:
    """缓存任务构建器"""
    
    def __init__(self, cache_dir: str = "data/cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        self.candidates_cache = {}
        self._load_cache()
    
    def _get_rtl_hash(self, rtl: str) -> str:
        """计算RTL的哈希值"""
        return hashlib.md5(rtl.encode()).hexdigest()[:16]
    
    def _load_cache(self):
        """加载缓存"""
        cache_file = self.cache_dir / "candidates_cache.pkl"
        if cache_file.exists():
            try:
                with open(cache_file, 'rb') as f:
                    self.candidates_cache = pickle.load(f)
                print(f"加载候选位置缓存: {len(self.candidates_cache)} 个RTL")
            except Exception as e:
                print(f"加载缓存失败: {e}")
                self.candidates_cache = {}
    
    def _save_cache(self):
        """保存缓存"""
        cache_file = self.cache_dir / "candidates_cache.pkl"
        with open(cache_file, 'wb') as f:
            pickle.dump(self.candidates_cache, f)
    
    def get_candidates_count(self, rtl: str, rule_id: str) -> int:
        """获取候选位置数量（带缓存）"""
        rtl_hash = self._get_rtl_hash(rtl)
        
        # 检查缓存
        if rtl_hash in self.candidates_cache and rule_id in self.candidates_cache[rtl_hash]:
            return self.candidates_cache[rtl_hash][rule_id]
        
        # 计算并缓存
        try:
            from core.transforms import create_engine
            engine = create_engine()
            candidates = engine._get_candidates_for_transform(rtl, rule_id)
            count = len(candidates)
            
            # 只缓存数量，不缓存具体对象
            if rtl_hash not in self.candidates_cache:
                self.candidates_cache[rtl_hash] = {}
            self.candidates_cache[rtl_hash][rule_id] = count
            
            return count
        except Exception as e:
            print(f"计算候选失败 {rule_id}: {e}")
            return 0
    
    def build_job_list(self, eval_data: List[Dict], rules_to_test: List[str], 
                      max_positions_per_rule: int = 10, random_seed: int = 42) -> List[Tuple]:
        """构建任务列表（带缓存）"""
        import random
        random.seed(random_seed)
        
        jobs = []
        cache_hits = 0
        cache_misses = 0
        
        print("构建攻击任务列表（使用缓存）...")
        
        for item in eval_data:
            task_id = item.get("task_id", "")
            rtl = item.get("canonical_solution", "")
            
            for rule_id in rules_to_test:
                # 获取候选位置数量（可能来自缓存）
                count = self.get_candidates_count(rtl, rule_id)
                
                if count > 0:
                    # 检查是否是缓存命中
                    rtl_hash = self._get_rtl_hash(rtl)
                    if rtl_hash in self.candidates_cache and rule_id in self.candidates_cache[rtl_hash]:
                        cache_hits += 1
                    else:
                        cache_misses += 1
                    
                    # 随机选择位置
                    positions = list(range(min(count, max_positions_per_rule)))
                    random.shuffle(positions)
                    
                    for pos_idx in positions:
                        jobs.append((item, rule_id, pos_idx))
        
        # 保存缓存
        self._save_cache()
        
        print(f"任务列表构建完成:")
        print(f"  总任务数: {len(jobs)}")
        print(f"  缓存命中: {cache_hits}")
        print(f"  缓存未命中: {cache_misses}")
        if cache_hits + cache_misses > 0:
            print(f"  缓存命中率: {cache_hits/(cache_hits+cache_misses)*100:.1f}%")
        else:
            print(f"  缓存命中率: N/A (无数据)")
        
        return jobs

def test_cached_builder():
    """测试缓存构建器"""
    
    # 读取测试数据
    with open('data/qualified_newcot_noconfidence.json') as f:
        eval_data = json.load(f)
    
    rules_to_test = ['T03', 'T12', 'T19', 'T20']  # 测试4个规则
    
    # 创建缓存构建器
    builder = CachedTaskBuilder()
    
    # 第一次构建
    print("第一次构建任务列表...")
    start = time.time()
    jobs1 = builder.build_job_list(eval_data[:1000], rules_to_test, max_positions_per_rule=5)
    time1 = time.time() - start
    print(f"耗时: {time1:.1f} 秒\n")
    
    # 第二次构建（应该更快）
    print("第二次构建任务列表（使用缓存）...")
    start = time.time()
    jobs2 = builder.build_job_list(eval_data[:1000], rules_to_test, max_positions_per_rule=5)
    time2 = time.time() - start
    print(f"耗时: {time2:.1f} 秒\n")
    
    print(f"性能提升: {time1/time2:.1f}x")
    print(f"任务数一致: {len(jobs1) == len(jobs2)}")

if __name__ == "__main__":
    test_cached_builder()
