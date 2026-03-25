#!/usr/bin/env python3
"""
可视化联动LLM实验结果
"""

import json
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

def load_results(jsonl_path):
    """加载JSONL结果"""
    results = []
    with open(jsonl_path, 'r') as f:
        for line in f:
            results.append(json.loads(line))
    return results

def plot_asr_comparison(report_path, output_dir):
    """绘制ASR对比图"""
    with open(report_path, 'r') as f:
        report = json.load(f)
    
    scenarios = list(report['scenarios'].keys())
    asrs = [report['scenarios'][s]['avg_linked_asr'] * 100 for s in scenarios]
    boosts = [report['scenarios'][s]['avg_linkage_boost'] * 100 for s in scenarios]
    synergy_rates = [report['scenarios'][s]['synergy_rate'] * 100 for s in scenarios]
    llm_rates = [report['scenarios'][s].get('linkage_used_rate', 0) * 100 for s in scenarios]
    
    # 简化场景名
    scenario_labels = [
        'Rename→Bitwidth',
        'DeadCode→Shannon',
        'Comment→Rename',
        'Rename→Intermediate'
    ]
    
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    
    # 1. ASR对比
    ax = axes[0, 0]
    bars = ax.bar(scenario_labels, asrs, color=['#ff6b6b', '#4ecdc4', '#45b7d1', '#96ceb4'])
    ax.set_ylabel('Average ASR (%)', fontsize=12)
    ax.set_title('Attack Success Rate by Scenario', fontsize=14, fontweight='bold')
    ax.set_ylim(0, 100)
    ax.grid(axis='y', alpha=0.3)
    
    # 添加数值标签
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}%',
                ha='center', va='bottom', fontsize=10)
    
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=15, ha='right')
    
    # 2. 联动增益
    ax = axes[0, 1]
    colors = ['#ff6b6b' if b < 0 else '#4ecdc4' for b in boosts]
    bars = ax.bar(scenario_labels, boosts, color=colors)
    ax.set_ylabel('Linkage Boost (%)', fontsize=12)
    ax.set_title('Linkage Boost (vs Max Single Rule)', fontsize=14, fontweight='bold')
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.grid(axis='y', alpha=0.3)
    
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:+.1f}%',
                ha='center', va='bottom' if height > 0 else 'top', fontsize=10)
    
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=15, ha='right')
    
    # 3. 协同率
    ax = axes[1, 0]
    bars = ax.bar(scenario_labels, synergy_rates, color=['#feca57', '#ff9ff3', '#54a0ff', '#48dbfb'])
    ax.set_ylabel('Synergy Rate (%)', fontsize=12)
    ax.set_title('Synergy Rate (Boost > 0)', fontsize=14, fontweight='bold')
    ax.set_ylim(0, 100)
    ax.grid(axis='y', alpha=0.3)
    
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}%',
                ha='center', va='bottom', fontsize=10)
    
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=15, ha='right')
    
    # 4. LLM使用率
    ax = axes[1, 1]
    bars = ax.bar(scenario_labels, llm_rates, color=['#ee5a6f', '#c7ecee', '#dfe6e9', '#74b9ff'])
    ax.set_ylabel('LLM Usage Rate (%)', fontsize=12)
    ax.set_title('LLM Parameter Generation Usage', fontsize=14, fontweight='bold')
    ax.set_ylim(0, 110)
    ax.grid(axis='y', alpha=0.3)
    
    for bar in bars:
        height = bar.get_height()
        ax.text(bar.get_x() + bar.get_width()/2., height,
                f'{height:.1f}%',
                ha='center', va='bottom', fontsize=10)
    
    plt.setp(ax.xaxis.get_majorticklabels(), rotation=15, ha='right')
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/asr_comparison.png', dpi=300, bbox_inches='tight')
    print(f"已保存: {output_dir}/asr_comparison.png")
    plt.close()

