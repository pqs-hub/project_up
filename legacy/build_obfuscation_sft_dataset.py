#!/usr/bin/env python3
"""
构建代码混淆SFT数据集

训练目标：让大模型学会生成混淆后的Verilog代码

数据格式：
- instruction: 系统提示词（教模型如何混淆代码）
- input: 原始代码 + 混淆规则
- output: 混淆后的代码

只使用攻击成功的样本（功能等价 + LLM被欺骗）
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

# 规则描述（供模型理解）
RULE_DESCRIPTIONS = {
    'T03': '冗余逻辑注入：添加冗余的逻辑运算（如 signal & 1\'b1）',
    'T07': '赋值重排：交换独立的assign语句顺序',
    'T09': '德摩根AND：将 a & b 转换为 ~(~a | ~b)',
    'T10': '德摩根OR：将 a | b 转换为 ~(~a & ~b)',
    'T12': '中间信号注入（三元）：将三元表达式的条件提取为中间信号',
    'T19': '虚假模式注入：插入永不执行的死代码块',
    'T20': '误导性注释：添加误导性的注释',
    'T30': '常量恒等变换：将常量替换为等价表达式（如 1\'b0 -> (1\'b1 & 1\'b0)）',
    'T31': '中间信号注入（赋值）：将赋值拆分为中间信号',
    'T32': '位宽算术变换：将位宽声明转换为算术表达式（如 [7:0] -> [8-1:0]）',
    'T34': '通用重命名：对信号进行误导性重命名',
    'T41': 'Case分支重排：重新排列case语句的分支顺序',
    'T45': '假性组合逻辑环：插入永假的矛盾项（如 a & ~a）',
    'T47': '数据流破碎：使用Shannon展开拆分比较器或加法器',
    'T48': '逆向拓扑重排：反转assign语句的顺序',
}

# 系统提示词
SYSTEM_PROMPT = """You are an expert Verilog code obfuscation assistant. Your task is to transform Verilog RTL code using adversarial obfuscation techniques while maintaining functional equivalence.

