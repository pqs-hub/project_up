#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
遍历所有攻击位置，生成详尽的攻击数据集（并行版本）

策略：
1. 对每个规则，遍历所有候选位置
2. 使用LLM生成参数（可选）
3. 只保留攻击成功的样本
4. 并行处理提高效率
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import json
import logging
import time
import argparse
import yaml
import random
from typing import List, Dict, Optional, Any
from collections import Counter
from tqdm import tqdm
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from core.transforms import create_engine
from core.target_model import TargetModelClient
from Testbench_valid import TestbenchRunner
from pipeline.cached_task_builder import CachedTaskBuilder
from config.prompts import format_attack_prompt, LLM_PARAM_RULES

# 导入原脚本的工具函数
import importlib.util
spec = importlib.util.spec_from_file_location("gen_module", PROJECT_ROOT / "pipeline" / "6_generate_attack_dataset.py")
gen_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gen_module)

analyze_transform_positions = gen_module.analyze_transform_positions
design_for_testbench = gen_module.design_for_testbench
create_attack_client = gen_module.create_attack_client
RENAME_RULES = gen_module.RENAME_RULES

logger = logging.getLogger(__name__)

ALL_RULES = ['T03', 'T07', 'T09', 'T10', 'T12', 'T19', 'T20', 'T30', 'T31', 'T32', 'T34', 'T41', 'T45', 'T47', 'T48']


