#!/usr/bin/env python3
"""
分析“攻击成功难易度”与 SPEC/RTL 特征的关联性。

核心定义（与 union_attack_coverage.py 一致）：
  - 仅对 orig_verdict_cache 里 original_passed==True 的 task 有意义
  - 对每个 task，统计它在多少条规则下满足：
        adversarial_passed == False (adv_eval/*_rep0.json)
    记该计数为 flip_rule_count（数值越大，表示越容易被攻击成功）
  - flip_rule_count==0 的任务即为“打不动”（未被任一规则 ASR flip）

为了快速，脚本对 success 样本做随机抽样提取 SPEC/RTL 特征；
未成功样本（flip_rule_count==0）全量统计。

输出：
  - 控制台打印关键摘要
  - --output-json 写入详细统计
"""

from __future__ import annotations

import argparse
import json
import random
import re
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _extract_cache_key(cache_blob: Dict[str, Any], cache_key: Optional[str]) -> str:
    if cache_key:
        if cache_key not in cache_blob:
            raise SystemExit(f"cache_key not found: {cache_key!r}")
        return cache_key
    keys = [k for k in cache_blob.keys() if k != "tasks" and isinstance(cache_blob.get(k), dict)]
    if len(keys) != 1:
        raise SystemExit("cache_key 未指定且分区不唯一，请用 --cache-key 指定")
    return keys[0]


def _comment_stats(code: str) -> Dict[str, float]:
    # 只做轻量级正则统计：忽略引号内的 // / /*，这是近似
    s = code or ""
    n_chars = len(s)
    if n_chars == 0:
        return {
            "n_chars": 0,
            "has_line_comment": 0.0,
            "has_block_comment": 0.0,
            "comment_chars_ratio": 0.0,
            "slash_comment_count": 0.0,
            "block_comment_count": 0.0,
        }

    line_comments = re.findall(r"//[^\n]*", s)
    # DOTALL 统计块注释文本
    block_comments = re.findall(r"/\*.*?\*/", s, flags=re.DOTALL)

    comment_chars = sum(len(x) for x in line_comments) + sum(len(x) for x in block_comments)
    return {
        "n_chars": float(n_chars),
        "has_line_comment": 1.0 if line_comments else 0.0,
        "has_block_comment": 1.0 if block_comments else 0.0,
        "comment_chars_ratio": float(comment_chars) / float(n_chars),
        "slash_comment_count": float(s.count("//")),
        "block_comment_count": float(len(block_comments)),
    }


def _rtl_stats(rtl: str) -> Dict[str, float]:
    s = rtl or ""
    # 粗特征：结构关键字出现次数
    return {
        "rtl_chars": float(len(s)),
        "rtl_lines": float(s.count("\n") + 1 if s else 0),
        "has_case": 1.0 if re.search(r"\bcase\b", s) else 0.0,
        "case_count": float(len(re.findall(r"\bcase\b", s))),
        "has_if": 1.0 if re.search(r"\bif\b", s) else 0.0,
        "if_count": float(len(re.findall(r"\bif\b", s))),
        "has_always": 1.0 if re.search(r"\balways\b", s) else 0.0,
        "always_count": float(len(re.findall(r"\balways\b", s))),
        "has_assign": 1.0 if re.search(r"\bassign\b", s) else 0.0,
        "assign_count": float(len(re.findall(r"\bassign\b", s))),
        "max_bus_width": float(_max_bus_width(s)),
    }


def _max_bus_width(rtl: str) -> int:
    # 找到 [msb:lsb] 的 msb 值，近似当作 bus width 规模；忽略非标准
    m = re.findall(r"\[(\d+)\s*:\s*(\d+)\]", rtl or "")
    if not m:
        return 1
    widths = []
    for a, b in m:
        try:
            msb = int(a)
            lsb = int(b)
            widths.append(msb - lsb + 1)
        except Exception:
            continue
    return max(widths) if widths else 1


def _spec_stats(prompt: str) -> Dict[str, float]:
    s = prompt or ""
    digits = re.findall(r"\d+", s)
    words = re.findall(r"[A-Za-z_]+", s)
    lower = s.lower()
    def has_kw(kw: str) -> float:
        return 1.0 if kw in lower else 0.0
    return {
        "prompt_chars": float(len(s)),
        "prompt_words": float(len(words)),
        "n_numbers": float(len(digits)),
        "has_clock": has_kw("clock"),
        "has_reset": has_kw("reset"),
        "has_enable": has_kw("enable"),
        "has_priority": has_kw("priority"),
        "has_arbiter": has_kw("arbiter"),
        "has_fsm": has_kw("fsm") or has_kw("state"),
    }


