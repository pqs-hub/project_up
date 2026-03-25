#!/usr/bin/env python3
"""
基于攻击成功样本构建SFT数据集（兼容现有JSONL格式）

与现有 AdversarialDatasetGenerator 系统兼容：
- 使用相同的 JSONL 格式
- instruction/input/output/history 结构
- 输出包含策略说明 + JSON配置

只统计注册表中的15个规则的攻击成功样本
"""

import json
from pathlib import Path
from typing import List, Dict, Any
from collections import defaultdict

# 注册表规则
REGISTRY_RULES = {
    'T03', 'T07', 'T09', 'T10', 'T12', 
    'T19', 'T20', 'T30', 'T31', 'T32', 
    'T34', 'T41', 'T45', 'T47', 'T48'
}

# 规则名映射（transform_id -> attack_name）
TRANSFORM_TO_ATTACK_NAME = {
    'T03': 'redundant_logic',
    'T07': 'assign_reorder',
    'T09': 'demorgan_and',
    'T10': 'demorgan_or',
    'T12': 'intermediate_signal',
    'T19': 'false_pattern_injection',
    'T20': 'misleading_comment',
    'T30': 'constant_identity',
    'T31': 'simple_intermediate',
    'T32': 'bitwidth_arithmetic',
    'T34': 'universal_rename',
    'T41': 'case_branch_reorder',
    'T45': 'pseudo_comb_loop',
    'T47': 'dataflow_shattering',
    'T48': 'anti_topological_shuffle',
}

# 规则策略说明
RULE_STRATEGIES = {
    'T03': 'Inject redundant logic operations to increase code complexity without changing functionality.',
    'T07': 'Reorder independent assignment statements to disrupt sequential flow understanding.',
    'T09': 'Apply DeMorgan\'s law to AND operations: a & b → ~(~a | ~b).',
    'T10': 'Apply DeMorgan\'s law to OR operations: a | b → ~(~a & ~b).',
    'T12': 'Extract ternary predicate into intermediate wire to add indirection.',
    'T19': 'Inject unreachable dead code blocks (wrapped in if(1\'b0)) to confuse control flow analysis.',
    'T20': 'Add misleading comments that describe incorrect functionality.',
    'T30': 'Replace bit constants with equivalent expressions: 1\'b0 → (1\'b1 & 1\'b0).',
    'T31': 'Split simple assignments into intermediate wires to increase indirection.',
    'T32': 'Transform bit-width declarations into arithmetic expressions: [7:0] → [8-1:0].',
    'T34': 'Rename signals with semantically confusing identifiers.',
    'T41': 'Rotate case statement branches to alter execution order perception.',
    'T45': 'Inject contradictory terms (a & ~a) that are always false to create pseudo-loops.',
    'T47': 'Apply Shannon expansion to shatter comparators or adders into bit-level operations.',
    'T48': 'Reverse the order of assignment statements in anti-topological manner.',
}

# 系统指令（与现有格式保持一致）
SYSTEM_INSTRUCTION = """You are a Verilog obfuscation expert. Given the functional spec and original code, choose one transformation rule that best misleads the verification model. Optionally give a short strategy, then output a JSON block. Use only these top-level keys (do not use the rule name as top-level key):
```json
{
  "attack_name": "rule name in English (required)",
  "target_line": 10,
  "target_signal": "signal_name",
  "parameters": {}
}
```
attack_name is required; target_line (1-based), target_signal, and parameters are optional. target_line must match the line number in the original code block (e.g. 1: means line 1). Omit keys you do not need; do not use null or empty string. Your reply must end with exactly one ```json ... ``` block; do not add any text after it."""

def load_dataset(dataset_path: Path) -> Dict[str, Dict]:
    """加载原始数据集"""
    with open(dataset_path, 'r') as f:
        dataset = json.load(f)
    return {task['task_id']: task for task in dataset}

def load_attack_results(results_dir: Path) -> Dict[str, Dict]:
    """加载攻击结果"""
    results = {}
    for json_file in results_dir.glob('*.json'):
        if json_file.name == 'summary.json':
            continue
        with open(json_file, 'r') as f:
            data = json.load(f)
            results[data['task_id']] = data
    return results

def add_line_numbers(code: str) -> str:
    """给代码添加行号（与现有格式一致）"""
    lines = code.split('\n')
    numbered = []
    for i, line in enumerate(lines, 1):
        numbered.append(f"{i}: {line}")
    return '\n'.join(numbered)

