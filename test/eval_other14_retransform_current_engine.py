#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用当前项目规则引擎，对外部数据集中除T19外的其余14规则样本重变换并评估攻击成功率。"""

import argparse
import json
import sys
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import yaml
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.target_model import TargetModelClient
from core.transforms import create_engine


def looks_like_verilog(code: str) -> bool:
    c = (code or "").strip().lower()
    return bool(c and "module " in c and "endmodule" in c)


def load_samples(dataset_path: Path, supported_rules: set):
    rows = []
    for line in dataset_path.open("r", encoding="utf-8"):
        if not line.strip():
            continue
        try:
            d = json.loads(line)
        except Exception:
            continue
        r = d.get("rule_id")
        if r in supported_rules and r != "T19":
            rows.append(d)
    return rows


def process_one(sample: dict, idx: int, engine, judge: TargetModelClient, use_cot: bool) -> dict:
    out = {
        "idx": idx,
        "task_id": sample.get("task_id"),
        "rule_id": sample.get("rule_id"),
        "original_correct": None,
        "transformed_incorrect": None,
        "attack_success": False,
        "original_confidence": None,
        "transformed_confidence": None,
        "confidence_drop": None,
        "error": None,
    }

    try:
        ds = sample.get("dataset_row") or {}
        ae = sample.get("adv_eval_row") or {}
        ar = sample.get("adv_result_row") or {}

        rule_id = sample.get("rule_id")
        spec = (ds.get("prompt") or "").strip()

        orig_from_ae = (ae.get("original_code") or "").strip()
        original_code = orig_from_ae if looks_like_verilog(orig_from_ae) else (ds.get("canonical_solution") or "")
        original_code = (original_code or "").strip()

        if not spec or not original_code or not rule_id:
            out["error"] = "missing_data"
            return out

        params = ar.get("params_used") or {}
        if not isinstance(params, dict):
            params = {}

        transformed = engine.apply_transform(original_code, rule_id, **params)
        if not transformed or transformed == original_code:
            out["error"] = "no_change"
            return out

        vo = judge.judge(spec, original_code, use_cot=use_cot)
        if not vo:
            out["error"] = "judge_original_failed"
            return out

        vt = judge.judge(spec, transformed, use_cot=use_cot)
        if not vt:
            out["error"] = "judge_transformed_failed"
            return out

        original_correct = bool(vo.get("is_correct", False))
        transformed_incorrect = not bool(vt.get("is_correct", True))

        oc = float(vo.get("confidence", 0.0))
        tc = float(vt.get("confidence", 0.0))

        out["original_correct"] = original_correct
        out["transformed_incorrect"] = transformed_incorrect
        out["attack_success"] = original_correct and transformed_incorrect
        out["original_confidence"] = oc
        out["transformed_confidence"] = tc
        out["confidence_drop"] = oc - tc

    except Exception as e:
        out["error"] = str(e)[:200]

    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--max-samples", type=int, default=0)
    ap.add_argument("--use-cot", action="store_true")
    ap.add_argument("--output-dir", default="doc/other14_retransform_eval")
    args = ap.parse_args()

    with open(PROJECT_ROOT / "config.yaml", "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    tm = cfg.get("target_model", {})
    judge = TargetModelClient(
        base_url=tm.get("base_url", "http://localhost:8001/v1"),
        api_key=tm.get("api_key", "EMPTY"),
        model=tm.get("model", ""),
        timeout=tm.get("timeout", 60),
        max_retries=tm.get("max_retries", 3),
    )

    engine = create_engine()
    supported_rules = set(engine.registry.keys())

    dataset_path = Path(args.dataset)
    samples = load_samples(dataset_path, supported_rules)
    if args.max_samples and args.max_samples > 0:
        samples = samples[: args.max_samples]

    total = len(samples)
    print(f"dataset: {dataset_path}")
    print(f"samples_other14: {total}")
    print(f"judge: {tm.get('base_url')} / {tm.get('model')}")

    stats = Counter()
    stats["total"] = total
    by_rule = defaultdict(Counter)
    lock = Lock()
    results = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(process_one, s, i, engine, judge, args.use_cot) for i, s in enumerate(samples)]
        pbar = tqdm(total=total, desc="other14_eval", unit="sample")
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            rule = r.get("rule_id") or "UNKNOWN"
            with lock:
                stats["seen"] += 1
                by_rule[rule]["total"] += 1
                if r["error"]:
                    stats["error"] += 1
                    by_rule[rule]["error"] += 1
                    by_rule[rule][f"err_{r['error']}"] += 1
                else:
                    stats["evaluated"] += 1
                    by_rule[rule]["evaluated"] += 1
                    if r["original_correct"]:
                        stats["original_correct"] += 1
                        by_rule[rule]["original_correct"] += 1
                    if r["transformed_incorrect"]:
                        stats["transformed_incorrect"] += 1
                        by_rule[rule]["transformed_incorrect"] += 1
                    if r["attack_success"]:
                        stats["attack_success"] += 1
                        by_rule[rule]["attack_success"] += 1
            pbar.update(1)
        pbar.close()

    per_rule = {}
    for rule, c in sorted(by_rule.items()):
        eval_cnt = c["evaluated"]
        orig_corr = c["original_correct"]
        succ = c["attack_success"]
        per_rule[rule] = {
            "total": c["total"],
            "evaluated": eval_cnt,
            "error": c["error"],
            "original_correct": orig_corr,
            "attack_success": succ,
            "attack_success_rate": (succ / eval_cnt) if eval_cnt else 0.0,
            "attack_success_rate_on_original_correct": (succ / orig_corr) if orig_corr else 0.0,
            "error_breakdown": {k.replace("err_", ""): v for k, v in c.items() if k.startswith("err_")},
        }

    evaluated = stats["evaluated"]
    attack_success = stats["attack_success"]
    original_correct = stats["original_correct"]

    payload = {
        "dataset": str(dataset_path),
        "rule_scope": "current_engine_supported_rules_excluding_T19",
        "judge": {"base_url": tm.get("base_url"), "model": tm.get("model")},
        "stats": {
            "total": total,
            "evaluated": evaluated,
            "error": stats["error"],
            "original_correct": original_correct,
            "transformed_incorrect": stats["transformed_incorrect"],
            "attack_success": attack_success,
            "attack_success_rate": (attack_success / evaluated) if evaluated else 0.0,
            "attack_success_rate_on_original_correct": (attack_success / original_correct) if original_correct else 0.0,
        },
        "per_rule": per_rule,
        "results": results,
    }

    out_dir = PROJECT_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "other14_retransform_eval.json"
    out_txt = out_dir / "summary.txt"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("除T19外14规则重变换攻击评估摘要\n")
        f.write("=" * 60 + "\n")
        f.write(f"dataset: {dataset_path}\n")
        f.write(f"judge: {tm.get('base_url')} / {tm.get('model')}\n")
        f.write(f"total: {total}\n")
        f.write(f"evaluated: {evaluated}\n")
        f.write(f"error: {stats['error']}\n")
        f.write(f"attack_success: {attack_success} ({(attack_success/evaluated*100) if evaluated else 0:.2f}%)\n")
        f.write(
            f"attack_success_on_original_correct: {attack_success}/{original_correct} = {(attack_success/original_correct*100) if original_correct else 0:.2f}%\n"
        )
        f.write("\nPer-rule:\n")
        for rule, s in per_rule.items():
            f.write(
                f"- {rule}: success={s['attack_success']}/{s['evaluated']} "
                f"({s['attack_success_rate']*100:.2f}%), "
                f"on_orig_correct={s['attack_success_rate_on_original_correct']*100:.2f}%\n"
            )

    print(f"saved: {out_json}")
    print(f"saved: {out_txt}")


if __name__ == "__main__":
    main()
