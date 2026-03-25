#!/usr/bin/env python3
"""统计 SFT jsonl 的分布，默认 sft_dataset_final.jsonl，可用 --input 指定。"""
import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SFT = PROJECT_ROOT / "data" / "sft_dataset_final.jsonl"
DEFAULT_OUT_TXT = PROJECT_ROOT / "data" / "sft_data_distribution.txt"
DEFAULT_OUT_JSON = PROJECT_ROOT / "data" / "sft_data_distribution.json"


def main():
    parser = argparse.ArgumentParser(description="统计 SFT jsonl 中 attack_name 等分布")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_SFT,
        help="输入 jsonl（默认 data/sft_dataset_final.jsonl）",
    )
    parser.add_argument(
        "--out-txt",
        type=Path,
        default=None,
        help="人类可读报告路径（默认：与输入同目录，文件名 <stem>_distribution.txt）",
    )
    parser.add_argument(
        "--out-json",
        type=Path,
        default=None,
        help="JSON 统计路径（默认：与输入同目录，文件名 <stem>_distribution.json）",
    )
    args = parser.parse_args()

    SFT_PATH = args.input
    if not SFT_PATH.is_absolute():
        SFT_PATH = PROJECT_ROOT / SFT_PATH
    if not SFT_PATH.exists():
        print(f"未找到 SFT 数据: {SFT_PATH}")
        return 1

    stem = SFT_PATH.stem
    OUT_TXT = args.out_txt or (SFT_PATH.parent / f"{stem}_distribution.txt")
    OUT_JSON = args.out_json or (SFT_PATH.parent / f"{stem}_distribution.json")
    if args.out_txt and not OUT_TXT.is_absolute():
        OUT_TXT = PROJECT_ROOT / OUT_TXT
    if args.out_json and not OUT_JSON.is_absolute():
        OUT_JSON = PROJECT_ROOT / OUT_JSON

    total = 0
    attack_name_counter = Counter()
    input_lens = []
    output_lens = []
    has_attack_name = 0

    with open(SFT_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            total += 1
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            inp = d.get("input", "")
            out = d.get("output", "")
            input_lens.append(len(inp))
            output_lens.append(len(out))
            m = re.search(r'"attack_name"\s*:\s*"([^"]+)"', out)
            if m:
                has_attack_name += 1
                attack_name_counter[m.group(1).strip()] += 1
            if total % 10000 == 0 and total > 0:
                print(f"  已处理 {total} 条...", file=sys.stderr)

    # 报告
    lines = []
    lines.append("=" * 60)
    lines.append("SFT 数据分布统计")
    lines.append(f"数据文件: {SFT_PATH}")
    lines.append(f"总样本数: {total}")
    lines.append("")

    lines.append("--- attack_name 分布 ---")
    lines.append(f"含 attack_name 的样本数: {has_attack_name} ({100*has_attack_name/max(1,total):.1f}%)")
    lines.append("")
    for name, count in attack_name_counter.most_common():
        pct = 100 * count / max(1, has_attack_name)
        lines.append(f"  {count:6d} ({pct:5.2f}%)  {name}")
    lines.append(f"  共 {len(attack_name_counter)} 种 attack_name")
    lines.append("")

    if input_lens:
        lines.append("--- input 长度（字符数）---")
        lines.append(f"  条数: {len(input_lens)}")
        lines.append(f"  最小: {min(input_lens)}, 最大: {max(input_lens)}")
        lines.append(f"  平均: {sum(input_lens)/len(input_lens):.0f}")
        lines.append("")
    if output_lens:
        lines.append("--- output 长度（字符数）---")
        lines.append(f"  条数: {len(output_lens)}")
        lines.append(f"  最小: {min(output_lens)}, 最大: {max(output_lens)}")
        lines.append(f"  平均: {sum(output_lens)/len(output_lens):.0f}")
        lines.append("")

    report = "\n".join(lines)
    with open(OUT_TXT, "w", encoding="utf-8") as f:
        f.write(report)
    print(report)
    print(f"报告已写入: {OUT_TXT}")

    out_obj = {
        "sft_file": str(SFT_PATH.resolve()),
        "total_samples": total,
        "samples_with_attack_name": has_attack_name,
        "attack_name_distribution": dict(attack_name_counter.most_common()),
        "input_length": {"min": min(input_lens) if input_lens else 0, "max": max(input_lens) if input_lens else 0, "mean": sum(input_lens)/len(input_lens) if input_lens else 0},
        "output_length": {"min": min(output_lens) if output_lens else 0, "max": max(output_lens) if output_lens else 0, "mean": sum(output_lens)/len(output_lens) if output_lens else 0},
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(out_obj, f, ensure_ascii=False, indent=2)
    print(f"JSON 已写入: {OUT_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
