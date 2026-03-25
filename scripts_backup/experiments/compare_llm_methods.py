#!/usr/bin/env python3
"""
对比历史感知 vs 独立LLM参数生成
"""

import json
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path


def load_jsonl(path):
    """加载JSONL文件"""
    results = []
    with open(path, 'r') as f:
        for line in f:
            results.append(json.loads(line))
    return results


def compare_methods(linked_results, independent_results, output_dir):
    """对比两种方法"""
    
    # 按场景匹配
    # linked: Semantic_Linkage_Comment_Rename
    # independent: Comment_Rename_Independent
    
    linked_comment_rename = [r for r in linked_results if r['scenario'] == 'Semantic_Linkage_Comment_Rename']
    independent_comment_rename = [r for r in independent_results if r['combination'] == 'Comment_Rename_Independent']
    
    # 统计
    stats = {
        "linked": {
            "n": len(linked_comment_rename),
            "avg_asr": np.mean([r['linked_asr'] for r in linked_comment_rename]) * 100,
            "avg_boost": np.mean([r['linkage_boost'] for r in linked_comment_rename]) * 100,
            "synergy_rate": np.mean([r.get('is_synergistic', False) for r in linked_comment_rename]) * 100,
            "llm_rate": np.mean([r['linkage_info'].get('llm_params_used', False) for r in linked_comment_rename]) * 100
        },
        "independent": {
            "n": len(independent_comment_rename),
            "avg_asr": np.mean([r['combined_asr'] for r in independent_comment_rename]) * 100,
            "avg_boost": np.mean([r['boost'] for r in independent_comment_rename]) * 100,
            "synergy_rate": np.mean([r['is_synergistic'] for r in independent_comment_rename]) * 100,
            "llm_rate": np.mean([r['llm_info'].get('llm_used', False) for r in independent_comment_rename]) * 100
        }
    }
    
    # 打印对比
    print("\n" + "="*60)
    print("历史感知 vs 独立LLM参数生成对比")
    print("="*60)
    print(f"\n场景: T20（注释）→ T34（重命名）\n")
    
    print(f"{'指标':<20} {'历史感知':>15} {'独立生成':>15} {'差异':>15}")
    print("-" * 70)
    print(f"{'样本数':<20} {stats['linked']['n']:>15} {stats['independent']['n']:>15} {'-':>15}")
    print(f"{'平均ASR (%)':<20} {stats['linked']['avg_asr']:>15.1f} {stats['independent']['avg_asr']:>15.1f} {stats['linked']['avg_asr']-stats['independent']['avg_asr']:>+15.1f}")
    print(f"{'平均增益 (%)':<20} {stats['linked']['avg_boost']:>15.1f} {stats['independent']['avg_boost']:>15.1f} {stats['linked']['avg_boost']-stats['independent']['avg_boost']:>+15.1f}")
    print(f"{'协同率 (%)':<20} {stats['linked']['synergy_rate']:>15.1f} {stats['independent']['synergy_rate']:>15.1f} {stats['linked']['synergy_rate']-stats['independent']['synergy_rate']:>+15.1f}")
    print(f"{'LLM使用率 (%)':<20} {stats['linked']['llm_rate']:>15.1f} {stats['independent']['llm_rate']:>15.1f} {stats['linked']['llm_rate']-stats['independent']['llm_rate']:>+15.1f}")
    print()
    
    # 绘制对比图
    plot_comparison(stats, output_dir)
    
    # 详细案例对比（统计所有案例的胜出次数）
    win_stats = compare_cases(linked_comment_rename, independent_comment_rename, output_dir)
    
    # 添加胜出统计到结果中
    stats['win_stats'] = win_stats
    
    return stats


