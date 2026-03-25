#!/usr/bin/env python3
"""
对verilog_eval.json数据集进行攻击实验
使用新的COT判题提示词，统计不同规则组合的攻击成功率
"""

import json
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from tqdm import tqdm
import argparse

# 添加项目路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from taget_model import TargetModelClient
from ast_transforms_loader import load_ast_transforms

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class AttackResult:
    """攻击结果"""
    task_id: str
    scenario_name: str
    original_correct: bool
    original_confidence: float
    attack_success: bool
    adversarial_confidence: float
    confidence_drop: float
    rules_used: List[str]
    params_used: Dict


# 定义攻击场景 - 只包含联合攻击（2个或以上规则）
# 注意：只使用实际存在的规则（T03,T07,T09,T10,T12,T19,T20,T30,T31,T32,T34,T41,T45,T47,T48）
ATTACK_SCENARIOS = {
    "T20_T34_Semantic": {
        "description": "语义劫持（注释+重命名）",
        "rules": ["T20", "T34"],
        "params": [
            {"custom_text": "// UART Serial Communication Controller"},
            {"custom_map": {}, "fallback_prefix": "uart_"}
        ]
    },
    "T34_T32_Signal_Affinity": {
        "description": "信号亲和性（重命名+位宽）",
        "rules": ["T34", "T32"],
        "params": [
            {"fallback_prefix": "flag_"},
            {"offset": 2, "use_multiply": False}
        ]
    },
    "T20_T34_T31_Multi_Layer": {
        "description": "多层语义劫持（注释+重命名+中间信号）",
        "rules": ["T20", "T34", "T31"],
        "params": [
            {"custom_text": "// SPI Master Controller with FIFO"},
            {"custom_map": {}, "fallback_prefix": "spi_"},
            {"wire_name": "spi_internal_buffer"}
        ]
    },
    "T19_T09_Structure": {
        "description": "结构混淆（死代码+DeMorgan）",
        "rules": ["T19", "T09"],
        "params": [
            {"custom_dead_stmts": "temp_unused = 1'b0;"},
            {}
        ]
    },
    "T34_T07_Logic": {
        "description": "逻辑混淆（重命名+赋值重排）",
        "rules": ["T34", "T07"],
        "params": [
            {"fallback_prefix": "reordered_"},
            {}
        ]
    },
    "T20_T32_Semantic_Bitwidth": {
        "description": "语义+位宽混淆（注释+位宽算术）",
        "rules": ["T20", "T32"],
        "params": [
            {"custom_text": "// 16-bit Counter Module"},
            {"offset": 1, "use_multiply": False}
        ]
    },
    "T34_T48_Dataflow": {
        "description": "数据流混淆（重命名+逆拓扑）",
        "rules": ["T34", "T48"],
        "params": [
            {"fallback_prefix": "reversed_"},
            {}
        ]
    },
    "T20_T34_T32_Deep": {
        "description": "深度混淆（注释+重命名+位宽）",
        "rules": ["T20", "T34", "T32"],
        "params": [
            {"custom_text": "// Advanced Memory Controller"},
            {"fallback_prefix": "mem_"},
            {"offset": 2, "use_multiply": False}
        ]
    },
}


def load_verilog_eval(dataset_path: str) -> List[Dict]:
    """加载verilog_eval数据集"""
    with open(dataset_path, 'r') as f:
        data = json.load(f)
    logger.info(f"加载了 {len(data)} 个测试样本")
    return data


def apply_attack_scenario(
    rtl: str,
    scenario: Dict,
    ast_transforms
) -> Optional[str]:
    """应用攻击场景"""
    try:
        result = rtl
        for rule_id, params in zip(scenario["rules"], scenario["params"]):
            # 获取变换函数
            transform = ast_transforms.AST_TRANSFORM_REGISTRY.get(rule_id)
            if not transform:
                logger.warning(f"规则 {rule_id} 不存在")
                return None
            
            # 应用变换 - 使用apply_func而不是func
            output = transform.apply_func(result, **params)
            
            # 某些规则（如T34）返回(code, rename_map)元组，需要提取code
            if isinstance(output, tuple):
                result = output[0]
            else:
                result = output
            
            # 检查是否有变化
            if result == rtl and rule_id not in ["T07", "T48"]:  # 某些规则可能不改变代码
                logger.debug(f"规则 {rule_id} 未产生变化")
        
        return result if result != rtl else None
    except Exception as e:
        logger.error(f"应用攻击场景失败: {e}")
        return None


