#!/usr/bin/env python3
"""
两步流程：
1. 筛选：adversarial_dataset.jsonl + adversarial_dataset.metadata.jsonl
   → 按原始样本(input)分组、同规则保留 confidence_delta 最大、每样本最多5条、规则均衡(单规则≤40%)
   → filtered_metadata.jsonl + filtered_adversarial_dataset.jsonl（行对齐）
2. 格式转换：filtered_* → 语义化名称 + 行号 + 短 CoT
   → sft_dataset_final.jsonl
"""
import json
import re
import hashlib
from collections import defaultdict
from pathlib import Path

# ============================================================
# 语义化映射
# ============================================================
SEMANTIC_NAMES = {
    "T03": "t03",
    "T04": "comment_decoy",
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
    "T35": "constant_wire_injection",
    "T41": "case_reorder",
    "T45": "pseudo_combinational_loop",
    "T47": "shannon_expansion",
    "T48": "anti_topological_reorder",
}

STRATEGY_DESC = {
    "T03": "Inject redundant logic using identities such as & 1'b1 to confuse the verification model.",
    "T04": "Insert misleading, function-irrelevant comments at key locations to bias the model's judgment.",
    "T07": "Shuffle the order of independent assign statements to disrupt dataflow reading.",
    "T09": "Use DeMorgan to rewrite AND into the negated OR form.",
    "T10": "Use DeMorgan to rewrite OR into the negated AND form.",
    "T12": "Extract the ternary condition into an intermediate wire to increase data-path layering.",
    "T19": "Inject an unreachable dead-code always block to disturb the model's control-flow reasoning.",
    "T20": "Insert a functionality description that contradicts the real behavior to mislead the model.",
    "T30": "Replace 1'b0/1'b1 with equivalent expressions to confuse constant recognition.",
    "T31": "Split a simple assignment into intermediate wires to increase indirection.",
    "T32": "Rewrite bit-width declarations into equivalent arithmetic expressions to trigger syntax anomaly checks.",
    "T34": "Rename internal signals with semantically confusing identifiers to mislead functionality.",
    "T35": "Route constants through wires to increase indirection.",
    "T41": "Rotate or reorder case branches to disturb control-flow reading.",
    "T45": "Inject a pseudo combinational loop based on contradictory terms like X & ~X to confuse combinational analysis.",
    "T47": "Apply Shannon expansion to comparators/adders to increase structural complexity.",
    "T48": "Reverse the order of concurrent assignments to disturb topology reading.",
}

INSTRUCTION = (
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


def _input_key(sample: dict) -> str:
    """用 input 内容的哈希作为同一原始样本的 key（支持 sample_id 全为 unknown）。"""
    return hashlib.sha256(sample["input"].encode("utf-8")).hexdigest()


def filter_samples(
    dataset_path: str,
    metadata_path: str,
    output_metadata_path: str,
    output_dataset_path: str,
) -> list:
    """
    筛选策略：
    1. 按原始样本（input 哈希）分组，与 metadata 行对齐
    2. 每组内只保留 testbench_passed=True
    3. 每组内按规则去重，同规则保留 confidence_delta 最大的
    4. 每个原始样本最多保留 5 条（按 confidence_delta 降序）
    5. 全局规则均衡：单规则不超过总数 40%，超出则按 delta 降序截断
    """
    with open(dataset_path, "r", encoding="utf-8") as f_d, open(
        metadata_path, "r", encoding="utf-8"
    ) as f_m:
        dataset = [json.loads(line) for line in f_d]
        metadata = [json.loads(line) for line in f_m]

    if len(dataset) != len(metadata):
        raise ValueError(
            f"dataset 与 metadata 行数不一致: {len(dataset)} vs {len(metadata)}"
        )

    # 按 input 分组（每行为 (sample, meta)）
    grouped = defaultdict(list)
    for s, m in zip(dataset, metadata):
        grouped[_input_key(s)].append((s, m))

    filtered_pairs = []
    rule_global_count = defaultdict(int)

    for _key, pairs in grouped.items():
        # 1. 只保留 testbench_passed=True
        attacks = [(s, m) for s, m in pairs if m.get("testbench_passed", False)]
        if not attacks:
            continue

        # 2. 按规则分桶，每个规则只保留 confidence_delta 最大的
        best_per_rule = {}
        for s, m in attacks:
            rule = m["transform_id"]
            if rule not in best_per_rule:
                best_per_rule[rule] = (s, m)
            elif m["confidence_delta"] > best_per_rule[rule][1]["confidence_delta"]:
                best_per_rule[rule] = (s, m)

        # 3. 按 confidence_delta 降序
        candidates = sorted(
            best_per_rule.values(),
            key=lambda x: x[1]["confidence_delta"],
            reverse=True,
        )

        # 4. 每个原始样本最多保留 5 条
        selected = candidates[:5]
        filtered_pairs.extend(selected)
        for _s, m in selected:
            rule_global_count[m["transform_id"]] += 1

    # 5. 全局规则均衡：单规则不超过 40%
    total = len(filtered_pairs)
    max_per_rule = max(1, int(total * 0.4))

    rule_count = defaultdict(int)
    final_pairs = []
    for item in sorted(
        filtered_pairs, key=lambda x: x[1]["confidence_delta"], reverse=True
    ):
        rule = item[1]["transform_id"]
        if rule_count[rule] < max_per_rule:
            final_pairs.append(item)
            rule_count[rule] += 1

    # 输出统计
    print(f"原始样本行数: {len(dataset)}")
    print(f"去重前组数: {len(grouped)}")
    print(f"筛选后样本数: {len(final_pairs)}")
    print("\n规则分布:")
    for rule, count in sorted(rule_count.items(), key=lambda x: -x[1]):
        pct = count / len(final_pairs) * 100 if final_pairs else 0
        print(f"  {rule}: {count} ({pct:.1f}%)")

    # 保存：metadata 与 dataset 行对齐
    out_meta = Path(output_metadata_path)
    out_ds = Path(output_dataset_path)
    out_meta.parent.mkdir(parents=True, exist_ok=True)
    out_ds.parent.mkdir(parents=True, exist_ok=True)

    with open(out_meta, "w", encoding="utf-8") as f_m, open(
        out_ds, "w", encoding="utf-8"
    ) as f_d:
        for s, m in final_pairs:
            f_m.write(json.dumps(m, ensure_ascii=False) + "\n")
            f_d.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"\n已保存: {out_meta}, {out_ds}")
    return final_pairs


