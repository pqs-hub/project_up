import json
import logging
import re
import threading
from pathlib import Path
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import yaml

logger = logging.getLogger(__name__)

from ast_transforms_loader import create_engine
from taget_model import TargetModelClient
from Testbench_valid import TestbenchRunner
from AttackConfigGenerator import AttackConfig, AttackConfigGenerator

# 重命名类规则：仿真时需对 testbench 做相同变量名替换
RENAME_RULES = {'T34'}

# 仅做注释插入的规则：若变换后仅注释不同，仿真失败不记入 testbench_failed
COMMENT_ONLY_RULES = {'T20'}


def _normalize_verilog_for_compare(code: str) -> str:
    """去掉注释、归一化空白，用于比较两段 RTL 是否功能等价。"""
    # 去掉 // 行尾和整行注释
    code = re.sub(r'//[^\n]*', '', code)
    # 去掉 /* ... */ 块注释（非贪婪）
    code = re.sub(r'/\*.*?\*/', '', code, flags=re.DOTALL)
    # 空白归一化：连续空白变为单空格，去掉首尾空白
    code = ' '.join(code.split())
    return code


def _is_comment_only_change(original_rtl: str, transformed_rtl: str) -> bool:
    """若变换仅增加/修改注释，功能代码一致则返回 True。"""
    return _normalize_verilog_for_compare(original_rtl) == _normalize_verilog_for_compare(transformed_rtl)


def _apply_rename_map_to_testbench(testbench: str, rename_map: Dict[str, str]) -> str:
    """对 testbench 中出现的旧名按 rename_map 做整词替换，使与变换后的 RTL 端口/信号名一致。"""
    if not rename_map:
        return testbench
    out = testbench
    for old_name, new_name in rename_map.items():
        out = re.sub(r'\b' + re.escape(old_name) + r'\b', new_name, out)
    return out


