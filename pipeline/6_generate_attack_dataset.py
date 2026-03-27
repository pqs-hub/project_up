#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
遍历所有攻击规则，对启用CoT的判断模型进行攻击，生成训练数据集

功能：
1. 遍历所有可用的攻击规则（T07, T19, T20, T34等）
2. 对每个规则尝试多个参数组合
3. 使用LLM生成某些规则的参数（如注释内容、重命名映射等）
4. 只保留攻击成功的样本（testbench通过 + CoT判断错误）
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
import difflib
import requests
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock
from typing import List, Dict, Optional, Any
from collections import Counter
from tqdm import tqdm

from core.target_model import TargetModelClient
from Testbench_valid import TestbenchRunner
from core.transforms import create_engine
from config.prompts import format_attack_prompt, LLM_PARAM_RULES

logger = logging.getLogger(__name__)


# 需要特殊处理重命名的规则（信号重命名会影响testbench）
RENAME_RULES = {'T34'}

# 每个规则的默认参数组合（全部15种规则）
DEFAULT_PARAM_SETS = {
    'T03': [{}],  # 冗余逻辑，无参数
    'T07': [{}],  # assign重排序，无参数
    'T09': [{}],  # DeMorgan AND，无参数
    'T10': [{}],  # DeMorgan OR，无参数
    'T12': [{}],  # 中间信号抽取，默认自动生成wire名
    'T19': [
        {},  # 默认死代码
        {'custom_dead_stmts': 'temp_var = 0;'},
    ],
    'T20': [
        {},  # 默认注释
    ],
    'T30': [{}],  # 常量恒等变换，无参数
    'T31': [{}],  # 简单中间信号，默认自动生成wire名
    'T32': [
        {},  # 默认位宽算术
        {'use_multiply': True},
    ],
    'T34': [
        {},  # 默认语义反转映射
    ],
    'T41': [{}],  # Case分支重排，无参数
    'T45': [{}],  # 伪组合循环，无参数
    'T47': [{}],  # 数据流分解，无参数
    'T48': [{}],  # 反拓扑排序，无参数
}


def analyze_transform_positions(original: str, transformed: str, rule_id: str, target_token: Optional[int] = None) -> Dict[str, Any]:
    """分析变换应用的位置信息（简化版：只记录行号和目标token）"""
    if not transformed or original == transformed:
        return {'changed': False}
    
    original_lines = original.splitlines()
    transformed_lines = transformed.splitlines()
    
    # 根据规则类型进行不同的位置分析
    if rule_id == 'T19':
        # T19死代码插入：只记录插入位置（always @(*)块的起始行）
        insert_line = None
        for i, line in enumerate(transformed_lines, 1):
            if 'always @(*)' in line and (i > len(original_lines) or 'always @(*)' not in original_lines[i-1]):
                insert_line = i
                break
        applied_lines = [insert_line] if insert_line else []
        
    elif rule_id == 'T20':
        # T20注释插入：找到注释添加的行
        applied_lines = []
        for i, (orig_line, trans_line) in enumerate(zip(original_lines, transformed_lines), 1):
            if '//' in trans_line and '//' not in orig_line:
                applied_lines.append(i)
        
    elif rule_id in ['T12', 'T31']:
        # T12/T31中间信号插入：找到wire声明的起始行
        insert_line = None
        for i, line in enumerate(transformed_lines, 1):
            if line.strip().startswith('wire ') and (i > len(original_lines) or not original_lines[i-1].strip().startswith('wire ')):
                insert_line = i
                break
        applied_lines = [insert_line] if insert_line else []
        
    else:
        # 其他规则：记录所有变更的行
        applied_lines = []
        for i, (orig_line, trans_line) in enumerate(zip(original_lines, transformed_lines), 1):
            if orig_line != trans_line:
                applied_lines.append(i)
        
        # 处理新增的行
        if len(transformed_lines) > len(original_lines):
            for i in range(len(original_lines) + 1, len(transformed_lines) + 1):
                applied_lines.append(i)
    
    return {
        'changed': True,
        'applied_lines': applied_lines,
        'target_token': target_token
    }


