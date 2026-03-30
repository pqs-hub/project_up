#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""检查外部旧引擎数据在当前15规则引擎上的可重放性与一致性。"""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.transforms import create_engine


def normalize_code(code: str) -> str:
    lines = [(ln.rstrip()) for ln in (code or "").replace("\r\n", "\n").split("\n")]
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def compact_code(code: str) -> str:
    return "".join((code or "").split())


def looks_like_verilog(code: str) -> bool:
    c = (code or "").strip().lower()
    if not c:
        return False
    return ("module " in c) and ("endmodule" in c)


def safe_params(params):
    if not isinstance(params, dict):
        return {}
    out = {}
    for k, v in params.items():
        if k in {"target_token", "target_line", "target_signal"}:
            out[k] = v
            continue
        # 仅保留基础可序列化值，复杂对象直接转字符串，避免旧数据脏值导致崩溃
        if isinstance(v, (str, int, float, bool, dict, list)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--max-samples", type=int, default=0)
    ap.add_argument("--output-dir", default="doc/replay_compat")
    args = ap.parse_args()

    engine = create_engine()
    supported_rules = set(engine.registry.keys())

    p = Path(args.dataset)
    rows = []
    with open(p, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    if args.max_samples and args.max_samples > 0:
        rows = rows[: args.max_samples]

    stats = Counter()
    rule_stats = defaultdict(Counter)
    unsupported_rules = Counter()
    examples = {
        "unsupported": [],
        "transform_error": [],
        "not_equal": [],
    }

    for i, row in enumerate(rows):
        stats["total"] += 1
        rule_id = row.get("rule_id") or "UNKNOWN"
        rule_stats[rule_id]["total"] += 1

        ds = row.get("dataset_row") or {}
        adv_eval = row.get("adv_eval_row") or {}
        adv_result = row.get("adv_result_row") or {}

        orig_from_adv = (adv_eval.get("original_code") or "").strip()
        adv_from_adv = (adv_eval.get("adversarial_code") or "").strip()

        original = orig_from_adv if looks_like_verilog(orig_from_adv) else (ds.get("canonical_solution") or "")
        old_transformed = adv_from_adv if looks_like_verilog(adv_from_adv) else (adv_result.get("final") or "")
        params = safe_params(adv_result.get("params_used") or {})

        if not original or not old_transformed:
            stats["missing_code"] += 1
            rule_stats[rule_id]["missing_code"] += 1
            continue

        if rule_id not in supported_rules:
            stats["unsupported_rule"] += 1
            rule_stats[rule_id]["unsupported_rule"] += 1
            unsupported_rules[rule_id] += 1
            if len(examples["unsupported"]) < 10:
                examples["unsupported"].append({"idx": i, "rule_id": rule_id, "task_id": row.get("task_id")})
            continue

        stats["supported_rule"] += 1
        rule_stats[rule_id]["supported_rule"] += 1

        try:
            new_transformed = engine.apply_transform(original, rule_id, **params)
        except Exception as e:
            stats["transform_error"] += 1
            rule_stats[rule_id]["transform_error"] += 1
            if len(examples["transform_error"]) < 10:
                examples["transform_error"].append(
                    {
                        "idx": i,
                        "rule_id": rule_id,
                        "task_id": row.get("task_id"),
                        "error": str(e)[:200],
                        "params": params,
                    }
                )
            continue

        stats["replayed"] += 1
        rule_stats[rule_id]["replayed"] += 1

        old_norm = normalize_code(old_transformed)
        new_norm = normalize_code(new_transformed)

        if new_norm == old_norm:
            stats["exact_equal"] += 1
            rule_stats[rule_id]["exact_equal"] += 1
        elif compact_code(new_norm) == compact_code(old_norm):
            stats["equal_ignore_ws"] += 1
            rule_stats[rule_id]["equal_ignore_ws"] += 1
        else:
            stats["not_equal"] += 1
            rule_stats[rule_id]["not_equal"] += 1
            if len(examples["not_equal"]) < 20:
                examples["not_equal"].append(
                    {
                        "idx": i,
                        "rule_id": rule_id,
                        "task_id": row.get("task_id"),
                        "params": params,
                        "old_head": old_norm[:300],
                        "new_head": new_norm[:300],
                    }
                )

    out_dir = PROJECT_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    supported = stats["supported_rule"]
    replayed = stats["replayed"]

    payload = {
        "dataset": str(p),
        "supported_rules_in_current_engine": sorted(supported_rules),
        "summary": {
            "total": stats["total"],
            "supported_rule": supported,
            "unsupported_rule": stats["unsupported_rule"],
            "missing_code": stats["missing_code"],
            "transform_error": stats["transform_error"],
            "replayed": replayed,
            "exact_equal": stats["exact_equal"],
            "equal_ignore_ws": stats["equal_ignore_ws"],
            "not_equal": stats["not_equal"],
            "supported_coverage": (supported / stats["total"]) if stats["total"] else 0.0,
            "replay_success_rate_on_supported": (replayed / supported) if supported else 0.0,
            "exact_equal_rate_on_replayed": (stats["exact_equal"] / replayed) if replayed else 0.0,
            "equal_ignore_ws_rate_on_replayed": ((stats["exact_equal"] + stats["equal_ignore_ws"]) / replayed) if replayed else 0.0,
        },
        "unsupported_rules": dict(unsupported_rules),
        "per_rule": {k: dict(v) for k, v in sorted(rule_stats.items())},
        "examples": examples,
    }

    out_json = out_dir / "replay_compat_report.json"
    out_txt = out_dir / "summary.txt"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(out_txt, "w", encoding="utf-8") as f:
        s = payload["summary"]
        f.write("旧引擎数据在当前规则引擎上的重放兼容性\n")
        f.write("=" * 64 + "\n")
        f.write(f"dataset: {p}\n")
        f.write(f"total: {s['total']}\n")
        f.write(f"supported_rule: {s['supported_rule']} ({s['supported_coverage']*100:.2f}%)\n")
        f.write(f"unsupported_rule: {s['unsupported_rule']}\n")
        f.write(f"missing_code: {s['missing_code']}\n")
        f.write(f"transform_error: {s['transform_error']}\n")
        f.write(f"replayed: {s['replayed']} (on supported: {s['replay_success_rate_on_supported']*100:.2f}%)\n")
        f.write(f"exact_equal: {s['exact_equal']} ({s['exact_equal_rate_on_replayed']*100:.2f}% of replayed)\n")
        f.write(f"equal_ignore_ws: {s['equal_ignore_ws']}\n")
        f.write(f"not_equal: {s['not_equal']}\n")

    print(f"saved: {out_json}")
    print(f"saved: {out_txt}")


if __name__ == "__main__":
    main()
