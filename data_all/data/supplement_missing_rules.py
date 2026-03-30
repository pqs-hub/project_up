#!/usr/bin/env python3
"""
为 SFT 数据集中缺失或少样本的变换规则「合成」样本并追加到 sft_dataset_final.jsonl。

注意：本脚本不做真实变换、不跑 testbench、不调用判题模型，因此追加的样本不保证「攻击成功」，
仅用于在数据量上拉高少样本规则的占比。若需要仅追加「攻击成功」的样本，请使用项目根目录下的
generate_missing_rules_verified.py（需 data/qualified_samples.json，会做变换+testbench+判题验证）。

1) 缺失规则：T03, T07, T18, T19, T37, T38, T41, T45, T47, T48（已移除 T02/T05/T08/T36/T42/T43/T44）。
2) 少样本规则：T09,T10,T11,T12,T13,T19,T35,T39 等，每规则可多补若干条。
从现有 SFT 中抽取 (spec, rtl) 池，对每条规则采样若干条并生成标准 SFT 格式后追加。
"""
import argparse
import json
import random
import re
from pathlib import Path

# 同目录下 import
import sys
sys.path.insert(0, str(Path(__file__).resolve().parent))
from filter_and_convert_sft import (
    build_sft_sample,
    STRATEGY_DESC,
    SEMANTIC_NAMES,
    INSTRUCTION,
)

# 缺失规则（当前 SFT 中未出现或极少的）
MISSING_RULES = [
    "T03", "T07", "T18", "T19", "T37", "T38",
    "T41", "T45", "T47", "T48",
]

# 少样本规则（已移除 T05/T08/T36）
UNDERREPRESENTED_RULES = [
    "T09", "T10", "T11", "T12", "T13",
    "T19", "T35", "T39",
]

# 各规则默认参数（与 ast_transforms 注册表一致）
DEFAULT_PARAMS = {
    "T38": {"temp_prefix": "temp"},
    "T47": {"width": 4},
}

# 不需要 target_token 的规则（与 AttackConfigGenerator 一致；T19 例外，使用 0..6 选择模式）
NO_TARGET_RULES = {
    "T01", "T03", "T07", "T16", "T18",
    "T34", "T37", "T38", "T41", "T45", "T48",
}


def _strip_line_numbers(rtl_block: str) -> str:
    """去掉带行号的代码块中的 'N: ' 前缀，得到原始 RTL。"""
    lines = rtl_block.split("\n")
    out = []
    for line in lines:
        out.append(re.sub(r"^\d+:\s*", "", line))
    return "\n".join(out)


def _extract_spec_and_rtl_from_sft_input(input_text: str) -> tuple:
    """从 SFT 的 input 字段提取 spec 和原始 RTL（去掉行号）。"""
    spec_match = re.search(
        r"### 功能规范\n(.*?)\n\n### 原始代码",
        input_text,
        re.DOTALL,
    )
    spec = spec_match.group(1).strip() if spec_match else ""

    rtl_match = re.search(r"```verilog\n(.*?)```", input_text, re.DOTALL)
    rtl_block = rtl_match.group(1).strip() if rtl_match else ""
    original_rtl = _strip_line_numbers(rtl_block)

    return spec, original_rtl


def _count_assigns(rtl: str) -> int:
    """统计 RTL 中 assign 语句行数（近似）。"""
    return sum(1 for line in rtl.split("\n") if "assign" in line)


