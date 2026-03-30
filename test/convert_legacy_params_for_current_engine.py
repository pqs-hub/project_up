#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将外部旧数据集中的变换参数转换为当前引擎可重放参数（尽量复现旧变体）。"""

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

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
    return bool(c and "module " in c and "endmodule" in c)


def safe_params(params):
    if not isinstance(params, dict):
        return {}
    out = {}
    for k, v in params.items():
        if isinstance(v, (str, int, float, bool, dict, list)) or v is None:
            out[k] = v
        else:
            out[k] = str(v)
    return out


def canonicalize_params(rule_id: str, params: dict) -> dict:
    p = dict(params or {})

    # 统一目标字段命名
    if "nth_occurrence" in p and "target_token" not in p:
        try:
            p["target_token"] = max(0, int(p["nth_occurrence"]) - 1)
        except Exception:
            pass

    # T20特殊处理：设置target_line为模块声明行（通常是第1行）
    if rule_id == "T20":
        p["target_line"] = 1  # 模块声明通常在第1行
        if "custom_text" in p:
            # 为T20准备legacy注释字面量，保持原始格式
            custom_text = p["custom_text"]
            if not custom_text.startswith("//"):
                # 如果不是以//开头，添加双斜杠以匹配旧引擎格式
                p["legacy_comment_literal"] = f"// {custom_text}\n"
            else:
                p["legacy_comment_literal"] = f"{custom_text}\n"
            p["custom_description"] = p["custom_text"]

    # 规则特定别名兼容
    if rule_id in {"T12", "T31"} and "wire_name" not in p:
        for k in ("tmp_wire", "new_wire", "intermediate_signal", "temp_wire"):
            if isinstance(p.get(k), str) and p[k].strip():
                p["wire_name"] = p[k].strip()
                break
    if rule_id in {"T12", "T31"}:
        p.setdefault("legacy_inline_decl", True)
    
    # T34: 不启用端口重命名，只处理内部信号
    if rule_id == "T34":
        # 如果有custom_map，提取第一个键作为target_signal（仅限内部信号）
        if "custom_map" in p and isinstance(p["custom_map"], dict) and p["custom_map"]:
            first_signal = next(iter(p["custom_map"].keys()))
            p["target_signal"] = first_signal
    
    # T48: 旧引擎使用full_text模式保留格式
    if rule_id == "T48":
        p.setdefault("full_text", True)
    
    # 通用：如果旧参数中有custom_map但没有对应的key，复制过去
    for k in ["custom_map", "target_map", "signal_map"]:
        if isinstance(p.get(k), dict):
            p["custom_map"] = p[k]
            break

    return p


def extract_code_fields(row: dict):
    ds = row.get("dataset_row") or {}
    adv_eval = row.get("adv_eval_row") or {}
    adv_result = row.get("adv_result_row") or {}

    orig_from_adv = (adv_eval.get("original_code") or "").strip()
    adv_from_adv = (adv_eval.get("adversarial_code") or "").strip()
    adv_from_result = (adv_result.get("final") or "").strip()
    
    rule_id = row.get("rule_id", "")

    original = orig_from_adv if looks_like_verilog(orig_from_adv) else (ds.get("canonical_solution") or "")
    
    # 特殊处理T20：直接使用adv_result.final，因为adv_eval.adversarial_code存储的是"NO"
    if rule_id == "T20":
        old_transformed = adv_from_result if looks_like_verilog(adv_from_result) else ""
    else:
        # 其他规则：优先使用adv_eval.adversarial_code
        if looks_like_verilog(adv_from_adv):
            old_transformed = adv_from_adv
        elif looks_like_verilog(adv_from_result):
            old_transformed = adv_from_result
        else:
            old_transformed = ""

    return (original or "").strip(), (old_transformed or "").strip(), safe_params(adv_result.get("params_used") or {})