def run_attack_experiment(
    dataset_path: str,
    victim_client: TargetModelClient,
    output_path: str,
    max_samples: Optional[int] = None
):
    """运行攻击实验"""
    
    # 加载数据集
    dataset = load_verilog_eval(dataset_path)
    if max_samples:
        dataset = dataset[:max_samples]
    
    # 加载AST变换
    ast_transforms = load_ast_transforms()
    
    results = []
    scenario_stats = {name: {"total": 0, "success": 0, "original_correct": 0} 
                     for name in ATTACK_SCENARIOS.keys()}
    
    print("\n" + "=" * 60)
    print("Verilog Eval 攻击实验 (COT判题)")
    print("=" * 60)
    
    for sample in tqdm(dataset, desc="处理样本"):
        task_id = sample["task_id"]
        spec = sample["prompt"]
        original_rtl = sample["canonical_solution"]
        
        # 1. 判断原始代码是否正确
        original_verdict = victim_client.judge(spec, original_rtl, use_cot=True)
        if not original_verdict:
            logger.warning(f"样本 {task_id} 原始判题失败")
            continue
        
        original_correct = original_verdict.get("is_correct", False)
        original_conf = original_verdict.get("confidence", 0.0)
        
        # 只对原始代码被判定为正确的样本进行攻击
        if not original_correct:
            logger.info(f"样本 {task_id} 原始代码未通过判题，跳过")
            continue
        
        # 2. 对每个攻击场景进行测试
        for scenario_name, scenario in ATTACK_SCENARIOS.items():
            scenario_stats[scenario_name]["total"] += 1
            scenario_stats[scenario_name]["original_correct"] += 1
            
            # 应用攻击
            adversarial_rtl = apply_attack_scenario(
                original_rtl, 
                scenario, 
                ast_transforms
            )
            
            if not adversarial_rtl:
                logger.debug(f"样本 {task_id} 场景 {scenario_name} 未产生对抗代码")
                continue
            
            # 判断对抗代码
            adv_verdict = victim_client.judge(spec, adversarial_rtl, use_cot=True)
            if not adv_verdict:
                logger.warning(f"样本 {task_id} 场景 {scenario_name} 对抗判题失败")
                continue
            
            adv_correct = adv_verdict.get("is_correct", False)
            adv_conf = adv_verdict.get("confidence", 0.0)
            
            # 攻击成功：原始正确 -> 对抗错误
            attack_success = original_correct and not adv_correct
            if attack_success:
                scenario_stats[scenario_name]["success"] += 1
            
            # 记录结果
            result = AttackResult(
                task_id=task_id,
                scenario_name=scenario_name,
                original_correct=original_correct,
                original_confidence=original_conf,
                attack_success=attack_success,
                adversarial_confidence=adv_conf,
                confidence_drop=original_conf - adv_conf,
                rules_used=scenario["rules"],
                params_used=scenario["params"]
            )
            results.append(asdict(result))
    
    # 保存详细结果
    output_file = Path(output_path) / "attack_results_cot.jsonl"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, 'w') as f:
        for result in results:
            f.write(json.dumps(result, ensure_ascii=False) + '\n')
    
    # 生成统计报告
    report = {
        "dataset": dataset_path,
        "total_samples": len(dataset),
        "scenarios": {}
    }
    
    print("\n" + "=" * 60)
    print("攻击成功率统计 (COT判题)")
    print("=" * 60)
    print(f"\n{'场景':<40} {'样本数':<10} {'成功数':<10} {'ASR':<10}")
    print("-" * 70)
    
    for scenario_name, stats in scenario_stats.items():
        total = stats["original_correct"]
        success = stats["success"]
        asr = (success / total * 100) if total > 0 else 0.0
        
        scenario_desc = ATTACK_SCENARIOS[scenario_name]["description"]
        rules = "+".join(ATTACK_SCENARIOS[scenario_name]["rules"])
        
        print(f"{scenario_desc:<30} ({rules:<8}) {total:<10} {success:<10} {asr:>6.1f}%")
        
        report["scenarios"][scenario_name] = {
            "description": scenario_desc,
            "rules": ATTACK_SCENARIOS[scenario_name]["rules"],
            "total_samples": total,
            "successful_attacks": success,
            "attack_success_rate": round(asr, 2)
        }
    
    # 保存报告
    report_file = Path(output_path) / "attack_report_cot.json"
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    
    print(f"\n详细结果已保存到: {output_file}")
    print(f"统计报告已保存到: {report_file}")


def main():
    parser = argparse.ArgumentParser(description="对verilog_eval数据集进行COT攻击实验")
    parser.add_argument(
        "--dataset",
        type=str,
        default="/data3/pengqingsong/LLM_attack/data/verilog_eval.json",
        help="数据集路径"
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default="http://localhost:8001/v1",
        help="模型API地址"
    )
    parser.add_argument(
        "--model",
        type=str,
        default="verilog_attack_merged_bal500",
        help="模型名称"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="results/verilog_eval_cot_attack",
        help="输出目录"
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="最大样本数（用于测试）"
    )
    
    args = parser.parse_args()
    
    # 创建victim模型客户端
    victim = TargetModelClient(
        base_url=args.base_url,
        api_key="EMPTY",
        model=args.model,
        timeout=60,
        max_retries=3
    )
    
    # 运行实验
    run_attack_experiment(
        dataset_path=args.dataset,
        victim_client=victim,
        output_path=args.output_dir,
        max_samples=args.max_samples
    )


if __name__ == "__main__":
    main()
