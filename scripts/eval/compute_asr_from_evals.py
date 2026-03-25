#!/usr/bin/env python3
"""
从已生成的 evaluate.py 输出中计算 ASR（无需再次调用 LLM）。

假设目录结构类似：
  rule_eval/metrics/rules_report.json
  rule_eval/metrics/<rule_id>/orig_eval/<task_id>_rep<k>.json
  rule_eval/metrics/<rule_id>/adv_eval/<task_id>_rep<k>.json

ASR 定义（与 plan 对齐的“flip”）：
  denom = 原始语义为 True 且对抗语义也为 True，且模型在原始上判对的数量
          （语义等价：original_truth == adversarial_truth == True）
  numer = 在 denom 前提下，模型在对抗上判错的数量
  asr = numer / denom
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List, Optional


def compute_asr_for_rule(rule_dir: Path) -> Optional[float]:
    orig_dir = rule_dir / "orig_eval"
    adv_dir = rule_dir / "adv_eval"
    if not orig_dir.exists() or not adv_dir.exists():
        return None

    denom = 0
    numer = 0

    for orig_file in orig_dir.glob("*_rep*.json"):
        if not orig_file.is_file():
            continue
        adv_file = adv_dir / orig_file.name
        if not adv_file.exists():
            continue

        orig_j = json.loads(orig_file.read_text(encoding="utf-8"))
        adv_j = json.loads(adv_file.read_text(encoding="utf-8"))

        orig_truth = orig_j.get("original_truth", None)
        adv_truth = adv_j.get("adversarial_truth", None)
        orig_passed = orig_j.get("original_passed", None)
        adv_passed = adv_j.get("adversarial_passed", None)

        # 语义等价口径：在同一份 task 下，仿真 truth 必须一致（这里按 plan：原始答案正确，因此要求两边 truth 都为 True）
        if orig_truth is True and adv_truth is True and orig_passed is True:
            denom += 1
            if adv_passed is False:
                numer += 1

    return (numer / denom) if denom else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Compute ASR by merging existing eval outputs.")
    ap.add_argument("--metrics-root", required=True, help="例如 rule_eval/metrics")
    ap.add_argument("--rules-report", default="rules_report.json", help="rules_report.json 文件名")
    args = ap.parse_args()

    metrics_root = Path(args.metrics_root)
    rules_report_path = metrics_root / args.rules_report
    if not rules_report_path.exists():
        raise FileNotFoundError(str(rules_report_path))

    rules_report: List[Dict] = json.loads(rules_report_path.read_text(encoding="utf-8"))

    for entry in rules_report:
        rule_id = entry.get("rule_id")
        if not rule_id:
            continue
        rule_dir = metrics_root / rule_id
        asr = compute_asr_for_rule(rule_dir)
        entry["asr"] = asr

        # 同步更新 per-rule report（如果存在）
        per_rule_report_path = metrics_root / f"{rule_id}_report.json"
        if per_rule_report_path.exists():
            per = json.loads(per_rule_report_path.read_text(encoding="utf-8"))
            per["asr"] = asr
            per_rule_report_path.write_text(
                json.dumps(per, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )

    rules_report_path.write_text(
        json.dumps(rules_report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"Updated ASR in {rules_report_path}")


if __name__ == "__main__":
    main()