def design_for_testbench(original_rtl: str, transformed_rtl: str, testbench: str = None) -> str:
    """拼装供 testbench 使用的 design：将模块名改为testbench期望的名称。
    动态从testbench中提取期望的模块名。"""
    import re
    
    # 检查原始RTL的模块名
    original_module_match = re.search(r'module\s+(\w+)\s*\(', original_rtl.strip())
    if not original_module_match:
        return transformed_rtl
    
    original_module_name = original_module_match.group(1)
    
    # 默认使用原始模块名
    expected_module_name = original_module_name
    
    # 如果提供了testbench，尝试从中提取期望的模块名
    if testbench:
        # 查找testbench中实例化的模块名
        # 模式: module_name dut(...)
        dut_match = re.search(r'(\w+)\s+dut\s*\(', testbench)
        if dut_match:
            expected_module_name = dut_match.group(1)
        else:
            # 备用模式: 查找 .module_name(...)
            alt_match = re.search(r'\.(\w+)\s*\(', testbench)
            if alt_match:
                expected_module_name = alt_match.group(1)
    
    # 将变换后的RTL中的模块名改为testbench期望的名称
    dut_part = re.sub(
        rf"\bmodule\s+{re.escape(original_module_name)}\b", 
        f"module {expected_module_name}", 
        transformed_rtl.strip(), 
        count=1
    )
    
    # 如果变换后的RTL被重命名为TopModule，也改过来
    dut_part = re.sub(rf"\bmodule\s+TopModule\b", f"module {expected_module_name}", dut_part, count=1)
    
    # 如果变换后的RTL被重命名为RefModule，也改过来  
    dut_part = re.sub(rf"\bmodule\s+RefModule\b", f"module {expected_module_name}", dut_part, count=1)
    
    return dut_part


