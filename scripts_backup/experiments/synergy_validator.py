"""
规则组合协同效应验证实验
验证多维度联动攻击的真实威力
"""

import json
import logging
import hashlib
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass, asdict
from concurrent.futures import ThreadPoolExecutor
import yaml

logger = logging.getLogger(__name__)


@dataclass
class AttackScenario:
    """攻击场景定义"""
    name: str
    description: str
    rule_chain: List[Dict]  # 规则链 [{"rule_id": "T34", "params": {...}}, ...]
    target_module_type: str  # "counter" | "state_machine" | "alu" | "mux"
    hypothesis: str  # 预期效果假设


@dataclass
class ExperimentResult:
    """实验结果"""
    scenario_name: str
    module_id: str
    original_rtl: str
    transformed_rtl: str
    
    # 单规则结果
    single_rule_results: Dict[str, Dict]  # rule_id -> {asr, confidence, verdict}
    
    # 组合规则结果
    combined_result: Dict  # {asr, confidence, verdict, reasoning_trace}
    
    # 协同效应指标
    synergy_metrics: Dict  # {delta_confidence, asr_boost, is_synergistic}


class SynergyValidator:
    """协同效应验证器"""
    
    def __init__(self, config_path: str):
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 延迟导入以避免循环依赖
        from ast_transforms_loader import create_engine
        from taget_model import TargetModelClient
        from Testbench_valid import TestbenchRunner
        
        self.engine = create_engine()
        self.victim = TargetModelClient(
            base_url=self.config['target_model']['base_url'],
            api_key=self.config['target_model']['api_key'],
            model=self.config['target_model']['model'],
            timeout=self.config['target_model']['timeout'],
            max_retries=self.config['target_model']['max_retries'],
            use_local_transformers=self.config['target_model'].get('use_local_transformers', False),
            max_new_tokens=self.config['target_model'].get('max_new_tokens', 512),
        )
        
        self.tb_runner = TestbenchRunner(
            simulator=self.config['testbench']['simulator'],
            timeout=self.config['testbench']['timeout']
        )
        
        self.results = []
    
    def run_experiment(self, scenarios: List[AttackScenario], test_modules: List[Dict]) -> List[ExperimentResult]:
        """运行完整实验"""
        logger.info(f"开始运行 {len(scenarios)} 个场景，{len(test_modules)} 个测试模块")
        
        for scenario in scenarios:
            logger.info(f"\n{'='*60}")
            logger.info(f"场景: {scenario.name}")
            logger.info(f"描述: {scenario.description}")
            logger.info(f"假设: {scenario.hypothesis}")
            logger.info(f"{'='*60}")
            
            # 筛选适用的模块
            applicable_modules = [
                m for m in test_modules 
                if m['type'] == scenario.target_module_type
            ]
            
            for module in applicable_modules:
                result = self._evaluate_scenario(scenario, module)
                self.results.append(result)
                self._print_result(result)
        
        return self.results
    
    def _evaluate_scenario(self, scenario: AttackScenario, module: Dict) -> ExperimentResult:
        """评估单个场景"""
        module_id = module['id']
        original_rtl = module['rtl']
        spec = module['spec']
        testbench = module.get('testbench', '')
        
        logger.info(f"  评估模块: {module_id}")
        
        # 1. 获取原始判决（baseline）
        original_verdict = self.victim.judge(spec, original_rtl, use_cot=True)
        if not original_verdict or not original_verdict.get('is_correct'):
            logger.warning(f"    模块 {module_id} 原始代码未通过判题，跳过")
            return None
        
        original_confidence = original_verdict.get('confidence', 1.0)
        logger.info(f"    原始置信度: {original_confidence:.4f}")
        
        # 2. 评估单个规则效果
        single_rule_results = {}
        for rule_step in scenario.rule_chain:
            rule_id = rule_step['rule_id']
            params = rule_step.get('params', {})
            target_token = rule_step.get('target_token', None)
            
            try:
                transformed = self.engine.apply_transform(
                    code=original_rtl,
                    transform_id=rule_id,
                    target_token=target_token,
                    **params
                )
                
                if transformed == original_rtl:
                    logger.warning(f"    规则 {rule_id} 变换失败")
                    single_rule_results[rule_id] = {
                        'success': False,
                        'asr': 0.0,
                        'confidence': original_confidence,
                        'verdict': original_verdict
                    }
                    continue
                
                # Testbench 验证
                if testbench:
                    tb_result = self.tb_runner.run(transformed, testbench)
                    if not tb_result['passed']:
                        logger.warning(f"    规则 {rule_id} 未通过 Testbench")
                        single_rule_results[rule_id] = {
                            'success': False,
                            'tb_passed': False
                        }
                        continue
                
                # 模型判题
                verdict = self.victim.judge(spec, transformed, use_cot=True)
                if not verdict:
                    logger.warning(f"    规则 {rule_id} 判题失败")
                    continue
                
                asr = 1.0 if verdict.get('is_correct') == False else 0.0
                confidence = verdict.get('confidence', 1.0)
                
                single_rule_results[rule_id] = {
                    'success': True,
                    'asr': asr,
                    'confidence': confidence,
                    'confidence_drop': original_confidence - confidence,
                    'verdict': verdict,
                    'transformed_rtl': transformed
                }
                
                logger.info(f"    规则 {rule_id}: ASR={asr:.2f}, Conf={confidence:.4f}, Drop={original_confidence - confidence:.4f}")
                
            except Exception as e:
                logger.error(f"    规则 {rule_id} 执行出错: {e}")
                single_rule_results[rule_id] = {'success': False, 'error': str(e)}
        
        # 3. 评估组合规则效果
        combined_rtl = original_rtl
        combined_success = True
        
        for rule_step in scenario.rule_chain:
            rule_id = rule_step['rule_id']
            params = rule_step.get('params', {})
            target_token = rule_step.get('target_token', None)
            
            try:
                combined_rtl = self.engine.apply_transform(
                    code=combined_rtl,
                    transform_id=rule_id,
                    target_token=target_token,
                    **params
                )
                
                if combined_rtl == original_rtl:
                    combined_success = False
                    break
                    
            except Exception as e:
                logger.error(f"    组合规则在 {rule_id} 失败: {e}")
                combined_success = False
                break
        
        combined_result = {}
        if combined_success:
            # Testbench 验证
            if testbench:
                tb_result = self.tb_runner.run(combined_rtl, testbench)
                if not tb_result['passed']:
                    logger.warning(f"    组合规则未通过 Testbench")
                    combined_result = {'success': False, 'tb_passed': False}
                    combined_success = False
            
            if combined_success:
                # 模型判题
                verdict = self.victim.judge(spec, combined_rtl, use_cot=True)
                if verdict:
                    asr = 1.0 if verdict.get('is_correct') == False else 0.0
                    confidence = verdict.get('confidence', 1.0)
                    
                    combined_result = {
                        'success': True,
                        'asr': asr,
                        'confidence': confidence,
                        'confidence_drop': original_confidence - confidence,
                        'verdict': verdict,
                        'transformed_rtl': combined_rtl
                    }
                    
                    logger.info(f"    组合规则: ASR={asr:.2f}, Conf={confidence:.4f}, Drop={original_confidence - confidence:.4f}")
        
        # 4. 计算协同效应指标
        synergy_metrics = self._compute_synergy(
            original_confidence,
            single_rule_results,
            combined_result
        )
        
        return ExperimentResult(
            scenario_name=scenario.name,
            module_id=module_id,
            original_rtl=original_rtl,
            transformed_rtl=combined_rtl if combined_success else "",
            single_rule_results=single_rule_results,
            combined_result=combined_result,
            synergy_metrics=synergy_metrics
        )
    
    def _compute_synergy(
        self,
        original_confidence: float,
        single_results: Dict,
        combined_result: Dict
    ) -> Dict:
        """计算协同效应指标"""
        
        if not combined_result.get('success'):
            return {
                'is_synergistic': False,
                'reason': 'combined_attack_failed'
            }
        
        # 单规则最大 ASR 和置信度下降
        max_single_asr = max(
            (r.get('asr', 0.0) for r in single_results.values() if r.get('success')),
            default=0.0
        )
        max_single_conf_drop = max(
            (r.get('confidence_drop', 0.0) for r in single_results.values() if r.get('success')),
            default=0.0
        )
        
        # 组合结果
        combined_asr = combined_result.get('asr', 0.0)
        combined_conf_drop = combined_result.get('confidence_drop', 0.0)
        
        # 协同效应判断
        asr_boost = combined_asr - max_single_asr
        conf_boost = combined_conf_drop - max_single_conf_drop
        
        # 非线性增益：组合效果显著超过单规则
        is_synergistic = (asr_boost > 0.2) or (conf_boost > 0.15)
        
        return {
            'is_synergistic': is_synergistic,
            'max_single_asr': max_single_asr,
            'combined_asr': combined_asr,
            'asr_boost': asr_boost,
            'max_single_conf_drop': max_single_conf_drop,
            'combined_conf_drop': combined_conf_drop,
            'confidence_boost': conf_boost,
            'synergy_ratio': combined_conf_drop / max_single_conf_drop if max_single_conf_drop > 0 else 0.0
        }
    
    def _print_result(self, result: ExperimentResult):
        """打印结果摘要"""
        if not result:
            return
        
        print(f"\n  模块 {result.module_id} 结果:")
        print(f"    单规则最大 ASR: {result.synergy_metrics.get('max_single_asr', 0):.2%}")
        print(f"    组合规则 ASR: {result.synergy_metrics.get('combined_asr', 0):.2%}")
        print(f"    ASR 提升: {result.synergy_metrics.get('asr_boost', 0):.2%}")
        print(f"    置信度提升: {result.synergy_metrics.get('confidence_boost', 0):.4f}")
        print(f"    协同效应: {'✓ 是' if result.synergy_metrics.get('is_synergistic') else '✗ 否'}")
    
    def save_results(self, output_path: str):
        """保存实验结果"""
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            for result in self.results:
                if result:
                    f.write(json.dumps(asdict(result), ensure_ascii=False) + '\n')
        
        logger.info(f"结果已保存到 {output_path}")
    
    def generate_report(self, output_path: str):
        """生成实验报告"""
        report = {
            'summary': {
                'total_scenarios': len(set(r.scenario_name for r in self.results if r)),
                'total_tests': len([r for r in self.results if r]),
                'synergistic_cases': len([r for r in self.results if r and r.synergy_metrics.get('is_synergistic')]),
            },
            'scenarios': {}
        }
        
        # 按场景聚合
        for result in self.results:
            if not result:
                continue
            
            scenario = result.scenario_name
            if scenario not in report['scenarios']:
                report['scenarios'][scenario] = {
                    'tests': [],
                    'avg_asr_boost': 0.0,
                    'avg_conf_boost': 0.0,
                    'synergy_rate': 0.0
                }
            
            report['scenarios'][scenario]['tests'].append({
                'module_id': result.module_id,
                'is_synergistic': result.synergy_metrics.get('is_synergistic'),
                'asr_boost': result.synergy_metrics.get('asr_boost', 0),
                'conf_boost': result.synergy_metrics.get('confidence_boost', 0)
            })
        
        # 计算统计量
        for scenario, data in report['scenarios'].items():
            tests = data['tests']
            if tests:
                data['avg_asr_boost'] = sum(t['asr_boost'] for t in tests) / len(tests)
                data['avg_conf_boost'] = sum(t['conf_boost'] for t in tests) / len(tests)
                data['synergy_rate'] = sum(1 for t in tests if t['is_synergistic']) / len(tests)
        
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        
        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        logger.info(f"报告已保存到 {output_path}")
        
        # 打印摘要
        print("\n" + "="*60)
        print("实验报告摘要")
        print("="*60)
        print(f"总场景数: {report['summary']['total_scenarios']}")
        print(f"总测试数: {report['summary']['total_tests']}")
        print(f"协同案例数: {report['summary']['synergistic_cases']}")
        print(f"协同率: {report['summary']['synergistic_cases'] / report['summary']['total_tests']:.2%}")
        print("\n各场景表现:")
        for scenario, data in report['scenarios'].items():
            print(f"\n  {scenario}:")
            print(f"    平均 ASR 提升: {data['avg_asr_boost']:.2%}")
            print(f"    平均置信度提升: {data['avg_conf_boost']:.4f}")
            print(f"    协同率: {data['synergy_rate']:.2%}")
        print("="*60)