def add_line_numbers(rtl: str) -> str:
    """添加行号"""
    lines = rtl.split("\n")
    return "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines))


def get_line_number(rtl: str, target_token: int, transform_id: str) -> int:
    """根据 target_token 推算行号（启发式）"""
    lines = rtl.split("\n")

    if transform_id == "T32":
        count = 0
        for i, line in enumerate(lines):
            if re.search(r"\[\d+:\d+\]", line):
                if count == target_token:
                    return i + 1
                count += 1

    elif transform_id in ("T04", "T20"):
        count = 0
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith("//"):
                if count == target_token:
                    return i + 1
                count += 1

    elif transform_id == "T31":
        count = 0
        for i, line in enumerate(lines):
            if "assign" in line:
                if count == target_token:
                    return i + 1
                count += 1

    elif transform_id == "T47":
        count = 0
        for i, line in enumerate(lines):
            if "assign" in line:
                if count == target_token:
                    return i + 1
                count += 1

    elif transform_id == "T19":
        # T19 candidate is the insertion point right before 'endmodule' keyword.
        # In most RTLs this corresponds to the first 'endmodule' occurrence (1-based line).
        count = 0
        for i, line in enumerate(lines):
            if re.search(r"\bendmodule\b", line):
                if count == target_token:
                    return i + 1
                count += 1

    return 1


def extract_target_signal(
    rtl: str, target_token: int, transform_id: str
) -> str:
    """从 RTL 中提取目标信号名"""
    lines = rtl.split("\n")

    if transform_id == "T32":
        count = 0
        for line in lines:
            if re.search(r"\[\d+:\d+\]", line):
                if count == target_token:
                    m = re.search(r"\[\d+:\d+\]\s+(\w+)", line)
                    if m:
                        return m.group(1)
                count += 1

    elif transform_id == "T31":
        count = 0
        for line in lines:
            if "assign" in line:
                if count == target_token:
                    m = re.search(r"assign\s+(\w+)", line)
                    if m:
                        return m.group(1)
                count += 1

    elif transform_id == "T47":
        count = 0
        for line in lines:
            if "assign" in line:
                if count == target_token:
                    m = re.search(r"assign\s+(\w+)", line)
                    if m:
                        return m.group(1)
                count += 1

    return ""


def _extract_spec_and_rtl(input_text: str) -> tuple:
    """从 dataset 的 input 中提取 spec 和 original_rtl"""
    # 支持 **功能规范**： 与 **原始代码**：（中英文冒号）
    spec_match = re.search(
        r"\*\*功能规范\*\*[：:]\s*\n(.*?)\n\n\*\*原始代码\*\*",
        input_text,
        re.DOTALL,
    )
    spec = spec_match.group(1).strip() if spec_match else ""

    rtl_match = re.search(r"```verilog\n(.*?)```", input_text, re.DOTALL)
    original_rtl = rtl_match.group(1).strip() if rtl_match else ""

    return spec, original_rtl


