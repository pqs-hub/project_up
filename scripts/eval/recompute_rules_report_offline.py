#!/usr/bin/env python3
"""
在不调用 LLM / evaluate.py 的前提下，仅从已有结果重算各规则 T*_report.json 与 rules_report.json。

保留每条规则旧报告中的「变换层」统计（num_samples、coverage、success_rate 等），
仅重算依赖 orig_verdict_cache + adv_eval 的字段：
  acc_orig, acc_adv, conf_*, conf_*_op, denom_orig_passed, gain, gain_conf, asr, strength

用法示例：
  python scripts/eval/recompute_rules_report_offline.py \\
    --eval-output rule_eval/metrics_conf_v2_on_fullall_adv \\
    --dataset data/qualified_dataset.normalized.json \\
    --orig-verdict-cache rule_eval/orig_verdict_cache_conf_v2.json
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


def _load_cache_tasks(cache_path: Path, cache_key: Optional[str]) -> Tuple[Dict[str, Any], str]:
    blob = json.loads(cache_path.read_text(encoding="utf-8"))
    if cache_key is not None:
        if cache_key not in blob:
            raise SystemExit(f"cache 中无分区: {cache_key!r}")
        key = cache_key
    else:
        keys = [k for k in blob if k != "tasks" and isinstance(blob.get(k), dict)]
        if len(keys) != 1:
            raise SystemExit(
                "请用 --cache-key 指定分区；候选:\n  " + "\n  ".join(keys[:8])
            )
        key = keys[0]
    section = blob[key]
    tasks = section.get("tasks") or {}
    if not isinstance(tasks, dict):
        raise SystemExit("cache 分区内无 tasks 对象")
    return tasks, key


def _rule_dirs(eval_root: Path) -> List[Path]:
    out: List[Path] = []
    for p in sorted(eval_root.iterdir()):
        if not p.is_dir():
            continue
        if not re.match(r"^T\d", p.name):
            continue
        if (p / "adv_eval").is_dir():
            out.append(p)
    return out


def _preserve_transform_block(old: Optional[Dict]) -> Dict[str, Any]:
    """从旧 Txx_report 拷贝变换层字段；若无则填占位。"""
    keys = [
        "num_samples",
        "applicable_samples",
        "success_samples",
        "total_candidates",
        "total_success",
        "coverage",
        "success_rate",
    ]
    base: Dict[str, Any] = {}
    if old:
        for k in keys:
            if k in old:
                base[k] = old[k]
    return base


def recompute_rule(
    rule_id: str,
    adv_eval_dir: Path,
    cache_tasks: Dict[str, Any],
    dataset_order: List[str],
    old_report: Optional[Dict],
) -> Dict[str, Any]:
    adv_tids = set()
    adv_by_tid: Dict[str, Dict] = {}
    for f in adv_eval_dir.glob("*_rep0.json"):
        if not f.is_file():
            continue
        tid = f.stem.split("_rep")[0]
        try:
            adv_by_tid[tid] = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        adv_tids.add(tid)

    success_task_ids = [tid for tid in dataset_order if tid in adv_tids]
    success_task_ids_set = set(success_task_ids)
    denom_samples = len(success_task_ids)

    block = _preserve_transform_block(old_report)
    if "num_samples" not in block and dataset_order:
        block["num_samples"] = len(dataset_order)
    if "success_samples" not in block:
        block["success_samples"] = denom_samples
    ns = int(block.get("num_samples") or 0) or len(dataset_order)
    if "coverage" not in block and ns:
        block["coverage"] = denom_samples / ns
    for k, default in [
        ("applicable_samples", denom_samples),
        ("total_candidates", denom_samples),
        ("total_success", denom_samples),
        ("success_rate", 1.0),
    ]:
        block.setdefault(k, default)

    orig_passed_cnt = 0
    conf_orig_sum = 0.0
    for tid in success_task_ids:
        entry = cache_tasks.get(tid) or {}
        if entry.get("original_passed") is True:
            orig_passed_cnt += 1
        c = entry.get("original_confidence")
        if isinstance(c, (int, float)):
            conf_orig_sum += float(c)

    acc_orig = (orig_passed_cnt / denom_samples) if denom_samples else 0.0
    conf_orig_avg = (conf_orig_sum / denom_samples) if denom_samples else 0.0

    adv_passed_cnt = 0
    denom_asr = 0
    numer_asr = 0
    conf_adv_sum = 0.0
    for tid in success_task_ids:
        adv_j = adv_by_tid.get(tid)
        if not adv_j:
            continue
        ap = adv_j.get("adversarial_passed", None)
        if ap is True:
            adv_passed_cnt += 1
        ca = adv_j.get("adversarial_confidence")
        if isinstance(ca, (int, float)):
            conf_adv_sum += float(ca)
        orig_entry = cache_tasks.get(tid) or {}
        if orig_entry.get("original_passed") is True:
            denom_asr += 1
            if ap is False:
                numer_asr += 1

    acc_adv = (adv_passed_cnt / denom_samples) if denom_samples else 0.0
    asr = (numer_asr / denom_asr) if denom_asr else None
    conf_adv_avg = (conf_adv_sum / denom_samples) if denom_samples else 0.0

    denom_op = orig_passed_cnt
    conf_orig_sum_op = 0.0
    conf_adv_sum_op = 0.0
    for tid in success_task_ids:
        entry = cache_tasks.get(tid) or {}
        if entry.get("original_passed") is not True:
            continue
        co = entry.get("original_confidence")
        if isinstance(co, (int, float)):
            conf_orig_sum_op += float(co)
        adv_j = adv_by_tid.get(tid) or {}
        ca = adv_j.get("adversarial_confidence")
        if isinstance(ca, (int, float)):
            conf_adv_sum_op += float(ca)

    conf_orig_op_avg = (conf_orig_sum_op / denom_op) if denom_op else 0.0
    conf_adv_op_avg = (conf_adv_sum_op / denom_op) if denom_op else 0.0
    gain_conf = conf_adv_op_avg - conf_orig_op_avg
    strength = block.get("coverage", 0.0) * gain_conf if gain_conf is not None else block.get("coverage", 0.0)

    out = {
        "rule_id": rule_id,
        **block,
        "acc_orig": acc_orig,
        "acc_adv": acc_adv,
        "conf_orig": conf_orig_avg,
        "conf_adv": conf_adv_avg,
        "conf_orig_op": conf_orig_op_avg,
        "conf_adv_op": conf_adv_op_avg,
        "denom_orig_passed": denom_op,
        "gain": gain_conf,
        "gain_conf": gain_conf,
        "asr": asr,
        "strength": strength,
    }
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="离线重算 rules 报告（不调用模型）")
    ap.add_argument("--eval-output", type=Path, required=True, help="含 Txx/adv_eval 的 metrics 根目录")
    ap.add_argument("--dataset", type=Path, required=True)
    ap.add_argument("--orig-verdict-cache", type=Path, required=True)
    ap.add_argument("--cache-key", default=None, help="orig cache 分区 key；不填则自动唯一分区")
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="只打印将写入的规则数，不写文件",
    )
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parents[2]
    eval_root = args.eval_output
    if not eval_root.is_dir():
        raise SystemExit(f"目录不存在: {eval_root}")

    ds_path = project_root / args.dataset if not args.dataset.is_absolute() else args.dataset
    data = json.loads(ds_path.read_text(encoding="utf-8"))
    dataset_order = [t["task_id"] for t in data if t.get("task_id")]

    cache_path = project_root / args.orig_verdict_cache if not args.orig_verdict_cache.is_absolute() else args.orig_verdict_cache
    cache_tasks, used_key = _load_cache_tasks(cache_path, args.cache_key)
    print(f"使用 orig cache 分区: {used_key[:80]}..." if len(used_key) > 80 else f"使用 orig cache 分区: {used_key}")

    overall: List[Dict[str, Any]] = []
    for rule_dir in _rule_dirs(eval_root):
        rule_id = rule_dir.name
        old_path = eval_root / f"{rule_id}_report.json"
        old_report: Optional[Dict] = None
        if old_path.is_file():
            try:
                old_report = json.loads(old_path.read_text(encoding="utf-8"))
            except Exception:
                old_report = None
        adv_eval_dir = rule_dir / "adv_eval"
        row = recompute_rule(rule_id, adv_eval_dir, cache_tasks, dataset_order, old_report)
        overall.append(row)
        if not args.dry_run:
            old_path.write_text(json.dumps(row, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  {rule_id}: acc_orig={row['acc_orig']:.4f} acc_adv={row['acc_adv']:.4f} gain_conf={row['gain_conf']:.4f} asr={row['asr']}")

    overall.sort(key=lambda x: x["rule_id"])
    if not args.dry_run:
        out_all = eval_root / "rules_report.json"
        out_all.write_text(json.dumps(overall, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n已写入 {len(overall)} 条规则 -> {out_all}")
    else:
        print(f"\n[dry-run] 将写入 {len(overall)} 条规则")


if __name__ == "__main__":
    main()