class ExhaustiveAttackDatasetGenerator:
    """详尽攻击数据集生成器（遍历所有候选位置）"""
    
    def __init__(
        self,
        judge_client: TargetModelClient,
        param_gen_client: Optional[Any] = None,  # 参数生成模型，可选
        tb_runner: TestbenchRunner = None,
        use_cot: bool = True,
        skip_verify: bool = False,
    ):
        self.judge_client = judge_client
        self.param_gen_client = param_gen_client  # 可选的参数生成模型
        self.tb_runner = tb_runner
        self.use_cot = use_cot
        self.skip_verify = skip_verify
        
        # 全局统计
        self.stats = {
            'total_attempts': 0,
            'testbench_pass': 0,
            'judge_fooled': 0,
            'attack_success': 0,
            'testbench_passed_not_fooled': 0,
            'by_rule': {},
            'by_position': {},  # 记录每个位置的成功率
        }
        self.stats_lock = Lock()
        
        # 跟踪每个任务的攻击成功状态
        self.task_success_tracker = {}  # task_id -> bool
        self.task_success_lock = Lock()
    
    def generate_llm_param(self, rule_id: str, code: str, spec: str = "", **context) -> Optional[Any]:
        """使用LLM生成规则参数"""
        # 如果没有专门的参数生成模型，复用judge模型
        if not hasattr(self, 'param_gen_client') or self.param_gen_client is None:
            # 使用judge模型作为参数生成模型
            param_gen_client = self.judge_client
        else:
            param_gen_client = self.param_gen_client
            
        generator = gen_module.AttackDatasetGenerator(
            self.judge_client,
            param_gen_client,
            self.tb_runner,
            enable_llm_params=True,
            use_cot=self.use_cot
        )
        return generator.generate_llm_param(rule_id, code, spec, **context)
    
    def process_single_position(
        self,
        task_id: str,
        spec: str,
        rtl: str,
        testbench: str,
        rule_id: str,
        target_token: int,
        candidates: List = None
    ) -> Optional[Dict]:
        """处理单个候选位置的攻击（用于并行）"""
        engine = create_engine()
        
        # 准备参数 - 在执行时生成LLM参数
        params = {}
        if rule_id in LLM_PARAM_RULES:
            context = {}
            
            # T03需要target_signal来生成误导性冗余信号名
            if rule_id == 'T03' and candidates and target_token < len(candidates):
                target_item = candidates[target_token]
                if hasattr(target_item, 'name'):
                    context['target_signal'] = target_item.name
            
            # 生成LLM参数
            llm_param = self.generate_llm_param(rule_id, rtl, spec=spec, **context)
            if llm_param:
                param_name = LLM_PARAM_RULES[rule_id]['param_name']
                params = {param_name: llm_param}
        
        apply_params = params.copy()
        apply_params['target_token'] = target_token
        
        with self.stats_lock:
            self.stats['total_attempts'] += 1
        
        try:
            # 应用变换
            transformed = engine.apply_transform(rtl, rule_id, **apply_params)
            
            # ===== 提取语义位置信息 =====
            try:
                candidates = engine._get_candidates_for_transform(rtl, rule_id)
                if candidates and 0 <= target_token < len(candidates):
                    target_obj = candidates[target_token]
                    
                    # 提取target_signal
                    if hasattr(target_obj, 'name'):
                        params['target_signal'] = target_obj.name
                    elif hasattr(target_obj, 'lhs_name'):
                        params['target_signal'] = target_obj.lhs_name
                    
                    # 提取target_line
                    if hasattr(target_obj, 'start') and target_obj.start is not None:
                        params['target_line'] = rtl[:target_obj.start].count('\n') + 1
                    elif hasattr(target_obj, 'offset') and target_obj.offset is not None:
                        params['target_line'] = rtl[:target_obj.offset].count('\n') + 1
            except Exception:
                pass
            
            # 检查是否有变化
            if not transformed or transformed == rtl:
                return None
            
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
                    
                    tb_design = design_for_testbench(rtl_for_ref, transformed, testbench)
                    tb_result = self.tb_runner.run(tb_design, testbench)
                    
                    if not tb_result.get("passed", False):
                        return None
                    
                    with self.stats_lock:
                        self.stats['testbench_pass'] += 1
                except Exception:
                    return None
            else:
                with self.stats_lock:
                    self.stats['testbench_pass'] += 1
            
            # 判断模型评估
            verdict_transformed = self.judge_client.judge(spec, transformed, use_cot=self.use_cot)
            if not verdict_transformed:
                return None
            
            verdict_original = self.judge_client.judge(spec, rtl, use_cot=self.use_cot)
            is_fooled = verdict_transformed.get("is_correct") is False
            
            if is_fooled:
                with self.stats_lock:
                    self.stats['judge_fooled'] += 1
                    self.stats['attack_success'] += 1
                    if rule_id not in self.stats['by_rule']:
                        self.stats['by_rule'][rule_id] = 0
                    self.stats['by_rule'][rule_id] += 1
                    
                    # 记录位置统计
                    pos_key = f"{rule_id}_pos{target_token}"
                    if pos_key not in self.stats['by_position']:
                        self.stats['by_position'][pos_key] = 0
                    self.stats['by_position'][pos_key] += 1
                
                # 更新任务成功跟踪器
                with self.task_success_lock:
                    if task_id not in self.task_success_tracker:
                        self.task_success_tracker[task_id] = True
                        logger.info(f"✅ {task_id} | 首次攻击成功！")
                
                sample = {
                    'task_id': task_id,
                    'prompt': spec,
                    'original_code': rtl,
                    'transformed_code': transformed,
                    'attack_rule': rule_id,
                    'attack_params': params,
                    'position_index': target_token,  # 记录位置索引
                    'status': 'success',
                    'testbench_passed': True,
                    'judge_fooled': True,
                    'judge_confidence': verdict_transformed.get('confidence', 0.0),
                    'judge_cot_transformed': verdict_transformed.get('raw_output', ''),
                    'judge_transformed_answer': 'no',
                    'judge_cot_original': verdict_original.get('raw_output', '') if verdict_original else '',
                    'judge_original_answer': 'yes' if verdict_original and verdict_original.get('is_correct') else 'no',
                }
                
                logger.info(f"✅ {task_id} | {rule_id} | pos={target_token} | 攻击成功！")
                return sample
            else:
                # Testbench通过但judge未被欺骗，保存到另一个文件
                with self.stats_lock:
                    self.stats['testbench_passed_not_fooled'] += 1
                
                sample = {
                    'task_id': task_id,
                    'prompt': spec,
                    'original_code': rtl,
                    'transformed_code': transformed,
                    'attack_rule': rule_id,
                    'attack_params': params,
                    'position_index': target_token,  # 记录位置索引
                    'status': 'testbench_passed_judge_not_fooled',
                    'testbench_passed': True,
                    'judge_fooled': False,
                    'judge_confidence': verdict_transformed.get('confidence', 0.0),
                    'judge_cot_transformed': verdict_transformed.get('raw_output', ''),
                    'judge_transformed_answer': 'yes' if verdict_transformed.get('is_correct') else 'no',
                    'judge_cot_original': verdict_original.get('raw_output', '') if verdict_original else '',
                    'judge_original_answer': 'yes' if verdict_original and verdict_original.get('is_correct') else 'no',
                }
                
                logger.info(f"⚠️  {task_id} | {rule_id} | pos={target_token} | Testbench通过但Judge未被欺骗")
                return sample
            
        except Exception as e:
            logger.warning(f"{task_id} | {rule_id} | pos={target_token} | 错误: {e}")
        
        return None
    
    def generate_dataset_exhaustive(
        self,
        eval_data: List[Dict],
        rules_to_test: Optional[List[str]] = None,
        max_samples: Optional[int] = None,
        max_positions_per_rule: int = 10,  # 限制每个规则最多遍历多少个位置
        workers: int = 8,
        random_seed: Optional[int] = None,  # 随机种子，用于复现
        save_callback: Optional[callable] = None,  # 实时保存回调
    ) -> List[Dict]:
        """详尽生成攻击数据集（随机遍历候选位置）
        
        Args:
            random_seed: 随机种子，设置后可以复现相同的随机选择
        """
        all_samples = []
        
        # 设置随机种子
        if random_seed is not None:
            random.seed(random_seed)
            logger.info(f"随机种子: {random_seed}")
        
        if rules_to_test is None:
            rules_to_test = ALL_RULES
        
        eval_subset = eval_data[:max_samples] if max_samples else eval_data
        
        logger.info(f"开始生成详尽数据集：{len(eval_subset)}个任务 × {len(rules_to_test)}个规则")
        logger.info(f"每个规则随机选择最多 {max_positions_per_rule} 个候选位置")
        logger.info(f"使用 {workers} 个并行worker")
        
        # 先过滤出原判正确的任务
        valid_tasks = []
        
        if hasattr(self, 'skip_verify') and self.skip_verify:
            # 跳过验证阶段，假设所有任务都正确
            logger.info("⚡ 跳过原始代码验证阶段")
            valid_tasks = [item for item in eval_subset if item.get("canonical_solution", "")]
            logger.info(f"有效任务数: {len(valid_tasks)}/{len(eval_subset)} (跳过验证)")
        else:
            # 并行验证阶段
            def verify_single(item):
                task_id = item.get("task_id", "")
                spec = item.get("prompt", "")
                rtl = item.get("canonical_solution", "")
                
                if not rtl:
                    return None
                
                try:
                    original_verdict = self.judge_client.judge(spec, rtl, use_cot=self.use_cot)
                    if original_verdict and original_verdict.get("is_correct"):
                        return item
                except Exception as e:
                    logger.warning(f"验证 {task_id} 失败: {e}")
                return None
            
            # 并行验证
            valid_tasks = []
            with ThreadPoolExecutor(max_workers=workers) as executor:
                futures = {executor.submit(verify_single, item): item for item in eval_subset}
                
                pbar = tqdm(total=len(eval_subset), desc="验证原始代码", ncols=100)
                
                for future in as_completed(futures):
                    result = future.result()
                    if result:
                        valid_tasks.append(result)
                    pbar.update(1)
                    pbar.set_postfix({'valid': len(valid_tasks)})
                
                pbar.close()
            
            logger.info(f"有效任务数: {len(valid_tasks)}/{len(eval_subset)}")
        
        # 直接构建任务列表（缓存没有性能优势）
        jobs = []
        engine = create_engine()
        
        logger.info("正在构建攻击任务列表...")
        for item in tqdm(valid_tasks, desc="构建任务", ncols=100):
            task_id = item.get("task_id", "")
            spec = item.get("prompt", "")
            rtl = item.get("canonical_solution", "")
            testbench = item.get("test", "")
            
            for rule_id in rules_to_test:
                # 获取候选位置数量
                try:
                    candidates = engine._get_candidates_for_transform(rtl, rule_id)
                    
                    # ===== 关键改进：随机打乱候选位置顺序 =====
                    # 创建候选索引列表并随机打乱
                    candidate_indices = list(range(len(candidates)))
                    random.shuffle(candidate_indices)  # 打乱顺序
                    
                    # 只取前max_positions_per_rule个（已打乱）
                    selected_indices = candidate_indices[:max_positions_per_rule]
                    
                    # 为每个选中的候选位置创建一个job
                    # 注意：LLM参数在执行时生成，不在构建时生成，以加快启动速度
                    for pos_idx in selected_indices:
                        jobs.append((item, rule_id, pos_idx, candidates))
                    
                except Exception as e:
                    logger.warning(f"{task_id} | {rule_id} | 获取候选失败: {e}")
        
        total_jobs = len(jobs)
        logger.info(f"总任务数: {total_jobs}")
        
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    self.process_single_position,
                    item.get("task_id", ""),
                    item.get("prompt", ""),
                    item.get("canonical_solution", ""),
                    item.get("test", ""),
                    rule_id,
                    pos_idx,
                    candidates
                ): (item.get("task_id", ""), rule_id, pos_idx)
                for item, rule_id, pos_idx, candidates in jobs
            }
            
            pbar = tqdm(total=total_jobs, desc="生成攻击样本", unit="job", ncols=100)
            
            for future in as_completed(futures):
                task_id, rule_id, pos_idx = futures[future]
                try:
                    sample = future.result()
                    if sample:
                        all_samples.append(sample)
                        # 实时保存成功的样本
                        if save_callback:
                            save_callback(sample)
                except Exception as e:
                    logger.warning(f"{task_id} | {rule_id} | pos={pos_idx} | 异常: {e}")
                
                pbar.update(1)
                with self.stats_lock:
                    success_rate = self.stats['attack_success'] / max(1, self.stats['total_attempts']) * 100
                
                with self.task_success_lock:
                    successful_tasks = len(self.task_success_tracker)
                    task_success_rate = successful_tasks / max(1, len(valid_tasks)) * 100
                
                pbar.set_postfix({
                    'samples': len(all_samples),
                    'success': self.stats['attack_success'],
                    'tasks': successful_tasks,
                    'task_rate': f'{task_success_rate:.1f}%',
                    'rate': f'{success_rate:.1f}%'
                })
            
            pbar.close()
        
        return all_samples


