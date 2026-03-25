#!/usr/bin/env python3
"""
基于已跑完的单规则评估目录，统计：数据集中有多少样本「至少存在一条规则」
在 ASR 口径下攻击成功（与 evaluate_rules.py 一致）。

口径（ASR flip）：
  - 从 orig_verdict_cache 读取该样本的 original_passed（必须与跑评估时同一 cache_key）；
  - 从各规则 metrics/<rule_id>/adv_eval/<tid>_rep0.json 读取 adversarial_passed；
  - 当 original_passed == True 且 adversarial_passed == False 时，记为该规则下攻击成功；
  - 对规则取并集：样本被统计为「可攻击」当且仅当存在至少一条规则满足上式。

「冗余规则」检验（你问的第二种统计）：
  - 对每条规则 R，记 Flip(R) = 被 R 单独打出 ASR-flip 的样本集合；
  - 若 Flip(R) 中每个样本都至少还被某条其它规则 R'≠R 打出 flip，即
    Flip(R) ⊆ ⋃_{R'≠R} Flip(R')，
    则称：在本批规则下，R 的攻击成功样本都可被其它规则覆盖（R 对并集无「独占」贡献）；
  - 脚本会列出满足上式且 |Flip(R)|>0 的规则，并标记是否存在这样的规则。

说明：
  - adv_eval 下出现某 tid，表示当时该规则对该样本变换成功并已跑过对抗评估；
  - 若 adversarial_passed 为 null（如 Connection error），不计入攻击成功。

用法示例：
  python scripts/analysis/union_attack_coverage.py \\
    --dataset data/qualified_dataset.normalized.json \\
    --metrics-root rule_eval/metrics_full_all_rules \\
    --orig-cache rule_eval/orig_verdict_cache.json \\
    --provider local --model qwen2.5-coder-7b --base-url http://localhost:8002/v1
"""

from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any, DefaultDict, Dict, List, Optional, Set, Tuple


def build_cache_key(
    provider: str,
    model: str,
    base_url: str,
    api_key: str,
) -> str:
    return "|".join(
        [
            str(provider),
            str(model),
            str(base_url or ""),
            str(api_key or ""),
            "max_tokens=2048",
            "llm_confidence_from_logprobs=no_minus_yes_v4",
        ]
    )


def load_orig_passed_map(
    cache_path: Path,
    cache_key: Optional[str],
) -> Tuple[Dict[str, Optional[bool]], str]:
    """返回 task_id -> original_passed；缺失的 key 不在 dict 中。"""
    if not cache_path.exists():
        raise FileNotFoundError(f"orig cache 不存在: {cache_path}")
    blob = json.loads(cache_path.read_text(encoding="utf-8"))
    if not isinstance(blob, dict):
        raise ValueError("orig cache 顶层应为 JSON object")

    key = cache_key
    if key is None:
        keys = [k for k in blob if k != "tasks" and isinstance(blob.get(k), dict)]
        if len(keys) == 1:
            key = keys[0]
        elif len(keys) == 0:
            raise ValueError("cache 中找不到模型分区，请显式传入 --cache-key")
        else:
            raise ValueError(
                "cache 中有多个模型分区，请用 --cache-key 指定其一，例如:\n  "
                + "\n  ".join(keys[:5])
                + ("\n  ..." if len(keys) > 5 else "")
            )

    section = blob.get(key)
    if not isinstance(section, dict):
        raise KeyError(f"cache 中无 key: {key!r}")

    tasks = section.get("tasks") or {}
    out: Dict[str, Optional[bool]] = {}
    for tid, row in tasks.items():
        if not isinstance(row, dict):
            continue
        op = row.get("original_passed")
        if op is None:
            out[str(tid)] = None
        else:
            out[str(tid)] = bool(op)
    return out, key


def discover_rule_adv_dirs(metrics_root: Path) -> List[Tuple[str, Path]]:
    """返回 [(rule_id, adv_eval_dir), ...]，按 rule_id 排序。"""
    pairs: List[Tuple[str, Path]] = []
    for adv in sorted(metrics_root.glob("*/adv_eval")):
        if adv.is_dir():
            pairs.append((adv.parent.name, adv))
    return pairs


