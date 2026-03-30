#!/usr/bin/env python3
"""
清洗 attack_success_samples_dedup.jsonl，生成两份干净的SFT数据集：
  sft_clean_v_json.jsonl  -- 纯JSON输出版（baseline推荐）
  sft_clean_v_cot.jsonl   -- 短策略+JSON输出版（对照实验）

两个版本共用相同的 system 提示词和短 instruction，
差异仅在 output 字段。
"""

import json
import re
import sys
from pathlib import Path
from collections import Counter, defaultdict

# ============================================================
# SYSTEM: 固定全局约束（放入 system 字段，不随样本重复）
# ============================================================
SYSTEM = (
    "You are a Verilog obfuscation expert. "
    "Your task is to choose exactly one transformation rule that best misleads a verification model, "
    "then output a single JSON object describing the attack decision.\n"
    "\n"
    "Allowed top-level keys (in order): attack_name, target_line, target_signal, parameters.\n"
    "- attack_name (required): must be exactly one of: "
    "redundant_logic_injection, assign_reorder, demorgan_and, demorgan_or, predicate_extraction, "
    "dead_code_injection, misleading_comment, constant_identity_transform, "
    "intermediate_wire_injection, bitwidth_arithmetic_obfuscation, "
    "semantic_inversion_rename, case_branch_reorder, pseudo_combinational_loop, "
    "shannon_expansion, anti_topological_reorder.\n"
    "- target_line (optional): 1-based integer matching the line number prefix in the code block.\n"
    "- target_signal (optional): signal name string.\n"
    "- parameters (optional): omit entirely if not needed; do NOT output empty object or null.\n"
    "\n"
    "Required parameters per rule:\n"
    "- predicate_extraction: parameters.wire_name (non-empty Verilog identifier)\n"
    "- intermediate_wire_injection: parameters.wire_name (non-empty Verilog identifier)\n"
    "- misleading_comment: parameters.custom_text (non-empty string)\n"
    "- dead_code_injection: parameters.custom_dead_stmts (non-empty Verilog statements; "
    "no outer always/initial/module/endmodule)\n"
    "- semantic_inversion_rename: parameters.custom_map (object) and parameters.fallback_prefix (non-empty string)\n"
    "\n"
    "Rules: do not invent extra keys; do not use null or empty string values; "
    "return exactly one ```json ... ``` block; do not add any text after the block."
)

# ============================================================
# INSTRUCTION: 每条样本统一的简短动作指令
# ============================================================
INSTRUCTION = (
    "Given the functional spec and original Verilog code below, "
    "choose the single best obfuscation attack and return exactly one JSON block."
)

# ============================================================
# 规则ID -> 标准 attack_name（与 SEMANTIC_NAMES 对齐）
# ============================================================
RULE_ID_TO_ATTACK_NAME = {
    "T03": "redundant_logic_injection",
    "T07": "assign_reorder",
    "T09": "demorgan_and",
    "T10": "demorgan_or",
    "T12": "predicate_extraction",
    "T19": "dead_code_injection",
    "T20": "misleading_comment",
    "T30": "constant_identity_transform",
    "T31": "intermediate_wire_injection",
    "T32": "bitwidth_arithmetic_obfuscation",
    "T34": "semantic_inversion_rename",
    "T41": "case_branch_reorder",
    "T45": "pseudo_combinational_loop",
    "T47": "shannon_expansion",
    "T48": "anti_topological_reorder",
}

# ============================================================
# 规则策略说明（英文）
# ============================================================
RULE_STRATEGIES = {
    "T03": "Inject redundant logic (signal & 1'b1) to increase code complexity without changing functionality.",
    "T07": "Reorder independent assignment statements to disrupt sequential flow understanding.",
    "T09": "Apply DeMorgan's law to AND operations: a & b → ~(~a | ~b).",
    "T10": "Apply DeMorgan's law to OR operations: a | b → ~(~a & ~b).",
    "T12": "Extract ternary predicate into an intermediate wire to add indirection layers.",
    "T19": "Inject unreachable dead code blocks (wrapped in if(1'b0)) to confuse control flow analysis.",
    "T20": "Add misleading comments that describe incorrect functionality to misdirect the verifier.",
    "T30": "Replace bit constants with equivalent identity expressions: 1'b0 → (1'b1 & 1'b0).",
    "T31": "Split simple assignments into intermediate wires to increase indirection.",
    "T32": "Transform bit-width declarations into arithmetic expressions: [7:0] → [8-1:0].",
    "T34": "Rename internal signals with semantically confusing identifiers to mislead signal tracing.",
    "T41": "Rotate case statement non-default branches to alter execution order perception.",
    "T45": "Inject contradictory terms (a & ~a) that are always false to create pseudo-combinational loops.",
    "T47": "Apply Shannon expansion to shatter comparators or adders into bit-level wire operations.",
    "T48": "Reverse the order of continuous assignment statements in an anti-topological manner.",
}