IMPORTANT:
- The transformed code MUST be functionally equivalent to the original code.
- Apply the specified obfuscation technique accurately.
- Maintain valid Verilog syntax.
- The obfuscated code should be harder for humans or LLMs to understand, but should pass the same testbench.
- Only output the obfuscated Verilog code, without any explanation."""

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

def collect_obfuscation_samples(eval_base: Path, results_base: Path, dataset: Dict) -> List[Dict[str, Any]]:
    """收集所有攻击成功的样本"""
    
    obf_samples = []
    
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
                        continue
                    
                    obf_samples.append({
                        'rule_id': rule_id,
                        'task_id': task_id,
                        'original_code': task.get('canonical_solution', ''),
                        'adversarial_code': adversarial_code,
                        'prompt': task.get('prompt', ''),
                        'adversarial_confidence': eval_data.get('adversarial_confidence'),
                    })
            
            except Exception as e:
                continue
    
    return obf_samples

def build_obfuscation_sft_dataset(samples: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """构建代码混淆SFT格式的数据集"""
    
    sft_dataset = []
    
    for sample in samples:
        rule_id = sample['rule_id']
        rule_desc = RULE_DESCRIPTIONS.get(rule_id, rule_id)
        
        # 构建用户输入（原始代码 + 混淆规则）
        user_input = (
            f"Original Verilog Code:\n"
            f"```verilog\n{sample['original_code']}\n```\n\n"
            f"Obfuscation Technique: {rule_desc}\n\n"
            f"Task: Apply the specified obfuscation technique to the above code while maintaining functional equivalence."
        )
        
        # 输出（混淆后的代码）
        output = sample['adversarial_code']
        
        sft_dataset.append({
            # 标准SFT格式
            'instruction': SYSTEM_PROMPT,
            'input': user_input,
            'output': output,
            
            # 元数据
            'metadata': {
                'rule_id': rule_id,
                'task_id': sample['task_id'],
                'rule_description': rule_desc,
                'adversarial_confidence': sample['adversarial_confidence'],
                'source': 'obfuscation_training',
            },
            
            # 额外信息
            'original_code': sample['original_code'],
            'specification': sample['prompt'],
        })
    
    return sft_dataset

def main():
    print("="*100)
    print("构建代码混淆SFT数据集")
    print("="*100)
    print("\n训练目标：让大模型学会生成混淆后的Verilog代码")
    
    # 路径配置
    dataset_path = Path('data/qualified_dataset.json')
    eval_base = Path('rule_eval/metrics_conf_v2_on_fullall_adv')
    results_base = Path('results/qualified_by_rule')
    output_path = Path('data/obfuscation_sft.json')
    
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
    obf_samples = collect_obfuscation_samples(eval_base, results_base, dataset)
    print(f"✓ 收集到 {len(obf_samples)} 个混淆样本")
    
    # 按规则统计
    rule_counts = defaultdict(int)
    for sample in obf_samples:
        rule_counts[sample['rule_id']] += 1
    
    print("\n各规则的混淆样本数:")
    print("-"*60)
    for rule_id in sorted(rule_counts.keys()):
        count = rule_counts[rule_id]
        desc = RULE_DESCRIPTIONS.get(rule_id, '')
        print(f"  {rule_id}: {count:,} 样本 - {desc}")
    
    # 构建SFT数据集
    print("\n构建SFT格式数据集...")
    sft_dataset = build_obfuscation_sft_dataset(obf_samples)
    print(f"✓ 构建了 {len(sft_dataset)} 条SFT数据")
    
    # 保存数据集
    print(f"\n保存到 {output_path}...")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(sft_dataset, f, indent=2, ensure_ascii=False)
    print(f"✓ 保存完成")
    
    # 数据集统计
    print("\n" + "="*100)
    print("混淆SFT数据集统计")
    print("="*100)
    
    print(f"\n总样本数: {len(sft_dataset):,}")
    print(f"涵盖规则数: {len(rule_counts)}")
    print(f"涵盖任务数: {len(set(s['task_id'] for s in obf_samples))}")
    
    # 代码长度统计
    orig_lengths = [len(s['original_code']) for s in sft_dataset]
    obf_lengths = [len(s['output']) for s in sft_dataset]
    
    print(f"\n代码长度统计:")
    print(f"  原始代码平均长度: {sum(orig_lengths) / len(orig_lengths):.0f} 字符")
    print(f"  混淆代码平均长度: {sum(obf_lengths) / len(obf_lengths):.0f} 字符")
    print(f"  平均膨胀率: {sum(obf_lengths) / sum(orig_lengths):.2%}")
    
    # 显示示例
    print("\n" + "="*100)
    print("数据样本示例（前3条）")
    print("="*100)
    
    for i, sample in enumerate(sft_dataset[:3], 1):
        print(f"\n样本 {i}:")
        print(f"规则: {sample['metadata']['rule_id']} - {sample['metadata']['rule_description']}")
        print(f"任务: {sample['metadata']['task_id']}")
        print(f"原始代码长度: {len(sample['original_code'])} 字符")
        print(f"混淆代码长度: {len(sample['output'])} 字符")
        print(f"混淆置信度: {sample['metadata']['adversarial_confidence']:.4f}")
    
    # 按规则拆分保存
    print("\n按规则拆分保存...")
    rule_split_dir = Path('data/obfuscation_sft_by_rule')
    rule_split_dir.mkdir(parents=True, exist_ok=True)
    
    rule_datasets = defaultdict(list)
    for item in sft_dataset:
        rule_id = item['metadata']['rule_id']
        rule_datasets[rule_id].append(item)
    
    for rule_id, items in rule_datasets.items():
        rule_file = rule_split_dir / f'obfuscation_{rule_id}.json'
        with open(rule_file, 'w', encoding='utf-8') as f:
            json.dump(items, f, indent=2, ensure_ascii=False)
        print(f"  {rule_id}: {len(items):,} 样本 -> {rule_file}")
    
    # 也保存一个轻量版本（不含specification）
    print("\n保存轻量版本...")
    lightweight_dataset = []
    for item in sft_dataset:
        lightweight_dataset.append({
            'instruction': item['instruction'],
            'input': item['input'],
            'output': item['output'],
            'metadata': item['metadata'],
        })
    
    lightweight_path = Path('data/obfuscation_sft_lite.json')
    with open(lightweight_path, 'w', encoding='utf-8') as f:
        json.dump(lightweight_dataset, f, indent=2, ensure_ascii=False)
    print(f"✓ 轻量版本保存到: {lightweight_path}")
    
    print("\n✓ 所有数据集构建完成！")
    print("\n文件列表:")
    print(f"  1. 完整版: {output_path}")
    print(f"  2. 轻量版: {lightweight_path}")
    print(f"  3. 按规则拆分: {rule_split_dir}/")
    
    # 计算文件大小
    import os
    file_size = os.path.getsize(output_path) / (1024 * 1024)
    print(f"\n文件大小: {file_size:.2f} MB")

if __name__ == '__main__':
    main()
