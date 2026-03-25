#!/usr/bin/env python3
"""将 SFT jsonl 中 output 的 nth_occurrence 转为 target_line 与 target_signal（引擎支持按行号/信号选择时）。"""
import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from ast_transforms_loader import create_engine

# attack_name -> transform_id，与 eval_attack_success / filter_and_convert_sft 一致
SEMANTIC_NAMES = {
    "T03": "t03", "T07": "assign_reorder",
    "T09": "demorgan_and", "T10": "demorgan_or",
    "T12": "predicate_extraction",
    "T19": "dead_code_injection", "T20": "misleading_comment",
    "T30": "constant_identity_transform", "T31": "intermediate_wire_injection",
    "T32": "bitwidth_arithmetic_obfuscation", "T34": "semantic_inversion_rename",
    "T35": "constant_wire_injection",
    "T45": "pseudo_combinational_loop", "T47": "shannon_expansion",
    "T48": "anti_topological_reorder",
}
ATTACK_NAME_TO_TID = {v: k for k, v in SEMANTIC_NAMES.items()}
for tid in list(SEMANTIC_NAMES.keys()):
    low = tid.lower()
    if low not in ATTACK_NAME_TO_TID:
        ATTACK_NAME_TO_TID[low] = tid

# 兼容旧数据：历史上使用过 "comment_decoy" 命名，现在只保留 T20
ATTACK_NAME_TO_TID["comment_decoy"] = "T20"

# 兼容旧数据：历史上 "adversarial_rename" 对应 T16；现在合并到 T34（包含端口名重命名）。
ATTACK_NAME_TO_TID["adversarial_rename"] = "T34"


def extract_rtl_from_input(input_text: str) -> str:
    """从 SFT input 中提取带行号的 Verilog 代码，并去掉行号前缀 'N: ' 还原为纯 RTL。"""
    m = re.search(r"```verilog\s*\n(.*?)```", input_text, re.DOTALL)
    if not m:
        return ""
    numbered = m.group(1).strip()
    lines = []
    for line in numbered.split("\n"):
        # 去掉行号前缀 "1: " 等
        if re.match(r"^\s*\d+\s*:\s*", line):
            line = re.sub(r"^\s*\d+\s*:\s*", "", line)
        lines.append(line)
    return "\n".join(lines)


def process_line(line: str, engine, attack_name_to_tid: dict) -> str:
    """处理单条 SFT 记录：若有 nth_occurrence 则尝试转为 target_line/target_signal。"""
    try:
        rec = json.loads(line)
    except json.JSONDecodeError:
        return line
    inp = rec.get("input") or ""
    out = rec.get("output") or ""
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", out, re.DOTALL)
    if not m:
        return line
    raw = m.group(1).strip()
    if not raw.startswith("{"):
        return line
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return line
    if obj.get("nth_occurrence") is None:
        return line
    # 一律删除 nth_occurrence；能解析出 line/signal 则写入，否则仅删 nth_occurrence
    new_obj = {k: v for k, v in obj.items() if k != "nth_occurrence"}
    name = (obj.get("attack_name") or "").strip().lower().replace("-", "_")
    tid = attack_name_to_tid.get(name)
    if not tid and re.match(r"t\d+", name):
        tid = name.upper()
    if tid:
        try:
            token = max(0, int(obj["nth_occurrence"]) - 1)
        except (TypeError, ValueError):
            token = 0
        rtl = extract_rtl_from_input(inp)
        if rtl:
            line_out, sig_out = engine.get_target_line_signal(rtl, tid, token)
            if line_out is not None:
                new_obj["target_line"] = line_out
            if sig_out:
                new_obj["target_signal"] = sig_out
    new_json = json.dumps(new_obj, ensure_ascii=False, indent=2)
    new_output = re.sub(r"```(?:json)?\s*\n?.*?```", "```json\n" + new_json + "\n```", out, count=1, flags=re.DOTALL)
    rec["output"] = new_output
    return json.dumps(rec, ensure_ascii=False)


def main():
    parser = argparse.ArgumentParser(description="将 SFT 中 nth_occurrence 转为 target_line、target_signal")
    parser.add_argument(
        "files",
        nargs="*",
        default=[
            PROJECT_ROOT / "data" / "sft_dataset_final.jsonl",
            PROJECT_ROOT / "data" / "sft_dataset_balanced_500.jsonl",
            PROJECT_ROOT / "data" / "sft_dataset_balanced.jsonl",
            PROJECT_ROOT / "data" / "sft_dataset_balanced_uniform300.jsonl",
            PROJECT_ROOT / "data" / "sft_dataset_balanced_uniform500.jsonl",
            PROJECT_ROOT / "data" / "sft_dataset_supplemented.jsonl",
        ],
        help="要处理的 jsonl",
    )
    parser.add_argument("--no-backup", action="store_true", help="不保留 .bak")
    parser.add_argument("--dry-run", action="store_true", help="只统计可转换条数")
    args = parser.parse_args()
    engine = create_engine()
    paths = [Path(p) if isinstance(p, Path) else Path(p) for p in args.files]
    for path in paths:
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            print(f"跳过（不存在）: {path}")
            continue
        converted = 0
        for line in open(path, "r", encoding="utf-8"):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                continue
            out = rec.get("output") or ""
            if "nth_occurrence" not in out:
                continue
            new_line = process_line(line, engine, ATTACK_NAME_TO_TID)
            if new_line != line:
                converted += 1
        if args.dry_run:
            print(f"可转换（含 nth_occurrence 且可解析）: {path} 约 {converted} 条")
            continue
        if converted == 0:
            print(f"无需转换: {path}")
            continue
        backup = path.with_suffix(path.suffix + ".bak")
        temp = path.with_suffix(path.suffix + ".tmp")
        written = 0
        with open(path, "r", encoding="utf-8") as f_in, open(temp, "w", encoding="utf-8") as f_out:
            for line in f_in:
                line = line.rstrip("\n")
                if not line.strip():
                    f_out.write(line + "\n")
                    continue
                new_line = process_line(line, engine, ATTACK_NAME_TO_TID)
                if new_line != line:
                    written += 1
                f_out.write(new_line + "\n")
        if not args.no_backup:
            path.rename(backup)
        temp.rename(path)
        print(f"已转换: {path}（{written} 条 nth_occurrence → target_line/target_signal" + (f"，备份 {backup}）" if not args.no_backup else "）"))


if __name__ == "__main__":
    main()