def extract_t20_legacy_literals(original_code: str, old_code: str):
    """从 old_code 与 original_code 的行级差异中提取注释插入块（按字面重放）。"""
    a = original_code.splitlines(keepends=True)
    b = old_code.splitlines(keepends=True)
    sm = difflib.SequenceMatcher(a=a, b=b)
    chunks = []
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag != "insert":
            continue
        piece = "".join(b[j1:j2])
        if "//" not in piece:
            continue
        if piece.strip():
            chunks.append(piece)

    out = []
    seen = set()
    for c in chunks:
        if c in seen:
            continue
        seen.add(c)
        out.append(c)
    return out


def build_target_candidates(engine, code: str, rule_id: str, params: dict, max_scan: int):
    cand = []

    # 1) 显式 target_token 优先
    if isinstance(params.get("target_token"), int):
        cand.append(params["target_token"])

    # 2) 无 token 时也尝试 None（让引擎按默认选择）
    cand.append(None)

    # 3) 扫描候选索引（用于修复旧数据目标定位差异）
    try:
        items = engine._get_candidates_for_transform(code, rule_id)  # pylint: disable=protected-access
        n = len(items or [])
        upper = min(n, max_scan)
        cand.extend(list(range(upper)))
    except Exception:
        pass

    # 去重保序
    out = []
    seen = set()
    for x in cand:
        key = ("N",) if x is None else ("I", int(x))
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def try_replay_exact(engine, code: str, old_code: str, rule_id: str, params: dict, max_scan: int):
    old_norm = normalize_code(old_code)
    old_compact = compact_code(old_norm)

    base = canonicalize_params(rule_id, params)

    # 可搜索参数版本（尽量少，保持简洁）
    param_versions = [base]

    if rule_id == "T20":
        for lit in extract_t20_legacy_literals(code, old_code):
            p_lit = dict(base)
            p_lit["legacy_comment_literal"] = lit
            param_versions.append(p_lit)

    # 对这类规则，若旧参数中有 target_line/signal 但可能不稳定，补一个去掉 hint 的版本
    if rule_id in {"T09", "T12", "T19", "T20", "T31", "T34", "T47", "T48"}:
        p2 = dict(base)
        p2.pop("target_line", None)
        p2.pop("target_signal", None)
        if p2 != base:
            param_versions.append(p2)

    ws_match = None

    for pv in param_versions:
        target_candidates = build_target_candidates(engine, code, rule_id, pv, max_scan=max_scan)

        for token in target_candidates:
            run_params = dict(pv)
            run_params.pop("target_token", None)
            if token is not None:
                run_params["target_token"] = token

            try:
                new_code = engine.apply_transform(code, rule_id, **run_params)
            except Exception:
                continue

            # T48特殊后处理：匹配旧引擎的格式
            if rule_id == "T48":
                new_code = post_process_t48_legacy_format(new_code)

            new_norm = normalize_code(new_code)
            if new_norm == old_norm:
                return {
                    "matched": "exact",
                    "converted_params": run_params,
                    "target_token": token,
                }

            if ws_match is None and compact_code(new_norm) == old_compact:
                ws_match = {
                    "matched": "ignore_ws",
                    "converted_params": run_params,
                    "target_token": token,
                }

    if ws_match is not None:
        return ws_match

    return {
        "matched": "none",
        "converted_params": base,
        "target_token": base.get("target_token"),
    }


