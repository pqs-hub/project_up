#!/usr/bin/env python3
"""
独立LLM参数生成实验（无历史感知）

用于对比：
1. 有历史感知的LLM参数生成（linked_combination_experiment.py）
2. 无历史感知的LLM参数生成（本脚本）
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
import random
from tqdm import tqdm

project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from ast_transforms_loader import create_engine
from taget_model import TargetModelClient
import yaml

# 导入textual_param_generator（独立生成，无历史）
sys.path.insert(0, str(project_root / 'scripts' / 'eval'))
from textual_param_generator import generate_textual_rule_parameters


@dataclass
class Combination:
    """规则组合定义"""
    name: str
    rule1: str
    rule2: str
    description: str


# 定义相同的组合场景（用于对比）
COMBINATIONS = [
    Combination(
        name="Comment_Rename_Independent",
        rule1="T20",
        rule2="T34",
        description="注释+重命名（独立生成，无历史感知）"
    ),
    Combination(
        name="Rename_Intermediate_Independent",
        rule1="T34",
        rule2="T12",
        description="重命名+中间信号（独立生成，无历史感知）"
    ),
]


class IndependentLLMExperiment:
    """独立LLM参数生成实验（无历史感知）"""
    
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.engine = create_engine()
        
        tm_config = self.config['target_model']
        self.model_client = TargetModelClient(
            base_url=tm_config['base_url'],
            api_key=tm_config.get('api_key', 'EMPTY'),
            model=tm_config['model'],
            timeout=tm_config.get('timeout', 60),
            max_retries=tm_config.get('max_retries', 3),
            use_local_transformers=tm_config.get('use_local_transformers', False),
            max_new_tokens=tm_config.get('max_new_tokens', 512)
        )
        
        # LLM配置
        self.llm_base_url = tm_config['base_url']
        self.llm_model = tm_config['model']
        self.llm_api_key = tm_config.get('api_key', 'EMPTY')
    
    def generate_independent_params(
        self,
        rule_id: str,
        spec: str,
        rtl: str,
        target_token: int = 0
    ) -> Dict:
        """
        独立生成参数（无历史感知）
        
        关键：不传入任何历史信息，每个规则独立生成
        """
        if rule_id not in ["T12", "T31", "T34", "T20", "T19"]:
            return {}
        
        try:
            params = generate_textual_rule_parameters(
                base_url=self.llm_base_url,
                model=self.llm_model,
                api_key=self.llm_api_key,
                rule_id=rule_id,
                task_prompt=spec,
                rtl=rtl,  # 注意：这里传的是原始RTL，不是变换后的
                target_token=target_token,
                temperature=0.7,
                max_tokens=256
            )
            return params
        except Exception as e:
            print(f"    独立LLM生成失败: {e}")
            return {}
    
    def apply_combination(
        self,
        rtl: str,
        spec: str,
        combo: Combination
    ) -> Tuple[str, Dict]:
        """
        应用组合（独立生成参数，无历史感知）
        """
        info = {
            "rule1_applied": False,
            "rule2_applied": False,
            "llm_used": False,
            "details": {}
        }
        
        # 1. 为rule1生成参数（基于原始RTL）
        params1 = self.generate_independent_params(
            rule_id=combo.rule1,
            spec=spec,
            rtl=rtl,  # 原始RTL
            target_token=0
        )
        
        if params1:
            info["llm_used"] = True
            info["details"]["rule1_params"] = params1
        
        # 2. 应用rule1
        try:
            transformed = self.engine.apply_transform(
                code=rtl,
                transform_id=combo.rule1,
                target_token=0,
                **params1
            )
            
            if transformed == rtl:
                return rtl, info
            
            info["rule1_applied"] = True
            
            # 获取重命名映射（如果有）
            rename_map = self.engine.get_last_rename_map()
            if rename_map:
                info["details"]["rename_map"] = rename_map
        
        except Exception as e:
            print(f"    Rule1 {combo.rule1} 失败: {e}")
            return rtl, info
        
        # 3. 为rule2生成参数（基于变换后的RTL，但无历史信息）
        # 注意：这里使用transformed而不是rtl，避免参数与代码状态不匹配
        # 但仍然是"独立"的，因为不传入rule1的历史信息
        params2 = self.generate_independent_params(
            rule_id=combo.rule2,
            spec=spec,
            rtl=transformed,  # ✅ 使用变换后的RTL（避免参数错误）
            target_token=0
        )
        
        if params2:
            info["details"]["rule2_params"] = params2
        
        # 4. 应用rule2
        try:
            transformed = self.engine.apply_transform(
                code=transformed,
                transform_id=combo.rule2,
                target_token=0,
                **params2
            )
            
            info["rule2_applied"] = True
        
        except Exception as e:
            print(f"    Rule2 {combo.rule2} 失败: {e}")
        
        return transformed, info
    
    def run_experiment(self, samples: List[Dict], output_dir: str):
        """运行实验"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        results_file = output_path / "independent_results.jsonl"
        
        all_results = []
        
        for combo in COMBINATIONS:
            print(f"\n{'='*60}")
            print(f"测试组合: {combo.name}")
            print(f"描述: {combo.description}")
            print(f"{'='*60}\n")
            
            combo_results = []
            
            for sample in tqdm(samples, desc=combo.name):
                sample_id = sample.get('task_id', sample.get('id', 'unknown'))
                spec = sample['prompt']
                rtl = sample.get('canonical_solution', sample.get('rtl', ''))
                
                if not rtl:
                    continue
                
                # 评估原始代码
                try:
                    orig_verdict = self.model_client.judge(spec, rtl)
                    if not orig_verdict or not orig_verdict['is_correct']:
                        continue
                    orig_conf = orig_verdict.get('confidence', 0.5)
                except:
                    continue
                
                # 评估单规则
                try:
                    r1_params = self.generate_independent_params(combo.rule1, spec, rtl, 0)
                    r1_transformed = self.engine.apply_transform(rtl, combo.rule1, target_token=0, **r1_params)
                    r1_verdict = self.model_client.judge(spec, r1_transformed)
                    r1_asr = 0.0 if (r1_verdict and r1_verdict['is_correct']) else 1.0
                    r1_conf = r1_verdict.get('confidence', 0.5) if r1_verdict else 0.5
                except:
                    r1_asr, r1_conf = 0.0, orig_conf
                
                try:
                    r2_params = self.generate_independent_params(combo.rule2, spec, rtl, 0)
                    r2_transformed = self.engine.apply_transform(rtl, combo.rule2, target_token=0, **r2_params)
                    r2_verdict = self.model_client.judge(spec, r2_transformed)
                    r2_asr = 0.0 if (r2_verdict and r2_verdict['is_correct']) else 1.0
                    r2_conf = r2_verdict.get('confidence', 0.5) if r2_verdict else 0.5
                except:
                    r2_asr, r2_conf = 0.0, orig_conf
                
                # 评估组合（独立生成）
                combined, info = self.apply_combination(rtl, spec, combo)
                
                if combined != rtl:
                    combined_verdict = self.model_client.judge(spec, combined)
                    combined_asr = 0.0 if (combined_verdict and combined_verdict['is_correct']) else 1.0
                    combined_conf = combined_verdict.get('confidence', 0.5) if combined_verdict else 0.5
                else:
                    combined_asr, combined_conf = 0.0, orig_conf
                
                # 计算增益
                max_single_asr = max(r1_asr, r2_asr)
                boost = combined_asr - max_single_asr
                
                # 使用与历史感知实验相同的协同判断标准
                conf_boost = max(r1_conf, r2_conf) - combined_conf
                is_synergistic = (boost > 0.2) or (conf_boost > 0.15)
                
                result = {
                    "combination": combo.name,
                    "sample_id": sample_id,
                    "rule1": combo.rule1,
                    "rule2": combo.rule2,
                    "original_conf": orig_conf,
                    "rule1_asr": r1_asr,
                    "rule2_asr": r2_asr,
                    "rule1_conf": r1_conf,
                    "rule2_conf": r2_conf,
                    "combined_asr": combined_asr,
                    "combined_conf": combined_conf,
                    "boost": boost,
                    "is_synergistic": is_synergistic,  # 统一标准：ASR提升>20% 或 置信度下降>0.15
                    "llm_info": info
                }
                
                combo_results.append(result)
                all_results.append(result)
                
                # 实时保存
                with open(results_file, 'a') as f:
                    f.write(json.dumps(result, ensure_ascii=False) + '\n')
        
        # 生成报告
        self.generate_report(all_results, output_path)
    
    def generate_report(self, results: List[Dict], output_path: Path):
        """生成报告"""
        report = {
            "total_tests": len(results),
            "combinations": {}
        }
        
        # 按组合分组
        by_combo = {}
        for r in results:
            combo = r['combination']
            if combo not in by_combo:
                by_combo[combo] = []
            by_combo[combo].append(r)
        
        # 统计每个组合
        for combo, combo_results in by_combo.items():
            n = len(combo_results)
            llm_used = sum(1 for r in combo_results if r['llm_info'].get('llm_used', False))
            avg_asr = sum(r['combined_asr'] for r in combo_results) / n if n > 0 else 0
            avg_boost = sum(r['boost'] for r in combo_results) / n if n > 0 else 0
            synergy_count = sum(1 for r in combo_results if r['is_synergistic'])
            
            report["combinations"][combo] = {
                "n": n,
                "llm_used_count": llm_used,
                "llm_used_rate": llm_used / n if n > 0 else 0,
                "avg_combined_asr": avg_asr,
                "avg_boost": avg_boost,
                "synergy_count": synergy_count,
                "synergy_rate": synergy_count / n if n > 0 else 0
            }
        
        # 保存报告
        with open(output_path / "independent_report.json", 'w') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        # 打印报告
        print(f"\n{'='*60}")
        print("独立LLM参数生成实验报告")
        print(f"{'='*60}\n")
        
        for combo, stats in report["combinations"].items():
            print(f"{combo}:")
            print(f"  测试数: {stats['n']}")
            print(f"  LLM使用率: {stats['llm_used_rate']*100:.1f}% ({stats['llm_used_count']}/{stats['n']})")
            print(f"  平均ASR: {stats['avg_combined_asr']*100:.1f}%")
            print(f"  平均增益: {stats['avg_boost']*100:+.1f}%")
            print(f"  协同率: {stats['synergy_rate']*100:.1f}% ({stats['synergy_count']}/{stats['n']})")
            print()
        
        print(f"报告已保存到: {output_path / 'independent_report.json'}")


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', default='config.yaml')
    parser.add_argument('--dataset', default='data/qualified_dataset.normalized.json')
    parser.add_argument('--n-samples', type=int, default=50)
    parser.add_argument('--output-dir', default='results/independent_llm_experiment')
    parser.add_argument('--seed', type=int, default=42, help='随机种子（与历史感知实验保持一致）')
    args = parser.parse_args()
    
    # 加载数据集
    with open(args.dataset, 'r') as f:
        dataset = json.load(f)
    
    # 设置随机种子（确保与历史感知实验采样一致）
    random.seed(args.seed)
    
    # 随机采样
    samples = random.sample(dataset, min(args.n_samples, len(dataset)))
    
    print(f"加载了 {len(samples)} 个测试样本\n")
    
    # 运行实验
    exp = IndependentLLMExperiment(args.config)
    exp.run_experiment(samples, args.output_dir)


if __name__ == '__main__':
    main()
