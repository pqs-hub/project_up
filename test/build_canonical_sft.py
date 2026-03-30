#!/usr/bin/env python3
"""
从 sft_clean_v_json.jsonl / sft_clean_v_cot.jsonl 中，
为每个 unique prompt 选取一个 canonical answer。

模式 A（默认）：纯规则优先级
  结构类 > 逻辑类 > 视觉类，同类内按样本总量降序

模式 B（--use-scores）：基于 flip_strength 的赋分公式
  假设已运行 score_flip_strength.py 生成了 sft_all_scored.jsonl

  硬过滤1：一致性校验——target_line 必须在 transformed_rtl 中真正发生变化
    - 若 JSON output 声称修改了第 N 行，但 diff 显示该行未变 → drop
  硬过滤2：剔除 p_no_adv < 0.5 的致盲攻击（Verifier 被搞晕而非被说服）
    - 若某 prompt 下所有候选均为致盲攻击，则保底选 code_diff_ratio 最小的一条
    - 致盲样本仍保留在 GRPO pool（带 blinding_attack 标记，供差异化 reward）

  赋分：0.50*FlipStrength + 0.30*Locality + 0.10*Simplicity + 0.10*RulePrior
  每个 prompt 取综合分最高的那条

输出：
  sft_canonical[_scored]_v_json.jsonl   -- SFT训练用（纯JSON，每 prompt 一条）
  sft_canonical[_scored]_v_cot.jsonl    -- SFT训练用（策略+JSON，每 prompt 一条）
  grpo_prompts[_scored].jsonl           -- GRPO用（含 success_rules 和 blinding_rules）
"""

import argparse
import difflib
import json
import hashlib
from collections import defaultdict
from pathlib import Path

BASE = Path("/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset")

# 规则优先级（数字越小越优先）
RULE_PRIORITY = {
    # 结构类
    "T32": 1, "T48": 2, "T41": 3, "T07": 4, "T47": 5,
    # 逻辑类
    "T09": 10, "T10": 11, "T12": 12, "T30": 13, "T31": 14, "T45": 15,
    # 视觉类
    "T03": 20, "T19": 21, "T20": 22, "T34": 23,
}

# 规则样本总量（作为同优先级内的次级排序，越多越稳定）
RULE_COUNT = {
    "T19": 14601, "T32": 11104, "T20": 8782, "T03": 8136,
    "T45": 6213, "T31": 2859, "T48": 937, "T41": 831,
    "T12": 694, "T34": 672, "T30": 576, "T07": 451,
    "T09": 368, "T10": 312, "T47": 123,
}

# 规则 Locality 分（规则改动越局部越好，用于赋分公式）
RULE_LOCALITY = {
    "T32": 1.0, "T09": 0.9, "T10": 0.9, "T30": 0.9, "T31": 0.85,
    "T12": 0.85, "T41": 0.8,  "T47": 0.8,  "T45": 0.75, "T07": 0.7,
    "T48": 0.7,  "T03": 0.65, "T19": 0.6,  "T20": 0.5,  "T34": 0.5,
}

# 规则 Simplicity 分（参数越简单越高）
RULE_SIMPLICITY = {
    "T07": 1.0, "T09": 1.0, "T10": 1.0, "T45": 1.0, "T48": 1.0,
    "T03": 0.9, "T32": 0.9, "T41": 0.9,
    "T30": 0.8, "T47": 0.8,
    "T12": 0.6, "T31": 0.6,
    "T19": 0.5, "T20": 0.5,
    "T34": 0.3,
}


def _extract_orig_rtl(input_str: str) -> list:
    """从 input 字段提取原始代码行（### 原始代码 块）"""
    lines = input_str.splitlines()
    in_block = False
    result = []
    for line in lines:
        if line.strip().startswith("### 原始代码"):
            in_block = True
            continue
        if in_block:
            if line.strip().startswith("###"):
                break
            result.append(line)
    return result


def _get_changed_lines(orig_lines: list, adv_lines: list) -> set:
    """用 difflib 找出原始代码中实际发生变化的行号集合（1-indexed）。
    忽略纯空白行变化（空格/空行差异不算实质改动）。
    """
    sm = difflib.SequenceMatcher(None, orig_lines, adv_lines, autojunk=False)
    changed = set()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        for ln in range(i1 + 1, i2 + 1):  # 1-indexed
            # 忽略纯空白行的变化
            orig_stripped = orig_lines[ln - 1].strip() if ln - 1 < len(orig_lines) else ""
            if orig_stripped:  # 非空行才计入
                changed.add(ln)
        # replace/insert 可能在 adv 侧新增非空行，也视为 orig 对应位置的变化
        if tag in ("replace", "insert") and i1 < len(orig_lines):
            adv_new = [adv_lines[k] for k in range(j1, j2) if k < len(adv_lines)]
            if any(l.strip() for l in adv_new):
                changed.add(i1 + 1)  # orig 的 i1+1 行是变化起点
    return changed


