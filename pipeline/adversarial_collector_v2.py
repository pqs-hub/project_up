#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
语义锚定束搜索攻击引擎 (Semantic-Anchored Beam Search Engine)
用于 VeriObf-RL 框架的高质量多规则攻击数据收集

核心功能：
- 启发式束搜索 (Heuristic Beam Search)：深度为 3，宽度为 3
- 动态语义追踪 (Dynamic Semantic Tracking)：自动追踪信号修改
- 闭环 TB 验证 (Closed-loop Testbench)：确保功能等效
- 多步逻辑合成 (Multi-step Reasoning Synthesis)：合成推理链
"""

import os
import json
import uuid
import logging
import sys
from dataclasses import dataclass, field
from typing import List, Dict, Any, Tuple, Optional
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# 项目路径设置
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# 导入项目核心组件
from core.transforms import create_engine, analyze
from core.testbench import simulate_verilog
from core.target_model import TargetModelClient
from config.prompts import JUDGE_SYSTEM_PROMPT_COT

# 配置工业级日志
# 确保日志目录存在
log_dir = PROJECT_ROOT / "logs"
log_dir.mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(log_dir / "beam_search_attack.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


@dataclass
class AttackState:
    """代表搜索树中的一个代码状态节点"""
    code: str
    task_id: str
    history: List[Dict] = field(default_factory=list)  # 记录动作序列
    confidence: float = 1.0        # Victim 对此代码的置信度
    verdict: str = "yes"           # Victim 的判决结果
    depth: int = 0
    rename_map: Dict[str, str] = field(default_factory=dict)  # 追踪信号更名
    node_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])

    def get_last_signal(self) -> Optional[str]:
        """获取上一步攻击涉及的信号名"""
        if not self.history:
            return None
        return self.history[-1].get('signal')


class AdversarialCollectorV2:
    """
    最高质量多规则攻击收集引擎：
    采用 Beam Search 算法在规则空间中寻找能使判决翻转的最优攻击路径。
    """
    
    def __init__(
        self, 
        target_model_client: TargetModelClient,
        beam_width: int = 3, 
        max_depth: int = 3,
        max_workers: int = 1
    ):
        """
        初始化收集器
        
        Args:
            target_model_client: 目标判断模型客户端
            beam_width: 束搜索宽度
            max_depth: 最大搜索深度
            max_workers: 并行worker数量
        """
        self.target_client = target_model_client
        self.engine = create_engine()
        self.beam_width = beam_width
        self.max_depth = max_depth
        self.max_workers = max_workers
        
        # 预定义专家协同规则：如果前一步用了 Key，下一步优先尝试 Value
        self.synergy_chains = {
            "T34": ["T20", "T12", "T31"],  # 重命名后接注释或中间变量
            "T12": ["T19", "T31", "T45"],  # 反义变量后接死代码或逻辑矛盾
            "T32": ["T47", "T48", "T07"],  # 声明混淆后接结构打碎
            "T20": ["T19", "T34", "T12"]   # 注释误导后用命名或逻辑夯实
        }
        
        # 所有可用规则列表
        self.all_rules = [
            "T34", "T12", "T20", "T19", "T31", "T32", "T47", 
            "T09", "T10", "T30", "T07", "T48", "T41", "T45", "T03"
        ]

    def process_sample(self, sample: Dict[str, Any]) -> List[Dict]:
        """
        对单个 Verilog 任务进行深度对抗搜索
        
        Args:
            sample: 包含 task_id, prompt, canonical_solution, test 等的样本
            
        Returns:
            成功翻转的攻击路径列表
        """
        task_id = sample['task_id']
        spec = sample['prompt']
        original_code = sample['canonical_solution']
        tb = sample['test']
        
        # 获取初始置信度
        initial_verdict = sample.get('judge_verdict', {})
        initial_conf = initial_verdict.get('confidence', 1.0)
        
        logger.info(f">>> Starting Attack Search on [{task_id}] (Init Conf: {initial_conf})")
        
        # 初始化根节点
        root = AttackState(
            code=original_code, 
            task_id=task_id, 
            confidence=initial_conf
        )
        beam = [root]
        successful_traces = []

        for depth in range(1, self.max_depth + 1):
            next_candidates = []
            
            for parent in beam:
                # 1. 探测动作空间：根据 AST 寻找所有可用的规则和位置
                actions = self._probe_valid_actions(parent)
                logger.debug(f"  Depth {depth}: Found {len(actions)} actions for {task_id}")
                
                if not actions:
                    logger.warning(f"  No valid actions found at depth {depth} for {task_id}")
                    continue
                
                for action in actions:
                    # 2. 执行变换并进行 TB 验证（确保功能等效）
                    transformed_code, meta = self._execute_step(parent, action, tb)
                    if not transformed_code:
                        logger.debug(f"    Transform failed: {action['rule']} at line {action['line']}")
                        continue
                    
                    logger.debug(f"    Evaluating: {action['rule']} at line {action['line']}")
                    
                    # 3. 对抗性评估：调用 Victim 模型获取置信度和判决
                    verdict, confidence, raw_output = self._evaluate_adversarial_impact(
                        transformed_code, spec
                    )
                    
                    logger.debug(f"    Result: verdict={verdict}, conf={confidence:.4f}")
                    
                    # 创建子节点
                    child_node = AttackState(
                        code=transformed_code,
                        task_id=task_id,
                        history=parent.history + [{
                            "rule": action['rule'],
                            "line": meta['line'],
                            "signal": meta['signal'],
                            "params": action['params'],
                            "victim_reasoning": raw_output
                        }],
                        confidence=confidence,
                        verdict=verdict,
                        depth=depth,
                        rename_map={**parent.rename_map, **meta.get('new_renames', {})}
                    )

                    # 4. 判定翻转 (Verdict Flip) 成功
                    if verdict == "no":
                        logger.info(f"🔥 [SUCCESS] Task {task_id} flipped at depth {depth}!")
                        final_trace = self._synthesize_final_data(sample, child_node)
                        successful_traces.append(final_trace)
                        # 如果只需一条最优路径，可以提前返回
                    
                    next_candidates.append(child_node)
            
            # 5. 束搜索剪枝：选择置信度下降最明显的 Top-K 分支
            # 排序标准：翻转成功优先，其次是置信度下降幅度
            next_candidates.sort(
                key=lambda x: (
                    1.0 if x.verdict == "no" else 0.0, 
                    root.confidence - x.confidence
                ), 
                reverse=True
            )
            beam = next_candidates[:self.beam_width]
            
            if not beam:
                break
            
            logger.info(
                f"  Depth {depth}: {len(next_candidates)} candidates, "
                f"keeping top {len(beam)}"
            )

        logger.info(f"<<< Finished [{task_id}]: {len(successful_traces)} successful traces")
        return successful_traces

    def _probe_valid_actions(self, state: AttackState) -> List[Dict]:
        """
        基于语义关联和协同矩阵，生成当前状态下最具潜力的动作列表
        
        Args:
            state: 当前搜索状态
            
        Returns:
            动作列表，每个动作包含 rule, target_token, params 等
        """
        actions = []
        
        last_rule = state.history[-1]['rule'] if state.history else None
        last_signal = state.get_last_signal()
        
        # 确定规则尝试顺序
        prioritized_rules = self.synergy_chains.get(last_rule, [])
        other_rules = [r for r in self.all_rules if r not in prioritized_rules]
        rule_queue = prioritized_rules + other_rules

        for rule in rule_queue:
            try:
                # 获取该规则的所有候选位置
                candidates = self.engine._get_candidates_for_transform(state.code, rule)
                if not candidates:
                    continue
                
                # 语义锚定：如果在上一步改过某个信号，这一步优先搜索包含该信号的位置
                best_idx = 0
                if last_signal:
                    # 检查重命名后的新名字
                    target_name = state.rename_map.get(last_signal, last_signal)
                    for i, cand in enumerate(candidates):
                        if target_name in str(cand):
                            best_idx = i
                            break
                
                # 每个规则只尝试最具潜力的 2 个位置，防止宽度爆炸
                indices_to_try = [best_idx, (best_idx + 1) % len(candidates)]
                indices_to_try = indices_to_try[:min(2, len(candidates))]
                
                for idx in indices_to_try:
                    try:
                        line, sig = self.engine.get_target_line_signal(
                            state.code, rule, idx
                        )
                        
                        # 生成该规则的默认参数
                        params = self._get_default_params(rule)
                        
                        actions.append({
                            "rule": rule,
                            "target_token": idx,
                            "params": params,
                            "line": line,
                            "signal": sig
                        })
                    except Exception as e:
                        logger.debug(f"Failed to get line/signal for {rule}[{idx}]: {e}")
                        continue
                        
            except Exception as e:
                logger.debug(f"Failed to probe rule {rule}: {e}")
                continue
        
        # 每层限制探测动作数量
        return actions[:10]

    def _execute_step(
        self, 
        parent: AttackState, 
        action: Dict, 
        tb: str
    ) -> Tuple[Optional[str], Dict]:
        """
        执行变换并验证 TB
        
        Args:
            parent: 父状态节点
            action: 要执行的动作
            tb: 测试台代码
            
        Returns:
            (变换后的代码, 元数据字典) 或 (None, {}) 如果失败
        """
        try:
            # 应用变换
            new_code = self.engine.apply_transform(
                parent.code,
                action['rule'],
                target_token=action['target_token'],
                **action['params']
            )
            
            # 获取重命名映射（如果有）
            renames = self.engine.get_last_rename_map() or {}
            
            # 功能等价性验证是底线
            if simulate_verilog(new_code, tb):
                return new_code, {
                    "line": action['line'],
                    "signal": action['signal'],
                    "new_renames": renames
                }
            else:
                logger.debug(
                    f"TB verification failed for {action['rule']} "
                    f"at line {action['line']}"
                )
                
        except Exception as e:
            logger.debug(f"Transform execution failed: {e}")
        
        return None, {}

    def _evaluate_adversarial_impact(
        self, 
        code: str, 
        spec: str
    ) -> Tuple[str, float, str]:
        """
        调用 Victim Judge 获取对抗效果
        
        Args:
            code: 混淆后的代码
            spec: 功能规格
            
        Returns:
            (判决结果, 置信度, 原始输出)
        """
        try:
            result = self.target_client.judge(spec, code, use_cot=True)
            
            if result is None:
                return "yes", 1.0, ""
            
            is_correct = result.get('is_correct', True)
            confidence = result.get('confidence', 1.0)
            raw_output = result.get('raw_output', '')
            
            verdict = "yes" if is_correct else "no"
            
            return verdict, confidence, raw_output
            
        except Exception as e:
            logger.warning(f"Evaluation failed: {e}")
            return "yes", 1.0, ""

    def _get_default_params(self, rule: str) -> Dict:
        """
        获取规则的默认参数
        
        Args:
            rule: 规则 ID
            
        Returns:
            参数字典
        """
        # 这里返回空字典，使用规则的默认参数
        # 如果需要针对特定规则自定义参数，可以在这里添加
        return {}

    def _synthesize_final_data(
        self, 
        sample: Dict, 
        final_state: AttackState
    ) -> Dict:
        """
        合成高质量的 SFT/RL 数据条目
        
        Args:
            sample: 原始样本
            final_state: 最终成功的状态节点
            
        Returns:
            合成的训练数据
        """
        # 构建攻击链描述
        history_desc = "\n".join([
            f"Step {i+1}: Rule {h['rule']} at line {h['line']} on signal '{h['signal']}'"
            for i, h in enumerate(final_state.history)
        ])
        
        # 简化版思考生成（可以接入更强的模型来生成更详细的分析）
        thought = f"""Multi-step attack analysis:
