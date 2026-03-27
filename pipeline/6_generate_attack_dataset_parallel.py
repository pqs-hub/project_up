#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
遍历所有攻击规则，对启用CoT的判断模型进行攻击，生成训练数据集（并行版本 + 全LLM参数生成）

功能：
1. 遍历所有15种攻击规则
2. 全部使用LLM生成参数（无默认参数模式）
3. 只保留攻击成功的样本（testbench通过 + CoT判断错误）
4. 并行处理多个任务
5. 输出JSONL格式的训练数据集
"""

import sys
from pathlib import Path

# 添加项目根目录到Python路径
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import json
import logging
import time
import argparse
import yaml
from typing import List, Dict, Optional, Any
from collections import Counter
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock

from core.target_model import TargetModelClient
from Testbench_valid import TestbenchRunner
from core.transforms import create_engine
from config.prompts import format_attack_prompt, LLM_PARAM_RULES

# 导入原脚本的工具函数
import importlib.util
spec = importlib.util.spec_from_file_location("gen_module", PROJECT_ROOT / "pipeline" / "6_generate_attack_dataset.py")
gen_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen_module)

# 重用原脚本的函数
analyze_transform_positions = gen_module.analyze_transform_positions
design_for_testbench = gen_module.design_for_testbench
create_attack_client = gen_module.create_attack_client
RENAME_RULES = gen_module.RENAME_RULES

logger = logging.getLogger(__name__)


# 所有15种规则（全部使用LLM生成参数）
ALL_RULES = ['T03', 'T07', 'T09', 'T10', 'T12', 'T19', 'T20', 'T30', 'T31', 'T32', 'T34', 'T41', 'T45', 'T47', 'T48']


class ParallelAttackDatasetGenerator:
    """并行攻击数据集生成器（全LLM参数生成）"""
    
    def __init__(
        self,
        judge_client: TargetModelClient,
        attack_client: Any,
        tb_runner: TestbenchRunner,
        use_cot: bool = True,
    ):
        self.judge_client = judge_client
        self.attack_client = attack_client
        self.tb_runner = tb_runner
        self.use_cot = use_cot
        
        # 全局统计
        self.stats = {
            'total_attempts': 0,
            'testbench_pass': 0,
            'judge_fooled': 0,
            'attack_success': 0,
            'by_rule': {},
        }
        self.stats_lock = Lock()
    
    def generate_llm_param(self, rule_id: str, code: str, spec: str = "", **context) -> Optional[Any]:
        """使用LLM生成规则参数"""
        # 重用原脚本的生成逻辑
        generator = gen_module.AttackDatasetGenerator(
            self.judge_client,
            self.attack_client,
            self.tb_runner,
            enable_llm_params=True,
            use_cot=self.use_cot
        )
        return generator.generate_llm_param(rule_id, code, spec, **context)
    
    def process_single_task_rule(
        self,
        task_id: str,
        spec: str,
        rtl: str,
        testbench: str,
        rule_id: str,
    ) -> List[Dict]:
        """处理单个任务的单个规则（用于并行）"""
        all_samples = []
        engine = create_engine()  # 每个线程独立的engine
        
        # 生成LLM参数
        context = {}
        
        # 根据规则类型提取上下文
        if rule_id == 'T20':
            from core.transforms import analyze, _extract_comment_insert_points
            vs = analyze(rtl)
            insert_points = _extract_comment_insert_points(rtl, vs)
            if insert_points:
                context['target_line'] = insert_points[0].line_text
        elif rule_id == 'T12':
            from core.transforms import analyze, Selectors
            vs = analyze(rtl)
            assigns = Selectors.continuous_assigns(vs)
            ternary_assigns = [a for a in assigns if a.rhs_expr and a.rhs_expr.kind == 'ternary']
            if ternary_assigns:
                context['target_expr'] = ternary_assigns[0].rhs_expr.predicate
        elif rule_id == 'T31':
            from core.transforms import analyze, Selectors
            vs = analyze(rtl)
            assigns = Selectors.continuous_assigns(vs)
            if assigns:
                context['target_expr'] = assigns[0].rhs
        elif rule_id == 'T34':
            import re
            signals = []
            for match in re.finditer(r'\breg\s+(?:\[[^\]]+\]\s*)?(\w+)', rtl):
                signals.append(match.group(1))
            for match in re.finditer(r'\bwire\s+(?:\[[^\]]+\]\s*)?(\w+)\s*[;=]', rtl):
                signals.append(match.group(1))
            if signals:
                context['signal_names'] = ', '.join(list(set(signals))[:5])
        
        # 生成LLM参数
        llm_param = self.generate_llm_param(rule_id, rtl, spec=spec, **context)
        
        if not llm_param and rule_id in LLM_PARAM_RULES:
            # LLM生成失败，跳过该规则
            logger.debug(f"{task_id} | {rule_id} | LLM参数生成失败，跳过")
            return []
        
        # 准备参数
        if rule_id in LLM_PARAM_RULES and llm_param:
            param_name = LLM_PARAM_RULES[rule_id]['param_name']
            params = {param_name: llm_param}
        else:
            params = {}
        
        # 默认使用第一个候选位置（target_token=0）
        # 但在记录时会转换为有语义的target_signal或target_line
        apply_params = params.copy()
        apply_params['target_token'] = 0
        
        with self.stats_lock:
            self.stats['total_attempts'] += 1
        
        try:
            # 应用变换
            transformed = engine.apply_transform(rtl, rule_id, **apply_params)
            
            # ===== 关键改进：将target_token转换为有语义的位置信息 =====
            # 获取候选列表，提取语义信息用于记录
            try:
                candidates = engine._get_candidates_for_transform(rtl, rule_id)
                if candidates and len(candidates) > 0:
                    target_obj = candidates[0]  # 我们使用的是第一个候选
                    
                    # 尝试提取target_signal
                    if hasattr(target_obj, 'name'):
                        params['target_signal'] = target_obj.name
                    elif hasattr(target_obj, 'lhs_name'):
                        params['target_signal'] = target_obj.lhs_name
                    
                    # 提取target_line（作为备选）
                    if hasattr(target_obj, 'start') and target_obj.start is not None:
                        params['target_line'] = rtl[:target_obj.start].count('\n') + 1
                    elif hasattr(target_obj, 'offset') and target_obj.offset is not None:
                        params['target_line'] = rtl[:target_obj.offset].count('\n') + 1
                    
                    # 移除target_token（记录时不需要无语义的索引）
                    if 'target_token' in params:
                        del params['target_token']
            except Exception:
                # 如果提取失败，保留原始params（可能包含LLM生成的参数）
                pass
            
            # 分析变换位置
            transform_positions = analyze_transform_positions(rtl, transformed, rule_id, params.get('target_token'))
            
            # 检查是否有变化
            if not transformed or transformed == rtl:
                return []
            
            # 运行testbench
            if self.tb_runner.available:
                try:
                    rtl_for_ref = rtl
                    if rule_id in RENAME_RULES:
                        rename_map = engine.get_last_rename_map()
                        if rename_map:
                            import re
                            for old_name, new_name in rename_map.items():
                                rtl_for_ref = re.sub(r"\b" + re.escape(old_name) + r"\b", new_name, rtl_for_ref)
                    
                    tb_design = design_for_testbench(rtl_for_ref, transformed)
                    tb_result = self.tb_runner.run(tb_design, testbench)
                    
                    if not tb_result.get("passed", False):
                        return []
                    
                    with self.stats_lock:
                        self.stats['testbench_pass'] += 1
                except Exception:
                    return []
            else:
                with self.stats_lock:
                    self.stats['testbench_pass'] += 1
            
            # 判断模型评估
            verdict_transformed = self.judge_client.judge(spec, transformed, use_cot=self.use_cot)
            if not verdict_transformed:
                return []
            
            verdict_original = self.judge_client.judge(spec, rtl, use_cot=self.use_cot)
            is_fooled = verdict_transformed.get("is_correct") is False
            
            if is_fooled:
                with self.stats_lock:
                    self.stats['judge_fooled'] += 1
                    self.stats['attack_success'] += 1
                    if rule_id not in self.stats['by_rule']:
                        self.stats['by_rule'][rule_id] = 0
                    self.stats['by_rule'][rule_id] += 1
                
                sample = {
                    'task_id': task_id,
                    'prompt': spec,
                    'original_code': rtl,
                    'transformed_code': transformed,
                    'attack_rule': rule_id,
                    'attack_params': params,
                    'status': 'success',
                    'testbench_passed': True,
                    'judge_fooled': True,
                    'judge_confidence': verdict_transformed.get('confidence', 0.0),
                    'judge_cot_transformed': verdict_transformed.get('raw_output', ''),
                    'judge_transformed_answer': 'no',
                    'judge_cot_original': verdict_original.get('raw_output', '') if verdict_original else '',
                    'judge_original_answer': 'yes' if verdict_original and verdict_original.get('is_correct') else 'no',
                    'transform_positions': transform_positions,
                }
                all_samples.append(sample)
                logger.info(f"✅ {task_id} | {rule_id} | 攻击成功！")
            
        except Exception as e:
            logger.debug(f"{task_id} | {rule_id} | 错误: {e}")
        
        return all_samples
    
    def generate_dataset_parallel(
        self,
        eval_data: List[Dict],
        rules_to_test: Optional[List[str]] = None,
        max_samples: Optional[int] = None,
        workers: int = 8,
    ) -> List[Dict]:
        """并行生成攻击数据集"""
        all_samples = []
        
        if rules_to_test is None:
            rules_to_test = ALL_RULES
        
        eval_subset = eval_data[:max_samples] if max_samples else eval_data
        
        logger.info(f"开始生成数据集：{len(eval_subset)}个任务 × {len(rules_to_test)}个规则")
        logger.info(f"使用 {workers} 个并行worker")
        
        # 先过滤出原判正确的任务
        valid_tasks = []
        for item in tqdm(eval_subset, desc="验证原始代码", ncols=100):
            task_id = item.get("task_id", "")
            spec = item.get("prompt", "")
            rtl = item.get("canonical_solution", "")
            
            if not rtl:
                continue
            
            original_verdict = self.judge_client.judge(spec, rtl, use_cot=self.use_cot)
            if original_verdict and original_verdict.get("is_correct"):
                valid_tasks.append(item)
        
        logger.info(f"有效任务数: {len(valid_tasks)}/{len(eval_subset)}")
        
        # 生成所有任务-规则对
        task_rule_pairs = [
            (item, rule_id)
            for item in valid_tasks
            for rule_id in rules_to_test
        ]
        
        total_jobs = len(task_rule_pairs)
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self.process_single_task_rule,
                    item.get("task_id", ""),
                    item.get("prompt", ""),
                    item.get("canonical_solution", ""),
                    item.get("test", ""),
                    rule_id
                ): (item.get("task_id", ""), rule_id)
                for item, rule_id in task_rule_pairs
            }
            
            pbar = tqdm(total=total_jobs, desc="生成攻击样本", unit="job", ncols=100)
            
            for future in as_completed(futures):
                task_id, rule_id = futures[future]
                try:
                    samples = future.result()
                    if samples:
                        all_samples.extend(samples)
                except Exception as e:
                    logger.debug(f"{task_id} | {rule_id} | 异常: {e}")
                
                pbar.update(1)
                with self.stats_lock:
                    success_rate = self.stats['attack_success'] / max(1, self.stats['total_attempts']) * 100
                    pbar.set_postfix({
                        'samples': len(all_samples),
                        'success': self.stats['attack_success'],
                        'rate': f'{success_rate:.1f}%'
                    })
            
            pbar.close()
        
        return all_samples


def main():
    parser = argparse.ArgumentParser(
        description="并行遍历攻击规则生成训练数据集（全LLM参数生成）"
    )
    parser.add_argument("--eval-file", type=str, required=True, help="评估数据文件路径")
    parser.add_argument("--output", type=str, required=True, help="输出JSONL文件路径")
    parser.add_argument("--max-samples", type=int, default=None, help="最多处理多少个样本")
    parser.add_argument("--rules", type=str, default=None, help="要测试的规则列表，逗号分隔（默认全部15种）")
    parser.add_argument("--use-cot", action="store_true", default=True, help="判断模型使用CoT模式")
    parser.add_argument("--attack-base-url", type=str, required=True, help="攻击模型base_url（用于LLM参数生成）")
    parser.add_argument("--attack-model", type=str, required=True, help="攻击模型名称")
    parser.add_argument("--workers", type=int, default=8, help="并行worker数量")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)
    
    # 加载配置
    config_path = PROJECT_ROOT / "config.yaml"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)
        tm_cfg = config.get("target_model", {})
    else:
        logger.warning("未找到config.yaml，使用默认配置")
        tm_cfg = {}
    
    # 创建判断模型客户端
    judge_client = TargetModelClient(
        base_url=tm_cfg.get("base_url", "http://localhost:8001/v1"),
        api_key=tm_cfg.get("api_key", "EMPTY"),
        model=tm_cfg.get("model", "Qwen2.5-Coder-7B"),
        timeout=tm_cfg.get("timeout", 60),
    )
    
    # 创建攻击模型客户端（用于LLM参数生成）
    attack_client = create_attack_client(
        args.attack_base_url,
        "EMPTY",
        args.attack_model
    )
    
    # 创建testbench runner
    tb_runner = TestbenchRunner(simulator="iverilog", timeout=30)
    
    # 加载评估数据
    eval_path = Path(args.eval_file)
    if not eval_path.exists():
        logger.error(f"评估文件不存在: {eval_path}")
        return
    
    with open(eval_path, "r", encoding="utf-8") as f:
        eval_data = json.load(f)
    
    # 解析规则列表
    rules_to_test = None
    if args.rules:
        rules_to_test = [r.strip() for r in args.rules.split(',')]
    
    # 创建生成器
    generator = ParallelAttackDatasetGenerator(
        judge_client=judge_client,
        attack_client=attack_client,
        tb_runner=tb_runner,
        use_cot=args.use_cot,
    )
    
    # 生成数据集
    logger.info("开始生成攻击数据集...")
    start_time = time.time()
    
    all_samples = generator.generate_dataset_parallel(
        eval_data,
        rules_to_test=rules_to_test,
        max_samples=args.max_samples,
        workers=args.workers,
    )
    
    elapsed = time.time() - start_time
    
    # 只保存攻击成功的样本
    successful_samples = [s for s in all_samples if s.get('status') == 'success']
    
    # 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for sample in successful_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    # 打印最终统计
    logger.info("=" * 60)
    logger.info(f"数据集生成完成！")
    logger.info(f"  耗时: {elapsed:.1f}秒")
    logger.info(f"  总尝试次数: {generator.stats['total_attempts']}")
    logger.info(f"  Testbench通过: {generator.stats['testbench_pass']}")
    logger.info(f"  判断模型被欺骗: {generator.stats['judge_fooled']}")
    logger.info(f"  攻击成功样本数: {len(successful_samples)}")
    logger.info(f"  输出文件: {output_path}")
    logger.info("=" * 60)
    
    # 统计成功规则分布
    if generator.stats['by_rule']:
        logger.info("攻击成功规则分布:")
        for rule_id, count in sorted(generator.stats['by_rule'].items(), key=lambda x: -x[1]):
            logger.info(f"  {rule_id}: {count}")
        logger.info("=" * 60)


if __name__ == "__main__":
    main()