def main():
    parser = argparse.ArgumentParser(
        description="随机遍历候选位置生成详尽攻击数据集"
    )
    parser.add_argument("--eval-file", type=str, required=True, help="评估数据文件路径")
    parser.add_argument("--output", type=str, required=True, help="攻击成功样本输出JSONL文件路径")
    parser.add_argument("--output-testbench-passed", type=str, help="testbench通过但judge未被欺骗的样本输出文件路径（可选）")
    parser.add_argument("--max-samples", type=int, default=None, help="最多处理多少个样本")
    parser.add_argument("--max-positions", type=int, default=10, help="每个规则随机选择最多多少个候选位置")
    parser.add_argument("--random-seed", type=int, default=42, help="随机种子，用于复现结果")
    parser.add_argument("--rules", type=str, default=None, help="要测试的规则列表，逗号分隔")
    parser.add_argument("--use-cot", action="store_true", default=True, help="判断模型使用CoT模式")
    parser.add_argument("--param-gen-base-url", type=str, help="参数生成模型base_url（可选，不设置则使用judge模型）")
    parser.add_argument("--param-gen-model", type=str, help="参数生成模型名称（可选，不设置则使用judge模型）")
    # 保留旧参数名以向后兼容
    parser.add_argument("--attack-base-url", type=str, help="(已弃用，请使用--param-gen-base-url)")
    parser.add_argument("--attack-model", type=str, help="(已弃用，请使用--param-gen-model)")
    parser.add_argument("--workers", type=int, default=8, help="并行worker数量")
    parser.add_argument("--skip-verify", action="store_true", help="跳过原始代码验证阶段（假设所有输入都正确）")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    
    args = parser.parse_args()
    
    # 设置日志级别
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # verbose模式也只显示INFO，不显示DEBUG
    logger.setLevel(logging.INFO)
    
    # 抑制第三方库的日志
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    
    # 加载配置
    config_path = Path(__file__).parent.parent / "config.yaml"
    with open(config_path, 'r') as f:
        config = yaml.safe_load(f)
    
    # 创建judge客户端
    tm_cfg = config.get("target_model", {})  # 配置文件中使用target_model键名
    judge_client = TargetModelClient(
        base_url=tm_cfg.get("base_url", "http://localhost:8001/v1"),
        api_key=tm_cfg.get("api_key", "EMPTY"),
        model=tm_cfg.get("model", "Qwen2.5-Coder-7B"),
        timeout=tm_cfg.get("timeout", 60),
        max_retries=tm_cfg.get("max_retries", 3),
        use_local_transformers=tm_cfg.get("use_local_transformers", False),
        max_new_tokens=tm_cfg.get("max_new_tokens", 512),
    )
    
    # 创建参数生成客户端（可选）
    param_gen_client = None
    if args.param_gen_base_url and args.param_gen_model:
        # 使用专门的参数生成模型
        param_gen_client = create_attack_client(
            args.param_gen_base_url,
            "EMPTY",
            args.param_gen_model
        )
        logger.info(f"使用专门的参数生成模型: {args.param_gen_model}")
    elif args.attack_base_url and args.attack_model:
        # 使用旧的参数名
        param_gen_client = create_attack_client(
            args.attack_base_url,
            "EMPTY",
            args.attack_model
        )
        logger.info(f"使用专门的参数生成模型: {args.attack_model}")
    else:
        # 复用judge模型作为参数生成模型
        # 创建适配器，让TargetModelClient具有post方法
        class TargetModelClientAdapter:
            def __init__(self, target_client):
                self.base_url = target_client.base_url
                self.api_key = "EMPTY"
                self.model = target_client.model
                self.client = target_client
            
            def post(self, url, **kwargs):
                # 将post调用转换为judge调用
                import json
                data = kwargs.get('json', {})
                messages = data.get('messages', [])
                if messages:
                    prompt = messages[-1].get('content', '')
                    try:
                        response = self.client.judge(prompt, "", use_cot=False)
                        if response:
                            # 模拟OpenAI格式的响应
                            mock_response = type('Response', (), {
                                'status_code': 200,
                                'json': lambda: {
                                    'choices': [{
                                        'message': {
                                            'content': response.get('raw_output', '')
                                        }
                                    }]
                                }
                            })()
                            return mock_response
                    except Exception:
                        pass
                
                # 返回错误响应
                return type('Response', (), {'status_code': 500})()
        
        param_gen_client = TargetModelClientAdapter(judge_client)
        logger.info("复用judge模型作为参数生成模型（使用适配器）")
    
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
    generator = ExhaustiveAttackDatasetGenerator(
        judge_client=judge_client,
        param_gen_client=param_gen_client,
        tb_runner=tb_runner,
        use_cot=args.use_cot,
        skip_verify=args.skip_verify,
    )
    
    # 生成数据集
    logger.info("开始生成详尽攻击数据集...")
    start_time = time.time()
    
    # 创建输出文件（实时保存）
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    # 断连续传：检查已存在的样本
    existing_samples = set()
    if output_path.exists():
        logger.info(f"检测到输出文件已存在，支持断连续传")
        with open(output_path, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    try:
                        sample = json.loads(line)
                        # 创建唯一标识：task_id + rule_id + position_index
                        key = (
                            sample.get('task_id', ''),
                            sample.get('attack_rule', ''),
                            sample.get('position_index', -1)
                        )
                        existing_samples.add(key)
                    except json.JSONDecodeError:
                        continue
        logger.info(f"已存在 {len(existing_samples)} 个样本，将跳过重复生成")
    
    logger.info(f"开始生成数据集，结果将实时保存到: {output_path}")
    
    # 生成数据集（带回调实时保存）
    success_count = 0
    skipped_count = 0
    
    def save_sample_callback(sample):
        """实时保存样本（攻击成功和testbench通过）"""
        nonlocal success_count, skipped_count
        
        # 确定保存路径
        if sample.get('status') == 'success':
            # 攻击成功的样本保存到主文件
            save_path = output_path
        elif sample.get('status') == 'testbench_passed_judge_not_fooled':
            # testbench通过但judge未被欺骗的样本保存到第二个文件
            if args.output_testbench_passed:
                save_path = Path(args.output_testbench_passed)
                save_path.parent.mkdir(parents=True, exist_ok=True)
            else:
                return  # 如果没有指定第二个文件，不保存
        else:
            return  # 其他状态不保存
        
        # 检查是否已存在（只检查主文件）
        key = (
            sample.get('task_id', ''),
            sample.get('attack_rule', ''),
            sample.get('position_index', -1)
        )
        if key in existing_samples and save_path == output_path:
            skipped_count += 1
            return
        
        # 保存样本
        with open(save_path, 'a', encoding='utf-8') as f:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
        
        if save_path == output_path:
            success_count += 1
            existing_samples.add(key)  # 只添加主文件的样本到已存在集合
            if success_count % 10 == 0:  # 每10个样本报告一次
                logger.info(f"已保存 {success_count} 个攻击成功样本")
                logger.info(f"新增 {success_count} 个成功样本（跳过 {skipped_count} 个重复）")
    
    all_samples = generator.generate_dataset_exhaustive(
        eval_data,
        rules_to_test=rules_to_test,
        max_samples=args.max_samples,
        max_positions_per_rule=args.max_positions,
        random_seed=args.random_seed,
        workers=args.workers,
        save_callback=save_sample_callback  # 添加保存回调
    )
    
    elapsed = time.time() - start_time
    
    logger.info(f"完成！耗时: {elapsed:.2f}秒")
    logger.info(f"总尝试: {generator.stats['total_attempts']}")
    logger.info(f"Testbench通过: {generator.stats['testbench_pass']}")
    logger.info(f"攻击成功（Judge被欺骗）: {generator.stats['attack_success']}")
    logger.info(f"Testbench通过但Judge未被欺骗: {generator.stats.get('testbench_passed_not_fooled', 0)}")
    logger.info(f"新增攻击成功样本: {success_count}")
    
    # 任务成功统计
    successful_tasks = len(generator.task_success_tracker)
    total_tasks = len(eval_data)
    logger.info(f"攻击成功的任务数: {successful_tasks}/{total_tasks}")
    logger.info(f"任务级攻击成功率: {successful_tasks/max(1,total_tasks)*100:.1f}%")
    
    if skipped_count > 0:
        logger.info(f"跳过重复: {skipped_count}")
        # 读取最终文件中的总样本数
        total_in_file = 0
        if output_path.exists():
            with open(output_path, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.strip():
                        total_in_file += 1
        logger.info(f"攻击成功文件总样本: {total_in_file}")
    
    # 检查第二个文件的样本数
    if args.output_testbench_passed:
        testbench_passed_path = Path(args.output_testbench_passed)
        if testbench_passed_path.exists():
            with open(testbench_passed_path, 'r', encoding='utf-8') as f:
                testbench_passed_count = sum(1 for line in f if line.strip())
            logger.info(f"Testbench通过但Judge未被欺骗样本数: {testbench_passed_count}")
            logger.info(f"已保存到: {testbench_passed_path}")
    
    logger.info(f"攻击成功率: {generator.stats['attack_success']/max(1, generator.stats['total_attempts'])*100:.1f}%")
    logger.info(f"Testbench通过率: {generator.stats['testbench_pass']/max(1, generator.stats['total_attempts'])*100:.1f}%")
    logger.info(f"攻击成功样本已保存到: {output_path}")
    
    # 断连续传提示
    if output_path.exists():
        logger.info("💡 提示：如需重新开始，请删除或重命名输出文件")


if __name__ == "__main__":
    main()