# ============================================================
# 各规则必须有的参数字段
# ============================================================
REQUIRED_PARAMS = {
    "T12": ["wire_name"],
    "T31": ["wire_name"],
    "T19": ["custom_dead_stmts"],
    "T20": ["custom_text"],
    "T34": ["custom_map", "fallback_prefix"],
}

# 旧名称 -> rule_id 的宽松映射（用于从 output 中的 attack_name 反推 rule_id）
ATTACK_NAME_TO_RULE_ID = {
    "t03": "T03", "redundant_logic": "T03", "redundant logic": "T03",
    "assign_reorder": "T07", "t07": "T07", "case_branch_reorder": "T07",
    "case_reorder": "T41",
    "demorgan_and": "T09", "t09": "T09",
    "demorgan_or": "T10", "t10": "T10",
    "predicate_extraction": "T12", "t12": "T12", "intermediate_signal": "T12",
    "dead_code_injection": "T19", "t19": "T19", "false_pattern_injection": "T19",
    "dead_code": "T19",
    "misleading_comment": "T20", "t20": "T20", "comment_decoy": "T20",
    "misleading_comments": "T20",
    "constant_identity_transform": "T30", "t30": "T30", "constant_identity": "T30",
    "intermediate_wire_injection": "T31", "t31": "T31", "simple_intermediate": "T31",
    "wire_injection": "T31", "dataflow_shattering": "T31",
    "bitwidth_arithmetic_obfuscation": "T32", "t32": "T32", "bitwidth_arithmetic": "T32",
    "semantic_inversion_rename": "T34", "t34": "T34", "universal_rename": "T34",
    "adversarial_rename": "T34",
    "t41": "T41",
    "pseudo_combinational_loop": "T45", "t45": "T45", "pseudo_comb_loop": "T45",
    "shannon_expansion": "T47", "t47": "T47",
    "anti_topological_reorder": "T48", "t48": "T48",
    "anti_topological_shuffle": "T48",
}


def normalize_name(name: str) -> str:
    return re.sub(r"[\s\-]+", "_", (name or "").strip().lower())


def parse_output_json(output: str):
    """从 output 字段中提取 JSON 块"""
    m = re.search(r"```json\s*(.*?)\s*```", output, re.DOTALL)
    if m:
        try:
            return json.loads(m.group(1))
        except Exception:
            pass
    # 尝试裸 JSON
    m2 = re.search(r"\{.*\}", output, re.DOTALL)
    if m2:
        try:
            return json.loads(m2.group(0))
        except Exception:
            pass
    return None


def check_required_params(rule_id: str, params: dict) -> tuple[bool, str]:
    """检查必要参数是否存在且非空"""
    required = REQUIRED_PARAMS.get(rule_id, [])
    for field in required:
        val = params.get(field)
        if val is None or val == "" or val == []:
            return False, f"missing required param: {field}"
    return True, ""


EXCLUDE_PARAM_KEYS = {
    "target_token", "legacy_comment_literal", "legacy_prefer_module_prefix",
    "legacy_inline_decl", "allow_port_rename", "full_text", "target_line",
    "target_signal", "nth_occurrence",
}


def build_json_obj(attack_name: str, obj: dict) -> dict:
    """构建规范JSON对象（固定key顺序，parameters不需要时完全省略）"""
    out_json = {"attack_name": attack_name}
    if obj.get("target_line") is not None:
        try:
            out_json["target_line"] = int(obj["target_line"])
        except (TypeError, ValueError):
            pass
    if obj.get("target_signal") and isinstance(obj.get("target_signal"), str):
        out_json["target_signal"] = obj["target_signal"].strip()
    params = obj.get("parameters") or {}
    clean_params = {k: v for k, v in params.items()
                    if k not in EXCLUDE_PARAM_KEYS and v is not None and v != ""}
    if clean_params:  # 完全省略，不输出空{}
        out_json["parameters"] = clean_params
    return out_json


def build_output_json(attack_name: str, obj: dict) -> str:
    """纯JSON版output"""
    json_str = json.dumps(build_json_obj(attack_name, obj), indent=2, ensure_ascii=False)
    return f"```json\n{json_str}\n```"


def build_output_cot(rule_id: str, attack_name: str, obj: dict) -> str:
    """短策略+JSON版output"""
    strategy = RULE_STRATEGIES.get(rule_id, f"Apply {attack_name} transformation.")
    json_str = json.dumps(build_json_obj(attack_name, obj), indent=2, ensure_ascii=False)
    return f"Strategy: {strategy}\n\n```json\n{json_str}\n```"


