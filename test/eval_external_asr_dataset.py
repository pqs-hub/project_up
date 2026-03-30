#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""评估外部ASR数据集在当前判断模型上的攻击成功率。"""

import argparse
import json
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from threading import Lock

import yaml
from tqdm import tqdm

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.target_model import TargetModelClient


def process_one(sample: dict, idx: int, judge: TargetModelClient, use_cot: bool) -> dict:
    result = {
        "idx": idx,
        "task_id": sample.get("task_id"),
        "rule_id": sample.get("rule_id"),
        "original_correct": None,
        "adversarial_incorrect": None,
        "attack_success": False,
        "original_confidence": None,
        "adversarial_confidence": None,
        "confidence_drop": None,
        "label_asr_success": sample.get("asr_success"),
        "error": None,
    }

    try:
        ds = sample.get("dataset_row") or {}
        adv = sample.get("adv_eval_row") or {}
        adv_result = sample.get("adv_result_row") or {}
        spec = (ds.get("prompt") or "").strip()
        original_code = (adv.get("original_code") or ds.get("canonical_solution") or "").strip()
        adversarial_code = (adv.get("adversarial_code") or adv_result.get("final") or "").strip()

        if not spec or not original_code or not adversarial_code:
            result["error"] = "missing_data"
            return result

        o = judge.judge(spec, original_code, use_cot=use_cot)
        if not o:
            result["error"] = "judge_original_failed"
            return result
        a = judge.judge(spec, adversarial_code, use_cot=use_cot)
        if not a:
            result["error"] = "judge_adversarial_failed"
            return result

        original_correct = bool(o.get("is_correct", False))
        adversarial_incorrect = not bool(a.get("is_correct", True))

        oc = float(o.get("confidence", 0.0))
        ac = float(a.get("confidence", 0.0))

        result["original_correct"] = original_correct
        result["adversarial_incorrect"] = adversarial_incorrect
        result["attack_success"] = original_correct and adversarial_incorrect
        result["original_confidence"] = oc
        result["adversarial_confidence"] = ac
        result["confidence_drop"] = oc - ac
    except Exception as e:
        result["error"] = str(e)[:200]

    return result


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--workers", type=int, default=16)
    ap.add_argument("--max-samples", type=int, default=0)
    ap.add_argument("--use-cot", action="store_true")
    ap.add_argument("--output-dir", default="doc/external_asr_eval")
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

    samples = []
    p = Path(args.dataset)
    with open(p, "r", encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                samples.append(json.loads(line))
            except Exception:
                continue

    if args.max_samples and args.max_samples > 0:
        samples = samples[: args.max_samples]

    total = len(samples)
    print(f"dataset: {p}")
    print(f"samples: {total}")
    print(f"judge: {tm.get('base_url')} / {tm.get('model')}")

    lock = Lock()
    stats = Counter()
    stats["total"] = total
    per_rule_total = Counter()
    for s in samples:
        per_rule_total[s.get("rule_id") or "UNKNOWN"] += 1

    results = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(process_one, s, i, judge, args.use_cot) for i, s in enumerate(samples)]
        pbar = tqdm(total=total, desc="eval", unit="sample")
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            with lock:
                if r["error"]:
                    stats["error"] += 1
                else:
                    stats["evaluated"] += 1
                    if r["original_correct"]:
                        stats["original_correct"] += 1
                    if r["adversarial_incorrect"]:
                        stats["adversarial_incorrect"] += 1
                    if r["attack_success"]:
                        stats["attack_success"] += 1
                        stats[f"succ_{r.get('rule_id') or 'UNKNOWN'}"] += 1
                    # 与标签一致性
                    lbl = r.get("label_asr_success")
                    if isinstance(lbl, bool):
                        stats["label_compared"] += 1
                        if lbl == r["attack_success"]:
                            stats["label_match"] += 1
            pbar.update(1)
        pbar.close()

    out_dir = PROJECT_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "external_asr_eval.json"
    out_txt = out_dir / "summary.txt"

    evaluated = stats["evaluated"]
    attack_success = stats["attack_success"]
    original_correct = stats["original_correct"]

    per_rule = {}
    for rule, t in per_rule_total.items():
        s = stats.get(f"succ_{rule}", 0)
        per_rule[rule] = {
            "total": t,
            "success": s,
            "success_rate": (s / t) if t else 0.0,
        }

    payload = {
        "dataset": str(p),
        "judge": {
            "base_url": tm.get("base_url"),
            "model": tm.get("model"),
        },
        "stats": {
            "total": total,
            "evaluated": evaluated,
            "error": stats["error"],
            "original_correct": original_correct,
            "adversarial_incorrect": stats["adversarial_incorrect"],
            "attack_success": attack_success,
            "attack_success_rate": (attack_success / evaluated) if evaluated else 0.0,
            "attack_success_rate_on_original_correct": (attack_success / original_correct) if original_correct else 0.0,
            "label_compared": stats["label_compared"],
            "label_match": stats["label_match"],
            "label_match_rate": (stats["label_match"] / stats["label_compared"]) if stats["label_compared"] else 0.0,
        },
        "per_rule": per_rule,
        "results": results,
    }

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("外部ASR数据集评估摘要\n")
        f.write("=" * 60 + "\n")
        f.write(f"dataset: {p}\n")
        f.write(f"judge: {tm.get('base_url')} / {tm.get('model')}\n")
        f.write(f"total: {total}\n")
        f.write(f"evaluated: {evaluated}\n")
        f.write(f"error: {stats['error']}\n")
        f.write(f"attack_success: {attack_success} ({(attack_success/evaluated*100) if evaluated else 0:.2f}%)\n")
        f.write(
            f"attack_success_on_original_correct: {attack_success}/{original_correct} = {(attack_success/original_correct*100) if original_correct else 0:.2f}%\n"
        )
        f.write(f"label_match_rate: {(stats['label_match']/stats['label_compared']*100) if stats['label_compared'] else 0:.2f}%\n")

    print(f"saved: {out_json}")
    print(f"saved: {out_txt}")


if __name__ == "__main__":
    main()