def _spearman_rank_corr(xs: List[float], ys: List[float]) -> Optional[float]:
    # 不依赖 scipy：用简单 Spearman 计算（处理并列用平均名次）
    if len(xs) != len(ys) or len(xs) < 3:
        return None
    n = len(xs)

    def rankdata(a: List[float]) -> List[float]:
        # 1-based rank
        sorted_idx = sorted(range(n), key=lambda i: a[i])
        ranks = [0.0] * n
        i = 0
        while i < n:
            j = i
            while j + 1 < n and a[sorted_idx[j + 1]] == a[sorted_idx[i]]:
                j += 1
            # average rank for ties
            avg_rank = (i + 1 + j + 1) / 2.0
            for k in range(i, j + 1):
                ranks[sorted_idx[k]] = avg_rank
            i = j + 1
        return ranks

    rx = rankdata(xs)
    ry = rankdata(ys)
    mx = sum(rx) / n
    my = sum(ry) / n
    cov = sum((rx[i] - mx) * (ry[i] - my) for i in range(n))
    vx = sum((rx[i] - mx) ** 2 for i in range(n))
    vy = sum((ry[i] - my) ** 2 for i in range(n))
    if vx == 0 or vy == 0:
        return None
    return cov / (vx ** 0.5 * vy ** 0.5)