def plot_comparison(stats, output_dir):
    """绘制对比图"""
    
    fig, axes = plt.subplots(2, 2, figsize=(12, 10))
    
    metrics = ['avg_asr', 'avg_boost', 'synergy_rate', 'llm_rate']
    titles = ['Average ASR (%)', 'Average Boost (%)', 'Synergy Rate (%)', 'LLM Usage Rate (%)']
    
    for idx, (metric, title) in enumerate(zip(metrics, titles)):
        ax = axes[idx // 2, idx % 2]
        
        linked_val = stats['linked'][metric]
        independent_val = stats['independent'][metric]
        
        x = ['History-Aware\nLLM', 'Independent\nLLM']
        y = [linked_val, independent_val]
        colors = ['#4ecdc4', '#ff6b6b']
        
        bars = ax.bar(x, y, color=colors, alpha=0.8)
        
        ax.set_ylabel(title.split('(')[0].strip(), fontsize=11)
        ax.set_title(title, fontsize=12, fontweight='bold')
        ax.grid(axis='y', alpha=0.3)
        
        # 添加数值标签
        for bar, val in zip(bars, y):
            height = bar.get_height()
            ax.text(bar.get_x() + bar.get_width()/2., height,
                    f'{val:.1f}%',
                    ha='center', va='bottom', fontsize=10, fontweight='bold')
        
        # 添加差异标注
        diff = linked_val - independent_val
        mid_x = 0.5
        mid_y = max(y) * 0.5
        ax.annotate(f'Δ = {diff:+.1f}%',
                   xy=(mid_x, mid_y),
                   fontsize=11,
                   ha='center',
                   bbox=dict(boxstyle='round,pad=0.5', facecolor='yellow', alpha=0.3))
    
    plt.suptitle('T20→T34: History-Aware vs Independent LLM Parameter Generation',
                 fontsize=14, fontweight='bold', y=0.995)
    plt.tight_layout()
    plt.savefig(f'{output_dir}/llm_method_comparison.png', dpi=300, bbox_inches='tight')
    print(f"已保存对比图: {output_dir}/llm_method_comparison.png")
    plt.close()


def compare_cases(linked_results, independent_results, output_dir):
    """对比具体案例"""
    
    # 找到相同的sample_id
    linked_ids = {r['sample_id']: r for r in linked_results}
    independent_ids = {r['sample_id']: r for r in independent_results}
    
    common_ids = set(linked_ids.keys()) & set(independent_ids.keys())
    
    print(f"\n共同样本数: {len(common_ids)}")
    
    # 找出差异最大的案例
    diffs = []
    linked_wins = 0
    independent_wins = 0
    ties = 0
    
    for sid in common_ids:
        linked = linked_ids[sid]
        independent = independent_ids[sid]
        
        linked_asr = linked['linked_asr']
        independent_asr = independent['combined_asr']
        diff = linked_asr - independent_asr
        
        # 统计胜出次数
        if linked_asr > independent_asr:
            linked_wins += 1
        elif independent_asr > linked_asr:
            independent_wins += 1
        else:
            ties += 1
        
        diffs.append({
            'sample_id': sid,
            'linked_asr': linked_asr,
            'independent_asr': independent_asr,
            'diff': diff,
            'linked_params': linked['linkage_info']['details'],
            'independent_params': independent['llm_info']['details']
        })
    
    # 排序
    diffs.sort(key=lambda x: abs(x['diff']), reverse=True)
    
    # 保存详细对比（所有案例）
    with open(f'{output_dir}/case_comparison.json', 'w') as f:
        json.dump(diffs, f, indent=2, ensure_ascii=False)
    
    # 打印胜出统计
    print(f"\n胜出统计（基于所有{len(common_ids)}个共同样本）:")
    print(f"{'方法':<20} {'胜出次数':>10} {'胜率':>10}")
    print("-" * 45)
    print(f"{'历史感知LLM':<20} {linked_wins:>10} {linked_wins/len(common_ids)*100:>9.1f}%")
    print(f"{'独立LLM':<20} {independent_wins:>10} {independent_wins/len(common_ids)*100:>9.1f}%")
    print(f"{'平局':<20} {ties:>10} {ties/len(common_ids)*100:>9.1f}%")
    
    print(f"\n差异最大的5个案例:")
    print(f"{'Sample ID':<15} {'历史感知ASR':>15} {'独立ASR':>15} {'差异':>15}")
    print("-" * 65)
    for case in diffs[:5]:
        print(f"{case['sample_id']:<15} {case['linked_asr']*100:>14.1f}% {case['independent_asr']*100:>14.1f}% {case['diff']*100:>+14.1f}%")
    
    # 返回胜出统计
    win_stats = {
        'total': len(common_ids),
        'linked_wins': linked_wins,
        'independent_wins': independent_wins,
        'ties': ties,
        'linked_win_rate': linked_wins / len(common_ids) if len(common_ids) > 0 else 0,
        'independent_win_rate': independent_wins / len(common_ids) if len(common_ids) > 0 else 0
    }
    
    # 分析参数差异
    print(f"\n参数生成差异示例:")
    for i, case in enumerate(diffs[:3], 1):
        print(f"\n案例 {i}: {case['sample_id']}")
        print(f"  历史感知ASR: {case['linked_asr']*100:.1f}%")
        print(f"  独立生成ASR: {case['independent_asr']*100:.1f}%")
        print(f"  差异: {case['diff']*100:+.1f}%")
        
        if 'rule1_llm_params' in case['linked_params']:
            print(f"  历史感知-Rule1参数: {case['linked_params']['rule1_llm_params']}")
        if 'rule2_llm_params' in case['linked_params']:
            print(f"  历史感知-Rule2参数: {case['linked_params']['rule2_llm_params']}")
        
        if 'rule1_params' in case['independent_params']:
            print(f"  独立生成-Rule1参数: {case['independent_params']['rule1_params']}")
        if 'rule2_params' in case['independent_params']:
            print(f"  独立生成-Rule2参数: {case['independent_params']['rule2_params']}")
    
    return win_stats


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--linked', default='results/linked_llm_experiment/linked_results.jsonl')
    parser.add_argument('--independent', default='results/independent_llm_experiment/independent_results.jsonl')
    parser.add_argument('--output-dir', default='results/llm_comparison')
    args = parser.parse_args()
    
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 加载结果
    print("加载实验结果...")
    linked_results = load_jsonl(args.linked)
    independent_results = load_jsonl(args.independent)
    
    print(f"历史感知结果: {len(linked_results)} 条")
    print(f"独立生成结果: {len(independent_results)} 条")
    
    # 对比
    stats = compare_methods(linked_results, independent_results, args.output_dir)
    
    # 保存统计
    with open(f'{args.output_dir}/comparison_stats.json', 'w') as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    
    print(f"\n对比完成！结果保存在: {args.output_dir}")


if __name__ == '__main__':
    main()