class AttackDatasetGenerator:
    """攻击数据集生成器"""
    
    def __init__(
        self,
        judge_client: TargetModelClient,
        attack_client: Any = None,
        tb_runner: TestbenchRunner = None,
        enable_llm_params: bool = True,
        use_cot: bool = True,
        workers: int = 1,
    ):
        self.judge_client = judge_client
        self.attack_client = attack_client
        self.tb_runner = tb_runner
        self.enable_llm_params = enable_llm_params
        self.use_cot = use_cot
        self.workers = workers
        
        # 创建变换引擎
        self.engine = create_engine()
        
        # 统计信息（需要线程安全）
        self.stats = {
            'total_attempts': 0,
            'testbench_pass': 0,
            'judge_fooled': 0,
            'attack_success': 0,
            'by_rule': {},
        }
        self.stats_lock = Lock()
    
    def generate_llm_param(self, rule_id: str, code: str, spec: str = "", **context) -> Optional[Any]:
        """使用LLM生成规则参数（专业版）"""
        if not self.enable_llm_params or not self.attack_client:
            return None
        
        if rule_id not in LLM_PARAM_RULES:
            return None
        
        # 导入格式化函数
        from config.prompts import format_attack_prompt
        
        # 准备参数
        signal_names = ""
        writable_signals = "<unknown>"
        readable_signals = "<unknown>"
        target_line = context.get('target_line', '')  # 从context获取目标行
        target_expr = context.get('target_expr', '')  # 从context获取目标表达式
        
        # 为T19提取可写和可读信号
        if rule_id == 'T19':
            import re
            # 提取可写信号（output reg + 内部reg）
            writable = []
            for match in re.finditer(r'\breg\s+(?:\[[^\]]+\]\s*)?(\w+)', code):
                writable.append(match.group(1))
            
            # 提取可读信号（input + reg + wire + parameter）
            readable = []
            # input端口
            for match in re.finditer(r'\binput\s+(?:wire\s+)?(?:\[[^\]]+\]\s*)?(\w+)', code):
                readable.append(match.group(1))
            # 添加所有reg（既可读又可写）
            readable.extend(writable)
            # wire信号
            for match in re.finditer(r'\bwire\s+(?:\[[^\]]+\]\s*)?(\w+)\s*[;=]', code):
                readable.append(match.group(1))
            
            # 去重并格式化
            if writable:
                writable_signals = ', '.join(list(set(writable))[:10])
                logger.debug(f"T19: 提取可写信号 -> {writable_signals}")
            else:
                writable_signals = "temp, data"  # fallback
                logger.warning("T19: 未找到可写信号，使用默认值")
            
            if readable:
                readable_signals = ', '.join(list(set(readable))[:15])
                logger.debug(f"T19: 提取可读信号 -> {readable_signals}")
            else:
                readable_signals = "clk, rst, 1'b0, 1'b1"  # fallback
                logger.warning("T19: 未找到可读信号，使用默认值")
        
        # 为T34提取所有内部信号名
        elif rule_id == 'T34':
            import re
            # 提取所有reg和wire声明的信号名（排除端口声明）
            signals = []
            # 查找reg声明
            for match in re.finditer(r'\breg\s+(?:\[[^\]]+\]\s*)?(\w+)', code):
                signals.append(match.group(1))
            # 查找wire声明（非端口）
            for match in re.finditer(r'\bwire\s+(?:\[[^\]]+\]\s*)?(\w+)\s*[;=]', code):
                signals.append(match.group(1))
            
            if not signals:
                # 如果没有找到内部信号，跳过LLM生成
                logger.debug(f"T34: 未找到内部信号，跳过LLM参数生成")
                return None
            
            # 去重并限制数量（避免太多信号）
            signals = list(set(signals))[:5]  # 最多5个信号
            signal_names = ', '.join(signals)
        
        # 格式化prompt
        prompt = format_attack_prompt(
            rule_id=rule_id,
            code_snippet=code,
            task_prompt=spec,
            signal_names=signal_names,
            writable_signals=writable_signals,
            readable_signals=readable_signals,
            target_line=target_line,
            target_expr=target_expr,
        )
        
        try:
            response = self.attack_client.post(
                f"{self.attack_client.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.attack_client.api_key}",
                },
                json={
                    "model": self.attack_client.model,
                    "messages": [
                        {"role": "system", "content": "你是Verilog代码混淆专家。"},
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.7,
                    "max_tokens": 200,
                },
                timeout=30,
            )
            
            if response.status_code == 200:
                data = response.json()
                content = data['choices'][0]['message']['content'].strip()
                
                # 解析不同类型的参数
                if rule_id == 'T34':
                    # T34: 必须解析JSON（custom_map字典）
                    try:
                        import re
                        json_match = re.search(r'\{[^}]+\}', content)
                        if json_match:
                            return json.loads(json_match.group())
                    except:
                        pass
                elif rule_id in ('T12', 'T31'):
                    # T12/T31: 优先接受直接wire名，JSON作为备选
                    import re
                    
                    # 清理内容
                    result = content.strip()
                    
                    # 移除markdown代码块标记
                    result = re.sub(r'```(?:json|verilog|text)?\s*', '', result).strip()
                    result = re.sub(r'```\s*$', '', result).strip()
                    result = result.strip('"').strip("'").strip()
                    
                    # 尝试JSON解析（备选方案）
                    if result.startswith('{'):
                        try:
                            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', result)
                            if json_match:
                                parsed = json.loads(json_match.group())
                                
                                if 'parameters' in parsed and 'wire_name' in parsed['parameters']:
                                    wire_name = parsed['parameters']['wire_name']
                                    if wire_name:
                                        logger.debug(f"{rule_id}: 解析JSON成功 -> {wire_name}")
                                        return wire_name
                                elif 'wire_name' in parsed:
                                    wire_name = parsed['wire_name']
                                    if wire_name:
                                        logger.debug(f"{rule_id}: 解析JSON成功 -> {wire_name}")
                                        return wire_name
                        except (json.JSONDecodeError, Exception) as e:
                            # JSON解析失败，忽略错误，使用直接文本
                            logger.debug(f"{rule_id}: JSON解析失败，使用直接文本: {e}")
                    
                    # 直接使用wire名（优先方案）
                    # 验证是否是合法的Verilog标识符
                    if result and re.match(r'^[A-Za-z_]\w*$', result):
                        logger.debug(f"{rule_id}: 直接使用wire名 -> {result}")
                        return result
                    
                    return None
                elif rule_id == 'T19':
                    # T19: 优先接受直接Verilog语句，JSON作为备选
                    import re
                    
                    # 清理内容
                    result = content.strip()
                    
                    # 移除markdown代码块标记
                    result = re.sub(r'```(?:json|verilog)?\s*', '', result).strip()
                    result = re.sub(r'```\s*$', '', result).strip()
                    result = result.strip('"').strip("'").strip()
                    
                    # 尝试JSON解析（备选方案）
                    if result.startswith('{'):
                        try:
                            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', result)
                            if json_match:
                                parsed = json.loads(json_match.group())
                                
                                if 'parameters' in parsed and 'custom_dead_stmts' in parsed['parameters']:
                                    stmt = parsed['parameters']['custom_dead_stmts']
                                    if stmt:
                                        logger.debug(f"T19: 解析JSON成功 -> {stmt[:50]}")
                                        return stmt
                                elif 'custom_dead_stmts' in parsed:
                                    stmt = parsed['custom_dead_stmts']
                                    if stmt:
                                        logger.debug(f"T19: 解析JSON成功 -> {stmt[:50]}")
                                        return stmt
                        except (json.JSONDecodeError, Exception) as e:
                            # JSON解析失败，忽略错误，使用直接文本
                            logger.debug(f"T19: JSON解析失败，使用直接文本: {e}")
                    
                    # 直接使用Verilog语句（优先方案）
                    # 验证是否看起来像Verilog代码（包含 <= 或 = 或 if 等）
                    if result and (';' in result or 'if' in result or 'case' in result or '<=' in result or '=' in result):
                        logger.debug(f"T19: 直接使用Verilog语句 -> {result[:50]}")
                        return result
                    
                    return result if result else None
                elif rule_id == 'T20':
                    # T20: 优先接受直接文本，JSON作为备选
                    import re
                    
                    # 清理内容
                    result = content.strip()
                    
                    # 移除markdown代码块标记
                    result = re.sub(r'```(?:json|verilog|text)?\s*', '', result).strip()
                    result = re.sub(r'```\s*$', '', result).strip()
                    result = result.strip('"').strip("'").strip()
                    
                    # 尝试JSON解析（备选方案）
                    if result.startswith('{'):
                        try:
                            json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', result)
                            if json_match:
                                parsed = json.loads(json_match.group())
                                
                                if 'parameters' in parsed and 'custom_text' in parsed['parameters']:
                                    text = parsed['parameters']['custom_text']
                                    if text:
                                        logger.debug(f"T20: 解析JSON成功 -> {text[:50]}")
                                        return text
                                elif 'custom_text' in parsed:
                                    text = parsed['custom_text']
                                    if text:
                                        logger.debug(f"T20: 解析JSON成功 -> {text[:50]}")
                                        return text
                        except (json.JSONDecodeError, Exception) as e:
                            # JSON解析失败，忽略错误，使用直接文本
                            logger.debug(f"T20: JSON解析失败，使用直接文本: {e}")
                    
                    # 直接使用注释文本（优先方案）
                    # 移除开头的 // 如果有的话
                    result = re.sub(r'^//\s*', '', result).strip()
                    
                    if result:
                        logger.debug(f"T20: 直接使用注释文本 -> {result[:50]}")
                        return result
                    
                    return None
                else:
                    # 其他规则：直接返回文本
                    return content.strip('"').strip("'")
                    
        except Exception as e:
            logger.warning(f"LLM参数生成失败 ({rule_id}): {e}")
        
        return None
    
    def get_param_sets(self, rule_id: str, code: str, spec: str = "") -> List[Dict]:
        """获取规则的所有参数组合"""
        # 如果启用LLM参数生成且该规则支持LLM生成
        if self.enable_llm_params and rule_id in LLM_PARAM_RULES:
            context = {}
            
            # 对T20规则，提取目标行内容
            if rule_id == 'T20':
                from core.transforms import analyze, _extract_comment_insert_points
                vs = analyze(code)
                insert_points = _extract_comment_insert_points(code, vs)
                if insert_points:
                    target_line = insert_points[0].line_text
                    context['target_line'] = target_line
                    logger.debug(f"T20: 目标行 = {target_line}")
            
            # 对T12规则，提取目标谓词表达式
            elif rule_id == 'T12':
                from core.transforms import analyze, Selectors
                vs = analyze(code)
                # 获取所有包含三元表达式的assign
                assigns = Selectors.continuous_assigns(vs)
                ternary_assigns = [a for a in assigns if a.rhs_expr and a.rhs_expr.kind == 'ternary']
                if ternary_assigns:
                    # 提取第一个三元表达式的谓词
                    target_expr = ternary_assigns[0].rhs_expr.predicate
                    context['target_expr'] = target_expr
                    logger.debug(f"T12: 目标谓词 = {target_expr}")
            
            # 对T31规则，提取目标赋值表达式
            elif rule_id == 'T31':
                from core.transforms import analyze, Selectors
                vs = analyze(code)
                # 获取所有连续赋值
                assigns = Selectors.continuous_assigns(vs)
                if assigns:
                    # 提取第一个assign的右侧表达式
                    target_expr = assigns[0].rhs
                    context['target_expr'] = target_expr
                    logger.debug(f"T31: 目标表达式 = {target_expr}")
            
            llm_param = self.generate_llm_param(rule_id, code, spec=spec, **context)
            if llm_param:
                param_name = LLM_PARAM_RULES[rule_id]['param_name']
                llm_param_set = {param_name: llm_param}
                # 只返回LLM生成的参数，不使用默认参数
                return [llm_param_set]
            else:
                # LLM生成失败，回退到默认参数
                logger.debug(f"{rule_id}: LLM参数生成失败，使用默认参数")
                return DEFAULT_PARAM_SETS.get(rule_id, [{}])
        else:
            # 未启用LLM或规则不支持，使用默认参数
            return DEFAULT_PARAM_SETS.get(rule_id, [{}])
    
    def _create_sample_record(
        self,
        task_id: str,
        spec: str,
        rtl: str,
        transformed: str,
        rule_id: str,
        params: dict,
        status: str,
        failure_reason: str = '',
        testbench_passed: bool = None,
        judge_fooled: bool = None,
        verdict_original: dict = None,
        verdict_transformed: dict = None,
        transform_positions: dict = None,
    ) -> dict:
        """创建样本记录"""
        sample = {
            'task_id': task_id,
            'prompt': spec,
            'original_code': rtl,
            'transformed_code': transformed,
            'attack_rule': rule_id,
            'attack_params': params,
            'status': status,  # success/attack_failed/testbench_failed/testbench_error/judge_error/no_change/exception
        }
        
        # 添加失败原因
        if failure_reason:
            sample['failure_reason'] = failure_reason
        
        # 添加testbench结果
        if testbench_passed is not None:
            sample['testbench_passed'] = testbench_passed
        
        # 添加判断结果
        if judge_fooled is not None:
            sample['judge_fooled'] = judge_fooled
        
        # 添加判断模型输出（如果有）
        if verdict_transformed:
            sample['judge_confidence'] = verdict_transformed.get('confidence', 0.0)
            sample['judge_cot_transformed'] = verdict_transformed.get('raw_output', '')
            sample['judge_transformed_answer'] = 'no' if verdict_transformed.get('is_correct') is False else 'yes'
        
        if verdict_original:
            sample['judge_cot_original'] = verdict_original.get('raw_output', '')
            sample['judge_original_answer'] = 'yes' if verdict_original.get('is_correct') else 'no'
            sample['judge_original_correct'] = verdict_original.get('is_correct', True)
        
        # 添加变换位置信息
        if transform_positions:
            sample['transform_positions'] = transform_positions
        
        return sample
    
    def try_attack_with_rule(
        self,
        task_id: str,
        spec: str,
        rtl: str,
        testbench: str,
        rule_id: str,
    ) -> List[Dict]:
        """使用指定规则尝试攻击，返回所有样本（成功和失败的）"""
        all_samples = []
        
        # 获取所有参数组合（传入spec以支持专业版prompt）
        param_sets = self.get_param_sets(rule_id, rtl, spec=spec)
        # 遍历所有参数组合
        for param_idx, params in enumerate(param_sets):
            with self.stats_lock:
                self.stats['total_attempts'] += 1
            
            try:
                # 应用变换
                # 提取target_token（如果有的话）
                target_token = params.get('target_token')
                transform_positions = None  # 初始化变量
                
                transformed = self.engine.apply_transform(
                    rtl,
                    rule_id,
                    **params
                )
                
                # ===== 关键改进：将target_token转换为有语义的位置信息 =====
                # 如果使用了target_token，尝试转换为target_signal或target_line
                if target_token is not None or ('target_signal' not in params and 'target_line' not in params):
                    try:
                        candidates = self.engine._get_candidates_for_transform(rtl, rule_id)
                        if candidates and len(candidates) > 0:
                            # 确定使用的是哪个候选
                            idx = target_token if target_token is not None else 0
                            if 0 <= idx < len(candidates):
                                target_obj = candidates[idx]
                                
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
                        # 如果提取失败，保留原始params
                        pass
                
                # 分析变换位置
                transform_positions = analyze_transform_positions(rtl, transformed, rule_id, target_token)
                
                # 检查是否有变化
                if not transformed or transformed == rtl:
                    # 记录无变化的样本
                    sample = self._create_sample_record(
                        task_id, spec, rtl, '', rule_id, params,
                        status='no_change',
                        failure_reason='变换未产生变化',
                        transform_positions=transform_positions
                    )
                    all_samples.append(sample)
                    continue
                
                # 运行testbench
                # 使用RefModule（原始）和TopModule（变换后）对比验证功能等价性
                if self.tb_runner.available:
                    try:
                        # 对于重命名规则，需要将重命名应用到RefModule
                        rtl_for_ref = rtl
                        if rule_id in RENAME_RULES:
                            rename_map = self.engine.get_last_rename_map()
                            if rename_map:
                                import re
                                for old_name, new_name in rename_map.items():
                                    rtl_for_ref = re.sub(r"\b" + re.escape(old_name) + r"\b", new_name, rtl_for_ref)
                        
                        # 组装design：RefModule + TopModule，并修正模块名以匹配testbench
                        tb_design = design_for_testbench(rtl_for_ref, transformed, testbench)
                        
                        # 运行testbench
                        tb_result = self.tb_runner.run(tb_design, testbench)
                        
                        if not tb_result.get("passed", False):
                            # 记录testbench失败的样本
                            sample = self._create_sample_record(
                                task_id, spec, rtl, transformed, rule_id, params,
                                status='testbench_failed',
                                failure_reason='功能不等价，testbench未通过',
                                testbench_passed=False,
                                transform_positions=transform_positions
                            )
                            all_samples.append(sample)
                            logger.debug(f"{task_id} | {rule_id} | 参数{param_idx} | testbench失败")
                            continue
                        
                        with self.stats_lock:
                            self.stats['testbench_pass'] += 1
                    except Exception as e:
                        # 记录testbench错误的样本
                        sample = self._create_sample_record(
                            task_id, spec, rtl, transformed, rule_id, params,
                            status='testbench_error',
                            failure_reason=f'Testbench运行错误: {str(e)}',
                            testbench_passed=False,
                            transform_positions=transform_positions
                        )
                        all_samples.append(sample)
                        logger.debug(f"{task_id} | {rule_id} | 参数{param_idx} | testbench错误: {e}")
                        continue
                else:
                    # 没有testbench runner，假设通过
                    with self.stats_lock:
                        self.stats['testbench_pass'] += 1
                
                # 判断模型评估（变换后代码）
                verdict_transformed = self.judge_client.judge(spec, transformed, use_cot=self.use_cot)
                
                if not verdict_transformed:
                    # 记录判断失败的样本
                    sample = self._create_sample_record(
                        task_id, spec, rtl, transformed, rule_id, params,
                        status='judge_error',
                        failure_reason='判断模型调用失败',
                        testbench_passed=True,
                        transform_positions=transform_positions
                    )
                    all_samples.append(sample)
                    logger.debug(f"{task_id} | {rule_id} | 参数{param_idx} | 判断失败")
                    continue
                
                # 获取原始代码的判断（用于对比）
                verdict_original = self.judge_client.judge(spec, rtl, use_cot=self.use_cot)
                
                is_fooled = verdict_transformed.get("is_correct") is False
                
                if is_fooled:
                    # 攻击成功
                    self.stats['judge_fooled'] += 1
                    self.stats['attack_success'] += 1
                    
                    if rule_id not in self.stats['by_rule']:
                        self.stats['by_rule'][rule_id] = 0
                    self.stats['by_rule'][rule_id] += 1
                    
                    sample = self._create_sample_record(
                        task_id, spec, rtl, transformed, rule_id, params,
                        status='success',
                        testbench_passed=True,
                        judge_fooled=True,
                        verdict_original=verdict_original,
                        verdict_transformed=verdict_transformed,
                        transform_positions=transform_positions
                    )
                    all_samples.append(sample)
                    logger.info(f"✅ {task_id} | {rule_id} | 攻击成功！")
                else:
                    # 攻击失败（testbench通过但判断模型仍判对）
                    sample = self._create_sample_record(
                        task_id, spec, rtl, transformed, rule_id, params,
                        status='attack_failed',
                        failure_reason='判断模型仍然判断正确',
                        testbench_passed=True,
                        judge_fooled=False,
                        verdict_original=verdict_original,
                        verdict_transformed=verdict_transformed,
                        transform_positions=transform_positions
                    )
                    all_samples.append(sample)
                    logger.debug(f"{task_id} | {rule_id} | 参数{param_idx} | 判断仍正确")
                    
            except Exception as e:
                # 记录异常的样本
                sample = self._create_sample_record(
                    task_id, spec, rtl, '', rule_id, params,
                    status='exception',
                    failure_reason=f'处理异常: {str(e)}',
                    transform_positions=transform_positions
                )
                all_samples.append(sample)
                logger.warning(f"{task_id} | {rule_id} | 参数{param_idx} | 错误: {e}")
                continue
        
        return all_samples
    
    def _process_single_task(self, item: Dict, idx: int, rules_to_test: List[str]) -> List[Dict]:
        """处理单个任务（用于并行）"""
        task_id = item.get("task_id", f"task_{idx}")
        spec = item.get("prompt", "")
        rtl = item.get("canonical_solution", "")
        testbench = item.get("test", "")
        
        if not rtl:
            return []
        
        # 先验证原始代码
        try:
            original_verdict = self.judge_client.judge(spec, rtl, use_cot=self.use_cot)
            if not original_verdict or not original_verdict.get("is_correct"):
                logger.warning(f"⚠️  {task_id} | 原始代码判断错误，跳过")
                return []
        except Exception as e:
            logger.error(f"❌ {task_id} | 判断失败: {e}")
            return []
        
        # 遍历所有规则
        task_samples = []
        for rule_id in rules_to_test:
            try:
                samples = self.try_attack_with_rule(
                    task_id, spec, rtl, testbench, rule_id
                )
                task_samples.extend(samples)
            except Exception as e:
                logger.error(f"❌ {task_id} | {rule_id} | 异常: {e}")
        
        return task_samples
    
    def generate_dataset(
        self,
        eval_data: List[Dict],
        rules_to_test: Optional[List[str]] = None,
        max_samples: Optional[int] = None,
    ) -> List[Dict]:
        """生成攻击数据集（包含成功和失败的样本）"""
        all_samples = []
        
        if rules_to_test is None:
            rules_to_test = list(DEFAULT_PARAM_SETS.keys())
        
        eval_subset = eval_data[:max_samples] if max_samples else eval_data
        
        logger.info(f"开始生成数据集：{len(eval_subset)}个任务 × {len(rules_to_test)}个规则")
        logger.info(f"并行worker数: {self.workers}")
        
        if self.workers <= 1:
            # 单线程模式（原始逻辑）
            task_pbar = tqdm(
                enumerate(eval_subset),
                total=len(eval_subset),
                desc="处理任务",
                unit="task",
                ncols=100
            )
            
            for idx, item in task_pbar:
                task_id = item.get("task_id", f"task_{idx}")
                task_pbar.set_description(f"处理 {task_id}")
                
                samples = self._process_single_task(item, idx, rules_to_test)
                all_samples.extend(samples)
                
                # 更新统计信息到进度条
                with self.stats_lock:
                    success_rate = self.stats['attack_success'] / self.stats['total_attempts'] * 100 if self.stats['total_attempts'] > 0 else 0
                task_pbar.set_postfix({
                    'samples': len(all_samples),
                    'success': self.stats['attack_success'],
                    'rate': f'{success_rate:.1f}%'
                })
            
            task_pbar.close()
        else:
            # 多线程模式
            all_samples_lock = Lock()
            
            with ThreadPoolExecutor(max_workers=self.workers) as executor:
                # 提交所有任务
                future_to_idx = {
                    executor.submit(self._process_single_task, item, idx, rules_to_test): (idx, item)
                    for idx, item in enumerate(eval_subset)
                }
                
                # 使用tqdm显示进度
                task_pbar = tqdm(
                    as_completed(future_to_idx),
                    total=len(future_to_idx),
                    desc="处理任务",
                    unit="task",
                    ncols=100
                )
                
                for future in task_pbar:
                    idx, item = future_to_idx[future]
                    task_id = item.get("task_id", f"task_{idx}")
                    
                    try:
                        samples = future.result()
                        with all_samples_lock:
                            all_samples.extend(samples)
                        
                        # 更新统计信息到进度条
                        with self.stats_lock:
                            success_rate = self.stats['attack_success'] / self.stats['total_attempts'] * 100 if self.stats['total_attempts'] > 0 else 0
                        
                        task_pbar.set_postfix({
                            'samples': len(all_samples),
                            'success': self.stats['attack_success'],
                            'rate': f'{success_rate:.1f}%'
                        })
                    except Exception as e:
                        logger.error(f"❌ {task_id} | 处理失败: {e}")
                
                task_pbar.close()
        
        return all_samples
    
    def _print_stats(self):
        """打印统计信息"""
        logger.info("=" * 60)
        logger.info(f"统计信息：")
        logger.info(f"  总尝试次数: {self.stats['total_attempts']}")
        logger.info(f"  testbench通过: {self.stats['testbench_pass']}")
        logger.info(f"  判断模型被欺骗: {self.stats['judge_fooled']}")
        logger.info(f"  攻击成功: {self.stats['attack_success']}")
        
        if self.stats['by_rule']:
            logger.info(f"  成功率按规则:")
            for rule_id, count in sorted(self.stats['by_rule'].items(), key=lambda x: -x[1]):
                logger.info(f"    {rule_id}: {count}")
        logger.info("=" * 60)