def fix_target_line_in_output(raw_out: str, new_target_line: int,
                               new_target_signal: str = None) -> str:
    """将 output JSON 中的 target_line（及可选的 target_signal）替换为修正后的值。"""
    try:
        text = raw_out.strip()
        has_fence = text.startswith("```")
        if has_fence:
            fence_lines = text.splitlines()
            inner = "\n".join(fence_lines[1:])
            inner = inner.rstrip("`").strip()
        else:
            inner = text
        data = json.loads(inner)
        data["target_line"] = new_target_line
        if new_target_signal is not None:
            data["target_signal"] = new_target_signal
        data["_target_line_corrected"] = True
        new_inner = json.dumps(data, ensure_ascii=False, indent=2)
        if has_fence:
            lang = fence_lines[0][3:].strip()
            return f"```{lang}\n{new_inner}\n```"
        return new_inner
    except Exception:
        return raw_out  # 修正失败时返回原始值


def correct_target_line(sample: dict) -> dict:
    """一致性修正：尝试将 output JSON 里的 target_line 修正为实际发生变化的行号。

    修正规则（按优先级）：
      1. 若已一致 → 直接返回原样本（无需修正）
      2. 若 diff 为空（代码未改动） → 标记 _drop_reason='no_diff'，这是唯一真正的无效样本
      3. 若 diff 只有 1 行 → 用该行替换 target_line
      4. 若 diff 有多行 → 取离原 target_line 最近的变化行替换
      5. 若 output 无 target_line 字段 → 返回原样本（无需修正）
    返回修正后的样本（可能带 _target_line_corrected=True 或 _drop_reason 字段）。
    """
    raw_out = sample.get("output", "")

    # 解析 target_line
    try:
        text = raw_out.strip()
        if text.startswith("```"):
            text = "\n".join(text.splitlines()[1:])
            text = text.rstrip("`").strip()
        data = json.loads(text)
        target_line = data.get("target_line")
        if target_line is None:
            return sample  # 无 target_line，无需校验
        target_line = int(target_line)
    except Exception:
        return sample  # 解析失败，保守放行

    # 提取原始代码行
    orig_lines_raw = _extract_orig_rtl(sample.get("input", ""))
    if not orig_lines_raw:
        return sample

    adv_raw = sample.get("transformed_rtl", "")
    if not adv_raw:
        return sample
    adv_lines_raw = adv_raw.splitlines()

    def strip_lineno(line: str) -> str:
        parts = line.split("\t", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            return parts[1]
        return line

    orig_clean = [strip_lineno(l) for l in orig_lines_raw]
    adv_clean  = [strip_lineno(l) for l in adv_lines_raw]

    changed = _get_changed_lines(orig_clean, adv_clean)

    # 情况2：代码完全未改动 → 真正无效样本
    if not changed:
        result = dict(sample)
        result["_drop_reason"] = "no_diff"
        return result

    # 情况1：已一致
    if target_line in changed:
        return sample

    # 情况3/4：不一致 → 修正
    if len(changed) == 1:
        correct_line = next(iter(changed))
    else:
        # 取离原 target_line 最近的变化行
        correct_line = min(changed, key=lambda ln: abs(ln - target_line))

    # 尝试修正 target_signal：取 orig 中该行对应的信号名（简单提取标识符）
    new_signal = None
    if 1 <= correct_line <= len(orig_clean):
        line_text = orig_clean[correct_line - 1]
        # 匹配 Verilog 端口/信号名：最后一个 \w+ 词（通常是信号名）
        import re as _re
        m = _re.search(r"(?:input|output|inout|wire|reg|logic)\s+(?:\[.*?\]\s*)?([\w]+)",
                       line_text)
        if m:
            new_signal = m.group(1)

    result = dict(sample)
    result["output"] = fix_target_line_in_output(raw_out, correct_line, new_signal)
    return result


def check_target_line_consistency(sample: dict) -> bool:
    """（保留兼容接口）检查样本是否已通过一致性校验（即不含 _drop_reason）。"""
    return sample.get("_drop_reason") is None


def prompt_hash(sample: dict) -> str:
    return hashlib.md5(sample["input"].encode()).hexdigest()


def rule_sort_key(rule_id: str) -> tuple:
    """Mode A: 纯规则优先级排序"""
    return (RULE_PRIORITY.get(rule_id, 99), -RULE_COUNT.get(rule_id, 0))


def composite_score(sample: dict) -> float:
    """Mode B: 0.50*FlipStrength + 0.30*Locality + 0.10*Simplicity + 0.10*RulePrior

    假设调用前已通过硬过滤剔除致盲攻击。
    """
    rid = sample.get("rule_id", "")

    # FlipStrength: flip_strength -> delta_yes -> 规则先验
    fs = sample.get("flip_strength")
    if fs is not None:
        flip = max(0.0, min(1.0, (fs + 2.0) / 6.0))  # [-4,6] -> [0,1]
    else:
        delta = sample.get("delta_yes")
        if delta is not None:
            flip = max(0.0, min(1.0, (delta + 0.2) / 1.2))
        else:
            flip = 1.0 - RULE_PRIORITY.get(rid, 99) / 100.0

    # Locality: code_diff_ratio -> 规则先验
    diff = sample.get("code_diff_ratio")
    locality = max(0.0, 1.0 - float(diff)) if diff is not None else RULE_LOCALITY.get(rid, 0.5)

    simplicity = RULE_SIMPLICITY.get(rid, 0.5)
    rule_prior = 1.0 - RULE_PRIORITY.get(rid, 23) / 25.0

    return 0.50 * flip + 0.30 * locality + 0.10 * simplicity + 0.10 * rule_prior


def select_canonical_mode_b(samples: list, scored_map: dict) -> tuple:
    """Mode B canonical 选取。
    入参 samples 已经过 correct_target_line 修正。
    返回 (best_sample, fallback_used, n_no_diff)
      fallback_used=True  表示所有候选均为致盲攻击，已用 code_diff_ratio 最小作为保底
      n_no_diff           本 prompt 中因代码未改动而剔除的样本数（唯一真正的 drop 原因）
    """
    # 将评分字段注入样本（保留 .fixed.jsonl 的 output 修正，只追加评分字段）
    scored = []
    for s in samples:
        score_fields = scored_map.get(s["rule_id"], {})
        merged = dict(s)
        merged.update(score_fields)
        scored.append(merged)

    # 硬过滤：剔除代码完全未改动的样本（唯一真正无效的情况）
    valid = [s for s in scored if not s.get("_drop_reason")]
    n_no_diff = len(scored) - len(valid)
    if not valid:
        valid = scored  # 全部无效时保守放行

    # 硬过滤2：剔除致盲攻击
    clean = [s for s in valid if not s.get("blinding_attack")]

    if clean:
        return max(clean, key=composite_score), False, n_no_diff
    else:
        # 全部是致盲攻击时保底：取 code_diff_ratio 最小的
        fallback = min(valid,
                       key=lambda s: s.get("code_diff_ratio") if s.get("code_diff_ratio") is not None else 1.0)
        return fallback, True, n_no_diff


# 从评分文件中提取的字段（不含 output/input 等训练字段，避免覆盖 .fixed.jsonl 的修正）
_SCORE_FIELDS = (
    "p_yes_orig", "p_no_orig", "margin_orig",
    "p_yes_adv",  "p_no_adv",  "margin_adv",
    "flip_strength", "delta_yes", "adv_is_correct", "blinding_attack",
    "code_diff_ratio", "code_length", "score_error",
)


def load_scores(scored_file: Path) -> dict:
    """Load scored samples, return {prompt_hash: {rule_id: score_fields_dict}}
    只保留评分字段，不保存 output/input 等训练内容，避免覆盖 .fixed.jsonl 的修正。
    """
    scores = defaultdict(dict)  # hash -> {rule_id: score_fields}
    with open(scored_file) as f:
        for line in f:
            if not line.strip():
                continue
            s = json.loads(line)
            h = prompt_hash(s)
            scores[h][s["rule_id"]] = {k: s[k] for k in _SCORE_FIELDS if k in s}
    return scores


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-scores", action="store_true",
                        help="Mode B: 基于 flip_strength 综合评分选取 canonical")
    parser.add_argument("--scored-file", type=str,
                        default=str(BASE / "sft_all_scored.jsonl"),
                        help="score_flip_strength.py 的输出文件（全量评估结果）")
    parser.add_argument("--all-tiers", action="store_true",
                        help="Mode B下同时输出三档纯净数据集（需配合--use-scores）")
    args = parser.parse_args()

    in_json = BASE / "sft_clean_v_json.fixed.jsonl"
    in_cot  = BASE / "sft_clean_v_cot.fixed.jsonl"

    suffix = "_scored" if args.use_scores else ""
    out_canon_json = BASE / f"sft_canonical{suffix}_v_json.jsonl"
    out_canon_cot  = BASE / f"sft_canonical{suffix}_v_cot.jsonl"
    out_grpo       = BASE / f"grpo_prompts{suffix}.jsonl"

    # 加载评分数据（Mode B）
    scores_map = {}
    if args.use_scores:
        scored_path = Path(args.scored_file)
        if not scored_path.exists():
            print(f"ERROR: scored file not found: {scored_path}")
            print("  请先运行: python test/score_flip_strength.py")
            return
        print(f"Mode B: 加载评分文件 {scored_path}")
        scores_map = load_scores(scored_path)

    # 按 prompt hash 分组
    groups_json = defaultdict(list)
    groups_cot  = defaultdict(list)

    with open(in_json) as fj, open(in_cot) as fc:
        for lj, lc in zip(fj, fc):
            if not lj.strip():
                continue
            sj = json.loads(lj)
            sc = json.loads(lc)
            h = prompt_hash(sj)
            groups_json[h].append(sj)
            groups_cot[h].append(sc)

    n_total  = sum(len(v) for v in groups_json.values())
    n_unique = len(groups_json)
    n_multi  = sum(1 for v in groups_json.values() if len(v) > 1)

    canon_json_lines = []
    canon_cot_lines  = []
    grpo_lines       = []
    n_has_flip    = 0   # Mode B: 有 flip_strength 数据的 prompt 数
    n_fallback    = 0   # Mode B: 全部致盲而用保底的 prompt 数
    n_blind_total    = 0   # Mode B: 被过滤的致盲攻击样本数
    n_inconsistent_total = 0  # Mode B/A: 被一致性校验过滤的样本数

    # 三档容器（仅 --all-tiers 时填充）
    tier1_json, tier1_cot = [], []  # 档位1: 零污染（全clean）
    tier2_json, tier2_cot = [], []  # 档位2: 有clean候选（排除全致盲保底）
    tier3_json, tier3_cot = [], []  # 档位3: 完整（含保底，等同于 out_canon）

    for h, samples in groups_json.items():
        cot_samples = groups_cot[h]

        if args.use_scores and h in scores_map:
            # Mode B
            scored_map_h = scores_map[h]  # rule_id -> scored sample
            best, fallback_used, n_inc = select_canonical_mode_b(samples, scored_map_h)
            n_inconsistent_total += n_inc

            if fallback_used:
                n_fallback += 1
            if best.get("flip_strength") is not None:
                n_has_flip += 1

            # 致盲攻击计数
            n_blind_total += sum(
                1 for s in scored_map_h.values() if s.get("blinding_attack")
            )

            # cot 版用相同 rule_id 对齐
            best_rid = best["rule_id"]
            best_cot = next((s for s in cot_samples if s["rule_id"] == best_rid),
                            cot_samples[0])

            # GRPO: 区分 clean / blinding rules
            # scored_map_h 的值是纯评分字段 dict，需配对 rule_id
            all_scored_pairs = [(s["rule_id"], scored_map_h.get(s["rule_id"], {}))
                                for s in samples]
            grpo_entry = {
                "system":        best["system"],
                "instruction":   best["instruction"],
                "input":         best["input"],
                "success_rules": [s["rule_id"] for s in samples],
                "clean_rules":   [rid for rid, sf in all_scored_pairs
                                   if not sf.get("blinding_attack")],
                "blinding_rules": [rid for rid, sf in all_scored_pairs
                                    if sf.get("blinding_attack")],
            }
        else:
            # Mode A: 纯规则优先级
            pool = [s for s in samples if not s.get("_drop_reason")] or samples
            best = min(pool, key=lambda s: rule_sort_key(s["rule_id"]))
            best_rid = best["rule_id"]
            best_cot = next((s for s in cot_samples if s["rule_id"] == best_rid),
                            cot_samples[0])
            grpo_entry = {
                "system":        best["system"],
                "instruction":   best["instruction"],
                "input":         best["input"],
                "success_rules": [s["rule_id"] for s in samples],
            }

        canon_json_lines.append(best)
        canon_cot_lines.append(best_cot)
        grpo_lines.append(grpo_entry)

        # 三档分流（仅 Mode B + --all-tiers）
        if args.use_scores and args.all_tiers and h in scores_map:
            scored_map_h = scores_map[h]
            all_scored = [scored_map_h.get(s["rule_id"], s) for s in samples]
            has_any_blind = any(s.get("blinding_attack") for s in all_scored)
            all_blind = all(s.get("blinding_attack") for s in all_scored)

            # 档位3: 全部（含保底）
            tier3_json.append(best)
            tier3_cot.append(best_cot)

            # 档位2: 排除全致盲保底
            if not all_blind:
                tier2_json.append(best)
                tier2_cot.append(best_cot)

            # 档位1: 零污染（所有候选均为clean）
            if not has_any_blind:
                tier1_json.append(best)
                tier1_cot.append(best_cot)

    with open(out_canon_json, "w") as f:
        for s in canon_json_lines:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    with open(out_canon_cot, "w") as f:
        for s in canon_cot_lines:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    with open(out_grpo, "w") as f:
        for s in grpo_lines:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    # 写三档文件
    if args.use_scores and args.all_tiers:
        for tier, tj, tc in [
            (1, tier1_json, tier1_cot),
            (2, tier2_json, tier2_cot),
            (3, tier3_json, tier3_cot),
        ]:
            p_json = BASE / f"sft_tier{tier}_v_json.jsonl"
            p_cot  = BASE / f"sft_tier{tier}_v_cot.jsonl"
            with open(p_json, "w") as f:
                for s in tj:
                    f.write(json.dumps(s, ensure_ascii=False) + "\n")
            with open(p_cot, "w") as f:
                for s in tc:
                    f.write(json.dumps(s, ensure_ascii=False) + "\n")

    from collections import Counter
    canon_rule_dist = Counter(s["rule_id"] for s in canon_json_lines)
    mode_label = "B (flip_strength scoring)" if args.use_scores else "A (rule priority)"

    print(f"=== Canonical SFT 数据集统计 [Mode {mode_label}] ===")
    print(f"原始样本数:       {n_total}")
    print(f"Unique prompt数:  {n_unique}")
    print(f"  多规则prompt:   {n_multi} ({n_multi/n_unique*100:.1f}%)")
    print(f"  单规则prompt:   {n_unique-n_multi} ({(n_unique-n_multi)/n_unique*100:.1f}%)")
    print(f"  一致性修正: target_line已修正，仅剔除 {n_inconsistent_total} 条代码完全未改动的无效样本")
    if args.use_scores:
        print(f"\n[Mode B 净化统计]")
        print(f"  有 flip_strength 的 prompt: {n_has_flip} ({n_has_flip/n_unique*100:.1f}%)")
        print(f"  致盲攻击样本总数: {n_blind_total} 条（已过滤出 SFT，保留在 GRPO pool）")
        print(f"  全致盲保底 prompt: {n_fallback} 个（所有候选均为致盲，取 diff 最小）")
    print(f"\nCanonical SFT样本数: {len(canon_json_lines)} (每 prompt 1条)")
    print(f"GRPO unique prompts: {len(grpo_lines)}")
    print("\nCanonical规则分布:")
    for rule, cnt in sorted(canon_rule_dist.items(), key=lambda x: -x[1]):
        print(f"  {rule}: {cnt} ({cnt/len(canon_json_lines)*100:.1f}%)")
    print(f"\n输出:")
    print(f"  SFT纯JSON版:    {out_canon_json}")
    print(f"  SFT策略+JSON版: {out_canon_cot}")
    print(f"  GRPO prompt池:  {out_grpo}")
    if args.use_scores and args.all_tiers:
        print(f"\n三档数据集:")
        print(f"  档位1 [零污染]:  sft_tier1_v_json.jsonl  {len(tier1_json)} 条"
              f"  （所有候选全clean，无任何致盲污染）")
        print(f"  档位2 [主力SFT]: sft_tier2_v_json.jsonl  {len(tier2_json)} 条"
              f"  （canonical为clean，排除全致盲保底prompt）")
        print(f"  档位3 [完整]:    sft_tier3_v_json.jsonl  {len(tier3_json)} 条"
              f"  （含全致盲保底，等同于 {out_canon_json.name}）")


if __name__ == "__main__":
    main()