Specification: {sample['prompt'][:100]}...

Attack trace:
{history_desc}

Strategy: This attack applies {len(final_state.history)} transformations to mislead the judge model. 
The initial confidence was {sample.get('judge_verdict', {}).get('confidence', 1.0):.2f}, 
and after the transformations it dropped to {final_state.confidence:.2f}, 
causing a verdict flip from 'yes' to 'no'.

Key tactics:
1. Semantic confusion through naming and comments
2. Structural obfuscation to hide true functionality
3. Logical complexity to overwhelm analysis
"""
        
        return {
            "task_id": sample['task_id'],
            "original_code": sample['canonical_solution'],
            "adversarial_code": final_state.code,
            "thought": thought,
            "original_confidence": sample.get('judge_verdict', {}).get('confidence', 1.0),
            "final_confidence": final_state.confidence,
            "attack_chain": final_state.history,
            "verdict_flip": True,
            "search_depth": final_state.depth
        }

    def process_dataset(
        self, 
        samples: List[Dict],
        save_path: Optional[Path] = None
    ) -> List[Dict]:
        """
        批量处理数据集
        
        Args:
            samples: 样本列表
            save_path: 保存路径（可选）
            
        Returns:
            所有成功的攻击路径
        """
        all_results = []
        
        if self.max_workers > 1:
            # 多线程处理
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                futures = {
                    executor.submit(self.process_sample, s): s 
                    for s in samples
                }
                
                for future in as_completed(futures):
                    try:
                        res_list = future.result()
                        if res_list:
                            all_results.extend(res_list)
                            logger.info(f"Total successful flips: {len(all_results)}")
                    except Exception as e:
                        logger.error(f"Sample processing failed: {e}")
        else:
            # 单线程处理
            for i, sample in enumerate(samples):
                logger.info(f"Processing sample {i+1}/{len(samples)}")
                try:
                    res_list = self.process_sample(sample)
                    if res_list:
                        all_results.extend(res_list)
                        logger.info(f"Total successful flips: {len(all_results)}")
                except Exception as e:
                    logger.error(f"Sample {sample.get('task_id')} failed: {e}")
        
        # 保存结果
        if save_path and all_results:
            save_path.parent.mkdir(parents=True, exist_ok=True)
            with open(save_path, 'w', encoding='utf-8') as f:
                json.dump(all_results, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(all_results)} results to {save_path}")
        
        return all_results


def main():
    """主函数示例"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="语义锚定束搜索攻击引擎"
    )
    parser.add_argument(
        "--dataset",
        type=str,
        required=True,
        help="输入数据集路径"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/gold_multi_rule_attacks.json",
        help="输出路径"
    )
    parser.add_argument(
        "--beam-width",
        type=int,
        default=3,
        help="束搜索宽度"
    )
    parser.add_argument(
        "--max-depth",
        type=int,
        default=3,
        help="最大搜索深度"
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="限制处理样本数量"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8001/v1",
        help="目标模型 API URL"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="Qwen/Qwen2.5-Coder-7B-Instruct",
        help="目标模型名称"
    )
    parser.add_argument(
        "--workers",
        type=int,
        default=1,
        help="并行 worker 数量"
    )
    
    args = parser.parse_args()
    
    # 初始化目标模型客户端
    target_client = TargetModelClient(
        base_url=args.base_url,
        api_key="EMPTY",
        model=args.model,
        timeout=120
    )
    
    # 初始化收集器
    collector = AdversarialCollectorV2(
        target_model_client=target_client,
        beam_width=args.beam_width,
        max_depth=args.max_depth,
        max_workers=args.workers
    )
    
    # 载入数据集
    logger.info(f"Loading dataset from {args.dataset}")
    with open(args.dataset, 'r', encoding='utf-8') as f:
        samples = json.load(f)
    
    # 过滤出适合作为攻击目标的高置信度样本
    if isinstance(samples, list):
        # 检查是否有 judge_verdict 字段
        if samples and 'judge_verdict' in samples[0]:
            hard_samples = [
                s for s in samples 
                if s.get('judge_verdict', {}).get('confidence', 0) > 0.8
            ]
            logger.info(
                f"Filtered {len(hard_samples)} high-confidence samples "
                f"(>0.8) from {len(samples)} total"
            )
        else:
            hard_samples = samples
            logger.info(f"Using all {len(samples)} samples (no confidence filtering)")
    else:
        logger.error("Dataset must be a list")
        return
    
    # 限制数量
    if args.limit:
        hard_samples = hard_samples[:args.limit]
        logger.info(f"Limited to {len(hard_samples)} samples")
    
    # 处理数据集
    results = collector.process_dataset(
        hard_samples,
        save_path=Path(args.output)
    )
    
    logger.info(f"Done! Total successful attacks: {len(results)}")


if __name__ == "__main__":
    main()