def build_pool(sft_path: str) -> list:
    """从 sft_dataset_final.jsonl 构建 (spec, original_rtl) 池并去重。"""
    pool = []
    seen = set()
    with open(sft_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            input_text = obj.get("input", "")
            spec, rtl = _extract_spec_and_rtl_from_sft_input(input_text)
            if not spec or not rtl or len(rtl) < 50:
                continue
            key = (spec[:200], rtl[:500])  # 简单去重
            if key in seen:
                continue
            seen.add(key)
            pool.append((spec, rtl))
    return pool


def _generate_for_rules(rules: list, pool: list, pool_with_assign: list, per_rule: int, default_params: dict, seed: int) -> list:
    """对给定规则列表从池中抽样并生成 SFT 样本。"""
    random.seed(seed)
    out = []
    for rule in rules:
        if rule not in STRATEGY_DESC:
            print(f"  跳过 {rule}：未在 STRATEGY_DESC 中")
            continue
        use_pool = pool_with_assign if rule == "T47" else pool
        if not use_pool:
            print(f"  跳过 {rule}：无可用池")
            continue
        n = min(per_rule, len(use_pool))
        sampled = random.sample(use_pool, n)
        for spec, rtl in sampled:
            if rule == "T19":
                # T19 使用 target_token 选择不同死代码模式（0..6）
                target_token = random.randint(0, 6)
            elif rule in NO_TARGET_RULES:
                target_token = None
            elif rule == "T47":
                target_token = 0
            else:
                target_token = None
            parameters = default_params.get(rule, {})
            metadata = {
                "transform_id": rule,
                "target_token": target_token,
                "parameters": parameters,
            }
            training_sample = {
                "input": (
                    f"**功能规范**：\n{spec}\n\n"
                    f"**原始代码**：\n```verilog\n{rtl}\n```"
                ),
            }
            sft_sample = build_sft_sample(training_sample, metadata)
            out.append(sft_sample)
        print(f"  {rule}: +{n}")
    return out


def main():
    parser = argparse.ArgumentParser(description="为缺失/少样本规则合成 SFT 样本并追加")
    parser.add_argument("--per-rule-missing", type=int, default=120, help="每条缺失规则(MISSING_RULES)生成样本数")
    parser.add_argument("--per-rule-underrepresented", type=int, default=300, help="每条少样本规则(UNDERREPRESENTED_RULES)生成样本数")
    parser.add_argument("--skip-missing", action="store_true", help="不处理 MISSING_RULES，只补少样本规则")
    parser.add_argument("--skip-underrepresented", action="store_true", help="不处理 UNDERREPRESENTED_RULES，只补缺失规则")
    parser.add_argument("--output", type=str, default=None, help="输出 jsonl 路径（默认追加到 sft_dataset_final.jsonl）")
    parser.add_argument("--seed", type=int, default=42, help="随机种子")
    args = parser.parse_args()

    data_dir = Path(__file__).resolve().parent
    sft_path = data_dir / "sft_dataset_final.jsonl"
    out_path = Path(args.output) if args.output else sft_path

    if not sft_path.exists():
        print(f"未找到 {sft_path}，请先运行 filter_and_convert_sft.py")
        return 1

    print("【说明】当前为「合成」模式：未做变换/testbench/判题验证，追加样本不保证攻击成功。")
    print("        若需仅追加攻击成功样本，请使用: python generate_missing_rules_verified.py")
    print("")
    print("正在从现有 SFT 构建 (spec, rtl) 池...")
    pool = build_pool(str(sft_path))
    print(f"  池大小: {len(pool)}")

    pool_with_assign = [(s, r) for s, r in pool if _count_assigns(r) >= 1]
    print(f"  含 assign 的样本数（供 T47）: {len(pool_with_assign)}")

    synthetic = []
    if not args.skip_missing:
        print(f"\n--- 缺失规则（每规则 {args.per_rule_missing} 条）---")
        synthetic.extend(_generate_for_rules(
            MISSING_RULES, pool, pool_with_assign,
            args.per_rule_missing, DEFAULT_PARAMS, args.seed,
        ))
    if not args.skip_underrepresented:
        print(f"\n--- 少样本规则（每规则 {args.per_rule_underrepresented} 条）---")
        synthetic.extend(_generate_for_rules(
            UNDERREPRESENTED_RULES, pool, pool_with_assign,
            args.per_rule_underrepresented, DEFAULT_PARAMS, args.seed + 1,
        ))

    if not synthetic:
        print("未生成任何合成样本，退出")
        return 1

    # 读取现有 SFT，追加合成样本后写出
    existing = []
    with open(sft_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                existing.append(line)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for line in existing:
            f.write(line + "\n")
        for item in synthetic:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"\n已追加 {len(synthetic)} 条合成样本 -> {out_path}")
    print(f"当前总条数: {len(existing) + len(synthetic)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