def sample_parameters_for_rule(engine, rule_id: str, original_code: str) -> Dict:
    """为规则采样真实参数"""
    from AttackConfigGenerator import AttackConfigGenerator
    
    # 创建配置生成器
    config_gen = AttackConfigGenerator(
        engine=engine,
        max_attacks_per_sample=1,
        max_positions_per_rule=1,
        max_params_per_rule=1
    )
    
    # 为指定规则生成配置
    try:
        configs = config_gen.generate_for_rules(original_code, [rule_id])
        if configs:
            return configs[0].parameters
    except Exception as e:
        pass
    
    return {}

def collect_attack_success_samples(
    eval_base: Path,
    results_base: Path,
    dataset: Dict,
    engine
) -> List[Dict[str, Any]]:
    """收集所有攻击成功的样本"""
    
    samples = []
    
    for rule_id in sorted(REGISTRY_RULES):
        eval_dir = eval_base / rule_id / 'adv_eval'
        results_dir = results_base / rule_id
        
        if not eval_dir.exists():
            continue
        
        # 加载攻击结果
        attack_results = {}
        if results_dir.exists():
            attack_results = load_attack_results(results_dir)
        
        for json_file in eval_dir.glob('*.json'):
            try:
                with open(json_file, 'r') as f:
                    eval_data = json.load(f)
                
                task_id = eval_data.get('task_id')
                orig_truth = eval_data.get('original_truth')
                adv_truth = eval_data.get('adversarial_truth')
                adv_passed = eval_data.get('adversarial_passed')
                
                # 筛选：功能等价 AND LLM判错（攻击成功）
                if orig_truth == True and adv_truth == True and adv_passed == False:
                    task = dataset.get(task_id)
                    if not task:
                        continue
                    
                    attack_result = attack_results.get(task_id, {})
                    adversarial_code = attack_result.get('final', '')
                    
                    if not adversarial_code:
                        continue
                    
                    # 获取 target_line、target_signal 和 parameters
                    original_code = task.get('canonical_solution', '')
                    target_line, target_signal = None, None
                    parameters = {}
                    
                    try:
                        # 从引擎获取第一个候选位置
                        target_line, target_signal = engine.get_target_line_signal(
                            original_code, rule_id, 0
                        )
                        
                        # 采样真实参数
                        parameters = sample_parameters_for_rule(engine, rule_id, original_code)
                    except Exception as e:
                        pass
                    
                    samples.append({
                        'rule_id': rule_id,
                        'task_id': task_id,
                        'prompt': task.get('prompt', ''),
                        'original_code': original_code,
                        'adversarial_code': adversarial_code,
                        'target_line': target_line,
                        'target_signal': target_signal,
                        'parameters': parameters,
                        'adversarial_confidence': eval_data.get('adversarial_confidence'),
                    })
            
            except Exception as e:
                continue
    
    return samples

