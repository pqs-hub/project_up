#!/usr/bin/env python3
"""
核对 adv_eval 里 adversarial_confidence 与 adversarial_code 解析出的 YES/NO、以及 adversarial_passed 是否自洽。

confidence 定义与 evaluate.py 一致：score = P(NO) - P(YES)。
- score > 0：整体偏 NO
- score < 0：整体偏 YES

典型「不一致」：score > 0 但正文最先匹配的单词为 yes（模型口头 YES、分布却偏 NO）。

用法：
  python scripts/eval/verify_adv_conf_vs_verdict.py --adv-eval rule_eval/metrics_conf_v2_on_fullall_adv/T47/adv_eval
  python scripts/eval/verify_adv_conf_vs_verdict.py --adv-eval rule_eval/metrics_conf_v2_on_fullall_adv/T47/adv_eval --max-examples 15
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def parse_yes_no(text: str) -> Optional[bool]:
    """与 evaluate.parse_yes_no 保持一致（避免 import evaluate 拉起重依赖）。"""
    if not text:
        return None
    low = text.strip().lower()
    m = re.search(r"\b(yes|no)\b", low)
    if m:
        return m.group(1) == "yes"
    tokens = [t for t in re.split(r"\s+", low) if t]
    for t in tokens[:5]:
        if t.startswith("yes"):
            return True
        if t.startswith("no"):
            return False
    return None


def analyze_one(row: Dict[str, Any], eps: float = 0.02) -> Dict[str, Any]:
    tid = row.get("task_id", "?")
    code = row.get("adversarial_code") or ""
    conf = row.get("adversarial_confidence")
    passed = row.get("adversarial_passed")
    truth = row.get("adversarial_truth")

    verdict = parse_yes_no(code)
    recomputed: Optional[bool] = None
    if verdict is not None and truth is not None:
        # 与 eval_single：model_thinks_correct == verdict; passed = (verdict == truth)
        recomputed = verdict == truth

    lean = None
    if isinstance(conf, (int, float)):
        if conf > 0:
            lean = "NO"
        elif conf < 0:
            lean = "YES"
        else:
            lean = "NEUTRAL"

    mismatch_lean_text = False
    if isinstance(conf, (int, float)) and verdict is not None:
        if conf > eps and verdict is True:
            mismatch_lean_text = True
        elif conf < -eps and verdict is False:
            mismatch_lean_text = True

    passed_mismatch = False
    if recomputed is not None and passed is not None:
        passed_mismatch = bool(recomputed) != bool(passed)

    return {
        "task_id": tid,
        "adversarial_confidence": conf,
        "lean_from_conf": lean,
        "verdict_from_text": verdict,
        "adversarial_truth": truth,
        "adversarial_passed": passed,
        "recomputed_passed": recomputed,
        "mismatch_lean_vs_text": mismatch_lean_text,
        "passed_field_mismatch": passed_mismatch,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description="核对 adversarial_confidence 与输出文本 / passed")
    ap.add_argument("--adv-eval", required=True, type=Path, help="某规则 adv_eval 目录")
    ap.add_argument(
        "--max-examples",
        type=int,
        default=20,
        help="每类不一致最多打印几条 task_id",
    )
    ap.add_argument(
        "--eps",
        type=float,
        default=0.02,
        help="|confidence|≤eps 视为中性，不计入「偏 YES/偏 NO 与正文冲突」",
    )
    args = ap.parse_args()
    adv_dir = args.adv_eval
    if not adv_dir.is_dir():
        raise SystemExit(f"不是目录: {adv_dir}")

    files = sorted(adv_dir.glob("*_rep0.json"))
    total = 0
    with_conf = 0
    mismatch_lean = 0
    mismatch_passed = 0
    no_verdict = 0
    examples_lean: List[str] = []
    examples_passed: List[str] = []

    for p in files:
        try:
            row = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        total += 1
        r = analyze_one(row, eps=args.eps)
        if isinstance(r["adversarial_confidence"], (int, float)):
            with_conf += 1
        if r["verdict_from_text"] is None:
            no_verdict += 1
        if r["mismatch_lean_vs_text"]:
            mismatch_lean += 1
            if len(examples_lean) < args.max_examples:
                examples_lean.append(
                    f"{r['task_id']}: conf={r['adversarial_confidence']} lean={r['lean_from_conf']} "
                    f"text_verdict={r['verdict_from_text']} code={repr((row.get('adversarial_code') or '')[:80])}"
                )
        if r["passed_field_mismatch"]:
            mismatch_passed += 1
            if len(examples_passed) < args.max_examples:
                examples_passed.append(
                    f"{r['task_id']}: passed={r['adversarial_passed']} recomputed={r['recomputed_passed']} "
                    f"truth={r['adversarial_truth']} verdict={r['verdict_from_text']}"
                )

    print(f"目录: {adv_dir}")
    print(f"rep0 文件数: {total}")
    print(f"有 adversarial_confidence 数值: {with_conf}")
    print(f"正文无法解析 yes/no: {no_verdict}")
    print()
    print(
        "「置信偏 NO(score>0) 但解析为 YES」或「偏 YES(score<0) 但解析为 NO」:"
        f" {mismatch_lean} / {with_conf if with_conf else total} "
        f"({100 * mismatch_lean / with_conf:.2f}% of with_conf)" if with_conf else f" {mismatch_lean}"
    )
    for line in examples_lean:
        print("  ", line)
    print()
    print(
        f"adversarial_passed 与 (parse_yes_no(code)==truth) 不一致: {mismatch_passed} / {total}"
    )
    for line in examples_passed:
        print("  ", line)


if __name__ == "__main__":
    main()