def main() -> None:
    ap = argparse.ArgumentParser(description="攻击成功难易度 vs SPEC/RTL 关联")
    ap.add_argument("--dataset", required=True, help="data/qualified_dataset.normalized.json")
    ap.add_argument("--orig-cache", required=True, help="rule_eval/orig_verdict_cache*.json")
    ap.add_argument("--metrics-root", required=True, help="rule_eval/metrics_full_all_rules 或 metrics_conf_v2")
    ap.add_argument("--cache-key", default=None, help="若 cache 分区不唯一，用此指定")
    ap.add_argument("--success-sample-size", type=int, default=5000, help="从成功样本抽样用于特征相关分析")
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--output-json", default=None, help="写出详细统计 JSON")
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    dataset_path = root / args.dataset
    orig_cache_path = root / args.orig_cache
    metrics_root = root / args.metrics_root

    dataset = _load_json(dataset_path)
    task_map = {str(t["task_id"]): t for t in dataset if t.get("task_id")}

    cache_blob = _load_json(orig_cache_path)
    cache_key_used = _extract_cache_key(cache_blob, args.cache_key)
    cache_tasks = cache_blob[cache_key_used]["tasks"]
    orig_pass_ids = {str(tid) for tid, row in cache_tasks.items() if isinstance(row, dict) and row.get("original_passed") is True}

    # discover rule dirs
    rule_dirs: List[Tuple[str, Path]] = []
    for p in sorted(metrics_root.iterdir()):
        if not p.is_dir():
            continue
        adv_eval = p / "adv_eval"
        if adv_eval.is_dir():
            rule_dirs.append((p.name, adv_eval))
    if not rule_dirs:
        raise SystemExit(f"在 {metrics_root} 下未发现 */adv_eval 目录")

    flip_rules_by_task: Dict[str, Set[str]] = defaultdict(set)
    # 统计 flip_rule_count: adversarial_passed==False
    for rule_id, adv_eval_dir in rule_dirs:
        for f in adv_eval_dir.glob("*_rep0.json"):
            if not f.is_file():
                continue
            tid = f.stem.split("_rep")[0]
            if tid not in orig_pass_ids:
                continue
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if j.get("adversarial_passed") is False:
                flip_rules_by_task[tid].add(rule_id)

    # build difficulty score for all orig_pass tasks
    all_orig = sorted(orig_pass_ids)
    flip_counts: Dict[str, int] = {}
    success_ids: List[str] = []
    unflipped_ids: List[str] = []
    for tid in all_orig:
        c = len(flip_rules_by_task.get(tid, set()))
        flip_counts[tid] = c
        if c > 0:
            success_ids.append(tid)
        else:
            unflipped_ids.append(tid)

    # sample success ids for feature analysis
    random.seed(args.seed)
    if len(success_ids) > args.success_sample_size:
        success_sample = random.sample(success_ids, args.success_sample_size)
    else:
        success_sample = success_ids

    # for features: unflipped(全部) + success_sample
    feature_ids = unflipped_ids + success_sample
    feature_ids_set = set(feature_ids)

    # extract features
    feat_rows: List[Dict[str, Any]] = []
    for tid in feature_ids:
        t = task_map.get(tid, {})
        prompt = t.get("prompt", "") or ""
        rtl = t.get("canonical_solution", "") or ""
        cs = _comment_stats(rtl)
        rs = _rtl_stats(rtl)
        ss = _spec_stats(prompt)
        row = {
            "task_id": tid,
            "flip_rule_count": flip_counts.get(tid, 0),
            **ss,
            **rs,
            **cs,
        }
        feat_rows.append(row)

    # bucket stats by flip_rule_count (difficulty)
    def bucket(c: int) -> str:
        if c <= 0:
            return "0 (unflipped)"
        if c == 1:
            return "1"
        if c == 2:
            return "2"
        if 3 <= c <= 5:
            return "3-5"
        return "6+"

    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for r in feat_rows:
        buckets[bucket(int(r["flip_rule_count"]))].append(r)

    numeric_keys = [
        "flip_rule_count",
        "prompt_chars",
        "prompt_words",
        "n_numbers",
        "rtl_chars",
        "rtl_lines",
        "max_bus_width",
        "has_case",
        "case_count",
        "has_always",
        "always_count",
        "has_assign",
        "assign_count",
        "has_line_comment",
        "comment_chars_ratio",
        "slash_comment_count",
    ]

    def summarize_bucket(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
        out: Dict[str, Any] = {"n": len(rows)}
        for k in numeric_keys:
            vals = [float(r.get(k, 0.0)) for r in rows if k in r]
            if not vals:
                continue
            vals.sort()
            mean = sum(vals) / len(vals)
            med = vals[len(vals) // 2]
            p90 = vals[int(0.9 * (len(vals) - 1))] if len(vals) > 1 else med
            out[k] = {"mean": mean, "median": med, "p90": p90, "min": vals[0], "max": vals[-1]}
        return out

    bucket_summaries = {bk: summarize_bucket(rows) for bk, rows in buckets.items()}

    # correlations (Spearman) on feature_ids for numeric features vs flip_rule_count
    # 仅对连续/数值特征做粗相关
    corr_targets = [
        "prompt_chars",
        "n_numbers",
        "rtl_chars",
        "rtl_lines",
        "max_bus_width",
        "has_case",
        "has_always",
        "has_assign",
        "comment_chars_ratio",
    ]
    flip_list = [float(r["flip_rule_count"]) for r in feat_rows]
    corr: Dict[str, Optional[float]] = {}
    for k in corr_targets:
        ys = [float(r.get(k, 0.0)) for r in feat_rows]
        corr[k] = _spearman_rank_corr(flip_list, ys)

    report = {
        "dataset": str(dataset_path),
        "orig_cache": str(orig_cache_path),
        "cache_key_used": cache_key_used,
        "metrics_root": str(metrics_root),
        "num_orig_pass_tasks": len(all_orig),
        "num_success_tasks": len(success_ids),
        "num_unflipped_tasks": len(unflipped_ids),
        "success_sample_size_for_features": len(success_sample),
        "feature_sample_size_total": len(feature_ids),
        "bucket_summaries": bucket_summaries,
        "spearman_corr_flip_rule_count_vs_features": corr,
        "notes": "flip_rule_count 越大表示越容易被攻击成功（更多规则都能 ASR flip）。SPEC/RTL 特征为正则近似，注释统计可能受字符串内容影响。",
    }

    print("\n=== 总体规模 ===")
    print(f"orig_pass tasks: {len(all_orig)}")
    print(f"success (flip_rule_count>0): {len(success_ids)}")
    print(f"unflipped (==0): {len(unflipped_ids)}")

    print("\n=== Spearman 相关（flip_rule_count vs 特征）=== ")
    for k, v in corr.items():
        print(f"{k:28s} : {None if v is None else round(v, 4)}")

    print("\n=== bucket 关键差异（只列 prompt_chars / rtl_chars / comment_chars_ratio 的 median）=== ")
    for bk in ["0 (unflipped)", "1", "2", "3-5", "6+"]:
        if bk not in bucket_summaries:
            continue
        bs = bucket_summaries[bk]
        print(
            f"{bk:14s} n={bs['n']:<5d} "
            f"prompt_med={bs['prompt_chars']['median']:.1f} "
            f"rtl_med={bs['rtl_chars']['median']:.1f} "
            f"comment_ratio_med={bs['comment_chars_ratio']['median']:.4f}"
        )

    if args.output_json:
        out_path = root / args.output_json
        out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n详细报告已写入：{out_path}")


if __name__ == "__main__":
    main()