def build_sft_jsonl(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """构建JSONL格式的SFT数据集"""
    
    sft_dataset = []
    
    for sample in samples:
        rule_id = sample['rule_id']
        attack_name = TRANSFORM_TO_ATTACK_NAME.get(rule_id, rule_id.lower())
        strategy = RULE_STRATEGIES.get(rule_id, f"Apply {attack_name} transformation.")
        
        # 添加行号的原始代码
        numbered_code = add_line_numbers(sample['original_code'])
        
        # 构建 input（与现有格式一致）
        input_text = (
            f"### 功能规范\n{sample['prompt']}\n\n"
            f"### 原始代码\n```verilog\n{numbered_code}\n```"
        )
        
        # 构建 output（策略 + JSON）
        output_json = {
            "attack_name": attack_name
        }
        
        # 只在有值时添加 target_line 和 target_signal
        if sample['target_line'] is not None:
            output_json["target_line"] = sample['target_line']
        if sample['target_signal'] is not None and sample['target_signal']:
            output_json["target_signal"] = sample['target_signal']
        
        # 添加真实采样的参数（如果有）
        if sample.get('parameters'):
            output_json["parameters"] = sample['parameters']
        
        output_text = (
            f"Strategy: {strategy}\n\n"
            f"```json\n{json.dumps(output_json, indent=2, ensure_ascii=False)}\n```"
        )
        
        # JSONL 格式（与现有一致）
        sft_sample = {
            "instruction": SYSTEM_INSTRUCTION,
            "input": input_text,
            "output": output_text,
            "history": []
        }
        
        sft_dataset.append(sft_sample)
    
    return sft_dataset

def main():
    print("="*100)
    print("基于攻击成功样本构建SFT数据集（JSONL格式）")
    print("="*100)
    
    # 加载引擎
    from ast_transforms_loader import create_engine
    engine = create_engine()
    
    # 路径配置
    dataset_path = Path('data/qualified_dataset.json')
    eval_base = Path('rule_eval/metrics_conf_v2_on_fullall_adv')
    results_base = Path('results/qualified_by_rule')
    output_path = Path('data/sft_attack_success_registry.jsonl')
    
    print(f"\n数据集路径: {dataset_path}")
    print(f"评估结果路径: {eval_base}")
    print(f"攻击结果路径: {results_base}")
    print(f"输出路径: {output_path}\n")
    
    # 加载数据集
    print("加载原始数据集...")
    dataset = load_dataset(dataset_path)
    print(f"✓ 加载了 {len(dataset)} 个任务")
    
    # 收集攻击成功样本
    print("\n收集攻击成功样本（仅15个注册表规则）...")
    print(f"统计规则: {sorted(REGISTRY_RULES)}")
    attack_samples = collect_attack_success_samples(eval_base, results_base, dataset, engine)
    print(f"✓ 收集到 {len(attack_samples)} 个攻击成功样本")
    
    # 按规则统计
    rule_counts = defaultdict(int)
    for sample in attack_samples:
        rule_counts[sample['rule_id']] += 1
    
    print("\n各规则的攻击成功样本数:")
    print("-"*60)
    for rule_id in sorted(rule_counts.keys()):
        count = rule_counts[rule_id]
        attack_name = TRANSFORM_TO_ATTACK_NAME.get(rule_id, rule_id)
        print(f"  {rule_id} ({attack_name}): {count:,} 样本")
    
    # 构建SFT数据集
    print("\n构建JSONL格式数据集...")
    sft_dataset = build_sft_jsonl(attack_samples)
    print(f"✓ 构建了 {len(sft_dataset)} 条SFT数据")
    
    # 保存数据集（JSONL格式）
    print(f"\n保存到 {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        for item in sft_dataset:
            f.write(json.dumps(item, ensure_ascii=False) + '\n')
    print(f"✓ 保存完成")
    
    # 数据集统计
    print("\n" + "="*100)
    print("SFT数据集统计（JSONL格式）")
    print("="*100)
    
    print(f"\n总样本数: {len(sft_dataset):,}")
    print(f"涵盖规则数: {len(rule_counts)}")
    print(f"涵盖任务数: {len(set(s['task_id'] for s in attack_samples))}")
    
    # 显示示例
    print("\n" + "="*100)
    print("数据样本示例（前2条）")
    print("="*100)
    
    for i, sample in enumerate(sft_dataset[:2], 1):
        print(f"\n样本 {i}:")
        print(f"Instruction: {sample['instruction'][:100]}...")
        print(f"Input长度: {len(sample['input'])} 字符")
        print(f"Output: {sample['output'][:200]}...")
        print()
    
    # 按规则拆分保存
    print("按规则拆分保存...")
    rule_split_dir = Path('data/sft_attack_success_by_rule')
    rule_split_dir.mkdir(parents=True, exist_ok=True)
    
    rule_datasets = defaultdict(list)
    for i, sample in enumerate(sft_dataset):
        # 从原始样本列表获取 rule_id
        rule_id = attack_samples[i]['rule_id']
        rule_datasets[rule_id].append(sample)
    
    for rule_id, items in rule_datasets.items():
        rule_file = rule_split_dir / f'sft_{rule_id}.jsonl'
        with open(rule_file, 'w', encoding='utf-8') as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + '\n')
        print(f"  {rule_id}: {len(items):,} 样本 -> {rule_file}")
    
    print("\n✓ 所有数据集构建完成！")
    print("\n文件列表:")
    print(f"  1. 主文件: {output_path}")
    print(f"  2. 按规则拆分: {rule_split_dir}/")
    
    # 计算文件大小
    import os
    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\n文件大小: {file_size:.2f} MB")
    
    # 与现有数据集比较
    existing_sft = Path('data/sft_from_eval_highquality.jsonl')
    if existing_sft.exists():
        with open(existing_sft, 'r') as f:
            existing_count = sum(1 for _ in f)
        print(f"\n对比现有数据集:")
        print(f"  现有: {existing_sft} ({existing_count:,} 样本)")
        print(f"  新生成: {output_path} ({len(sft_dataset):,} 样本)")

if __name__ == '__main__':
    main()
