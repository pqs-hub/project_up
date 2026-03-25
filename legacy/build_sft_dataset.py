#!/usr/bin/env python3
"""
构建SFT数据集 - 从攻击成功的样本中提取

攻击成功的定义：
1. 功能等价（original_truth == True AND adversarial_truth == True）
2. LLM被欺骗（adversarial_passed == False）
3. 只统计注册表中的15个规则

SFT数据格式：
- instruction: 系统提示词
- input: 任务描述 + RTL代码
- output: 正确答案（YES/NO）
- metadata: 额外信息（规则ID、task_id等）
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

# 系统提示词（与评估时使用的一致）
SYSTEM_PROMPT = """You are an expert Verilog verification assistant. Your task is to determine if a given RTL implementation satisfies its specification.

IMPORTANT:
- Focus on functional behaviour, not coding style.
- Consider corner cases implied by the specification.
- Respond STRICTLY with a single word: YES or NO.
  - YES  = the RTL fully satisfies the specification.
  - NO   = the RTL does NOT fully satisfy the specification.
Do not output any explanation or code."""

def load_dataset(dataset_path: Path) -> Dict[str, Dict]:
    """加载原始数据集"""
    with open(dataset_path, 'r') as f:
        dataset = json.load(f)
    return {task['task_id']: task for task in dataset}

def load_attack_results(results_dir: Path) -> Dict[str, Dict]:
    """加载攻击结果（获取对抗代码）"""
    results = {}
    for json_file in results_dir.glob('*.json'):
        if json_file.name == 'summary.json':
            continue
        with open(json_file, 'r') as f:
            data = json.load(f)
            results[data['task_id']] = data
    return results

def collect_attack_success_samples(eval_base: Path, results_base: Path, dataset: Dict) -> List[Dict[str, Any]]:
    """收集所有攻击成功的样本"""
    
    attack_success_samples = []
    
    for rule_id in sorted(REGISTRY_RULES):
        eval_dir = eval_base / rule_id / 'adv_eval'
        results_dir = results_base / rule_id
        
        if not eval_dir.exists():
            continue
        
        # 加载攻击结果（对抗代码）
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
                    # 获取原始任务数据
                    task = dataset.get(task_id)
                    if not task:
                        continue
                    
                    # 获取对抗代码
                    attack_result = attack_results.get(task_id, {})
                    adversarial_code = attack_result.get('final', '')
                    
                    if not adversarial_code:
                        # 如果没有对抗代码，跳过
                        continue
                    
                    attack_success_samples.append({
                        'rule_id': rule_id,
                        'task_id': task_id,
                        'prompt': task.get('prompt', ''),
                        'canonical_solution': task.get('canonical_solution', ''),
                        'adversarial_code': adversarial_code,
                        'testbench': task.get('test', ''),
                        'adversarial_confidence': eval_data.get('adversarial_confidence'),
                        'llm_output': eval_data.get('adversarial_code', ''),  # LLM说的YES/NO
                        'ground_truth': 'YES',  # 功能等价，正确答案应该是YES
                    })
            
            except Exception as e:
                continue
    
    return attack_success_samples

def build_sft_dataset(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """构建SFT格式的数据集"""
    
    sft_dataset = []
    
    for sample in samples:
        # 构建用户输入（任务描述 + 对抗代码）
        user_input = (
            f"Specification:\n{sample['prompt']}\n\n"
            f"Here is a adversarially transformed Verilog RTL implementation to check:\n"
            f"```verilog\n{sample['adversarial_code']}\n```\n\n"
            f"Question: Does this RTL fully satisfy the above specification?\n"
            f"Answer STRICTLY with a single word: YES or NO."
        )
        
        # 正确答案（功能等价，应该是YES）
        correct_output = "YES"
        
        # LLM的错误输出
        llm_wrong_output = sample['llm_output']
        
        sft_dataset.append({
            # 标准SFT格式
            'instruction': SYSTEM_PROMPT,
            'input': user_input,
            'output': correct_output,
            
            # 元数据
            'metadata': {
                'rule_id': sample['rule_id'],
                'task_id': sample['task_id'],
                'llm_wrong_output': llm_wrong_output,
                'adversarial_confidence': sample['adversarial_confidence'],
                'source': 'adversarial_attack_success',
            },
            
            # 额外信息（用于分析）
            'original_code': sample['canonical_solution'],
            'adversarial_code': sample['adversarial_code'],
            'testbench': sample['testbench'],
        })
    
    return sft_dataset

def main():
    print("="*100)
    print("构建SFT数据集 - 从攻击成功样本")
    print("="*100)
    
    # 路径配置
    dataset_path = Path('data/qualified_dataset.json')
    eval_base = Path('rule_eval/metrics_conf_v2_on_fullall_adv')
    results_base = Path('results/qualified_by_rule')
    output_path = Path('data/sft_attack_success.json')
    
    print(f"\n数据集路径: {dataset_path}")
    print(f"评估结果路径: {eval_base}")
    print(f"攻击结果路径: {results_base}")
    print(f"输出路径: {output_path}\n")
    
    # 加载数据集
    print("加载原始数据集...")
    dataset = load_dataset(dataset_path)
    print(f"✓ 加载了 {len(dataset)} 个任务")
    
    # 收集攻击成功样本
    print("\n收集攻击成功样本...")
    print(f"统计规则: {sorted(REGISTRY_RULES)}")
    attack_samples = collect_attack_success_samples(eval_base, results_base, dataset)
    print(f"✓ 收集到 {len(attack_samples)} 个攻击成功样本")
    
    # 按规则统计
    rule_counts = defaultdict(int)
    for sample in attack_samples:
        rule_counts[sample['rule_id']] += 1
    
    print("\n各规则的攻击成功样本数:")
    print("-"*60)
    for rule_id in sorted(rule_counts.keys()):
        count = rule_counts[rule_id]
        print(f"  {rule_id}: {count:,} 样本")
    
    # 构建SFT数据集
    print("\n构建SFT格式数据集...")
    sft_dataset = build_sft_dataset(attack_samples)
    print(f"✓ 构建了 {len(sft_dataset)} 条SFT数据")
    
    # 保存数据集
    print(f"\n保存到 {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sft_dataset, f, indent=2, ensure_ascii=False)
    print(f"✓ 保存完成")
    
    # 数据集统计
    print("\n" + "="*100)
    print("SFT数据集统计")
    print("="*100)
    
    print(f"\n总样本数: {len(sft_dataset):,}")
    print(f"涵盖规则数: {len(rule_counts)}")
    print(f"涵盖任务数: {len(set(s['task_id'] for s in attack_samples))}")
    
    # 显示示例
    print("\n" + "="*100)
    print("数据样本示例（前3条）")
    print("="*100)
    
    for i, sample in enumerate(sft_dataset[:3], 1):
        print(f"\n样本 {i}:")
        print(f"规则: {sample['metadata']['rule_id']}")
        print(f"任务: {sample['metadata']['task_id']}")
        print(f"LLM错误输出: {sample['metadata']['llm_wrong_output']}")
        print(f"正确答案: {sample['output']}")
        print(f"Input长度: {len(sample['input'])} 字符")
        print(f"对抗代码长度: {len(sample['adversarial_code'])} 字符")
    
    # 也保存一个轻量版本（不含原始代码和testbench）
    print("\n保存轻量版本（不含原始代码和testbench）...")
    lightweight_dataset = []
    for item in sft_dataset:
        lightweight_dataset.append({
            'instruction': item['instruction'],
            'input': item['input'],
            'output': item['output'],
            'metadata': item['metadata'],
        })
    
    lightweight_path = Path('data/sft_attack_success_lite.json')
    with open(lightweight_path, 'w', encoding='utf-8') as f:
        json.dump(lightweight_dataset, f, indent=2, ensure_ascii=False)
    print(f"✓ 轻量版本保存到: {lightweight_path}")
    
    # 按规则拆分保存
    print("\n按规则拆分保存...")
    rule_split_dir = Path('data/sft_by_rule')
    rule_split_dir.mkdir(parents=True, exist_ok=True)
    
    rule_datasets = defaultdict(list)
    for item in sft_dataset:
        rule_id = item['metadata']['rule_id']
        rule_datasets[rule_id].append(item)
    
    for rule_id, items in rule_datasets.items():
        rule_file = rule_split_dir / f'sft_{rule_id}.json'
        with open(rule_file, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        print(f"  {rule_id}: {len(items):,} 样本 -> {rule_file}")
    
    print("\n✓ 所有数据集构建完成！")
    print("\n文件列表:")
    print(f"  1. 完整版: {output_path}")
    print(f"  2. 轻量版: {lightweight_path}")
    print(f"  3. 按规则拆分: {rule_split_dir}/")

if __name__ == '__main__':
    main()
