#!/usr/bin/env python3
"""
分析协同效应实验结果
生成论文级别的表格和图表
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict
import sys

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')  # 非交互式后端
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False
    print("警告: matplotlib未安装，将跳过图表生成")


class SynergyAnalyzer:
    """协同效应分析器"""
    
    def __init__(self, results_file: str):
        self.results_file = Path(results_file)
        self.results = self._load_results()
    
    def _load_results(self) -> List[Dict]:
        """加载实验结果"""
        results = []
        with open(self.results_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        return results
    
    def generate_latex_table(self, output_file: str):
        """生成LaTeX格式的结果表格"""
        
        # 按场景分组
        scenario_stats = {}
        for result in self.results:
            scenario = result['scenario_name']
            if scenario not in scenario_stats:
                scenario_stats[scenario] = {
                    'tests': [],
                    'synergistic_count': 0
                }
            
            scenario_stats[scenario]['tests'].append(result)
            if result['synergy_metrics'].get('is_synergistic'):
                scenario_stats[scenario]['synergistic_count'] += 1
        
        # 生成LaTeX表格
        latex = []
        latex.append("\\begin{table}[htbp]")
        latex.append("\\centering")
        latex.append("\\caption{Synergistic Attack Effectiveness}")
        latex.append("\\label{tab:synergy}")
        latex.append("\\begin{tabular}{lccccc}")
        latex.append("\\hline")
        latex.append("Scenario & Tests & ASR$_{single}$ & ASR$_{combined}$ & $\\Delta$ASR & Synergy \\\\")
        latex.append("\\hline")
        
        for scenario, stats in scenario_stats.items():
            tests = stats['tests']
            n = len(tests)
            
            # 计算平均值
            avg_single_asr = sum(t['synergy_metrics'].get('max_single_asr', 0) for t in tests) / n
            avg_combined_asr = sum(t['synergy_metrics'].get('combined_asr', 0) for t in tests) / n
            avg_boost = sum(t['synergy_metrics'].get('asr_boost', 0) for t in tests) / n
            synergy_rate = stats['synergistic_count'] / n
            
            # 格式化场景名称（去掉前缀，使用下划线分隔）
            scenario_short = scenario.replace('_', ' ').title()
            
            synergy_mark = '\\checkmark' if synergy_rate > 0.5 else '\\times'
            latex.append(
                f"{scenario_short} & {n} & "
                f"{avg_single_asr:.1%} & {avg_combined_asr:.1%} & "
                f"{avg_boost:+.1%} & {synergy_mark} \\\\"
            )
        
        latex.append("\\hline")
        latex.append("\\end{tabular}")
        latex.append("\\end{table}")
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('\n'.join(latex), encoding='utf-8')
        
        print(f"LaTeX表格已保存到: {output_file}")
        
        # 同时打印到控制台
        print("\n" + "="*80)
        print("实验结果表格（LaTeX格式）")
        print("="*80)
        print('\n'.join(latex))
        print("="*80)
    
    def generate_markdown_table(self, output_file: str):
        """生成Markdown格式的结果表格"""
        
        # 按场景分组
        scenario_stats = {}
        for result in self.results:
            scenario = result['scenario_name']
            module = result['module_id']
            
            if scenario not in scenario_stats:
                scenario_stats[scenario] = []
            
            scenario_stats[scenario].append({
                'module': module,
                'single_asr': result['synergy_metrics'].get('max_single_asr', 0),
                'combined_asr': result['synergy_metrics'].get('combined_asr', 0),
                'asr_boost': result['synergy_metrics'].get('asr_boost', 0),
                'conf_boost': result['synergy_metrics'].get('confidence_boost', 0),
                'is_synergistic': result['synergy_metrics'].get('is_synergistic', False)
            })
        
        # 生成Markdown
        md = []
        md.append("# 规则组合协同效应实验结果\n")
        
        for scenario, tests in scenario_stats.items():
            md.append(f"## {scenario}\n")
            md.append("| 模块 | ASR (单规则) | ASR (组合) | ASR提升 | 置信度提升 | 协同效应 |")
            md.append("|------|-------------|-----------|---------|-----------|---------|")
            
            for t in tests:
                synergy_mark = "✓" if t['is_synergistic'] else "✗"
                md.append(
                    f"| {t['module']} | {t['single_asr']:.1%} | {t['combined_asr']:.1%} | "
                    f"{t['asr_boost']:+.1%} | {t['conf_boost']:+.4f} | {synergy_mark} |"
                )
            
            # 统计
            n = len(tests)
            avg_single = sum(t['single_asr'] for t in tests) / n
            avg_combined = sum(t['combined_asr'] for t in tests) / n
            avg_boost = sum(t['asr_boost'] for t in tests) / n
            synergy_count = sum(1 for t in tests if t['is_synergistic'])
            
            md.append(f"| **平均** | **{avg_single:.1%}** | **{avg_combined:.1%}** | "
                     f"**{avg_boost:+.1%}** | - | **{synergy_count}/{n}** |")
            md.append("")
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('\n'.join(md), encoding='utf-8')
        
        print(f"Markdown表格已保存到: {output_file}")
    
    def plot_synergy_comparison(self, output_file: str):
        """绘制协同效应对比图"""
        if not HAS_MATPLOTLIB:
            print("跳过图表生成（matplotlib未安装）")
            return
        
        # 按场景分组数据
        scenario_data = {}
        for result in self.results:
            scenario = result['scenario_name']
            if scenario not in scenario_data:
                scenario_data[scenario] = {
                    'single_asr': [],
                    'combined_asr': []
                }
            
            scenario_data[scenario]['single_asr'].append(
                result['synergy_metrics'].get('max_single_asr', 0)
            )
            scenario_data[scenario]['combined_asr'].append(
                result['synergy_metrics'].get('combined_asr', 0)
            )
        
        # 计算平均值
        scenarios = list(scenario_data.keys())
        single_means = [sum(scenario_data[s]['single_asr']) / len(scenario_data[s]['single_asr']) 
                       for s in scenarios]
        combined_means = [sum(scenario_data[s]['combined_asr']) / len(scenario_data[s]['combined_asr']) 
                         for s in scenarios]
        
        # 绘图
        fig, ax = plt.subplots(figsize=(12, 6))
        
        x = range(len(scenarios))
        width = 0.35
        
        bars1 = ax.bar([i - width/2 for i in x], single_means, width, 
                      label='Single Rule (Max)', color='#3498db', alpha=0.8)
        bars2 = ax.bar([i + width/2 for i in x], combined_means, width,
                      label='Combined Rules', color='#e74c3c', alpha=0.8)
        
        # 添加数值标签
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.1%}',
                       ha='center', va='bottom', fontsize=9)
        
        # 格式化
        ax.set_xlabel('Attack Scenario', fontsize=12, fontweight='bold')
        ax.set_ylabel('Attack Success Rate (ASR)', fontsize=12, fontweight='bold')
        ax.set_title('Synergistic Effect: Single vs Combined Rules', 
                    fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels([s.replace('_', '\n') for s in scenarios], 
                          rotation=0, ha='center', fontsize=9)
        ax.legend(fontsize=11)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        ax.set_ylim(0, max(max(single_means), max(combined_means)) * 1.2)
        
        plt.tight_layout()
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"对比图已保存到: {output_file}")
    
    def plot_confidence_drop(self, output_file: str):
        """绘制置信度下降对比图"""
        if not HAS_MATPLOTLIB:
            return
        
        # 收集数据
        scenario_data = {}
        for result in self.results:
            scenario = result['scenario_name']
            if scenario not in scenario_data:
                scenario_data[scenario] = {
                    'single_drop': [],
                    'combined_drop': []
                }
            
            scenario_data[scenario]['single_drop'].append(
                result['synergy_metrics'].get('max_single_conf_drop', 0)
            )
            scenario_data[scenario]['combined_drop'].append(
                result['synergy_metrics'].get('combined_conf_drop', 0)
            )
        
        # 计算平均值
        scenarios = list(scenario_data.keys())
        single_means = [sum(scenario_data[s]['single_drop']) / len(scenario_data[s]['single_drop']) 
                       for s in scenarios]
        combined_means = [sum(scenario_data[s]['combined_drop']) / len(scenario_data[s]['combined_drop']) 
                         for s in scenarios]
        
        # 绘图
        fig, ax = plt.subplots(figsize=(12, 6))
        
        x = range(len(scenarios))
        width = 0.35
        
        bars1 = ax.bar([i - width/2 for i in x], single_means, width,
                      label='Single Rule (Max)', color='#2ecc71', alpha=0.8)
        bars2 = ax.bar([i + width/2 for i in x], combined_means, width,
                      label='Combined Rules', color='#f39c12', alpha=0.8)
        
        # 添加数值标签
        for bars in [bars1, bars2]:
            for bar in bars:
                height = bar.get_height()
                ax.text(bar.get_x() + bar.get_width()/2., height,
                       f'{height:.3f}',
                       ha='center', va='bottom', fontsize=9)
        
        ax.set_xlabel('Attack Scenario', fontsize=12, fontweight='bold')
        ax.set_ylabel('Confidence Drop', fontsize=12, fontweight='bold')
        ax.set_title('Model Confidence Degradation: Single vs Combined Rules',
                    fontsize=14, fontweight='bold')
        ax.set_xticks(x)
        ax.set_xticklabels([s.replace('_', '\n') for s in scenarios],
                          rotation=0, ha='center', fontsize=9)
        ax.legend(fontsize=11)
        ax.grid(axis='y', alpha=0.3, linestyle='--')
        
        plt.tight_layout()
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"置信度下降图已保存到: {output_file}")
    
    def generate_statistical_summary(self, output_file: str):
        """生成统计摘要"""
        
        total_tests = len(self.results)
        synergistic_tests = sum(1 for r in self.results 
                               if r['synergy_metrics'].get('is_synergistic'))
        
        # 计算全局统计
        all_single_asr = [r['synergy_metrics'].get('max_single_asr', 0) 
                         for r in self.results]
        all_combined_asr = [r['synergy_metrics'].get('combined_asr', 0) 
                           for r in self.results]
        all_asr_boost = [r['synergy_metrics'].get('asr_boost', 0) 
                        for r in self.results]
        all_conf_boost = [r['synergy_metrics'].get('confidence_boost', 0) 
                         for r in self.results]
        
        summary = {
            'total_tests': total_tests,
            'synergistic_tests': synergistic_tests,
            'synergy_rate': synergistic_tests / total_tests if total_tests > 0 else 0,
            'avg_single_asr': sum(all_single_asr) / len(all_single_asr) if all_single_asr else 0,
            'avg_combined_asr': sum(all_combined_asr) / len(all_combined_asr) if all_combined_asr else 0,
            'avg_asr_boost': sum(all_asr_boost) / len(all_asr_boost) if all_asr_boost else 0,
            'avg_conf_boost': sum(all_conf_boost) / len(all_conf_boost) if all_conf_boost else 0,
            'max_asr_boost': max(all_asr_boost) if all_asr_boost else 0,
            'max_conf_boost': max(all_conf_boost) if all_conf_boost else 0,
        }
        
        # 保存JSON
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(summary, f, indent=2, ensure_ascii=False)
        
        # 打印摘要
        print("\n" + "="*80)
        print("统计摘要")
        print("="*80)
        print(f"总测试数: {summary['total_tests']}")
        print(f"协同案例数: {summary['synergistic_tests']}")
        print(f"协同率: {summary['synergy_rate']:.1%}")
        print(f"\n平均单规则ASR: {summary['avg_single_asr']:.1%}")
        print(f"平均组合ASR: {summary['avg_combined_asr']:.1%}")
        print(f"平均ASR提升: {summary['avg_asr_boost']:+.1%}")
        print(f"\n平均置信度提升: {summary['avg_conf_boost']:+.4f}")
        print(f"最大ASR提升: {summary['max_asr_boost']:+.1%}")
        print(f"最大置信度提升: {summary['max_conf_boost']:+.4f}")
        print("="*80)
        
        print(f"\n统计摘要已保存到: {output_file}")


def main():
    parser = argparse.ArgumentParser(description='分析协同效应实验结果')
    parser.add_argument(
        'results_file',
        type=str,
        help='实验结果文件路径 (JSONL格式)'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='results/synergy_experiments/analysis',
        help='输出目录'
    )
    parser.add_argument(
        '--latex',
        action='store_true',
        help='生成LaTeX表格'
    )
    parser.add_argument(
        '--markdown',
        action='store_true',
        help='生成Markdown表格'
    )
    parser.add_argument(
        '--plots',
        action='store_true',
        help='生成图表'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='生成所有输出'
    )
    
    args = parser.parse_args()
    
    # 检查结果文件
    if not Path(args.results_file).exists():
        print(f"错误: 结果文件不存在: {args.results_file}")
        sys.exit(1)
    
    # 创建分析器
    analyzer = SynergyAnalyzer(args.results_file)
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成输出
    if args.all or args.latex:
        analyzer.generate_latex_table(str(output_dir / 'results_table.tex'))
    
    if args.all or args.markdown:
        analyzer.generate_markdown_table(str(output_dir / 'results_table.md'))
    
    if args.all or args.plots:
        analyzer.plot_synergy_comparison(str(output_dir / 'synergy_comparison.png'))
        analyzer.plot_confidence_drop(str(output_dir / 'confidence_drop.png'))
    
    # 总是生成统计摘要
    analyzer.generate_statistical_summary(str(output_dir / 'statistical_summary.json'))


if __name__ == '__main__':
    main()