def main() -> None:
    ap = argparse.ArgumentParser(description="多规则并集：至少一条规则 ASR-flip 覆盖统计")
    ap.add_argument("--dataset", required=True, help="dataset.json 路径")
    ap.add_argument(
        "--metrics-root",
        required=True,
        help="单规则评估输出根目录（其下为 T03/T09/...，各含 adv_eval/）",
    )
    ap.add_argument("--orig-cache", required=True, help="orig_verdict_cache*.json 路径")
    ap.add_argument(
        "--cache-key",
        default=None,
        help="缓存分区键；默认在仅有一个分区时自动选用",
    )
    ap.add_argument("--provider", default="", help="与 evaluate_rules 一致，用于拼 cache_key")
    ap.add_argument("--model", default="", help="同上")
    ap.add_argument("--base-url", default="", help="同上")
    ap.add_argument("--api-key", default="", help="同上（未设置可传空字符串）")
    ap.add_argument(
        "--output",
        default=None,
        help="可选：将详细结果写入 JSON（含每样本命中的规则列表等）",
    )
    ap.add_argument(
        "--list-unflipped-orig-pass",
        default=None,
        help="可选：将「cache 中 original_passed 为真、且并集上无任何规则 flip」的 task_id 逐行写入",
    )
    args = ap.parse_args()

    root = Path(__file__).resolve().parents[2]
    dataset_path = root / args.dataset
    metrics_root = root / args.metrics_root
    cache_path = root / args.orig_cache

    data = json.loads(dataset_path.read_text(encoding="utf-8"))
    all_ids = sorted({str(t.get("task_id")) for t in data if t.get("task_id")})
    n_all = len(all_ids)
    all_set = set(all_ids)

    cache_key = args.cache_key
    if cache_key is None and args.provider:
        cache_key = build_cache_key(
            args.provider,
            args.model,
            args.base_url or "",
            args.api_key if args.api_key is not None else "",
        )

    orig_map, used_key = load_orig_passed_map(cache_path, cache_key)

    orig_pass_ids = {tid for tid, v in orig_map.items() if v is True}
    orig_fail_ids = {tid for tid, v in orig_map.items() if v is False}
    missing_cache = sorted(all_set - set(orig_map.keys()))

    # tid -> set of rules that achieved flip
    flipped_rules: DefaultDict[str, Set[str]] = defaultdict(set)
    # tid -> rules where we have adv json (transform + eval attempted)
    evaluated_rules: DefaultDict[str, Set[str]] = defaultdict(set)
    # (tid, rule) -> adversarial_passed for debug
    adv_status: Dict[Tuple[str, str], Optional[bool]] = {}

    rule_dirs = discover_rule_adv_dirs(metrics_root)
    if not rule_dirs:
        raise SystemExit(f"在 {metrics_root} 下未发现任何 */adv_eval 目录")

    for rule_id, adv_dir in rule_dirs:
        for f in adv_dir.glob("*_rep0.json"):
            if not f.is_file():
                continue
            tid = f.stem.split("_rep")[0]
            evaluated_rules[tid].add(rule_id)
            try:
                j = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                adv_status[(tid, rule_id)] = None
                continue
            ap_ = j.get("adversarial_passed")
            adv_status[(tid, rule_id)] = ap_ if isinstance(ap_, (bool, type(None))) else None
            if ap_ is not True and ap_ is not False:
                continue
            op = orig_map.get(tid)
            if op is True and ap_ is False:
                flipped_rules[tid].add(rule_id)

    union_flipped = set(flipped_rules.keys())

    # rule -> set of tid ASR-flipped by this rule
    flip_by_rule: DefaultDict[str, Set[str]] = defaultdict(set)
    for tid, rs in flipped_rules.items():
        for r in rs:
            flip_by_rule[r].add(tid)

    rule_ids_ordered = [r for r, _ in rule_dirs]
    redundant_nonempty: List[str] = []
    per_rule_redundancy: List[Dict[str, Any]] = []
    for r in rule_ids_ordered:
        fr = flip_by_rule.get(r, set())
        others_union: Set[str] = set()
        for r2, s2 in flip_by_rule.items():
            if r2 != r:
                others_union |= s2
        exclusive = fr - others_union  # 仅被 r 命中、不被任何其它规则 flip 的样本
        covered_by_others = len(fr) > 0 and not exclusive
        per_rule_redundancy.append(
            {
                "rule_id": r,
                "num_asr_flip": len(fr),
                "num_exclusive_flip_not_by_other_rules": len(exclusive),
                "every_flip_also_flipped_by_some_other_rule": covered_by_others,
            }
        )
        if covered_by_others:
            redundant_nonempty.append(r)

    exists_redundant_nonempty_rule = len(redundant_nonempty) > 0

    # 在「原始判对」子集中，既被某规则评估过、又从未 flip 的样本
    orig_pass_evaluated = {
        tid
        for tid in orig_pass_ids
        if tid in evaluated_rules and evaluated_rules[tid]
    }
    orig_pass_never_flipped = orig_pass_evaluated - union_flipped
    orig_pass_no_rule_eval = orig_pass_ids - orig_pass_evaluated
    # 并集口径下「仍未被攻击成功」的 orig 判对样本（含从未出现在任何 adv_eval 中的）
    orig_pass_not_in_union = orig_pass_ids - union_flipped

    report: Dict[str, Any] = {
        "dataset": str(dataset_path),
        "metrics_root": str(metrics_root),
        "orig_cache": str(cache_path),
        "cache_key_used": used_key,
        "num_dataset_tasks": n_all,
        "num_rules_with_adv_eval": len(rule_dirs),
        "rule_ids": [r for r, _ in rule_dirs],
        "num_tasks_in_orig_cache": len(orig_map),
        "num_dataset_missing_orig_cache": len(missing_cache),
        "definition": "union_over_rules: original_passed==True (cache) AND adversarial_passed==False (adv_eval rep0)",
        "num_original_passed_in_cache": len(orig_pass_ids),
        "num_original_failed_in_cache": len(orig_fail_ids),
        "num_union_asr_flip": len(union_flipped),
        "rate_union_asr_flip_vs_all_dataset": round(len(union_flipped) / n_all, 6) if n_all else 0.0,
        "rate_union_asr_flip_vs_original_passed": round(len(union_flipped) / len(orig_pass_ids), 6)
        if orig_pass_ids
        else None,
        "num_orig_pass_had_some_rule_eval": len(orig_pass_evaluated),
        "num_orig_pass_no_rule_adv_eval": len(orig_pass_no_rule_eval),
        "num_orig_pass_never_flipped_among_evaluated": len(orig_pass_never_flipped),
        "rate_orig_pass_never_flipped_among_evaluated": round(
            len(orig_pass_never_flipped) / len(orig_pass_evaluated), 6
        )
        if orig_pass_evaluated
        else None,
        "num_orig_pass_not_in_union_flip": len(orig_pass_not_in_union),
        "rate_orig_pass_not_in_union_flip": round(len(orig_pass_not_in_union) / len(orig_pass_ids), 6)
        if orig_pass_ids
        else None,
        "redundant_rule_definition": "nonempty Flip(R) and Flip(R) ⊆ union_{R'≠R} Flip(R')",
        "exists_rule_whose_all_asr_flips_are_also_asr_flips_of_other_rules": exists_redundant_nonempty_rule,
        "rules_nonempty_all_flips_covered_by_other_rules": redundant_nonempty,
        "per_rule_redundancy_vs_others": per_rule_redundancy,
    }

    print(json.dumps(report, ensure_ascii=False, indent=2))

    if args.list_unflipped_orig_pass:
        out_path = root / args.list_unflipped_orig_pass
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            "\n".join(sorted(orig_pass_not_in_union)) + ("\n" if orig_pass_not_in_union else ""),
            encoding="utf-8",
        )
        print(f"\n已写入 orig 判对但并集未 ASR-flip 的 task_id: {out_path}", flush=True)

    if args.output:
        out_path = root / args.output
        out_path.parent.mkdir(parents=True, exist_ok=True)
        flip_by_rule_json = {k: sorted(v) for k, v in sorted(flip_by_rule.items())}
        exclusive_by_rule = {}
        for r in rule_ids_ordered:
            fr = flip_by_rule.get(r, set())
            others_union: Set[str] = set()
            for r2, s2 in flip_by_rule.items():
                if r2 != r:
                    others_union |= s2
            exclusive_by_rule[r] = sorted(fr - others_union)
        detail = {
            **report,
            "missing_orig_cache_task_ids_sample": missing_cache[:50],
            "union_flip_task_ids": sorted(union_flipped),
            "flipped_by_task": {k: sorted(v) for k, v in sorted(flipped_rules.items())},
            "flip_by_rule": flip_by_rule_json,
            "exclusive_flip_task_ids_by_rule": exclusive_by_rule,
        }
        out_path.write_text(json.dumps(detail, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n详细 JSON: {out_path}", flush=True)


if __name__ == "__main__":
    main()
