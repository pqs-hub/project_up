#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
对比评估：旧框架 vs 新框架的T19变换攻击效果
"""
import argparse
import json
import re
import sys
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from tqdm import tqdm

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "test"))

from core.target_model import TargetModelClient
from legacy_t19_transform import legacy_t19_transform


def extract_spec_and_code(input_text: str):
    """从input字段提取spec和代码（兼容中文模板）"""
    spec = ""
    code = ""

    spec_match = re.search(r'### 功能规范\s*\n(.*?)\n(?:###|```)', input_text, re.DOTALL)
    if spec_match:
        spec = spec_match.group(1).strip()

    code_match = re.search(r'```verilog\s*\n(.*?)```', input_text, re.DOTALL)
    if code_match:
        code_with_numbers = code_match.group(1).strip()
        lines = []
        for line in code_with_numbers.split('\n'):
            m = re.match(r'^\d+:\s*(.*)$', line)
            if m:
                lines.append(m.group(1))
            else:
                lines.append(line)
        code = '\n'.join(lines)

    return spec, code


def process_single_sample(
    sample, idx, total,
    judge_client, use_cot,
    stats_lock, stats_counter
):
    """处理单个T19样本：对比新旧框架变换效果"""
    result = {
        "idx": idx,
        "rule_id": "T19",
        "new_framework": {
            "attack_success": False,
            "original_correct": None,
            "transformed_incorrect": None,
            "confidence_drop": None,
        },
        "legacy_framework": {
            "attack_success": False,
            "original_correct": None,
            "transformed_incorrect": None,
            "confidence_drop": None,
        },
        "error": None,
    }
    
    try:
        input_text = sample.get("input", "")
        spec, original_code = extract_spec_and_code(input_text)
        
        if not spec or not original_code:
            result["error"] = "missing_data"
            with stats_lock:
                stats_counter["errors"] += 1
            return result
        
        # 判断原始代码
        original_verdict = judge_client.judge(spec, original_code, use_cot=use_cot)
        if not original_verdict:
            result["error"] = "judge_original_failed"
            with stats_lock:
                stats_counter["errors"] += 1
            return result
        
        original_correct = original_verdict.get("is_correct", False)
        original_confidence = original_verdict.get("confidence", 0.0)
        
        result["new_framework"]["original_correct"] = original_correct
        result["legacy_framework"]["original_correct"] = original_correct
        
        # 评估新框架变体（数据集中的transformed_rtl）
        new_transformed = sample.get("transformed_rtl", "")
        if new_transformed:
            new_verdict = judge_client.judge(spec, new_transformed, use_cot=use_cot)
            if new_verdict:
                new_incorrect = not new_verdict.get("is_correct", True)
                new_confidence = new_verdict.get("confidence", 0.0)
                result["new_framework"]["transformed_incorrect"] = new_incorrect
                result["new_framework"]["confidence_drop"] = original_confidence - new_confidence
                result["new_framework"]["attack_success"] = original_correct and new_incorrect
        
        # 用旧框架重新生成变体
        legacy_transformed = legacy_t19_transform(
            original_code,
            target_token=sample.get("target_token"),
            custom_dead_stmts=None
        )
        
        if legacy_transformed != original_code:
            legacy_verdict = judge_client.judge(spec, legacy_transformed, use_cot=use_cot)
            if legacy_verdict:
                legacy_incorrect = not legacy_verdict.get("is_correct", True)
                legacy_confidence = legacy_verdict.get("confidence", 0.0)
                result["legacy_framework"]["transformed_incorrect"] = legacy_incorrect
                result["legacy_framework"]["confidence_drop"] = original_confidence - legacy_confidence
                result["legacy_framework"]["attack_success"] = original_correct and legacy_incorrect
        
        # 更新统计
        with stats_lock:
            stats_counter["total_evaluated"] += 1
            if result["new_framework"]["attack_success"]:
                stats_counter["new_success"] += 1
            if result["legacy_framework"]["attack_success"]:
                stats_counter["legacy_success"] += 1
            if original_correct:
                stats_counter["original_correct"] += 1
        
    except Exception as e:
        result["error"] = str(e)[:200]
        with stats_lock:
            stats_counter["errors"] += 1
    
    return result


def main():
    parser = argparse.ArgumentParser(description="对比评估新旧T19框架攻击效果")
    parser.add_argument("--dataset", required=True, help="数据集路径")
    parser.add_argument("--max-samples", type=int, help="限制样本数量")
    parser.add_argument("--workers", type=int, default=16, help="并行worker数")
    parser.add_argument("--use-cot", action="store_true", help="使用CoT推理")
    parser.add_argument("--output-dir", help="输出目录")
    args = parser.parse_args()
    
    dataset_path = Path(args.dataset)
    print(f"📖 加载数据集: {dataset_path}")
    
    t19_samples = []
    for line in dataset_path.open('r', encoding='utf-8'):
        if not line.strip():
            continue
        try:
            sample = json.loads(line)
            if sample.get("rule_id") == "T19":
                t19_samples.append(sample)
        except json.JSONDecodeError:
            continue
    
    if args.max_samples:
        t19_samples = t19_samples[:args.max_samples]
    
    print(f"✅ 找到 {len(t19_samples)} 个T19样本")
    
    config_path = PROJECT_ROOT / "config.yaml"
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    tm_cfg = config.get("target_model", {})
    judge_client = TargetModelClient(
        base_url=tm_cfg.get("base_url", "http://localhost:8001/v1"),
        api_key=tm_cfg.get("api_key", "EMPTY"),
        model=tm_cfg.get("model", ""),
        timeout=tm_cfg.get("timeout", 60),
        max_retries=tm_cfg.get("max_retries", 3),
    )
    print(f"🔗 判断模型: {tm_cfg.get('base_url')} / {tm_cfg.get('model')}")
    
    stats_counter = {
        "total_evaluated": 0,
        "original_correct": 0,
        "new_success": 0,
        "legacy_success": 0,
        "errors": 0,
    }
    stats_lock = Lock()
    
    results = []
    results_lock = Lock()
    
    print(f"🔄 使用 {args.workers} 个并行worker开始对比评估...")
    print()
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_single_sample,
                sample, idx, len(t19_samples),
                judge_client, args.use_cot,
                stats_lock, stats_counter
            ): idx
            for idx, sample in enumerate(t19_samples)
        }
        
        pbar = tqdm(total=len(t19_samples), desc="对比评估", unit="sample")
        
        for future in as_completed(futures):
            result = future.result()
            with results_lock:
                results.append(result)
            
            with stats_lock:
                new_succ = stats_counter["new_success"]
                legacy_succ = stats_counter["legacy_success"]
                total_eval = stats_counter["total_evaluated"]
            
            postfix = {
                "新框架": f"{new_succ}/{total_eval}",
                "旧框架": f"{legacy_succ}/{total_eval}",
            }
            pbar.set_postfix(postfix)
            pbar.update(1)
        
        pbar.close()
    
    # 输出统计
    print("\n" + "="*70)
    print("T19变换框架对比评估结果")
    print("="*70)
    
    total = len(t19_samples)
    evaluated = stats_counter["total_evaluated"]
    orig_corr = stats_counter["original_correct"]
    new_succ = stats_counter["new_success"]
    legacy_succ = stats_counter["legacy_success"]
    
    print(f"总样本数:           {total}")
    print(f"成功评估:           {evaluated} ({evaluated/total*100:.1f}%)")
    print(f"原始代码判正确:     {orig_corr} ({orig_corr/evaluated*100:.1f}%)" if evaluated else "N/A")
    print()
    print(f"🆕 新框架攻击成功:   {new_succ} / {evaluated} = {new_succ/evaluated*100:.2f}%" if evaluated else "N/A")
    print(f"   (基于原判正确):   {new_succ} / {orig_corr} = {new_succ/orig_corr*100:.2f}%" if orig_corr else "N/A")
    print()
    print(f"🔙 旧框架攻击成功:   {legacy_succ} / {evaluated} = {legacy_succ/evaluated*100:.2f}%" if evaluated else "N/A")
    print(f"   (基于原判正确):   {legacy_succ} / {orig_corr} = {legacy_succ/orig_corr*100:.2f}%" if orig_corr else "N/A")
    print()
    
    # 计算差异
    if evaluated > 0:
        diff = legacy_succ - new_succ
        diff_pct = diff / evaluated * 100
        print(f"📊 差异分析:")
        print(f"   旧框架 - 新框架 = {diff:+d} ({diff_pct:+.2f}%)")
        if diff > 0:
            print(f"   ✅ 旧框架更有效")
        elif diff < 0:
            print(f"   ✅ 新框架更有效")
        else:
            print(f"   ⚖️  两者效果相同")
    
    # 保存结果
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = dataset_path.parent / "t19_comparison_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    output_path = output_dir / "t19_comparison.json"
    output_data = {
        "dataset": str(dataset_path),
        "total_samples": total,
        "evaluated": evaluated,
        "statistics": {
            "original_correct": orig_corr,
            "new_framework_success": new_succ,
            "legacy_framework_success": legacy_succ,
            "new_framework_rate": new_succ / evaluated if evaluated else 0,
            "legacy_framework_rate": legacy_succ / evaluated if evaluated else 0,
            "difference": legacy_succ - new_succ,
        },
        "per_sample_results": results,
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"\n📄 详细结果已保存: {output_path}")
    
    summary_path = output_dir / "summary.txt"
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("T19变换框架对比评估摘要\n")
        f.write("="*70 + "\n")
        f.write(f"数据集: {dataset_path}\n")
        f.write(f"总样本数: {total}\n")
        f.write(f"成功评估: {evaluated}\n\n")
        f.write(f"新框架攻击成功: {new_succ} / {evaluated} = {new_succ/evaluated*100:.2f}%\n" if evaluated else "N/A\n")
        f.write(f"旧框架攻击成功: {legacy_succ} / {evaluated} = {legacy_succ/evaluated*100:.2f}%\n" if evaluated else "N/A\n")
        f.write(f"\n差异: {legacy_succ - new_succ:+d} ({(legacy_succ - new_succ)/evaluated*100:+.2f}%)\n" if evaluated else "\n")
    print(f"📄 摘要已保存: {summary_path}")
    
    print("\n✅ 对比评估完成!")


if __name__ == "__main__":
    main()