def validate_output_json(output: str) -> tuple[bool, str]:
    """验证output中JSON块是否合法且包含必填的attack_name"""
    m = re.search(r"```json\s*(.*?)\s*```", output, re.DOTALL)
    if not m:
        return False, "no json block"
    try:
        obj = json.loads(m.group(1))
    except json.JSONDecodeError as e:
        return False, f"json parse error: {e}"
    if not isinstance(obj.get("attack_name"), str) or not obj["attack_name"].strip():
        return False, "missing attack_name"
    return True, ""


def main():
    input_file = "/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/attack_success_samples_dedup.jsonl"
    out_json_file = "/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/sft_clean_v_json.jsonl"
    out_cot_file  = "/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/sft_clean_v_cot.jsonl"
    report_file   = "/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/clean_report.txt"

    total = 0
    kept = 0
    filter_stats = Counter()
    rule_stats = defaultdict(lambda: {"input": 0, "kept": 0})

    with open(out_json_file, "w", encoding="utf-8") as fj, \
         open(out_cot_file,  "w", encoding="utf-8") as fc, \
         open(input_file,    "r", encoding="utf-8") as f:

        for line in f:
            if not line.strip():
                continue
            total += 1
            sample = json.loads(line)
            rule_id = sample.get("rule_id", "")
            rule_stats[rule_id]["input"] += 1

            # --- 1. 解析 output 中的 JSON ---
            raw_output = sample.get("output", "")
            obj = parse_output_json(raw_output)
            if obj is None:
                filter_stats["no_json_in_output"] += 1
                continue

            # --- 2. 确认 rule_id ---
            if rule_id not in RULE_ID_TO_ATTACK_NAME:
                filter_stats["unsupported_rule"] += 1
                continue

            # --- 3. 检查必要参数 ---
            params = obj.get("parameters") or {}
            ok, reason = check_required_params(rule_id, params)
            if not ok:
                filter_stats[f"missing_param_{rule_id}"] += 1
                continue

            # --- 4. 确定标准 attack_name ---
            attack_name = RULE_ID_TO_ATTACK_NAME[rule_id]

            # --- 5. 构建两个版本的 output ---
            output_json_ver = build_output_json(attack_name, obj)
            output_cot_ver  = build_output_cot(rule_id, attack_name, obj)

            # --- 6. 验证 JSON 合法性 ---
            valid, reason = validate_output_json(output_json_ver)
            if not valid:
                filter_stats["invalid_output_json"] += 1
                continue

            # --- 7. 构建并写入两份样本 ---
            base = {
                "system": SYSTEM,
                "instruction": INSTRUCTION,
                "input": sample.get("input", ""),
                "rule_id": rule_id,
                "transformed_rtl": sample.get("transformed_rtl", ""),
                "source_file": sample.get("source_file", ""),
            }
            fj.write(json.dumps({**base, "output": output_json_ver}, ensure_ascii=False) + "\n")
            fc.write(json.dumps({**base, "output": output_cot_ver},  ensure_ascii=False) + "\n")
            kept += 1
            rule_stats[rule_id]["kept"] += 1

    # --- 报告 ---
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("SFT数据集清洗报告\n")
        f.write("=" * 50 + "\n")
        f.write(f"输入样本数: {total}\n")
        f.write(f"保留样本数: {kept}\n")
        f.write(f"过滤样本数: {total - kept} ({(total-kept)/total*100:.1f}%)\n\n")
        f.write("过滤原因统计:\n")
        f.write("-" * 30 + "\n")
        for reason, cnt in sorted(filter_stats.items(), key=lambda x: -x[1]):
            f.write(f"  {reason}: {cnt}\n")
        f.write("\n各规则保留情况:\n")
        f.write("-" * 30 + "\n")
        for rid, stats in sorted(rule_stats.items()):
            aname = RULE_ID_TO_ATTACK_NAME.get(rid, "?")
            f.write(f"  {rid} ({aname}): {stats['kept']}/{stats['input']} (drop {stats['input']-stats['kept']})\n")

    print("清洗完成!")
    print(f"  输入: {total}")
    print(f"  保留: {kept} ({kept/total*100:.1f}%)")
    print(f"  过滤: {total - kept}")
    print("\n过滤原因:")
    for reason, cnt in sorted(filter_stats.items(), key=lambda x: -x[1]):
        print(f"  {reason}: {cnt}")
    print("\n各规则保留情况:")
    for rid, stats in sorted(rule_stats.items()):
        aname = RULE_ID_TO_ATTACK_NAME.get(rid, "?")
        print(f"  {rid} ({aname}): {stats['kept']}/{stats['input']}")
    print(f"\n纯JSON版: {out_json_file}")
    print(f"策略+JSON版: {out_cot_file}")
    print(f"报告: {report_file}")


if __name__ == "__main__":
    main()
