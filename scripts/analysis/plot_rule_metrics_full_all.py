#!/usr/bin/env python3
"""
从各规则 T*_report.json 生成指标图。

示例：
  python scripts/analysis/plot_rule_metrics_full_all.py \\
    --metrics-dir rule_eval/metrics_conf_v2_on_fullall_adv \\
    --output-dir rule_eval/plots_metrics_conf_v2_fullall
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import font_manager


def _load_reports(metrics_dir: Path) -> list[dict]:
    reports: list[dict] = []
    for p in sorted(metrics_dir.glob("T*_report.json"), key=lambda x: x.name):
        try:
            j = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(j, dict) and j.get("rule_id"):
            reports.append(j)
    return reports


def _savefig(out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    plt.tight_layout()
    plt.savefig(out_path, dpi=160, bbox_inches="tight")
    plt.close()


def _load_transform_english_names() -> dict[str, str]:
    """
    从 `ast_transforms_loader` 读取每个规则的英文名（to_llm_schema()['name']）。
    这样可以避免中文 STRATEGY_DESC 太长，也符合你想要“英文名”的需求。
    """
    import sys

    project_root = Path(__file__).resolve().parents[2]
    if str(project_root) not in sys.path:
        sys.path.insert(0, str(project_root))

    # ast_transforms_loader 会动态加载 ast_transforms.2.py
    from ast_transforms_loader import create_engine  # type: ignore

    engine = create_engine()
    names: dict[str, str] = {}
    for tid in engine.registry.keys():
        info = engine.get_transform_info(tid) or {}
        n = info.get("name")
        if isinstance(n, str) and n.strip():
            names[tid] = n.strip()

    # T04 已移除并与 T20 合并（历史上 doc comment decoy 对应 T20）
    if "T04" not in names:
        if "T20" in names:
            names["T04"] = names["T20"]
        else:
            names["T04"] = "Flexible Misleading Comment"
    return names


def _short_label(s: str, max_len: int = 18) -> str:
    s = (s or "").strip()
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def _conf_shift_gain(r: dict) -> float:
    """置信度位移 gain_conf；旧报告仅有 gain（语义相同）。"""
    gc = r.get("gain_conf")
    if gc is not None:
        return float(gc)
    return float(r.get("gain") or 0.0)


def _gain_acc(r: dict) -> float:
    """准确率下降 acc_orig - acc_adv（小数）。"""
    return float(r.get("acc_orig") or 0.0) - float(r.get("acc_adv") or 0.0)


def _set_cjk_font() -> None:
    fonts = {f.name for f in font_manager.fontManager.ttflist}
    for name in ("SimHei", "Noto Sans CJK JP", "Noto Sans CJK", "Droid Sans Fallback"):
        if name in fonts:
            plt.rcParams["font.family"] = name
            return


def main() -> None:
    ap = argparse.ArgumentParser(description="绘制单规则评估指标图（T*_report.json）")
    ap.add_argument(
        "--metrics-dir",
        type=Path,
        default=Path("rule_eval/metrics_full_all_rules"),
        help="含 T*_report.json 的目录",
    )
    ap.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="图输出目录（默认：metrics-dir 的兄弟目录 plots_<metrics_dir 名>）",
    )
    ap.add_argument(
        "--cjk-font",
        action="store_true",
        help="尝试设置中文字体（标题等含中文时建议开启）",
    )
    args = ap.parse_args()

    if args.cjk_font:
        _set_cjk_font()

    metrics_dir = args.metrics_dir
    reports = _load_reports(metrics_dir)
    if not reports:
        raise SystemExit(f"No reports found under: {metrics_dir}")

    # ensure required keys exist
    keys = ["coverage", "acc_orig", "acc_adv", "gain", "gain_conf", "asr", "strength"]
    for r in reports:
        for k in keys:
            r.setdefault(k, None)
        if r.get("gain_conf") is None and r.get("gain") is not None:
            r["gain_conf"] = r["gain"]

    transform_name_map = _load_transform_english_names()

    # sort for nicer plots
    reports_sorted = sorted(reports, key=lambda x: (x.get("strength") is None, -(x.get("strength") or 0.0)))

    if args.output_dir is not None:
        plot_dir = args.output_dir
    else:
        plot_dir = metrics_dir.parent / f"plots_{metrics_dir.name}"

    # Labels: use English rule names (avoid TXX)
    rule_ids = [r["rule_id"] for r in reports_sorted]
    labels_english = [transform_name_map.get(rid, rid) for rid in rule_ids]
    labels_english_short = [_short_label(x, 22) for x in labels_english]

    # 1) strength ranking
    strengths = [float(r.get("strength") or 0.0) for r in reports_sorted]
    plt.figure(figsize=(10.5, max(4.0, 0.42 * len(rule_ids))))
    plt.barh(labels_english_short[::-1], strengths[::-1], color="#4C78A8")
    plt.xlabel("strength (coverage * gain_conf)")
    plt.title("Rule strength ranking (all rules)")
    _savefig(plot_dir / "01_strength_rank.png")

    # 1b) gain_conf ranking（置信度向 NO 偏移）
    gains = [_conf_shift_gain(r) for r in reports_sorted]
    # use gain_conf-sorted order for ranking readability
    reports_gain_sorted = sorted(reports_sorted, key=_conf_shift_gain, reverse=True)
    labels_gain = [_short_label(transform_name_map.get(r["rule_id"], r["rule_id"]), 22) for r in reports_gain_sorted]
    gains_gain = [_conf_shift_gain(r) for r in reports_gain_sorted]
    plt.figure(figsize=(10.5, max(4.0, 0.42 * len(reports_gain_sorted))))
    plt.barh(labels_gain[::-1], gains_gain[::-1], color="#E45756")
    plt.xlabel("gain_conf (conf_adv_op - conf_orig_op on original_passed subset)")
    plt.title("LLM confidence shift (gain_conf) ranking")
    _savefig(plot_dir / "01b_gain_conf_rank.png")

    # 2) coverage vs ASR scatter (size=gain_conf)
    coverages = [float(r.get("coverage") or 0.0) for r in reports_sorted]
    asrs = [r.get("asr") for r in reports_sorted]
    # asr may be None; treat as 0 for plotting
    asrs_plot = [float(a or 0.0) for a in asrs]
    gains = [_conf_shift_gain(r) for r in reports_sorted]
    sizes = [max(10.0, 900.0 * abs(g) + 10.0) for g in gains]
    plt.figure(figsize=(8.6, 6.2))
    plt.scatter(coverages, asrs_plot, s=sizes, c=gains, cmap="viridis", alpha=0.88)
    for x, y, lab in zip(coverages, asrs_plot, labels_english_short):
        plt.annotate(lab, (x, y), textcoords="offset points", xytext=(4, 4), fontsize=7)
    plt.xlabel("coverage")
    plt.ylabel("ASR (flipped rate among original_passed)")
    plt.title("coverage vs ASR (point size ~ |gain_conf|)")
    plt.colorbar(label="gain_conf")
    _savefig(plot_dir / "02_coverage_vs_asr.png")

    # 3) acc_orig vs acc_adv grouped bars
    # show all rules; keep readable by sorting by acc_adv desc then label rotation
    reports_bar = sorted(reports, key=lambda x: float(x.get("acc_adv") or 0.0), reverse=True)
    rule_ids_bar = [r["rule_id"] for r in reports_bar]
    labels_english_bar = [_short_label(transform_name_map.get(rid, rid), 22) for rid in rule_ids_bar]
    acc_orig = [float(r.get("acc_orig") or 0.0) for r in reports_bar]
    acc_adv = [float(r.get("acc_adv") or 0.0) for r in reports_bar]
    x = list(range(len(rule_ids_bar)))
    w = 0.42
    plt.figure(figsize=(13.5, 6.0))
    plt.bar([i - w / 2 for i in x], acc_orig, width=w, label="acc_orig", color="#F58518")
    plt.bar([i + w / 2 for i in x], acc_adv, width=w, label="acc_adv", color="#54A24B")
    plt.xticks(x, labels_english_bar, rotation=45, ha="right", fontsize=9)
    plt.ylim(0, 1.02)
    plt.ylabel("accuracy rate")
    plt.title("Original vs adversarial accuracy (all rules)")
    plt.legend()
    _savefig(plot_dir / "03_acc_orig_vs_acc_adv.png")

    # 4) heatmap-like grid using imshow
    # We avoid seaborn dependency by using matplotlib imshow + annotations.
    metrics_cols = ["coverage", "acc_orig", "acc_adv", "gain_conf", "asr", "strength"]
    grid = []
    row_labels = []
    for r in reports_sorted:
        row_labels.append(_short_label(transform_name_map.get(r["rule_id"], r["rule_id"]), 22))
        row = []
        for c in metrics_cols:
            v = r.get(c)
            if v is None:
                v = 0.0
            row.append(float(v))
        grid.append(row)
    # Normalize each column to [0,1] for visual consistency
    import numpy as np

    arr = np.array(grid, dtype=float)
    col_min = arr.min(axis=0, keepdims=True)
    col_max = arr.max(axis=0, keepdims=True)
    denom = np.where(col_max - col_min == 0, 1.0, col_max - col_min)
    arr_norm = (arr - col_min) / denom

    plt.figure(figsize=(10.5, max(4.0, 0.42 * len(row_labels))))
    im = plt.imshow(arr_norm, aspect="auto", cmap="YlOrRd")
    plt.colorbar(im, label="normalized value")
    plt.yticks(range(len(row_labels)), row_labels, fontsize=9)
    plt.xticks(range(len(metrics_cols)), metrics_cols, rotation=25, ha="right")

    # annotate with raw values (compact format)
    for i in range(arr.shape[0]):
        for j in range(arr.shape[1]):
            v = arr[i, j]
            txt = f"{v:.3f}" if abs(v) < 100 else f"{v:.1f}"
            plt.text(j, i, txt, ha="center", va="center", fontsize=7, color="black")

    plt.title("Heatmap of rule metrics (normalized per column)")
    _savefig(plot_dir / "04_metrics_heatmap.png")

    # 5) gain_conf vs ASR（看「置信偏移」与 flip 是否同向）
    plt.figure(figsize=(8.6, 6.2))
    gc_vals = [_conf_shift_gain(r) for r in reports_sorted]
    asrs2 = [float(r.get("asr") or 0.0) for r in reports_sorted]
    plt.scatter(gc_vals, asrs2, s=120, c=range(len(reports_sorted)), cmap="tab20", alpha=0.85, edgecolors="k", linewidths=0.3)
    for r, x, y, lab in zip(reports_sorted, gc_vals, asrs2, labels_english_short):
        plt.annotate(lab, (x, y), textcoords="offset points", xytext=(4, 3), fontsize=7)
    plt.xlabel("gain_conf")
    plt.ylabel("ASR")
    plt.title("gain_conf vs ASR (per rule)")
    plt.grid(True, alpha=0.25)
    _savefig(plot_dir / "05_gain_conf_vs_asr.png")

    # 6) 准确率下降 (acc_orig - acc_adv) 排序
    reports_acc_sorted = sorted(reports, key=_gain_acc, reverse=True)
    labels_acc = [_short_label(transform_name_map.get(r["rule_id"], r["rule_id"]), 22) for r in reports_acc_sorted]
    gains_acc = [_gain_acc(r) for r in reports_acc_sorted]
    plt.figure(figsize=(10.5, max(4.0, 0.42 * len(reports_acc_sorted))))
    plt.barh(labels_acc[::-1], gains_acc[::-1], color="#72B7B2")
    plt.xlabel("gain_acc = acc_orig - acc_adv")
    plt.title("Accuracy drop ranking (gain_acc)")
    plt.xlim(0, max(gains_acc) * 1.08 if gains_acc else 1.0)
    _savefig(plot_dir / "06_gain_acc_rank.png")

    # 7) 热力图含 gain_acc
    metrics_cols7 = ["coverage", "acc_orig", "acc_adv", "gain_acc", "gain_conf", "asr", "strength"]
    grid7 = []
    row_labels7 = []
    for r in reports_sorted:
        row_labels7.append(_short_label(transform_name_map.get(r["rule_id"], r["rule_id"]), 22))
        row7 = []
        for c in metrics_cols7:
            if c == "gain_acc":
                v = _gain_acc(r)
            else:
                v = r.get(c)
            if v is None:
                v = 0.0
            row7.append(float(v))
        grid7.append(row7)

    import numpy as np

    arr7 = np.array(grid7, dtype=float)
    cmin = arr7.min(axis=0, keepdims=True)
    cmax = arr7.max(axis=0, keepdims=True)
    denom7 = np.where(cmax - cmin == 0, 1.0, cmax - cmin)
    arr7n = (arr7 - cmin) / denom7

    plt.figure(figsize=(11.0, max(4.0, 0.42 * len(row_labels7))))
    im7 = plt.imshow(arr7n, aspect="auto", cmap="YlOrRd")
    plt.colorbar(im7, label="normalized per column")
    plt.yticks(range(len(row_labels7)), row_labels7, fontsize=9)
    plt.xticks(range(len(metrics_cols7)), metrics_cols7, rotation=30, ha="right")

    for i in range(arr7.shape[0]):
        for j in range(arr7.shape[1]):
            v = arr7[i, j]
            txt = f"{v:.3f}" if abs(v) < 100 else f"{v:.1f}"
            plt.text(j, i, txt, ha="center", va="center", fontsize=6, color="black")

    plt.title("Heatmap incl. gain_acc (normalized per column)")
    _savefig(plot_dir / "07_metrics_heatmap_with_gain_acc.png")

    print("Plot saved to:", plot_dir)
    for name in [
        "01_strength_rank.png",
        "01b_gain_conf_rank.png",
        "02_coverage_vs_asr.png",
        "03_acc_orig_vs_acc_adv.png",
        "04_metrics_heatmap.png",
        "05_gain_conf_vs_asr.png",
        "06_gain_acc_rank.png",
        "07_metrics_heatmap_with_gain_acc.png",
    ]:
        print(" -", plot_dir / name)


if __name__ == "__main__":
    main()

