#!/usr/bin/env python3
"""调试T20变换的具体问题"""

import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from core.transforms import create_engine

# 直接复制需要的函数以避免导入问题
def normalize_code(code: str) -> str:
    lines = [(ln.rstrip()) for ln in (code or "").replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)

def compact_code(code: str) -> str:
    return "".join((code or "").split())

def looks_like_verilog(code: str) -> bool:
    c = (code or "").strip().lower()
    return bool(c and "module " in c and "endmodule" in c)

def safe_params(params):
    if not isinstance(params, dict):
        return {}
    out = {}
    for k, v in params.items():
        if isinstance(v, (str, int, float, bool, dict, list)) or v is None:
            out[k] = v
    return out

def extract_code_fields(row: dict):
    ds = row.get("dataset_row") or {}
    adv_eval = row.get("adv_eval_row") or {}
    adv_result = row.get("adv_result_row") or {}

    orig_from_adv = (adv_eval.get("original_code") or "").strip()
    adv_from_adv = (adv_eval.get("adversarial_code") or "").strip()
    adv_from_result = (adv_result.get("final") or "").strip()

    original = orig_from_adv if looks_like_verilog(orig_from_adv) else (ds.get("canonical_solution") or "")
    if looks_like_verilog(adv_from_adv):
        old_transformed = adv_from_adv
    elif looks_like_verilog(adv_from_result):
        old_transformed = adv_from_result
    else:
        old_transformed = ""

    return (original or "").strip(), (old_transformed or "").strip(), safe_params(adv_result.get("params_used") or {})

def canonicalize_params(rule_id: str, params: dict) -> dict:
    """参数规范化（简化版）"""
    p = dict(params or {})
    # T20 特殊处理
    if rule_id == "T20":
        p["target_line"] = 1  # 模块声明通常在第1行
        if "custom_text" in p:
            p["custom_description"] = p["custom_text"]
    return p

def analyze_t20_sample(dataset_path: str, sample_limit: int = 10):
    """分析T20样本的具体问题"""
    engine = create_engine()
    
    with open(dataset_path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    
    t20_count = 0
    for i, line in enumerate(lines):
        if t20_count >= sample_limit:
            break
            
        row = json.loads(line)
        if row.get("rule_id") != "T20":
            continue
            
        t20_count += 1
        print(f"\n=== T20 Sample {t20_count} (line {i}) ===")
        
        # 提取代码字段
        original, old_transformed, old_params = extract_code_fields(row)
        
        print(f"Original code length: {len(original)}")
        print(f"Old transformed length: {len(old_transformed)}")
        print(f"Old params: {old_params}")
        
        if not original:
            print("❌ No original code found")
            continue
            
        if not old_transformed:
            print("❌ No transformed code found") 
            continue
            
        # 显示代码片段
        print(f"\nOriginal code (first 300 chars):")
        print(repr(original[:300]))
        print(f"\nOld transformed (first 300 chars):")
        print(repr(old_transformed[:300]))
        
        # 尝试参数转换和当前引擎变换
        try:
            canon_params = canonicalize_params("T20", old_params)
            print(f"\nCanonical params: {canon_params}")
            
            # 尝试直接用当前引擎变换看看结果
            current_result = engine.apply_transform(original, "T20", **canon_params)
            print(f"\nCurrent engine result length: {len(current_result)}")
            print(f"Current engine result (first 300 chars):")
            print(repr(current_result[:300]))
            
            # 比较归一化后的代码
            old_norm = normalize_code(old_transformed)
            current_norm = normalize_code(current_result)
            print(f"\nOld normalized length: {len(old_norm)}")
            print(f"Current normalized length: {len(current_norm)}")
            print(f"Normalized match: {old_norm == current_norm}")
            
            if old_norm != current_norm:
                print("❌ Normalized codes differ")
                # 显示差异的前几个字符
                for i, (a, b) in enumerate(zip(old_norm[:200], current_norm[:200])):
                    if a != b:
                        print(f"First difference at position {i}: {repr(a)} vs {repr(b)}")
                        break
            else:
                print("✅ Normalized codes match")
                
        except Exception as e:
            print(f"❌ Transform failed: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    dataset_path = "/mnt/public/pqs/LLM_attack1/LLM_attack/data/all_rules_asr_success_fullinfo_dedup_trp.jsonl"
    analyze_t20_sample(dataset_path, sample_limit=5)
