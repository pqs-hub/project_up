#!/usr/bin/env python3
"""
当只重跑部分规则（例如只重跑 T16）时，evaluate_rules.py 会覆盖 rules_report.json。
本脚本把当前 rules_report.json 中的条目合并回 backup（保留其它规则原有条目），
并覆盖回 rule_eval/metrics/rules_report.json。
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, List


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge partial rules_report into backup.")
    ap.add_argument("--metrics-root", default="rule_eval/metrics", help="例如 rule_eval/metrics")
    ap.add_argument("--backup-file", default="rules_report_backup.json", help="备份文件名")
    ap.add_argument("--current-file", default="rules_report.json", help="当前文件名")
    ap.add_argument("--write-asr", action="store_true", help="合并后再运行 compute_asr_from_evals.py 统一计算 asr")
    args = ap.parse_args()

    metrics_root = Path(args.metrics_root)
    backup_path = metrics_root / args.backup_file
    current_path = metrics_root / args.current_file

    backup: List[Dict] = json.loads(backup_path.read_text(encoding="utf-8"))
    current: List[Dict] = json.loads(current_path.read_text(encoding="utf-8"))

    backup_map: Dict[str, Dict] = {e["rule_id"]: e for e in backup if e.get("rule_id")}
    for e in current:
        rid = e.get("rule_id")
        if not rid:
            continue
        if rid in backup_map:
            backup_map[rid].update(e)
        else:
            backup.append(e)
            backup_map[rid] = e

    # 写回（保持原 backup 的顺序）
    merged = [backup_map.get(e["rule_id"], e) for e in backup if e.get("rule_id")]
    current_path.write_text(json.dumps(merged, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Merged into {current_path}")

    if args.write_asr:
        # 延后计算 asr：确保口径是 compute_asr_from_evals.py 的语义等价版
        from subprocess import run

        scripts_dir = Path(__file__).resolve().parents[1]
        compute = scripts_dir / "eval" / "compute_asr_from_evals.py"
        run(
            ["python", str(compute), "--metrics-root", str(metrics_root)],
            cwd=str(Path(__file__).resolve().parents[2]),
            check=True,
        )


if __name__ == "__main__":
    main()

