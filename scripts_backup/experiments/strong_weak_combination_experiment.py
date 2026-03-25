#!/usr/bin/env python3
"""
强强组合 vs 强弱组合实验

研究问题：
1. 最强的两个规则组合是否一定效果最好？
2. 强规则+弱规则是否可能因为互补效应超过强强组合？
3. 在100个样本上验证不同组合策略的效果
"""

import json
import sys
from pathlib import Path
from typing import List, Dict, Tuple
from dataclasses import dataclass
import random
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from ast_transforms_loader import create_engine
from taget_model import TargetModelClient
import yaml


@dataclass
class RuleStrength:
    """规则强度信息"""
    rule_id: str
    asr: float
    gain: float
    coverage: float
    strength: float


@dataclass
class CombinationResult:
    """组合结果"""
    combination_type: str  # "strong_strong", "strong_weak", "weak_weak"
    rule1: str
    rule2: str
    rule1_strength: float
    rule2_strength: float
    sample_id: str
    
    # 单规则结果
    rule1_asr: float
    rule2_asr: float
    rule1_conf: float
    rule2_conf: float
    
    # 组合结果
    combined_asr: float
    combined_conf: float
    
    # 协同指标
    asr_boost: float
    conf_boost: float
    is_synergistic: bool


class StrongWeakExperiment:
    """强弱组合实验"""
    
    def __init__(self, config_path: str):
        with open(config_path, 'r') as f:
            self.config = yaml.safe_load(f)
        
        self.engine = create_engine()
        
        # 获取可用规则列表
        self.available_rules = set(self.engine.registry.keys())
        print(f"引擎支持的规则: {sorted(self.available_rules)}")
        
        # 初始化模型客户端
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
        self.rule_strengths = self._load_rule_strengths()
    
    def _load_rule_strengths(self) -> List[RuleStrength]:
        """加载所有规则的强度信息"""
        metrics_dir = Path("/data3/pengqingsong/LLM_attack/rule_eval/metrics_full_all_rules")
        
        strengths = []
        for report_file in metrics_dir.glob("T*_report.json"):
            with open(report_file, 'r') as f:
                data = json.load(f)
            
            rule_id = data['rule_id']
            
            # 只加载引擎支持的规则
            if rule_id not in self.available_rules:
                continue
            
            strengths.append(RuleStrength(
                rule_id=rule_id,
                asr=data.get('asr', 0.0),
                gain=data.get('gain', 0.0),
                coverage=data.get('coverage', 0.0),
                strength=data.get('strength', 0.0)
            ))
        
        # 按ASR排序
        strengths.sort(key=lambda x: x.asr, reverse=True)
        
        print(f"\n加载了 {len(strengths)} 个可用规则的强度信息")
        print(f"\n前10强规则:")
        for i, s in enumerate(strengths[:10], 1):
            print(f"  {i}. {s.rule_id}: ASR={s.asr:.3f}, Gain={s.gain:.3f}")
        
        return strengths
    
    def select_combinations(self) -> Dict[str, List[Tuple[str, str]]]:
        """选择不同类型的规则组合"""
        
        # 定义强、中、弱规则
        n = len(self.rule_strengths)
        strong_rules = [r.rule_id for r in self.rule_strengths[:5]]  # Top 5
        medium_rules = [r.rule_id for r in self.rule_strengths[5:15]]  # 6-15
        weak_rules = [r.rule_id for r in self.rule_strengths[15:]]  # 16+
        
        print(f"\n规则分类:")
        print(f"  强规则 (Top 5): {strong_rules}")
        print(f"  中等规则 (6-15): {medium_rules[:5]}...")
        print(f"  弱规则 (16+): {weak_rules[:5]}...")
        
        combinations = {
            "strong_strong": [],
            "strong_medium": [],
            "strong_weak": [],
            "medium_medium": [],
            "medium_weak": [],
            "weak_weak": []
        }
        
        # 强强组合（所有可能的Top5组合）
        for i in range(len(strong_rules)):
            for j in range(i+1, len(strong_rules)):
                combinations["strong_strong"].append((strong_rules[i], strong_rules[j]))
        
        # 强中组合（每个强规则配3个中等规则）
        for strong in strong_rules:
            for medium in random.sample(medium_rules, min(3, len(medium_rules))):
                combinations["strong_medium"].append((strong, medium))
        
        # 强弱组合（每个强规则配2个弱规则）
        for strong in strong_rules:
            for weak in random.sample(weak_rules, min(2, len(weak_rules))):
                combinations["strong_weak"].append((strong, weak))
        
        # 中中组合（随机选10对）
        for _ in range(10):
            if len(medium_rules) >= 2:
                pair = random.sample(medium_rules, 2)
                combinations["medium_medium"].append(tuple(pair))
        
        # 中弱组合（随机选10对）
        for _ in range(10):
            if medium_rules and weak_rules:
                combinations["medium_weak"].append((
                    random.choice(medium_rules),
                    random.choice(weak_rules)
                ))
        
        # 弱弱组合（随机选5对）
        for _ in range(5):
            if len(weak_rules) >= 2:
                pair = random.sample(weak_rules, 2)
                combinations["weak_weak"].append(tuple(pair))
        
        print(f"\n组合数量:")
        for ctype, pairs in combinations.items():
            print(f"  {ctype}: {len(pairs)} 对")
        
        return combinations
    
    def load_test_samples(self, n_samples: int = 100) -> List[Dict]:
        """加载测试样本"""
        dataset_path = Path("/data3/pengqingsong/LLM_attack/data/qualified_dataset.normalized.json")
        
        with open(dataset_path, 'r') as f:
            all_samples = json.load(f)
        
        # 随机选择n_samples个
        selected = random.sample(all_samples, min(n_samples, len(all_samples)))
        
        print(f"\n加载了 {len(selected)} 个测试样本")
        return selected
    
    def evaluate_single_rule(self, rtl: str, spec: str, rule_id: str) -> Tuple[float, float]:
        """评估单个规则"""
        try:
            # 应用变换
            transformed = self.engine.apply_transform(
                code=rtl,
                transform_id=rule_id,
                target_token=0
            )
            
            if transformed == rtl:
                # 变换失败
                return 0.0, 1.0
            
            # 查询模型
            verdict = self.model_client.judge(spec, transformed)
            
            if verdict is None:
                return 0.0, 1.0
            
            asr = 0.0 if verdict['is_correct'] else 1.0
            conf = verdict.get('confidence', 0.5)
            
            return asr, conf
            
        except Exception as e:
            print(f"    规则 {rule_id} 评估失败: {e}")
            return 0.0, 1.0
    
    def evaluate_combination(
        self, 
        rtl: str, 
        spec: str, 
        rule1: str, 
        rule2: str
    ) -> Tuple[float, float]:
        """评估规则组合"""
        try:
            # 先应用rule1
            transformed = self.engine.apply_transform(
                code=rtl,
                transform_id=rule1,
                target_token=0
            )
            
            if transformed == rtl:
                return 0.0, 1.0
            
            # 再应用rule2
            transformed = self.engine.apply_transform(
                code=transformed,
                transform_id=rule2,
                target_token=0
            )
            
            # 查询模型
            verdict = self.model_client.judge(spec, transformed)
            
            if verdict is None:
                return 0.0, 1.0
            
            asr = 0.0 if verdict['is_correct'] else 1.0
            conf = verdict.get('confidence', 0.5)
            
            return asr, conf
            
        except Exception as e:
            print(f"    组合 {rule1}+{rule2} 评估失败: {e}")
            return 0.0, 1.0
    
    def run_experiment(
        self, 
        combinations: Dict[str, List[Tuple[str, str]]],
        samples: List[Dict],
        output_dir: str
    ):
        """运行实验"""
        output_path = Path(output_dir)
        output_path.mkdir(parents=True, exist_ok=True)
        
        results_file = output_path / "combination_results.jsonl"
        
        # 为每种组合类型选择样本
        samples_per_type = max(1, len(samples) // len(combinations))
        
        all_results = []
        
        for ctype, pairs in combinations.items():
            print(f"\n{'='*60}")
            print(f"测试组合类型: {ctype}")
            print(f"{'='*60}")
            
            # 为这种类型选择样本
            type_samples = random.sample(samples, min(samples_per_type, len(samples)))
            
            for sample in tqdm(type_samples, desc=f"{ctype}"):
                rtl = sample.get('canonical_solution', sample.get('rtl', ''))
                spec = sample['prompt']
                sample_id = sample.get('task_id', sample.get('id', 'unknown'))
                
                # 为这个样本测试几对组合
                test_pairs = random.sample(pairs, min(3, len(pairs)))
                
                for rule1, rule2 in test_pairs:
                    # 获取规则强度
                    r1_strength = next((r.asr for r in self.rule_strengths if r.rule_id == rule1), 0.0)
                    r2_strength = next((r.asr for r in self.rule_strengths if r.rule_id == rule2), 0.0)
                    
                    # 评估单规则
                    r1_asr, r1_conf = self.evaluate_single_rule(rtl, spec, rule1)
                    r2_asr, r2_conf = self.evaluate_single_rule(rtl, spec, rule2)
                    
                    # 评估组合
                    comb_asr, comb_conf = self.evaluate_combination(rtl, spec, rule1, rule2)
                    
                    # 计算协同指标
                    max_single_asr = max(r1_asr, r2_asr)
                    asr_boost = comb_asr - max_single_asr
                    
                    max_single_conf = max(r1_conf, r2_conf)
                    conf_boost = max_single_conf - comb_conf
                    
                    is_synergistic = (asr_boost > 0.2) or (conf_boost > 0.15)
                    
                    result = CombinationResult(
                        combination_type=ctype,
                        rule1=rule1,
                        rule2=rule2,
                        rule1_strength=r1_strength,
                        rule2_strength=r2_strength,
                        sample_id=sample_id,
                        rule1_asr=r1_asr,
                        rule2_asr=r2_asr,
                        rule1_conf=r1_conf,
                        rule2_conf=r2_conf,
                        combined_asr=comb_asr,
                        combined_conf=comb_conf,
                        asr_boost=asr_boost,
                        conf_boost=conf_boost,
                        is_synergistic=is_synergistic
                    )
                    
                    all_results.append(result)
                    
                    # 实时保存
                    with open(results_file, 'a', encoding='utf-8') as f:
                        f.write(json.dumps(result.__dict__, ensure_ascii=False) + '\n')
        
        print(f"\n实验完成！共 {len(all_results)} 个测试")
        print(f"结果已保存到: {results_file}")
        
        # 生成汇总报告
        self._generate_report(all_results, output_path)
    
    def _generate_report(self, results: List[CombinationResult], output_dir: Path):
        """生成汇总报告"""
        
        # 按组合类型分组
        by_type = {}
        for r in results:
            if r.combination_type not in by_type:
                by_type[r.combination_type] = []
            by_type[r.combination_type].append(r)
        
        report = {
            "total_tests": len(results),
            "by_combination_type": {}
        }
        
        print(f"\n{'='*60}")
        print("实验报告")
        print(f"{'='*60}")
        
        for ctype, type_results in by_type.items():
            n = len(type_results)
            
            avg_asr = sum(r.combined_asr for r in type_results) / n
            avg_boost = sum(r.asr_boost for r in type_results) / n
            synergy_count = sum(1 for r in type_results if r.is_synergistic)
            synergy_rate = synergy_count / n
            
            avg_r1_strength = sum(r.rule1_strength for r in type_results) / n
            avg_r2_strength = sum(r.rule2_strength for r in type_results) / n
            avg_strength = (avg_r1_strength + avg_r2_strength) / 2
            
            report["by_combination_type"][ctype] = {
                "n": n,
                "avg_rule_strength": avg_strength,
                "avg_combined_asr": avg_asr,
                "avg_asr_boost": avg_boost,
                "synergy_count": synergy_count,
                "synergy_rate": synergy_rate
            }
            
            print(f"\n{ctype}:")
            print(f"  测试数: {n}")
            print(f"  平均规则强度: {avg_strength:.3f}")
            print(f"  平均组合ASR: {avg_asr:.3f}")
            print(f"  平均ASR提升: {avg_boost:+.3f}")
            print(f"  协同率: {synergy_rate:.1%} ({synergy_count}/{n})")
        
        # 保存报告
        report_file = output_dir / "combination_report.json"
        with open(report_file, 'w', encoding='utf-8') as f:
            json.dump(report, f, indent=2, ensure_ascii=False)
        
        print(f"\n报告已保存到: {report_file}")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='强强组合 vs 强弱组合实验')
    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='配置文件路径'
    )
    parser.add_argument(
        '--n-samples',
        type=int,
        default=100,
        help='测试样本数'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='results/strong_weak_experiment',
        help='输出目录'
    )
    parser.add_argument(
        '--seed',
        type=int,
        default=42,
        help='随机种子'
    )
    
    args = parser.parse_args()
    
    # 设置随机种子
    random.seed(args.seed)
    
    print("="*60)
    print("强强组合 vs 强弱组合实验")
    print("="*60)
    print(f"配置文件: {args.config}")
    print(f"样本数: {args.n_samples}")
    print(f"输出目录: {args.output_dir}")
    print(f"随机种子: {args.seed}")
    
    # 创建实验
    experiment = StrongWeakExperiment(args.config)
    
    # 选择组合
    combinations = experiment.select_combinations()
    
    # 加载样本
    samples = experiment.load_test_samples(args.n_samples)
    
    # 运行实验
    experiment.run_experiment(combinations, samples, args.output_dir)


if __name__ == '__main__':
    main()