def post_process_t48_legacy_format(code: str) -> str:
    """后处理T48输出以匹配旧引擎格式：移除注释，统一缩进为2空格"""
    lines = code.split('\n')
    result_lines = []
    
    for line in lines:
        stripped = line.strip()
        if stripped.startswith('assign'):
            # 移除行内注释
            if '//' in stripped:
                stripped = stripped[:stripped.index('//')].strip()
            # 统一缩进为2个空格
            result_lines.append(f'  {stripped}')
        else:
            result_lines.append(line)
    
    return '\n'.join(result_lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dataset", required=True)
    ap.add_argument("--output-dir", default="doc/replay_param_conversion")
    ap.add_argument("--max-samples", type=int, default=0)
    ap.add_argument("--max-target-scan", type=int, default=128)
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

    out_dir = PROJECT_ROOT / args.output_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    out_jsonl = out_dir / "converted_params_dataset.jsonl"

    stats = Counter()
    per_rule = defaultdict(Counter)

    with open(out_jsonl, "w", encoding="utf-8") as wf:
        for idx, row in enumerate(rows):
            rule_id = row.get("rule_id") or "UNKNOWN"
            stats["total"] += 1
            per_rule[rule_id]["total"] += 1

            record = {
                "idx": idx,
                "task_id": row.get("task_id"),
                "rule_id": rule_id,
                "supported": rule_id in supported_rules,
                "status": "",
                "converted_params": None,
            }

            if rule_id not in supported_rules:
                record["status"] = "unsupported_rule"
                stats["unsupported_rule"] += 1
                per_rule[rule_id]["unsupported_rule"] += 1
                wf.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            original, old_transformed, old_params = extract_code_fields(row)
            if not original or not old_transformed:
                record["status"] = "missing_code"
                stats["missing_code"] += 1
                per_rule[rule_id]["missing_code"] += 1
                wf.write(json.dumps(record, ensure_ascii=False) + "\n")
                continue

            # baseline（仅规范化参数，不做搜索）
            baseline_params = canonicalize_params(rule_id, old_params)
            try:
                baseline_new = engine.apply_transform(original, rule_id, **baseline_params)
                b_exact = normalize_code(baseline_new) == normalize_code(old_transformed)
            except Exception:
                b_exact = False
            if b_exact:
                stats["baseline_exact"] += 1
                per_rule[rule_id]["baseline_exact"] += 1

            result = try_replay_exact(
                engine=engine,
                code=original,
                old_code=old_transformed,
                rule_id=rule_id,
                params=old_params,
                max_scan=args.max_target_scan,
            )

            matched = result["matched"]
            record["status"] = matched
            record["converted_params"] = result["converted_params"]

            stats[f"converted_{matched}"] += 1
            per_rule[rule_id][f"converted_{matched}"] += 1

            # 输出简化后的新行，避免主目录脏化；原行放在 payload 中便于后续复用
            payload = {
                "meta": record,
                "original_row": row,
            }
            wf.write(json.dumps(payload, ensure_ascii=False) + "\n")

    report = {
        "dataset": str(p),
        "total": stats["total"],
        "unsupported_rule": stats["unsupported_rule"],
        "missing_code": stats["missing_code"],
        "baseline_exact": stats["baseline_exact"],
        "converted_exact": stats["converted_exact"],
        "converted_ignore_ws": stats["converted_ignore_ws"],
        "converted_none": stats["converted_none"],
        "baseline_exact_rate": (stats["baseline_exact"] / stats["total"]) if stats["total"] else 0.0,
        "converted_exact_rate": (stats["converted_exact"] / stats["total"]) if stats["total"] else 0.0,
        "converted_equal_ignore_ws_rate": ((stats["converted_exact"] + stats["converted_ignore_ws"]) / stats["total"]) if stats["total"] else 0.0,
        "per_rule": {k: dict(v) for k, v in sorted(per_rule.items())},
        "output_jsonl": str(out_jsonl),
    }

    out_json = out_dir / "conversion_report.json"
    out_txt = out_dir / "summary.txt"

    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    with open(out_txt, "w", encoding="utf-8") as f:
        f.write("旧参数到当前引擎兼容参数转换报告\n")
        f.write("=" * 64 + "\n")
        f.write(f"dataset: {p}\n")
        f.write(f"total: {report['total']}\n")
        f.write(f"unsupported_rule: {report['unsupported_rule']}\n")
        f.write(f"missing_code: {report['missing_code']}\n")
        f.write(f"baseline_exact: {report['baseline_exact']} ({report['baseline_exact_rate']*100:.2f}%)\n")
        f.write(f"converted_exact: {report['converted_exact']} ({report['converted_exact_rate']*100:.2f}%)\n")
        f.write(
            f"converted_equal_ignore_ws: {report['converted_exact'] + report['converted_ignore_ws']} "
            f"({report['converted_equal_ignore_ws_rate']*100:.2f}%)\n"
        )
        f.write(f"converted_none: {report['converted_none']}\n")

    print(f"saved: {out_jsonl}")
    print(f"saved: {out_json}")
    print(f"saved: {out_txt}")


if __name__ == "__main__":
    main()
