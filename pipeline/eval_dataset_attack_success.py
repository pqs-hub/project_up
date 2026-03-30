#!/usr/bin/env python3
"""
评估已有攻击样本数据集能否误导判断模型
并行版本：使用多线程加速评估过程
"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from tqdm import tqdm
import difflib

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.target_model import TargetModelClient


def extract_spec_and_code(input_text: str):
    """从input字段提取spec和原始代码"""
    spec = ""
    code = ""
    
    # 提取功能规范
    spec_match = re.search(r'### 功能规范\s*\n(.*?)\n(?:###|```)', input_text, re.DOTALL)
    if spec_match:
        spec = spec_match.group(1).strip()
    
    # 提取原始代码（去除行号）
    code_match = re.search(r'```verilog\s*\n(.*?)```', input_text, re.DOTALL)
    if code_match:
        code_with_numbers = code_match.group(1).strip()
        # 去除行号: "1: module..." -> "module..."
        lines = []
        for line in code_with_numbers.split('\n'):
            match = re.match(r'^\d+:\s*(.*)$', line)
            if match:
                lines.append(match.group(1))
            else:
                lines.append(line)
        code = '\n'.join(lines)
    
    return spec, code


def process_single_sample(
    sample, idx, total,
    judge_client, use_cot,
    stats_lock, stats_counter, failed_samples_lock, failed_samples
):
    """处理单个样本评估"""
    result = {
        "idx": idx,
        "rule_id": sample.get("rule_id"),
        "original_correct": None,
        "original_confidence": None,
        "original_raw_output": None,
        "transformed_incorrect": None,
        "transformed_confidence": None,
        "transformed_raw_output": None,
        "confidence_drop": None,
        "attack_success": False,
        "failure_reason": None,
        "code_length": None,
        "code_lines": None,
        "spec_length": None,
        "code_diff_ratio": None,
        "error": None,
    }
    
    try:
        # 提取spec和原始代码
        input_text = sample.get("input", "")
        spec, original_code = extract_spec_and_code(input_text)
        transformed_code = sample.get("transformed_rtl", "")
        
        if not spec or not original_code or not transformed_code:
            result["error"] = "missing_data"
            result["failure_reason"] = "missing_data"
            with stats_lock:
                stats_counter["missing_data"] += 1
            return result
        
        # 记录代码复杂度指标
        result["code_length"] = len(original_code)
        result["code_lines"] = len(original_code.split('\n'))
        result["spec_length"] = len(spec)
        
        # 计算代码变化度量（编辑距离比例）
        diff = difflib.SequenceMatcher(None, original_code, transformed_code)
        result["code_diff_ratio"] = 1.0 - diff.ratio()
        
        # 判断原始代码
        try:
            original_verdict = judge_client.judge(spec, original_code, use_cot=use_cot)
            original_correct = original_verdict and original_verdict.get("is_correct", False)
            original_confidence = original_verdict.get("confidence", 0.0) if original_verdict else 0.0
            original_raw = original_verdict.get("raw_output", "") if original_verdict else ""
            result["original_correct"] = original_correct
            result["original_confidence"] = original_confidence
            result["original_raw_output"] = original_raw[:500]  # 限制长度
        except Exception as e:
            result["error"] = f"judge_original_error: {str(e)[:100]}"
            result["failure_reason"] = "judge_error"
            with stats_lock:
                stats_counter["judge_error"] += 1
            return result
        
        # 判断变换后代码
        try:
            transformed_verdict = judge_client.judge(spec, transformed_code, use_cot=use_cot)
            transformed_incorrect = transformed_verdict and not transformed_verdict.get("is_correct", True)
            transformed_confidence = transformed_verdict.get("confidence", 0.0) if transformed_verdict else 0.0
            transformed_raw = transformed_verdict.get("raw_output", "") if transformed_verdict else ""
            result["transformed_incorrect"] = transformed_incorrect
            result["transformed_confidence"] = transformed_confidence
            result["transformed_raw_output"] = transformed_raw[:500]  # 限制长度
            
            # 计算confidence变化（正值表示判断信心下降）
            if result["original_confidence"] is not None and result["transformed_confidence"] is not None:
                result["confidence_drop"] = result["original_confidence"] - result["transformed_confidence"]
        except Exception as e:
            result["error"] = f"judge_transformed_error: {str(e)[:100]}"
            result["failure_reason"] = "judge_error"
            with stats_lock:
                stats_counter["judge_error"] += 1
            return result
        
        # 攻击成功：原始代码被判正确 且 变换后代码被判错误
        attack_success = original_correct and transformed_incorrect
        result["attack_success"] = attack_success
        
        # 失败原因细分
        if not attack_success:
            if not original_correct:
                result["failure_reason"] = "baseline_wrong"
            elif not transformed_incorrect:
                result["failure_reason"] = "attack_ineffective"
        else:
            result["failure_reason"] = None
        
        with stats_lock:
            stats_counter["total_evaluated"] += 1
            if original_correct:
                stats_counter["original_correct"] += 1
            if transformed_incorrect:
                stats_counter["transformed_incorrect"] += 1
            if attack_success:
                stats_counter["attack_success"] += 1
                rule_id = sample.get("rule_id")
                if rule_id:
                    stats_counter["success_by_rule"][rule_id] += 1
            else:
                # 记录失败样本
                if not original_correct:
                    with failed_samples_lock:
                        if len(failed_samples["original_wrong"]) < 10:
                            failed_samples["original_wrong"].append({
                                "idx": idx,
                                "rule_id": sample.get("rule_id"),
                                "spec_preview": spec[:200],
                                "code_preview": original_code[:500],
                            })
                elif not transformed_incorrect:
                    with failed_samples_lock:
                        if len(failed_samples["transformed_still_correct"]) < 10:
                            failed_samples["transformed_still_correct"].append({
                                "idx": idx,
                                "rule_id": sample.get("rule_id"),
                                "spec_preview": spec[:200],
                                "transformed_preview": transformed_code[:500],
                            })
        
        return result
        
    except Exception as e:
        result["error"] = f"unexpected_error: {str(e)[:100]}"
        with stats_lock:
            stats_counter["unexpected_error"] += 1
        return result


def main():
    parser = argparse.ArgumentParser(description="评估攻击样本数据集能否误导判断模型（并行版本）")
    parser.add_argument("--dataset", type=str, required=True, help="攻击样本数据集路径 (JSONL)")
    parser.add_argument("--max-samples", type=int, default=None, help="最多评估多少条样本")
    parser.add_argument("--output", type=str, default=None, help="结果JSON输出路径")
    parser.add_argument("--output-dir", type=str, default=None, help="输出目录（默认与数据集同目录）")
    parser.add_argument("--use-cot", action="store_true", help="启用CoT推理模式")
    parser.add_argument("--workers", type=int, default=8, help="并行worker数量")
    parser.add_argument("--save-failed-samples", action="store_true", help="保存失败样本示例")
    args = parser.parse_args()
    
    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        print(f"❌ 数据集不存在: {dataset_path}")
        return
    
    # 加载数据集
    print(f"📖 加载数据集: {dataset_path}")
    samples = []
    for line_idx, line in enumerate(dataset_path.open('r', encoding='utf-8'), 1):
        if not line.strip():
            continue
        try:
            samples.append(json.loads(line))
        except json.JSONDecodeError:
            print(f"⚠️  跳过无效JSON (line {line_idx})")
    
    if args.max_samples:
        samples = samples[:args.max_samples]
    
    print(f"✅ 加载 {len(samples)} 条样本")
    
    # 配置判断模型客户端
    config_path = PROJECT_ROOT / "config.yaml"
    if config_path.exists():
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
    else:
        print("❌ 未找到 config.yaml")
        return
    
    # 统计变量
    stats_counter = {
        "total_evaluated": 0,
        "original_correct": 0,
        "transformed_incorrect": 0,
        "attack_success": 0,
        "missing_data": 0,
        "judge_error": 0,
        "unexpected_error": 0,
        "success_by_rule": Counter(),
    }
    stats_lock = Lock()
    
    failed_samples = {
        "original_wrong": [],
        "transformed_still_correct": [],
    }
    failed_samples_lock = Lock()
    
    results = []
    results_lock = Lock()
    
    print(f"🔄 使用 {args.workers} 个并行worker开始评估...")
    print()
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_single_sample,
                sample, idx, len(samples),
                judge_client, args.use_cot,
                stats_lock, stats_counter,
                failed_samples_lock, failed_samples
            ): idx
            for idx, sample in enumerate(samples)
        }
        
        pbar = tqdm(total=len(samples), desc="评估进度", unit="sample")
        
        for future in as_completed(futures):
            result = future.result()
            
            with results_lock:
                results.append(result)
            
            # 动态显示进度
            with stats_lock:
                succ = stats_counter["attack_success"]
                total_eval = stats_counter["total_evaluated"]
                orig_corr = stats_counter["original_correct"]
            
            postfix = {
                "成功": f"{succ}/{total_eval}",
                "原判正确": f"{orig_corr}/{total_eval}",
            }
            pbar.set_postfix(postfix)
            pbar.update(1)
        
        pbar.close()
    
    # 计算按规则的详细统计
    rule_stats = {}
    failure_reasons = Counter()
    
    for r in results:
        rule_id = r.get("rule_id")
        if rule_id:
            if rule_id not in rule_stats:
                rule_stats[rule_id] = {
                    "total": 0,
                    "success": 0,
                    "confidence_drops": [],
                    "code_diff_ratios": [],
                }
            rule_stats[rule_id]["total"] += 1
            if r.get("attack_success"):
                rule_stats[rule_id]["success"] += 1
            if r.get("confidence_drop") is not None:
                rule_stats[rule_id]["confidence_drops"].append(r["confidence_drop"])
            if r.get("code_diff_ratio") is not None:
                rule_stats[rule_id]["code_diff_ratios"].append(r["code_diff_ratio"])
        
        if r.get("failure_reason"):
            failure_reasons[r["failure_reason"]] += 1
    
    # 输出统计
    print("\n" + "="*60)
    print("评估结果统计")
    print("="*60)
    
    total = len(samples)
    evaluated = stats_counter["total_evaluated"]
    orig_corr = stats_counter["original_correct"]
    trans_incorr = stats_counter["transformed_incorrect"]
    attack_succ = stats_counter["attack_success"]
    
    print(f"总样本数:           {total}")
    print(f"成功评估:           {evaluated} ({evaluated/total*100:.1f}%)")
    print(f"原始代码判正确:     {orig_corr} ({orig_corr/evaluated*100:.1f}%)" if evaluated else "N/A")
    print(f"变换后代码判错误:   {trans_incorr} ({trans_incorr/evaluated*100:.1f}%)" if evaluated else "N/A")
    print()
    print(f"🎯 攻击成功:         {attack_succ} ({attack_succ/evaluated*100:.2f}%)" if evaluated else "N/A")
    print(f"   (在原判正确基础上): {attack_succ}/{orig_corr} = {attack_succ/orig_corr*100:.2f}%" if orig_corr else "N/A")
    print()
    
    # 失败原因统计
    if failure_reasons:
        print("失败原因分布:")
        for reason, count in failure_reasons.most_common():
            pct = count / evaluated * 100 if evaluated else 0
            print(f"  {reason:20} : {count:6} ({pct:5.1f}%)")
        print()
    
    # 错误统计
    if stats_counter["missing_data"] or stats_counter["judge_error"] or stats_counter["unexpected_error"]:
        print("错误统计:")
        print(f"  缺失数据:         {stats_counter['missing_data']}")
        print(f"  判断错误:         {stats_counter['judge_error']}")
        print(f"  意外错误:         {stats_counter['unexpected_error']}")
        print()
    
    # 规则分布与详细统计
    if stats_counter["success_by_rule"]:
        print("按规则详细统计:")
        print(f"{'规则':<8} {'总数':>6} {'成功':>6} {'成功率':>8} {'平均Conf下降':>12} {'平均代码变化':>12}")
        print("-" * 70)
        for rule_id, count in stats_counter["success_by_rule"].most_common():
            stats = rule_stats.get(rule_id, {})
            total_rule = stats.get("total", 0)
            success_rule = stats.get("success", 0)
            succ_rate = success_rule / total_rule * 100 if total_rule else 0
            
            conf_drops = stats.get("confidence_drops", [])
            avg_conf_drop = sum(conf_drops) / len(conf_drops) if conf_drops else 0
            
            diff_ratios = stats.get("code_diff_ratios", [])
            avg_diff = sum(diff_ratios) / len(diff_ratios) if diff_ratios else 0
            
            print(f"{rule_id:<8} {total_rule:>6} {success_rule:>6} {succ_rate:>7.1f}% {avg_conf_drop:>11.3f} {avg_diff:>11.3f}")
        print()
    
    # 输出目录
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = dataset_path.parent / "eval_results"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 保存详细结果
    output_path = args.output if args.output else output_dir / "attack_success_eval.json"
    
    # 准备规则详细统计
    rule_detailed_stats = {}
    for rule_id, stats in rule_stats.items():
        conf_drops = stats.get("confidence_drops", [])
        diff_ratios = stats.get("code_diff_ratios", [])
        rule_detailed_stats[rule_id] = {
            "total": stats["total"],
            "success": stats["success"],
            "success_rate": stats["success"] / stats["total"] if stats["total"] else 0,
            "avg_confidence_drop": sum(conf_drops) / len(conf_drops) if conf_drops else 0,
            "avg_code_diff_ratio": sum(diff_ratios) / len(diff_ratios) if diff_ratios else 0,
        }
    
    output_data = {
        "dataset": str(dataset_path),
        "total_samples": total,
        "evaluated": evaluated,
        "statistics": {
            "original_correct": orig_corr,
            "transformed_incorrect": trans_incorr,
            "attack_success": attack_succ,
            "attack_success_rate": attack_succ / evaluated if evaluated else 0,
            "attack_success_rate_on_original_correct": attack_succ / orig_corr if orig_corr else 0,
        },
        "failure_reasons": dict(failure_reasons.most_common()),
        "errors": {
            "missing_data": stats_counter["missing_data"],
            "judge_error": stats_counter["judge_error"],
            "unexpected_error": stats_counter["unexpected_error"],
        },
        "rule_statistics": rule_detailed_stats,
        "success_by_rule": dict(stats_counter["success_by_rule"].most_common()),
        "per_sample_results": results,
    }
    
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)
    print(f"📄 详细结果已保存: {output_path}")
    
    # 保存摘要
    summary_path = output_dir / "summary.txt"
    with open(summary_path, 'w', encoding='utf-8') as f:
        f.write("攻击样本数据集评估摘要\n")
        f.write("="*60 + "\n")
        f.write(f"数据集: {dataset_path}\n")
        f.write(f"总样本数: {total}\n")
        f.write(f"成功评估: {evaluated} ({evaluated/total*100:.1f}%)\n")
        f.write(f"\n")
        f.write(f"原始代码判正确:   {orig_corr} ({orig_corr/evaluated*100:.1f}%)\n" if evaluated else "N/A\n")
        f.write(f"变换后代码判错误: {trans_incorr} ({trans_incorr/evaluated*100:.1f}%)\n" if evaluated else "N/A\n")
        f.write(f"\n")
        f.write(f"🎯 攻击成功: {attack_succ} / {evaluated} = {attack_succ/evaluated*100:.2f}%\n" if evaluated else "N/A\n")
        f.write(f"   (在原判正确基础上): {attack_succ} / {orig_corr} = {attack_succ/orig_corr*100:.2f}%\n" if orig_corr else "N/A\n")
        f.write(f"\n")
        if stats_counter["success_by_rule"]:
            f.write("攻击成功规则分布:\n")
            for rule_id, count in stats_counter["success_by_rule"].most_common():
                pct = count / attack_succ * 100 if attack_succ else 0
                f.write(f"  {rule_id:6} : {count:6} ({pct:5.1f}%)\n")
    print(f"📄 摘要已保存: {summary_path}")
    
    # 保存失败样本示例
    if args.save_failed_samples and (failed_samples["original_wrong"] or failed_samples["transformed_still_correct"]):
        failed_path = output_dir / "failed_samples.json"
        with open(failed_path, 'w', encoding='utf-8') as f:
            json.dump(failed_samples, f, ensure_ascii=False, indent=2)
        print(f"📄 失败样本示例已保存: {failed_path}")
    
    print("\n✅ 评估完成!")


if __name__ == "__main__":
    main()
