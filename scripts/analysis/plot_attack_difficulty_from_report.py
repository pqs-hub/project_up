#!/usr/bin/env python3
"""
根据 attack_difficulty_report_unflipped_vs_success.json 生成可视化图表。

输入：
  --report-json rule_eval/attack_difficulty_report_*.json

输出：
  --out-dir rule_eval/plots_attack_difficulty/
    - 01_bucket_medians_lengths.png
    - 02_bucket_comments.png
    - 03_bucket_structure_rates.png
    - 04_bucket_numbers.png（可选轻量）
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

import matplotlib.pyplot as plt
from matplotlib import font_manager


def _set_cjk_font() -> None:
    # 尝试选择一个包含中文的字体，避免 glyph missing 导致方块
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    preferred = [
        "SimHei",
        "Noto Sans CJK JP",
        "Noto Sans CJK",
        "Droid Sans Fallback",
    ]
    for name in preferred:
        if name in fonts:
            plt.rcParams["font.family"] = name
            return


def _get_bucket_order(report: Dict[str, Any]) -> List[str]:
    # 尽量保持脚本里固定桶的顺序；若缺失就回退排序
    wanted = ["0 (unflipped)", "1", "2", "3-5", "6+"]
    buckets = list(report.get("bucket_summaries", {}).keys())
    if all(w in buckets for w in wanted):
        return wanted
    return sorted(buckets)


def _y_from_feature(bucket_summary: Dict[str, Any], feature: str, stat: str) -> float:
    v = bucket_summary.get(feature, {})
    if isinstance(v, (int, float)):
        return float(v)
    if stat in v:
        return float(v[stat])
    # fallback
    if "median" in v:
        return float(v["median"])
    if "mean" in v:
        return float(v["mean"])
    return 0.0


def main() -> None:
    ap = argparse.ArgumentParser(description="Plot attack difficulty vs SPEC/RTL features")
    ap.add_argument("--report-json", required=True, help="输入 report json")
    ap.add_argument("--out-dir", required=True, help="输出目录（将创建）")
    args = ap.parse_args()

    report_path = Path(args.report_json)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    report = json.loads(report_path.read_text(encoding="utf-8"))
    buckets = _get_bucket_order(report)
    bs = report["bucket_summaries"]

    # 全局图风格
    _set_cjk_font()
    plt.rcParams.update({"figure.dpi": 140})

    # 1) lengths: prompt_chars & rtl_chars (median)
    xs = list(range(len(buckets)))
    prompt_med = [_y_from_feature(bs[b], "prompt_chars", "median") for b in buckets]
    rtl_med = [_y_from_feature(bs[b], "rtl_chars", "median") for b in buckets]

    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.plot(xs, prompt_med, marker="o", label="SPEC长度(prompt_chars) 中位数")
    ax1.plot(xs, rtl_med, marker="o", label="RTL长度(rtl_chars) 中位数")
    ax1.set_xticks(xs)
    ax1.set_xticklabels(buckets, rotation=0)
    ax1.set_xlabel("flip_rule_count 桶（= 被成功 flip 的规则数）")
    ax1.set_ylabel("长度（字符数）中位数")
    ax1.set_title("攻击成功难易度 vs SPEC/RTL 长度")
    ax1.grid(True, alpha=0.25)
    ax1.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "01_bucket_medians_lengths.png")
    plt.close(fig)

    # 2) comments: comment_chars_ratio (mean) & has_line_comment (mean)
    comment_mean = [_y_from_feature(bs[b], "comment_chars_ratio", "mean") for b in buckets]
    has_line_mean = [_y_from_feature(bs[b], "has_line_comment", "mean") for b in buckets]

    fig, ax1 = plt.subplots(figsize=(10, 4))
    ax1.plot(xs, comment_mean, marker="o", color="#d95f02", label="注释密度 comment_chars_ratio 均值")
    ax1.set_xticks(xs)
    ax1.set_xticklabels(buckets, rotation=0)
    ax1.set_xlabel("flip_rule_count 桶")
    ax1.set_ylabel("comment_chars_ratio 均值（注释字符/总字符）")
    ax1.set_title("攻击成功难易度 vs 注释密度")
    ax1.grid(True, alpha=0.25)
    ax1.legend(loc="upper left")

    ax2 = ax1.twinx()
    ax2.plot(xs, has_line_mean, marker="s", color="#1b9e77", label="是否含 // 注释 has_line_comment 均值（0/1均值）")
    ax2.set_ylabel("has_line_comment 均值（0-1）")
    fig.legend(loc="upper right")

    fig.tight_layout()
    fig.savefig(out_dir / "02_bucket_comments.png")
    plt.close(fig)

    # 3) structure rates: has_always / has_case / has_assign (mean)
    has_always_mean = [_y_from_feature(bs[b], "has_always", "mean") for b in buckets]
    has_case_mean = [_y_from_feature(bs[b], "has_case", "mean") for b in buckets]
    has_assign_mean = [_y_from_feature(bs[b], "has_assign", "mean") for b in buckets]

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.bar([x - 0.25 for x in xs], has_case_mean, width=0.25, label="has_case（case出现）均值")
    ax.bar([x + 0.0 for x in xs], has_always_mean, width=0.25, label="has_always（always出现）均值")
    ax.bar([x + 0.25 for x in xs], has_assign_mean, width=0.25, label="has_assign（assign出现）均值")
    ax.set_xticks(xs)
    ax.set_xticklabels(buckets, rotation=0)
    ax.set_xlabel("flip_rule_count 桶")
    ax.set_ylabel("结构特征出现率（0/1 均值，近似为比例）")
    ax.set_ylim(0, 1.05)
    ax.set_title("攻击成功难易度 vs RTL 结构特征")
    ax.grid(True, axis="y", alpha=0.25)
    ax.legend()
    fig.tight_layout()
    fig.savefig(out_dir / "03_bucket_structure_rates.png")
    plt.close(fig)

    # 4) numbers: n_numbers (median)
    n_numbers_med = [_y_from_feature(bs[b], "n_numbers", "median") for b in buckets]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(xs, n_numbers_med, marker="o")
    ax.set_xticks(xs)
    ax.set_xticklabels(buckets, rotation=0)
    ax.set_xlabel("flip_rule_count 桶")
    ax.set_ylabel("SPEC 数字数量 中位数")
    ax.set_title("攻击成功难易度 vs SPEC 里的数字量（粗特征）")
    ax.grid(True, alpha=0.25)
    fig.tight_layout()
    fig.savefig(out_dir / "04_bucket_numbers.png")
    plt.close(fig)

    print(f"已导出图表到：{out_dir}")
    for f in sorted(out_dir.glob("*.png")):
        print(f" - {f.name}")


if __name__ == "__main__":
    main()

