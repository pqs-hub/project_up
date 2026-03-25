#!/usr/bin/env python3
"""批量将 SFT jsonl 中每条样本的 instruction 替换为写明 JSON 格式的新 instruction。"""
import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(PROJECT_ROOT))

# 与 data/filter_and_convert_sft.py 中 INSTRUCTION 一致
NEW_INSTRUCTION = (
    "You are a Verilog obfuscation expert. Given the functional spec and original code, "
    "choose one transformation rule that best misleads the verification model. "
    "Optionally give a short strategy, then output a JSON block. "
    "Use only these top-level keys (do not use the rule name as top-level key):\n"
    "```json\n"
    "{\n"
    "  \"attack_name\": \"rule name in English (required)\",\n"
    "  \"target_line\": 10,\n"
    "  \"target_signal\": \"signal_name\",\n"
    "  \"parameters\": {}\n"
    "}\n"
    "```\n"
    "attack_name is required; target_line (1-based), target_signal, and parameters are optional. "
    "target_line must match the line number in the original code block (e.g. 1: means line 1). "
    "Omit keys you do not need; do not use null or empty string. "
    "Your reply must end with exactly one ```json ... ``` block; do not add any text after it."
)


def main():
    parser = argparse.ArgumentParser(description="批量替换 SFT jsonl 中的 instruction 为新格式")
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
        help="要处理的 jsonl 文件（默认 data 下所有 sft_dataset*.jsonl）",
    )
    parser.add_argument("--no-backup", action="store_true", help="不保留 .bak 备份")
    parser.add_argument("--dry-run", action="store_true", help="只打印将处理的文件与条数，不写入")
    args = parser.parse_args()

    paths = [Path(p) for p in args.files]
    for path in paths:
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            print(f"跳过（不存在）: {path}")
            continue
        if args.dry_run:
            n = sum(1 for _ in open(path, "r", encoding="utf-8") if _.strip())
            print(f"将处理: {path} 共 {n} 条")
            continue
        backup = path.with_suffix(path.suffix + ".bak")
        temp = path.with_suffix(path.suffix + ".tmp")
        updated = 0
        with open(path, "r", encoding="utf-8") as f_in, open(temp, "w", encoding="utf-8") as f_out:
            for line in f_in:
                line = line.rstrip("\n")
                if not line.strip():
                    f_out.write(line + "\n")
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    f_out.write(line + "\n")
                    continue
                if "instruction" in obj:
                    obj["instruction"] = NEW_INSTRUCTION
                    updated += 1
                f_out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        if updated > 0:
            if not args.no_backup:
                path.rename(backup)
            temp.rename(path)
            print(f"已更新: {path}（{updated} 条 instruction 已替换" + (f"，原文件备份为 {backup}）" if not args.no_backup else "）"))
        else:
            temp.unlink()
            print(f"无需更新: {path}（未发现 instruction 字段或已为新格式）")


if __name__ == "__main__":
    main()
