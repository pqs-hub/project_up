#!/usr/bin/env python3
"""将 SFT jsonl 中每条 output 的 JSON 块统一为顶层 key：attack_name（必填）、target_line、target_signal、parameters（可选）。"""
import argparse
import json
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

ALLOWED_KEYS = {"attack_name", "target_line", "target_signal", "parameters"}


def normalize_decision(obj: dict) -> dict:
    """只保留 attack_name、target_line、target_signal、parameters，其余丢弃。"""
    out = {}
    if "attack_name" in obj and obj["attack_name"]:
        out["attack_name"] = obj["attack_name"]
    if "target_line" in obj and obj["target_line"] is not None:
        try:
            out["target_line"] = int(obj["target_line"])
        except (TypeError, ValueError):
            pass
    if "target_signal" in obj and obj["target_signal"] and isinstance(obj["target_signal"], str):
        out["target_signal"] = str(obj["target_signal"]).strip()
    if "parameters" in obj and isinstance(obj["parameters"], dict) and obj["parameters"]:
        out["parameters"] = obj["parameters"]
    return out


def normalize_output_text(output: str) -> str:
    """将 output 中 ```json ... ``` 内的 JSON 归一化为 attack_name / target_line / target_signal / parameters，其余不变。"""
    def replace_block(m):
        raw = m.group(1).strip()
        if not raw.startswith("{"):
            return m.group(0)
        try:
            obj = json.loads(raw)
        except json.JSONDecodeError:
            return m.group(0)
        normalized = normalize_decision(obj)
        if not normalized.get("attack_name"):
            return m.group(0)
        new_json = json.dumps(normalized, ensure_ascii=False, indent=2)
        return "```json\n" + new_json + "\n```"
    return re.sub(r"```(?:json)?\s*\n?(.*?)```", replace_block, output, flags=re.DOTALL)


def main():
    parser = argparse.ArgumentParser(description="统一 SFT output 中 JSON 为 attack_name / target_line / target_signal / parameters")
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
        help="要处理的 jsonl 文件",
    )
    parser.add_argument("--no-backup", action="store_true", help="不保留 .bak 备份")
    parser.add_argument("--dry-run", action="store_true", help="只统计会修改的条数，不写入")
    args = parser.parse_args()

    paths = [Path(p) if isinstance(p, Path) else Path(p) for p in args.files]
    for path in paths:
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        if not path.exists():
            print(f"跳过（不存在）: {path}")
            continue

        changed = 0
        for line in open(path, "r", encoding="utf-8"):
            line = line.rstrip("\n")
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            out = obj.get("output") or ""
            new_out = normalize_output_text(out)
            if new_out != out:
                changed += 1

        if args.dry_run:
            print(f"将修改: {path} 约 {changed} 条")
            continue

        if changed == 0:
            print(f"无需修改: {path}")
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
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    f_out.write(line + "\n")
                    continue
                out = rec.get("output") or ""
                new_out = normalize_output_text(out)
                if new_out != out:
                    rec["output"] = new_out
                    written += 1
                f_out.write(json.dumps(rec, ensure_ascii=False) + "\n")

        if not args.no_backup:
            path.rename(backup)
        temp.rename(path)
        print(f"已统一: {path}（{written} 条 output 已归一化" + (f"，原文件备份为 {backup}）" if not args.no_backup else "）"))


if __name__ == "__main__":
    main()