def plot_llm_params_analysis(results_path, output_dir):
    """分析LLM生成的参数"""
    results = load_results(results_path)
    
    # 统计LLM生成的参数类型
    llm_params_count = {}
    rename_prefixes = []
    
    for r in results:
        if r.get('linkage_info', {}).get('llm_params_used'):
            details = r['linkage_info']['details']
            
            # 统计rule1参数
            if 'rule1_llm_params' in details:
                params = details['rule1_llm_params']
                if 'custom_map' in params:
                    for old, new in params['custom_map'].items():
                        # 提取前缀
                        if '_' in new:
                            prefix = new.split('_')[0]
                            rename_prefixes.append(prefix)
    
    # 统计前缀频率
    from collections import Counter
    prefix_counts = Counter(rename_prefixes)
    
    # 绘制前缀分布
    if prefix_counts:
        fig, ax = plt.subplots(figsize=(10, 6))
        
        prefixes = list(prefix_counts.keys())[:10]  # 前10个
        counts = [prefix_counts[p] for p in prefixes]
        
        bars = ax.barh(prefixes, counts, color='#4ecdc4')
        ax.set_xlabel('Frequency', fontsize=12)
        ax.set_ylabel('Rename Prefix', fontsize=12)
        ax.set_title('LLM-Generated Rename Prefixes Distribution', fontsize=14, fontweight='bold')
        ax.grid(axis='x', alpha=0.3)
        
        for i, (bar, count) in enumerate(zip(bars, counts)):
            ax.text(count, i, f' {count}', va='center', fontsize=10)
        
        plt.tight_layout()
        plt.savefig(f'{output_dir}/llm_params_distribution.png', dpi=300, bbox_inches='tight')
        print(f"已保存: {output_dir}/llm_params_distribution.png")
        plt.close()

def plot_scenario_details(results_path, output_dir):
    """绘制每个场景的详细分析"""
    results = load_results(results_path)
    
    # 按场景分组
    scenarios = {}
    for r in results:
        scenario = r['scenario']
        if scenario not in scenarios:
            scenarios[scenario] = []
        scenarios[scenario].append(r)
    
    # 为每个场景绘制ASR分布
    fig, axes = plt.subplots(2, 2, figsize=(14, 10))
    axes = axes.flatten()
    
    scenario_names = list(scenarios.keys())
    
    for idx, scenario in enumerate(scenario_names):
        ax = axes[idx]
        data = scenarios[scenario]
        
        # 提取ASR数据
        rule1_asrs = [d['rule1_asr'] * 100 for d in data]
        rule2_asrs = [d['rule2_asr'] * 100 for d in data]
        linked_asrs = [d['linked_asr'] * 100 for d in data]
        
        # 绘制箱线图
        box_data = [rule1_asrs, rule2_asrs, linked_asrs]
        bp = ax.boxplot(box_data, labels=['Rule1', 'Rule2', 'Linked'],
                        patch_artist=True)
        
        # 设置颜色
        colors = ['#ff6b6b', '#4ecdc4', '#45b7d1']
        for patch, color in zip(bp['boxes'], colors):
            patch.set_facecolor(color)
            patch.set_alpha(0.7)
        
        ax.set_ylabel('ASR (%)', fontsize=10)
        ax.set_title(scenario.replace('_', ' '), fontsize=11, fontweight='bold')
        ax.set_ylim(0, 105)
        ax.grid(axis='y', alpha=0.3)
    
    plt.tight_layout()
    plt.savefig(f'{output_dir}/scenario_details.png', dpi=300, bbox_inches='tight')
    print(f"已保存: {output_dir}/scenario_details.png")
    plt.close()

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--results', default='results/linked_llm_experiment/linked_results.jsonl')
    parser.add_argument('--report', default='results/linked_llm_experiment/linked_report.json')
    parser.add_argument('--output-dir', default='results/linked_llm_experiment')
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("生成可视化图表...")
    
    # 1. ASR对比图
    plot_asr_comparison(args.report, args.output_dir)
    
    # 2. LLM参数分析
    plot_llm_params_analysis(args.results, args.output_dir)
    
    # 3. 场景详细分析
    plot_scenario_details(args.results, args.output_dir)
    
    print("\n所有图表已生成！")

if __name__ == '__main__':
    main()
