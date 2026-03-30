#!/usr/bin/env python3
"""调试T48变换的具体问题"""

import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from core.transforms import create_engine

def looks_like_verilog(code: str) -> bool:
    c = (code or "").strip().lower()
    return bool(c and "module " in c and "endmodule" in c)

def extract_code_fields(row: dict):
    ds = row.get("dataset_row") or {}
    adv_result = row.get("adv_result_row") or {}

    original = ds.get("canonical_solution", "")
    transformed = adv_result.get("final", "")
    
    return original.strip(), transformed.strip(), {}

def analyze_t48_sample(dataset_path: str, sample_limit: int = 5):
    """分析T48样本的具体问题"""
    engine = create_engine()
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    t48_count = 0
    for i, line in enumerate(lines):
        if t48_count >= sample_limit:
            break
            
        row = json.loads(line)
        if row.get("rule_id") != "T48":
            continue
            
        t48_count += 1
        print(f"\n=== T48 Sample {t48_count} (line {i}) ===")
        
        # 提取代码字段
        original, old_transformed, old_params = extract_code_fields(row)
        
        print(f"Original code length: {len(original)}")
        print(f"Old transformed length: {len(old_transformed)}")
        
        if not original:
            print("❌ No original code found")
            continue
            
        if not old_transformed:
            print("❌ No transformed code found") 
            continue
            
        # 显示代码片段
        print(f"\nOriginal code:")
        print(repr(original))
        print(f"\nOld transformed:")
        print(repr(old_transformed))
        
        # 尝试用当前引擎变换
        try:
            # 先测试普通模式
            current_result = engine.apply_transform(original, "T48")
            print(f"\nCurrent engine result length (normal): {len(current_result)}")
            
            # 再测试legacy模式
            current_legacy_result = engine.apply_transform(original, "T48", legacy_format=True)
            print(f"Current engine result length (legacy): {len(current_legacy_result)}")
            print(f"Current engine result (legacy):")
            print(repr(current_legacy_result))
            
            # 比较结果
            if old_transformed == current_legacy_result:
                print("✅ Legacy mode exact match!")
            elif old_transformed == current_result:
                print("✅ Normal mode exact match!")
            else:
                print("❌ Both modes differ")
                # 显示legacy模式的差异
                old_lines = old_transformed.split('\n')
                legacy_lines = current_legacy_result.split('\n')
                print(f"Old lines: {len(old_lines)}, Legacy lines: {len(legacy_lines)}")
                
                for i, (old_line, legacy_line) in enumerate(zip(old_lines[:10], legacy_lines[:10])):
                    if old_line != legacy_line:
                        print(f"First difference at line {i+1}:")
                        print(f"  Old: {repr(old_line)}")
                        print(f"  Legacy: {repr(legacy_line)}")
                        break
                
        except Exception as e:
            print(f"❌ Transform failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    dataset_path = "/mnt/public/pqs/LLM_attack1/LLM_attack/data/all_rules_asr_success_fullinfo_dedup_trp.jsonl"
    analyze_t48_sample(dataset_path, sample_limit=3)
