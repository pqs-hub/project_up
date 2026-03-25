#!/usr/bin/env python3
"""
分析强强组合 vs 强弱组合实验结果
"""

import json
import argparse
from pathlib import Path
from typing import List, Dict
import sys

try:
    import matplotlib.pyplot as plt
    import matplotlib
    matplotlib.use('Agg')
    HAS_MATPLOTLIB = True
except ImportError:
    HAS_MATPLOTLIB = False


class StrongWeakAnalyzer:
    """强弱组合分析器"""
    
    def __init__(self, results_file: str):
        self.results_file = Path(results_file)
        self.results = self._load_results()
    
    def _load_results(self) -> List[Dict]:
        """加载结果"""
        results = []
        with open(self.results_file, 'r', encoding='utf-8') as f:
            for line in f:
                if line.strip():
                    results.append(json.loads(line))
        return results
    
    def generate_comparison_table(self, output_file: str):
        """生成对比表格"""
        
        # 按类型分组
        by_type = {}
        for r in self.results:
            ctype = r['combination_type']
            if ctype not in by_type:
                by_type[ctype] = []
            by_type[ctype].append(r)
        
        # 生成Markdown表格
        md = []
        md.append("# 强强组合 vs 强弱组合实验结果\n")
        md.append("## 核心发现\n")
        
        # 计算关键指标
        strong_strong = by_type.get('strong_strong', [])
        strong_weak = by_type.get('strong_weak', [])
        
        if strong_strong and strong_weak:
            ss_asr = sum(r['combined_asr'] for r in strong_strong) / len(strong_strong)
            sw_asr = sum(r['combined_asr'] for r in strong_weak) / len(strong_weak)
            
            ss_synergy = sum(1 for r in strong_strong if r['is_synergistic']) / len(strong_strong)
            sw_synergy = sum(1 for r in strong_weak if r['is_synergistic']) / len(strong_weak)
            
            if sw_asr > ss_asr:
                md.append(f"**🎯 关键发现：强弱组合优于强强组合！**\n")
                md.append(f"- 强弱组合平均ASR: **{sw_asr:.1%}**")
                md.append(f"- 强强组合平均ASR: {ss_asr:.1%}")
                md.append(f"- 提升幅度: **+{(sw_asr - ss_asr):.1%}**\n")
            else:
                md.append(f"**强强组合效果更好（符合预期）**\n")
                md.append(f"- 强强组合平均ASR: **{ss_asr:.1%}**")
                md.append(f"- 强弱组合平均ASR: {sw_asr:.1%}")
                md.append(f"- 差距: {(ss_asr - sw_asr):.1%}\n")
        
        md.append("## 详细对比\n")
        md.append("| 组合类型 | 测试数 | 平均规则强度 | 平均ASR | 平均提升 | 协同率 |")
        md.append("|---------|--------|------------|---------|---------|--------|")
        
        # 按平均ASR排序
        sorted_types = sorted(
            by_type.items(),
            key=lambda x: sum(r['combined_asr'] for r in x[1]) / len(x[1]),
            reverse=True
        )
        
        for ctype, results in sorted_types:
            n = len(results)
            avg_strength = sum((r['rule1_strength'] + r['rule2_strength'])/2 for r in results) / n
            avg_asr = sum(r['combined_asr'] for r in results) / n
            avg_boost = sum(r['asr_boost'] for r in results) / n
            synergy_rate = sum(1 for r in results if r['is_synergistic']) / n
            
            md.append(
                f"| {ctype} | {n} | {avg_strength:.3f} | "
                f"{avg_asr:.1%} | {avg_boost:+.1%} | {synergy_rate:.1%} |"
            )
        
        md.append("\n## 最佳组合 Top 10\n")
        md.append("| 排名 | 规则1 | 规则2 | 类型 | ASR | 提升 |")
        md.append("|------|-------|-------|------|-----|------|")
        
        # 找出ASR最高的10个组合
        top_combinations = sorted(
            self.results,
            key=lambda x: x['combined_asr'],
            reverse=True
        )[:10]
        
        for i, r in enumerate(top_combinations, 1):
            md.append(
                f"| {i} | {r['rule1']} | {r['rule2']} | {r['combination_type']} | "
                f"{r['combined_asr']:.1%} | {r['asr_boost']:+.1%} |"
            )
        
        md.append("\n## 最强协同效应 Top 10\n")
        md.append("| 排名 | 规则1 | 规则2 | 类型 | ASR提升 | 置信度提升 |")
        md.append("|------|-------|-------|------|---------|-----------|")
        
        # 找出协同效应最强的10个
        top_synergy = sorted(
            self.results,
            key=lambda x: x['asr_boost'],
            reverse=True
        )[:10]
        
        for i, r in enumerate(top_synergy, 1):
            md.append(
                f"| {i} | {r['rule1']} | {r['rule2']} | {r['combination_type']} | "
                f"{r['asr_boost']:+.1%} | {r['conf_boost']:+.4f} |"
            )
        
        # 保存
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text('\n'.join(md), encoding='utf-8')
        
        print(f"对比表格已保存到: {output_file}")
        
        # 打印到控制台
        print("\n" + "="*60)
        print('\n'.join(md[:20]))  # 打印前20行
        print("="*60)
    
    def plot_comparison(self, output_file: str):
        """绘制对比图"""
        if not HAS_MATPLOTLIB:
            print("跳过图表生成（matplotlib未安装）")
            return
        
        # 按类型分组
        by_type = {}
        for r in self.results:
            ctype = r['combination_type']
            if ctype not in by_type:
                by_type[ctype] = []
            by_type[ctype].append(r)
        
        # 计算每种类型的平均ASR
        types = []
        asrs = []
        synergy_rates = []
        
        for ctype, results in sorted(by_type.items()):
            types.append(ctype.replace('_', '\n'))
            asrs.append(sum(r['combined_asr'] for r in results) / len(results))
            synergy_rates.append(sum(1 for r in results if r['is_synergistic']) / len(results))
        
        # 创建图表
        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(14, 6))
        
        # ASR对比
        bars1 = ax1.bar(range(len(types)), asrs, color='#3498db', alpha=0.8)
        ax1.set_xlabel('Combination Type', fontsize=12, fontweight='bold')
        ax1.set_ylabel('Average ASR', fontsize=12, fontweight='bold')
        ax1.set_title('ASR by Combination Type', fontsize=14, fontweight='bold')
        ax1.set_xticks(range(len(types)))
        ax1.set_xticklabels(types, rotation=45, ha='right', fontsize=9)
        ax1.grid(axis='y', alpha=0.3)
        
        # 添加数值标签
        for bar in bars1:
            height = bar.get_height()
            ax1.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1%}',
                    ha='center', va='bottom', fontsize=9)
        
        # 协同率对比
        bars2 = ax2.bar(range(len(types)), synergy_rates, color='#e74c3c', alpha=0.8)
        ax2.set_xlabel('Combination Type', fontsize=12, fontweight='bold')
        ax2.set_ylabel('Synergy Rate', fontsize=12, fontweight='bold')
        ax2.set_title('Synergy Rate by Combination Type', fontsize=14, fontweight='bold')
        ax2.set_xticks(range(len(types)))
        ax2.set_xticklabels(types, rotation=45, ha='right', fontsize=9)
        ax2.grid(axis='y', alpha=0.3)
        
        # 添加数值标签
        for bar in bars2:
            height = bar.get_height()
            ax2.text(bar.get_x() + bar.get_width()/2., height,
                    f'{height:.1%}',
                    ha='center', va='bottom', fontsize=9)
        
        plt.tight_layout()
        
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"对比图已保存到: {output_file}")
    
    def generate_insights(self, output_file: str):
        """生成洞察报告"""
        
        # 按类型分组
        by_type = {}
        for r in self.results:
            ctype = r['combination_type']
            if ctype not in by_type:
                by_type[ctype] = []
            by_type[ctype].append(r)
        
        insights = {
            "key_findings": [],
            "recommendations": []
        }
        
        # 对比强强 vs 强弱
        if 'strong_strong' in by_type and 'strong_weak' in by_type:
            ss = by_type['strong_strong']
            sw = by_type['strong_weak']
            
            ss_asr = sum(r['combined_asr'] for r in ss) / len(ss)
            sw_asr = sum(r['combined_asr'] for r in sw) / len(sw)
            
            if sw_asr > ss_asr:
                insights["key_findings"].append({
                    "finding": "强弱组合优于强强组合",
                    "evidence": f"强弱ASR={sw_asr:.1%} > 强强ASR={ss_asr:.1%}",
                    "explanation": "可能存在互补效应：弱规则在某些维度上补充了强规则的不足"
                })
                insights["recommendations"].append(
                    "在MCTS搜索时，不应只关注强规则，应探索强弱组合的互补性"
                )
            else:
                insights["key_findings"].append({
                    "finding": "强强组合效果最好（符合预期）",
                    "evidence": f"强强ASR={ss_asr:.1%} > 强弱ASR={sw_asr:.1%}",
                    "explanation": "强规则的高ASR具有累加效应"
                })
                insights["recommendations"].append(
                    "MCTS搜索应优先探索强规则组合"
                )
        
        # 找出最佳组合类型
        best_type = max(by_type.items(), key=lambda x: sum(r['combined_asr'] for r in x[1]) / len(x[1]))
        best_asr = sum(r['combined_asr'] for r in best_type[1]) / len(best_type[1])
        
        insights["key_findings"].append({
            "finding": f"最佳组合类型: {best_type[0]}",
            "evidence": f"平均ASR={best_asr:.1%}",
            "explanation": "该类型组合在测试样本上表现最优"
        })
        
        # 协同效应分析
        synergistic = [r for r in self.results if r['is_synergistic']]
        if synergistic:
            synergy_rate = len(synergistic) / len(self.results)
            insights["key_findings"].append({
                "finding": f"协同效应普遍存在",
                "evidence": f"协同率={synergy_rate:.1%} ({len(synergistic)}/{len(self.results)})",
                "explanation": "大部分组合都展现出非线性增益"
            })
        
        # 保存
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(insights, f, indent=2, ensure_ascii=False)
        
        print(f"洞察报告已保存到: {output_file}")
        
        # 打印关键发现
        print("\n" + "="*60)
        print("关键发现")
        print("="*60)
        for finding in insights["key_findings"]:
            print(f"\n{finding['finding']}")
            print(f"  证据: {finding['evidence']}")
            print(f"  解释: {finding['explanation']}")
        
        print("\n" + "="*60)
        print("建议")
        print("="*60)
        for i, rec in enumerate(insights["recommendations"], 1):
            print(f"{i}. {rec}")


def main():
    parser = argparse.ArgumentParser(description='分析强弱组合实验结果')
    parser.add_argument(
        'results_file',
        type=str,
        help='实验结果文件路径'
    )
    parser.add_argument(
        '--output-dir',
        type=str,
        default='results/strong_weak_experiment/analysis',
        help='输出目录'
    )
    parser.add_argument(
        '--all',
        action='store_true',
        help='生成所有分析输出'
    )
    
    args = parser.parse_args()
    
    if not Path(args.results_file).exists():
        print(f"错误: 结果文件不存在: {args.results_file}")
        sys.exit(1)
    
    analyzer = StrongWeakAnalyzer(args.results_file)
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 生成分析
    analyzer.generate_comparison_table(str(output_dir / 'comparison_table.md'))
    analyzer.plot_comparison(str(output_dir / 'comparison_plot.png'))
    analyzer.generate_insights(str(output_dir / 'insights.json'))


if __name__ == '__main__':
    main()
