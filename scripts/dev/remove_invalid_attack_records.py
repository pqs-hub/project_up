#!/usr/bin/env python3
"""从 SFT jsonl 中删除 attack_name 在引擎中无对应规则的记录。"""
import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

from ast_transforms_loader import create_engine

# 与 sft_nth_to_line_signal / eval_attack_success 一致，并补全引擎有但此前未列出的 T41
SEMANTIC_NAMES = {
    # 兼容旧数据：T13 等已从引擎删除，仍需能把旧 attack_name 映射到 tid，再按 valid_tids 删记录。
    "T03": "redundant_logic_injection", "T07": "assign_reorder",
    "T09": "demorgan_and", "T10": "demorgan_or",
    "T12": "predicate_extraction",
    "T13": "ternary_explicit_compare",
    "T19": "dead_code_injection", "T20": "misleading_comment",
    "T30": "constant_identity_transform", "T31": "intermediate_wire_injection",
    "T32": "bitwidth_arithmetic_obfuscation", "T34": "semantic_inversion_rename",
    "T35": "constant_wire_injection",
    "T41": "case_branch_reorder",
    "T45": "pseudo_combinational_loop", "T47": "shannon_expansion",
    "T48": "anti_topological_reorder",
}
ATTACK_NAME_TO_TID = {v: k for k, v in SEMANTIC_NAMES.items()}
for tid in list(SEMANTIC_NAMES.keys()):
    low = tid.lower()
    if low not in ATTACK_NAME_TO_TID:
        ATTACK_NAME_TO_TID[low] = tid

# 兼容旧数据：历史上 "adversarial_rename" 对应 T16；现在合并到 T34
ATTACK_NAME_TO_TID["adversarial_rename"] = "T34"

# 兼容旧数据：历史上使用过 "comment_decoy" 命名，现在只保留 T20
ATTACK_NAME_TO_TID["comment_decoy"] = "T20"


def get_valid_tids():
    """引擎中已注册的规则 ID 集合。"""
    engine = create_engine()
    return set(engine.registry.keys())


def extract_attack_name_from_output(output: str) -> Optional[str]:
    """从 output 的 ```json ... ``` 中解析 attack_name，未找到或解析失败返回 None。"""
    if not output:
        return None
    m = re.search(r"```(?:json)?\s*\n?(.*?)```", output, re.DOTALL)
    if not m:
        return None
    raw = m.group(1).strip()
    if not raw.startswith("{"):
        return None
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return None
    name = obj.get("attack_name")
    if name is None or not isinstance(name, str):
        return None
    return name.strip().lower().replace("-", "_")


def attack_name_to_tid(name: str) -> Optional[str]:
    """将 attack_name 解析为引擎中的 transform id，无法解析返回 None。"""
    tid = ATTACK_NAME_TO_TID.get(name)
    if not tid and re.match(r"t\d+", name):
        tid = name.upper()
    return tid


def main():
    parser = argparse.ArgumentParser(description="删除 SFT 中规则不存在的记录")
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
    parser.add_argument("--dry-run", action="store_true", help="只统计将删除的条数，不写回")
    args = parser.parse_args()

    valid_tids = get_valid_tids()
    paths = [Path(p) if isinstance(p, Path) else Path(p) for p in args.files]

    for path in paths:
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            print(f"跳过（不存在）: {path}")
            continue
        lines = list(open(path, "r", encoding="utf-8"))
        kept = []
        removed = 0
        removed_names = {}
        for line in lines:
            line = line.rstrip("\n")
            if not line:
                kept.append(line)
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError:
                kept.append(line)
                continue
            out = rec.get("output") or ""
            attack_name = extract_attack_name_from_output(out)
            if attack_name is None:
                kept.append(line)
                continue
            tid = attack_name_to_tid(attack_name)
            if tid and tid in valid_tids:
                kept.append(line)
                continue
            removed += 1
            removed_names[attack_name] = removed_names.get(attack_name, 0) + 1
        if args.dry_run:
            print(f"[dry-run] {path.name}: 将删除 {removed} 条", end="")
            if removed_names:
                print(" ", sorted(removed_names.items(), key=lambda x: -x[1]))
            else:
                print()
            continue
        if removed == 0:
            print(f"未删除: {path.name}")
            continue
        if not args.no_backup:
            bak = path.with_suffix(path.suffix + ".bak")
            with open(bak, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + ("\n" if lines else ""))
            print(f"已备份: {bak}")
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + ("\n" if kept else ""))
        print(f"已删除 {removed} 条（规则不存在）: {path.name} ", sorted(removed_names.items(), key=lambda x: -x[1]))


if __name__ == "__main__":
    main()
