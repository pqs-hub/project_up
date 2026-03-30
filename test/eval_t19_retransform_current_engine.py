#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""使用当前项目T19规则，对外部数据集T19样本重变换并评估攻击成功率。"""

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
from core.transforms import create_engine


def looks_like_verilog(code: str) -> bool:
    c = (code or "").strip().lower()
    return bool(c and "module " in c and "endmodule" in c)


def load_t19_samples(dataset_path: Path):
    rows = []
    with open(dataset_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception:
                continue
            if d.get("rule_id") == "T19":
                rows.append(d)
    return rows


def process_one(sample: dict, idx: int, engine, judge: TargetModelClient, use_cot: bool) -> dict:
    out = {
        "idx": idx,
        "task_id": sample.get("task_id"),
        "rule_id": "T19",
        "params_used": (sample.get("adv_result_row") or {}).get("params_used") or {},
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

        spec = (ds.get("prompt") or "").strip()
        orig_from_ae = (ae.get("original_code") or "").strip()
        original_code = orig_from_ae if looks_like_verilog(orig_from_ae) else (ds.get("canonical_solution") or "")
        original_code = (original_code or "").strip()

        if not spec or not original_code:
            out["error"] = "missing_data"
            return out

        params = ar.get("params_used") or {}
        if not isinstance(params, dict):
            params = {}

        transformed = engine.apply_transform(original_code, "T19", **params)
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
    ap.add_argument("--output-dir", default="doc/t19_retransform_eval")
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
    dataset_path = Path(args.dataset)
    samples = load_t19_samples(dataset_path)
    if args.max_samples and args.max_samples > 0:
        samples = samples[: args.max_samples]

    total = len(samples)
    print(f"dataset: {dataset_path}")
    print(f"t19_samples: {total}")
    print(f"judge: {tm.get('base_url')} / {tm.get('model')}")

    stats = Counter()
    stats["total"] = total
    lock = Lock()
    results = []

    with ThreadPoolExecutor(max_workers=args.workers) as ex:
        futures = [ex.submit(process_one, s, i, engine, judge, args.use_cot) for i, s in enumerate(samples)]
        pbar = tqdm(total=total, desc="t19_eval", unit="sample")
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            with lock:
                if r["error"]:
                    stats["error"] += 1
                    stats[f"err_{r['error']}"] += 1
                else:
                    stats["evaluated"] += 1
                    if r["original_correct"]:
                        stats["original_correct"] += 1
                    if r["transformed_incorrect"]:
                        stats["transformed_incorrect"] += 1
                    if r["attack_success"]:
                        stats["attack_success"] += 1
            pbar.update(1)
        pbar.close()

    out_dir = PROJECT_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    evaluated = stats["evaluated"]
    attack_success = stats["attack_success"]
    original_correct = stats["original_correct"]

    payload = {
        "dataset": str(dataset_path),
        "rule": "T19",
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
            "error_breakdown": {k.replace("err_", ""): v for k, v in stats.items() if k.startswith("err_")},
        },
        "results": results,
    }

    out_json = out_dir / "t19_retransform_eval.json"
    out_txt = out_dir / "summary.txt"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("T19重变换攻击评估摘要\n")
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
        if stats["error"]:
            f.write("error_breakdown:\n")
            for k, v in sorted(payload["stats"]["error_breakdown"].items(), key=lambda x: -x[1]):
                f.write(f"  - {k}: {v}\n")

    print(f"saved: {out_json}")
    print(f"saved: {out_txt}")


if __name__ == "__main__":
    main()
