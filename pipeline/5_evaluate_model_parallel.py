#!/usr/bin/env python3
"""
并行版本的评估脚本：使用多线程加速评估过程
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

import requests
import yaml

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from ast_transforms_loader import create_engine
from Testbench_valid import TestbenchRunner
from core.target_model import TargetModelClient

# 导入原评估脚本的工具函数
import importlib.util
spec = importlib.util.spec_from_file_location("eval_module", PROJECT_ROOT / "pipeline" / "5_evaluate_model.py")
eval_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(eval_module)

# 重用原脚本的常量和函数
SEMANTIC_NAMES = eval_module.SEMANTIC_NAMES
ATTACK_NAME_TO_TID = eval_module.ATTACK_NAME_TO_TID
INSTRUCTION = eval_module.INSTRUCTION
RENAME_RULES = eval_module.RENAME_RULES
add_line_numbers = eval_module.add_line_numbers
parse_model_output = eval_module.parse_model_output
call_attack_model = eval_module.call_attack_model
design_for_testbench = eval_module.design_for_testbench
apply_rename_to_testbench = eval_module.apply_rename_to_testbench


def process_single_task(
    item, idx, total,
    judge_client, attack_base_url, attack_model, attack_api_key,
    n_per, temperature, use_cot, args,
    first_raw_response_lock, first_tb_fail_lock,
    success_examples_lock, all_responses_lock, detailed_log_lock,
    first_raw_response_holder, first_tb_fail_holder, success_examples, success_rule_counter
):
    """处理单个评估任务（用于并行）"""
    task_id = item.get("task_id", str(idx))
    spec = item.get("prompt", "")
    rtl = item.get("canonical_solution", "")
    testbench = item.get("test", "")
    
    # 初始化结果
    result = {
        "task_id": task_id,
        "success_1": False,
        "success_3": False,
        "success_5": False,
        "success_10": False,
    }
    diag = {
        "attempts": 0,
        "parse_ok": 0,
        "transform_changed": 0,
        "tb_pass": 0,
        "judge_flipped": 0,
    }
    
    if not rtl or not testbench:
        return result, diag, False
    
    # 创建task专用的engine和tb_runner（避免线程冲突）
    engine = create_engine()
    tb_runner = TestbenchRunner(simulator="iverilog", timeout=30)
    
    # 原始判决
    try:
        original_verdict = judge_client.judge(spec, rtl, use_cot=use_cot)
        if not original_verdict or not original_verdict.get("is_correct"):
            return result, diag, False
    except Exception as e:
        return result, diag, False
    
    # 调用攻击模型
    numbered_rtl = add_line_numbers(rtl)
    input_text = f"### 功能规范\n{spec}\n\n### 原始代码\n```verilog\n{numbered_rtl}\n```"
    
    try:
        responses = call_attack_model(
            INSTRUCTION, input_text, attack_base_url,
            attack_model, attack_api_key,
            max_tokens=512, temperature=temperature, n=n_per,
            system_prompt=eval_module.ATTACK_SYSTEM_PROMPT,
        )
    except Exception as e:
        return result, diag, True
    
    successes = []
    
    for resp_idx, resp in enumerate(responses):
        diag["attempts"] += 1
        
        # 记录第一个原始响应
        if resp and resp.strip():
            with first_raw_response_lock:
                if first_raw_response_holder[0] is None:
                    first_raw_response_holder[0] = resp.strip()
        
        parsed = parse_model_output(resp)
        transformed = None
        tid = None
        
        if parsed:
            diag["parse_ok"] += 1
            tid, target_token, params = parsed
            if tid in engine.registry:
                try:
                    transformed = engine.apply_transform(
                        code=rtl,
                        transform_id=tid,
                        target_token=target_token,
                        **params,
                    )
                except Exception:
                    pass
                if transformed == rtl:
                    transformed = None
        
        if transformed is None:
            successes.append(False)
            continue
        
        diag["transform_changed"] += 1
        
        # 处理重命名规则
        rtl_for_ref = rtl
        transformed_for_tb = transformed
        tb_to_run = testbench
        if tid and tid in RENAME_RULES:
            rename_map = engine.get_last_rename_map()
            if rename_map:
                tb_to_run, resolved_map = apply_rename_to_testbench(tb_to_run, rename_map)
                if resolved_map != rename_map:
                    for old_name, new_name in resolved_map.items():
                        rtl_for_ref = re.sub(r"\b" + re.escape(old_name) + r"\b", new_name, rtl_for_ref)
                        orig_new_name = rename_map.get(old_name)
                        if orig_new_name and orig_new_name != new_name:
                            transformed_for_tb = re.sub(r"\b" + re.escape(orig_new_name) + r"\b", new_name, transformed_for_tb)
                else:
                    for old_name, new_name in resolved_map.items():
                        rtl_for_ref = re.sub(r"\b" + re.escape(old_name) + r"\b", new_name, rtl_for_ref)
        
        # Testbench测试
        tb_rtl = design_for_testbench(rtl_for_ref, transformed_for_tb)
        if tb_runner.available:
            run_result = tb_runner.run(tb_rtl, tb_to_run)
            if not run_result.get("passed", False):
                with first_tb_fail_lock:
                    if first_tb_fail_holder[0] is None:
                        first_tb_fail_holder[0] = {
                            "task_id": task_id,
                            "design_preview": tb_rtl[:2000] + ("..." if len(tb_rtl) > 2000 else ""),
                            "tb_preview": tb_to_run[:1500] + ("..." if len(tb_to_run) > 1500 else ""),
                            "error": run_result.get("error", ""),
                            "output": run_result.get("output", "")[:1000],
                        }
                successes.append(False)
                continue
        
        diag["tb_pass"] += 1
        
        # 判断变换后代码
        try:
            new_verdict = judge_client.judge(spec, transformed, use_cot=use_cot)
            if not new_verdict:
                successes.append(False)
                continue
            
            attack_ok = original_verdict.get("is_correct") is True and new_verdict.get("is_correct") is False
            
            if attack_ok:
                diag["judge_flipped"] += 1
                if tid:
                    with success_examples_lock:
                        success_rule_counter[tid] += 1
                        if len(success_examples) < args.max_success_examples:
                            success_examples.append({
                                "task_id": task_id,
                                "model_response": resp.strip() if resp else "",
                                "transform_id": tid,
                                "transformed_preview": (transformed[:1500] + ("..." if len(transformed) > 1500 else "")) if transformed else "",
                            })
            
            successes.append(attack_ok)
        except Exception as e:
            successes.append(False)
    
    # 计算pass@k
    s1 = successes[0] if len(successes) >= 1 else False
    s3 = any(successes[:3]) if len(successes) >= 3 else (s1 if successes else False)
    s5 = any(successes[:5]) if len(successes) >= 5 else (any(successes[:3]) if len(successes) >= 3 else (s1 if successes else False))
    s10 = any(successes[:10]) if len(successes) >= 10 else (any(successes) if successes else False)
    
    result.update({
        "success_1": s1,
        "success_3": s3,
        "success_5": s5,
        "success_10": s10,
    })
    
    return result, diag, True


def main():
    parser = argparse.ArgumentParser(description="评估攻击模型（并行版本）：pass@1/5/10 攻击成功率")
    parser.add_argument("--eval-file", type=str, default=None, help="verilog_eval.json 路径")
    parser.add_argument("--attack-model", type=str, default=None, help="攻击模型 API 的 model 名")
    parser.add_argument("--attack-base-url", type=str, default=None, help="攻击模型 base_url")
    parser.add_argument("--max-samples", type=int, default=None, help="最多评估多少条")
    parser.add_argument("--n-per-task", type=int, default=10, help="每个 task 采样数")
    parser.add_argument("--temperature", type=float, default=0.3, help="采样温度")
    parser.add_argument("--output", type=str, default=None, help="结果 JSON 输出路径")
    parser.add_argument("--max-success-examples", type=int, default=3000, help="最多保存多少条成功样例")
    parser.add_argument("--use-cot", action="store_true", help="启用CoT推理模式")
    parser.add_argument("--workers", type=int, default=4, help="并行worker数量")
    parser.add_argument("--verbose", action="store_true", help="打印诊断计数")
    args = parser.parse_args()
    
    eval_path = Path(args.eval_file or PROJECT_ROOT / "data" / "verilog_eval.json")
    if not eval_path.exists():
        print(f"未找到评估文件: {eval_path}")
        return
    
    with open(eval_path, "r", encoding="utf-8") as f:
        eval_data = json.load(f)
    if args.max_samples:
        eval_data = eval_data[:args.max_samples]
    
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
        attack_base_url = args.attack_base_url or tm_cfg.get("base_url")
        attack_model = args.attack_model or tm_cfg.get("model", "")
        attack_api_key = tm_cfg.get("api_key", "EMPTY")
    else:
        print("未找到 config.yaml，请指定参数")
        return
    
    print(f"📖 加载了 {len(eval_data)} 个样本")
    print(f"🔄 使用 {args.workers} 个并行worker...")
    print()
    
    # 共享变量
    results = []
    first_raw_response_holder = [None]
    first_tb_fail_holder = [None]
    success_examples = []
    success_rule_counter = Counter()
    
    # 锁
    first_raw_response_lock = Lock()
    first_tb_fail_lock = Lock()
    success_examples_lock = Lock()
    all_responses_lock = Lock()
    detailed_log_lock = Lock()
    results_lock = Lock()
    
    # 统计
    total_diag = {
        "attempts": 0,
        "parse_ok": 0,
        "transform_changed": 0,
        "tb_pass": 0,
        "judge_flipped": 0,
    }
    n_originally_correct = 0
    pass1, pass3, pass5, pass10 = 0, 0, 0, 0
    total = len(eval_data)
    n_per = args.n_per_task
    
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        futures = {
            executor.submit(
                process_single_task,
                item, idx, total,
                judge_client, attack_base_url, attack_model, attack_api_key,
                args.n_per_task, args.temperature, args.use_cot, args,
                first_raw_response_lock, first_tb_fail_lock,
                success_examples_lock, all_responses_lock, detailed_log_lock,
                first_raw_response_holder, first_tb_fail_holder,
                success_examples, success_rule_counter
            ): (item, idx)
            for idx, item in enumerate(eval_data)
        }
        
        pbar = tqdm(total=len(eval_data), desc="评估进度", unit="task")
        
        for future in as_completed(futures):
            result, diag, is_originally_correct = future.result()
            
            with results_lock:
                results.append(result)
                if is_originally_correct:
                    n_originally_correct += 1
                    for k in diag:
                        total_diag[k] += diag[k]
                    
                    if result["success_1"]:
                        pass1 += 1
                    if result["success_3"]:
                        pass3 += 1
                    if result["success_5"]:
                        pass5 += 1
                    if result["success_10"]:
                        pass10 += 1
            
            pbar.update(1)
            # 根据n_per_task动态显示指标
            postfix = {"p@1": f"{pass1}/{n_originally_correct}" if n_originally_correct else "0/0"}
            if n_per >= 3:
                postfix["p@3"] = f"{pass3}/{n_originally_correct}" if n_originally_correct else "0/0"
            if n_per >= 5:
                postfix["p@5"] = f"{pass5}/{n_originally_correct}" if n_originally_correct else "0/0"
            if n_per >= 10:
                postfix["p@10"] = f"{pass10}/{n_originally_correct}" if n_originally_correct else "0/0"
            pbar.set_postfix(postfix)
        
        pbar.close()
    
    # 输出统计
    denom = n_originally_correct if n_originally_correct else 1
    rate1 = pass1 / denom
    rate3 = pass3 / denom
    rate5 = pass5 / denom
    rate10 = pass10 / denom
    
    print("\n=== 攻击成功率（在「原判正确」的样本上）===")
    print(f"  原判正确任务数: {n_originally_correct} / {total}")
    print(f"  pass@1:  {pass1}/{n_originally_correct} = {rate1:.2%}")
    if n_per >= 3:
        print(f"  pass@3:  {pass3}/{n_originally_correct} = {rate3:.2%}")
    if n_per >= 5:
        print(f"  pass@5:  {pass5}/{n_originally_correct} = {rate5:.2%}")
    if n_per >= 10:
        print(f"  pass@10: {pass10}/{n_originally_correct} = {rate10:.2%}")
    
    if success_rule_counter:
        print("\n=== 攻击成功规则分布 ===")
        total_success = sum(success_rule_counter.values())
        for tid, count in success_rule_counter.most_common():
            print(f"  {tid}: {count} ({100*count/total_success:.1f}%)")
    
    # 输出诊断信息
    if total_diag["attempts"] > 0:
        print("\n=== 失败阶段诊断 ===")
        print(f"  总尝试次数: {total_diag['attempts']}")
        print(f"  解析成功: {total_diag['parse_ok']} ({100*total_diag['parse_ok']/total_diag['attempts']:.1f}%)")
        print(f"  变换成功: {total_diag['transform_changed']} ({100*total_diag['transform_changed']/total_diag['attempts']:.1f}%)")
        print(f"  Testbench通过: {total_diag['tb_pass']} ({100*total_diag['tb_pass']/total_diag['attempts']:.1f}%)")
        print(f"  判断翻转(攻击成功): {total_diag['judge_flipped']} ({100*total_diag['judge_flipped']/total_diag['attempts']:.1f}%)")
        print()
        print("  🔍 失败漏斗分析:")
        parse_fail = total_diag['attempts'] - total_diag['parse_ok']
        transform_fail = total_diag['parse_ok'] - total_diag['transform_changed']
        tb_fail = total_diag['transform_changed'] - total_diag['tb_pass']
        judge_fail = total_diag['tb_pass'] - total_diag['judge_flipped']
        print(f"    解析失败: {parse_fail} ({100*parse_fail/total_diag['attempts']:.1f}%)")
        print(f"    变换失败: {transform_fail} ({100*transform_fail/total_diag['attempts']:.1f}%)")
        print(f"    Testbench失败: {tb_fail} ({100*tb_fail/total_diag['attempts']:.1f}%)  ⚠️")
        print(f"    判断未翻转: {judge_fail} ({100*judge_fail/total_diag['attempts']:.1f}%)")
    
    # 保存结果
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        out = {
            "pass_at_1": rate1,
            "pass_at_3": rate3,
            "pass_at_5": rate5,
            "pass_at_10": rate10,
            "count_pass_1": pass1,
            "count_pass_3": pass3,
            "count_pass_5": pass5,
            "count_pass_10": pass10,
            "total_tasks": total,
            "n_originally_correct": n_originally_correct,
            "per_task": results,
        }
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)
        print(f"\n结果已保存到: {args.output}")


if __name__ == "__main__":
    main()