class AdversarialDatasetGenerator:
    """对抗数据集生成器"""
    
    def __init__(self, config_path: str):
        # 加载配置
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        
        # 初始化组件
        self.engine = create_engine()
        
        self.target_model = TargetModelClient(
            base_url=self.config['target_model']['base_url'],
            api_key=self.config['target_model']['api_key'],
            model=self.config['target_model']['model'],
            timeout=self.config['target_model']['timeout'],
            max_retries=self.config['target_model']['max_retries'],
            use_local_transformers=self.config['target_model'].get('use_local_transformers', False),
            max_new_tokens=self.config['target_model'].get('max_new_tokens', 512),
        )
        
        if self.config['testbench']['enabled']:
            self.testbench_runner = TestbenchRunner(
                simulator=self.config['testbench']['simulator'],
                timeout=self.config['testbench']['timeout']
            )
        else:
            self.testbench_runner = None
        
        self.attack_generator = AttackConfigGenerator(
            engine=self.engine,
            max_attacks_per_sample=self.config['sampling']['max_attacks_per_sample'],
            max_positions_per_rule=self.config['sampling']['max_positions_per_rule'],
            max_params_per_rule=self.config['sampling']['max_params_per_rule']
        )
        
        self.num_workers = self.config['parallelism']['num_workers']
        
        # Testbench 失败记录：单独文件，多线程写用锁
        self._tb_failed_path = Path(self.config['data'].get('testbench_failed_path', 'data/testbench_failed.jsonl'))
        self._tb_failed_lock = threading.Lock()
        
        # 统计信息
        self.stats = {
            'total_samples': 0,
            'filtered_samples': 0,
            'total_attacks': 0,
            'successful_attacks': 0,
            'testbench_passed': 0,
            'testbench_failed': 0,
            'api_errors': 0
        }
    
    def generate(self):
        """生成数据集"""
        logger.info("开始生成对抗数据集")
        
        # 1. 加载输入数据
        input_path = Path(self.config['data']['input_path'])
        with open(input_path, 'r', encoding='utf-8') as f:
            input_samples = json.load(f)
        
        self.stats['total_samples'] = len(input_samples)
        logger.info(f"加载了 {len(input_samples)} 个输入样本")
        
        # 2. 过滤合格样本（若输入已是合格样本则跳过）
        input_already_qualified = self.config['data'].get('input_already_qualified', False)
        if input_already_qualified:
            logger.info("输入已为合格样本，跳过过滤")
            qualified_samples = input_samples
            self.stats['filtered_samples'] = len(qualified_samples)
        else:
            logger.info("过滤合格样本（目标模型判断为正确）...")
            qualified_samples = self._filter_qualified_samples(input_samples)
            self.stats['filtered_samples'] = len(qualified_samples)
            logger.info(f"保留了 {len(qualified_samples)} 个合格样本")
        
        if not qualified_samples:
            logger.error("没有合格样本，退出")
            return
        
        # 3. 批量处理样本
        output_path = Path(self.config['data']['output_path'])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        
        metadata_path = output_path.with_suffix('.metadata.jsonl')
        
        # 若配置了 testbench 失败输出路径，先清空（本次运行覆盖）
        tb_failed_path = self._tb_failed_path
        if tb_failed_path:
            tb_failed_path.parent.mkdir(parents=True, exist_ok=True)
            tb_failed_path.write_text('', encoding='utf-8')
        
        with open(output_path, 'w', encoding='utf-8') as out_f, \
             open(metadata_path, 'w', encoding='utf-8') as meta_f:
            
            with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
                # 提交所有任务
                futures = {
                    executor.submit(self._process_sample, sample): sample
                    for sample in qualified_samples
                }
                
                # 进度条
                pbar = tqdm(total=len(futures), desc="处理样本")
                
                for future in as_completed(futures):
                    sample = futures[future]
                    try:
                        results = future.result()
                        
                        # 保存成功的攻击
                        for result in results:
                            # 训练数据
                            training_sample = result['training_sample']
                            out_f.write(json.dumps(training_sample, ensure_ascii=False) + '\n')
                            out_f.flush()
                            
                            # 元数据
                            if self.config['data']['save_metadata']:
                                meta_f.write(json.dumps(result['metadata'], ensure_ascii=False) + '\n')
                                meta_f.flush()
                        
                        self.stats['successful_attacks'] += len(results)
                        
                    except Exception as e:
                        logger.error(f"处理样本失败 ({sample.get('id', 'unknown')}): {e}")
                    
                    pbar.update(1)
                
                pbar.close()
        
        # 4. 输出统计
        self._print_statistics()
        logger.info(f"数据集已保存到 {output_path}")
    
    def _filter_qualified_samples(self, samples: List[Dict]) -> List[Dict]:
        """过滤合格样本（目标模型判断为正确）"""
        qualified = []
        
        with ThreadPoolExecutor(max_workers=self.num_workers) as executor:
            futures = {
                executor.submit(
                    self.target_model.judge,
                    sample['spec'],
                    sample['rtl']
                ): sample
                for sample in samples
            }
            
            pbar = tqdm(total=len(futures), desc="查询目标模型")
            
            for future in as_completed(futures):
                sample = futures[future]
                try:
                    verdict = future.result()
                    
                    if verdict and verdict.get('is_correct', False):
                        sample['original_verdict'] = verdict
                        qualified.append(sample)
                    
                except Exception as e:
                    logger.warning(f"判断样本失败 ({sample.get('id', 'unknown')}): {e}")
                    self.stats['api_errors'] += 1
                
                pbar.update(1)
            
            pbar.close()
        
        return qualified
    
    def _process_sample(self, sample: Dict) -> List[Dict]:
        """处理单个样本（生成所有攻击变体）"""
        sample_id = sample.get('id', 'unknown')
        spec = sample['spec']
        original_rtl = sample['rtl']
        testbench = sample.get('testbench', '')
        original_verdict = sample['original_verdict']
        
        # 1. 生成攻击配置
        attack_configs = self.attack_generator.generate(original_rtl)
        self.stats['total_attacks'] += len(attack_configs)
        
        # 2. 执行所有攻击
        successful_attacks = []
        
        for config in attack_configs:
            result = self._try_attack(
                sample_id=sample_id,
                spec=spec,
                original_rtl=original_rtl,
                testbench=testbench,
                original_verdict=original_verdict,
                attack_config=config
            )
            
            if result:
                successful_attacks.append(result)
        
        return successful_attacks
    
    def _try_attack(
        self,
        sample_id: str,
        spec: str,
        original_rtl: str,
        testbench: str,
        original_verdict: Dict,
        attack_config: AttackConfig
    ) -> Optional[Dict]:
        """尝试单个攻击"""
        
        try:
            # 1. 执行变换
            transformed_rtl = self.engine.apply_transform(
                code=original_rtl,
                transform_id=attack_config.transform_id,
                target_token=attack_config.target_token,
                **attack_config.parameters
            )
            
            # 变换失败
            if transformed_rtl == original_rtl:
                return None
            
            # 2. Testbench 验证（重命名类规则需对 testbench 做相同变量名替换）
            tb_to_run = testbench
            if attack_config.transform_id in RENAME_RULES:
                rename_map = self.engine.get_last_rename_map()
                if rename_map:
                    tb_to_run = _apply_rename_map_to_testbench(testbench, rename_map)
            
            if self.testbench_runner and testbench:
                tb_result = self.testbench_runner.run(transformed_rtl, tb_to_run)
                
                if self.config['testbench']['filter_mode']:
                    # 过滤模式：不通过则丢弃，并单独保存失败记录
                    if not tb_result['passed']:
                        # T04/T20 仅改注释时，RTL 功能等价，用原始 RTL 再跑一次以判断是否 testbench 自身问题
                        if (attack_config.transform_id in COMMENT_ONLY_RULES
                                and _is_comment_only_change(original_rtl, transformed_rtl)):
                            tb_orig = self.testbench_runner.run(original_rtl, tb_to_run)
                            if tb_orig['passed']:
                                # 原始 RTL 通过 → 说明仅注释的变换未破坏功能，按通过处理，继续后续流程
                                tb_result = tb_orig
                                logger.debug(
                                    "T04/T20 comment-only: tb failed on transformed_rtl, passed on original_rtl; treating as passed."
                                )
                            else:
                                # 原始 RTL 也失败 → testbench 或设计问题，非变换导致，不记入失败
                                logger.debug(
                                    "T04/T20 comment-only: tb fails on both transformed and original RTL (testbench/design issue), not counting as failure."
                                )
                                return None
                        else:
                            self.stats['testbench_failed'] += 1
                            self._save_testbench_failed(
                                sample_id=sample_id,
                                spec=spec,
                                original_rtl=original_rtl,
                                transformed_rtl=transformed_rtl,
                                testbench=testbench,
                                attack_config=attack_config,
                                tb_result=tb_result,
                            )
                            return None
                
                self.stats['testbench_passed'] += 1
            else:
                tb_result = {'passed': None, 'output': '', 'error': ''}
            
            # 3. 查询目标模型
            new_verdict = self.target_model.judge(spec, transformed_rtl)
            
            if not new_verdict:
                self.stats['api_errors'] += 1
                return None
            
            # 4. 判断攻击是否成功（判断翻转）
            attack_success = (
                original_verdict['is_correct'] == True and
                new_verdict['is_correct'] == False
            )
            
            if not attack_success:
                return None
            
            # 5. 构造训练样本
            return self._create_training_sample(
                sample_id=sample_id,
                spec=spec,
                original_rtl=original_rtl,
                transformed_rtl=transformed_rtl,
                attack_config=attack_config,
                original_verdict=original_verdict,
                new_verdict=new_verdict,
                tb_result=tb_result
            )
            
        except Exception as e:
            logger.warning(f"攻击失败: {e}")
            return None
    
    def _save_testbench_failed(
        self,
        sample_id: str,
        spec: str,
        original_rtl: str,
        transformed_rtl: str,
        testbench: str,
        attack_config: AttackConfig,
        tb_result: Dict,
    ) -> None:
        """将 Testbench 未通过的记录追加到单独文件（线程安全）。"""
        if not self._tb_failed_path:
            return
        record = {
            'sample_id': sample_id,
            'spec': spec,
            'original_rtl': original_rtl,
            'transformed_rtl': transformed_rtl,
            'testbench': testbench,
            'transform_id': attack_config.transform_id,
            'target_token': attack_config.target_token,
            'parameters': attack_config.parameters,
            'tb_passed': tb_result.get('passed'),
            'tb_output': tb_result.get('output', ''),
            'tb_error': tb_result.get('error', ''),
        }
        line = json.dumps(record, ensure_ascii=False) + '\n'
        with self._tb_failed_lock:
            with open(self._tb_failed_path, 'a', encoding='utf-8') as f:
                f.write(line)
    
    def _create_training_sample(
        self,
        sample_id: str,
        spec: str,
        original_rtl: str,
        transformed_rtl: str,
        attack_config: AttackConfig,
        original_verdict: Dict,
        new_verdict: Dict,
        tb_result: Dict
    ) -> Dict:
        """构造训练样本"""
        
        # 决策 JSON（纯字符串）
        decision_json = json.dumps({
            "transform_id": attack_config.transform_id,
            "target_token": attack_config.target_token,
            "parameters": attack_config.parameters
        }, ensure_ascii=False)
        
        # Alpaca 格式（单轮样本，无多轮对话故 history 为空；若下游不需要可忽略该字段）
        training_sample = {
            "instruction": "你是 Verilog 代码混淆专家。分析代码结构，选择最有可能让验证模型误判的变换规则和参数。输出 JSON 格式的决策。",
            "input": f"**功能规范**：\n{spec}\n\n**原始代码**：\n```verilog\n{original_rtl}\n```",
            "output": decision_json,
            "history": []  # 多轮对话历史，单轮任务恒为空
        }
        
        # 元数据
        transform = self.engine.registry.get(attack_config.transform_id)
        metadata = {
            "sample_id": sample_id,
            "transform_id": attack_config.transform_id,
            "target_token": attack_config.target_token,
            "parameters": attack_config.parameters,
            "original_verdict": original_verdict,
            "new_verdict": new_verdict,
            "attack_success": True,
            "verdict_flipped": True,
            "confidence_delta": abs(
                new_verdict.get('confidence', 0) - original_verdict.get('confidence', 0)
            ),
            "testbench_passed": tb_result['passed'],
            "transform_info": {
                "category": transform.category if transform else "unknown",
                "complexity": transform.complexity if transform else 0,
                "equivalence_preserving": transform.equivalence_preserving if transform else False
            },
            "transformed_rtl": transformed_rtl
        }
        
        return {
            "training_sample": training_sample,
            "metadata": metadata
        }
    
    def _print_statistics(self):
        """打印统计信息"""
        print("\n" + "="*60)
        print("数据生成统计")
        print("="*60)
        print(f"输入样本数: {self.stats['total_samples']}")
        print(f"合格样本数: {self.stats['filtered_samples']}")
        print(f"总攻击尝试: {self.stats['total_attacks']}")
        print(f"成功攻击数: {self.stats['successful_attacks']}")
        
        if self.stats['total_attacks'] > 0:
            success_rate = self.stats['successful_attacks'] / self.stats['total_attacks'] * 100
            print(f"攻击成功率: {success_rate:.2f}%")
        
        if self.testbench_runner:
            print(f"Testbench 通过: {self.stats['testbench_passed']}")
            print(f"Testbench 失败: {self.stats['testbench_failed']}")
            if self._tb_failed_path and self.stats['testbench_failed'] > 0:
                print(f"Testbench 失败记录已保存: {self._tb_failed_path}")
        
        print(f"API 错误次数: {self.stats['api_errors']}")
        print("="*60)