def build_sft_sample(training_sample: dict, metadata: dict) -> dict:
    """将原始格式转换为推荐的 SFT 格式（语义化名称 + 行号 + 短 CoT）"""
    input_text = training_sample["input"]
    spec, original_rtl = _extract_spec_and_rtl(input_text)

    transform_id = metadata["transform_id"]
    target_token = metadata.get("target_token")
    parameters = metadata.get("parameters") or {}

    attack_name = SEMANTIC_NAMES.get(transform_id, transform_id.lower())
    strategy = STRATEGY_DESC.get(transform_id, "Use a structure-preserving transformation to mislead the verification model.")

    # Ground the strategy in code-visible signals/targets when possible.
    # For T19, the only meaningful "target" is typically reflected inside custom_dead_stmts.
    if transform_id == "T19" and parameters:
        cds = parameters.get("custom_dead_stmts") or ""
        m = re.search(r"\b([A-Za-z_]\w*)\s*(?:<=|=)", cds)
        if m:
            sig = m.group(1)
            strategy = (
                "Inject an unreachable dead-code always block (wrapped in if(1'b0)) "
                f"that assigns to signal '{sig}' to disturb the model's control-flow and dependency reasoning."
            )

    # 优先用评估阶段落盘的 target_line / target_signal（与引擎 get_target_line_signal 一致）；
    # 否则再用 target_token 走启发式推算（与旧数据兼容）。
    saved_line = metadata.get("target_line")
    saved_signal = metadata.get("target_signal")

    target_line = None
    target_signal = ""

    if saved_line is not None:
        try:
            target_line = int(saved_line)
        except (TypeError, ValueError):
            target_line = None
    if target_line is None and target_token is not None:
        target_line = get_line_number(original_rtl, target_token, transform_id)

    if isinstance(saved_signal, str) and saved_signal.strip():
        target_signal = saved_signal.strip()
    elif target_token is not None:
        target_signal = extract_target_signal(original_rtl, target_token, transform_id)

    # 统一顶层 key：attack_name（必填）；定位用 target_line、target_signal（不再输出 nth_occurrence）
    decision = {"attack_name": attack_name}
    if target_line is not None:
        decision["target_line"] = target_line
    if target_signal:
        decision["target_signal"] = target_signal
    if parameters:
        decision["parameters"] = parameters

    decision_str = json.dumps(decision, ensure_ascii=False, indent=2)
    numbered_rtl = add_line_numbers(original_rtl)

    return {
        "instruction": INSTRUCTION,
        "input": (
            f"### 功能规范\n{spec}\n\n"
            f"### 原始代码\n```verilog\n{numbered_rtl}\n```"
        ),
        "output": f"Strategy: {strategy}\n\n```json\n{decision_str}\n```",
        "history": [],
    }


def convert_dataset(
    filtered_dataset_path: str,
    filtered_metadata_path: str,
    output_path: str,
) -> list:
    """批量转换：filtered 的 dataset + metadata（行对齐）→ SFT 最终格式"""
    with open(filtered_dataset_path, "r", encoding="utf-8") as f_d, open(
        filtered_metadata_path, "r", encoding="utf-8"
    ) as f_m:
        samples = [json.loads(line) for line in f_d]
        metas = [json.loads(line) for line in f_m]

    if len(samples) != len(metas):
        raise ValueError(
            f"filtered dataset 与 metadata 行数不一致: {len(samples)} vs {len(metas)}"
        )

    converted = [
        build_sft_sample(s, m) for s, m in zip(samples, metas)
    ]

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        for item in converted:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    print(f"成功转换: {len(converted)} 条")
    print(f"已保存至: {output_path}")
    return converted


# ============================================================
# 运行
# ============================================================
if __name__ == "__main__":
    data_dir = Path(__file__).resolve().parent

    # Step 1: 筛选
    filter_samples(
        dataset_path=str(data_dir / "adversarial_dataset.jsonl"),
        metadata_path=str(data_dir / "adversarial_dataset.metadata.jsonl"),
        output_metadata_path=str(data_dir / "filtered_metadata.jsonl"),
        output_dataset_path=str(data_dir / "filtered_adversarial_dataset.jsonl"),
    )

    # Step 2: 格式转换
    converted = convert_dataset(
        filtered_dataset_path=str(data_dir / "filtered_adversarial_dataset.jsonl"),
        filtered_metadata_path=str(data_dir / "filtered_metadata.jsonl"),
        output_path=str(data_dir / "sft_dataset_final.jsonl"),
    )

    if converted:
        print("\n=== 样本示例 ===")
        print(json.dumps(converted[0], indent=2, ensure_ascii=False))