def create_attack_client(base_url: str, api_key: str, model: str):
    """创建简单的攻击模型客户端（用于LLM参数生成）"""
    class SimpleClient:
        def __init__(self, base_url, api_key, model):
            self.base_url = base_url.rstrip('/')
            self.api_key = api_key
            self.model = model
        
        def post(self, url, **kwargs):
            return requests.post(url, **kwargs)
    
    return SimpleClient(base_url, api_key, model)


def main():
    parser = argparse.ArgumentParser(
        description="遍历攻击规则生成训练数据集（针对CoT判断模型）"
    )
    parser.add_argument("--eval-file", type=str, required=True, help="评估数据文件路径")
    parser.add_argument("--output", type=str, required=True, help="输出JSONL文件路径")
    parser.add_argument("--max-samples", type=int, default=None, help="最多处理多少个样本")
    parser.add_argument("--rules", type=str, default=None, help="要测试的规则列表，逗号分隔（默认全部）")
    parser.add_argument("--use-cot", action="store_true", default=True, help="判断模型使用CoT模式")
    parser.add_argument("--enable-llm-params", action="store_true", help="启用LLM生成参数")
    parser.add_argument("--attack-base-url", type=str, default=None, help="攻击模型base_url（用于LLM参数生成）")
    parser.add_argument("--attack-model", type=str, default=None, help="攻击模型名称")
    parser.add_argument("--only-valid-samples", action="store_true", help="只保留testbench通过的样本")
    parser.add_argument("--workers", type=int, default=1, help="并行worker数量（默认1，单线程）")
    parser.add_argument("--verbose", action="store_true", help="详细日志")
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
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
    attack_client = None
    if args.enable_llm_params:
        if not args.attack_base_url or not args.attack_model:
            logger.error("启用LLM参数生成需要指定 --attack-base-url 和 --attack-model")
            return
        
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
    generator = AttackDatasetGenerator(
        judge_client=judge_client,
        attack_client=attack_client,
        tb_runner=tb_runner,
        enable_llm_params=args.enable_llm_params,
        use_cot=args.use_cot,
        workers=args.workers
    )
    
    # 生成数据集
    logger.info("开始生成攻击数据集...")
    start_time = time.time()
    
    all_samples = generator.generate_dataset(
        eval_data,
        rules_to_test=rules_to_test,
        max_samples=args.max_samples,
    )
    
    elapsed = time.time() - start_time
    
    # 统计成功和失败样本
    successful_samples = [s for s in all_samples if s.get('status') == 'success']
    failed_samples = [s for s in all_samples if s.get('status') != 'success']
    
    # 根据参数决定保存哪些样本
    if args.only_valid_samples:
        # 只保留testbench通过的样本（过滤掉 no_change, testbench_failed, testbench_error, exception）
        samples_to_save = [s for s in all_samples if s.get('testbench_passed', False)]
        logger.info(f"只保留testbench通过的样本: {len(samples_to_save)}/{len(all_samples)}")
    else:
        # 保存所有样本
        samples_to_save = all_samples
    
    # 保存结果
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, "w", encoding="utf-8") as f:
        for sample in samples_to_save:
            f.write(json.dumps(sample, ensure_ascii=False) + '\n')
    
    # 打印最终统计
    logger.info("=" * 60)
    logger.info(f"数据集生成完成！")
    logger.info(f"  耗时: {elapsed:.1f}秒")
    logger.info(f"  总样本数: {len(all_samples)}")
    logger.info(f"  成功样本数: {len(successful_samples)}")
    logger.info(f"  失败样本数: {len(failed_samples)}")
    if args.only_valid_samples:
        logger.info(f"  已保存样本数: {len(samples_to_save)} (只包含testbench通过的)")
    else:
        logger.info(f"  已保存样本数: {len(samples_to_save)} (包含所有样本)")
    logger.info(f"  输出文件: {output_path}")
    logger.info("=" * 60)
    
    # 统计失败原因
    if failed_samples:
        from collections import Counter
        failure_reasons = Counter(s.get('status', 'unknown') for s in failed_samples)
        logger.info("失败样本统计:")
        for reason, count in failure_reasons.most_common():
            logger.info(f"  {reason}: {count}")
        logger.info("=" * 60)
    
    generator._print_stats()


if __name__ == "__main__":
    main()
