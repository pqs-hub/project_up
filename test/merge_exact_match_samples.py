#!/usr/bin/env python3
"""合并所有完全匹配的样本到rule15_verified_dataset中"""

import json
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent))

from core.transforms import create_engine

# 直接复制需要的函数
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

def extract_t20_legacy_literals(original_code: str, old_code: str):
    """从 old_code 与 original_code 的行级差异中提取注释插入块（按字面重放）。"""
    import difflib
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

def convert_external_sample_to_verified_format(row: dict, converted_params: dict, target_token: int) -> dict:
    """将外部数据集样本转换为verified_dataset格式"""
    dataset_row = row.get("dataset_row", {})
    adv_result_row = row.get("adv_result_row", {})
    
    # 提取原始代码和功能规范
    original_code = dataset_row.get("canonical_solution", "")
    prompt = dataset_row.get("prompt", "")
    
    # 构建input字段（功能规范+原始代码）
    if prompt:
        input_text = f"### 功能规范\n{prompt}\n\n### 原始代码\n```verilog\n"
        lines = original_code.split('\n')
        for i, line in enumerate(lines, 1):
            input_text += f"{i}: {line}\n"
        input_text += "```"
    else:
        input_text = f"### 原始代码\n```verilog\n"
        lines = original_code.split('\n')
        for i, line in enumerate(lines, 1):
            input_text += f"{i}: {line}\n"
        input_text += "```"
    
    # 获取变换后的代码
    transformed_code = adv_result_row.get("final", "")
    
    # 构建output字段（策略描述+JSON参数）
    rule_id = row.get("rule_id", "")
    strategy_map = {
        "T03": "策略：添加冗余的 tapped 信号以误导验证模型。",
        "T07": "策略：交换可交换对中的信号位置，保持功能等价。",
        "T07b": "策略：交换可交换对中的信号位置，保持功能等价。",
        "T09": "策略：使用德摩根定律转换AND表达式为OR表达式。",
        "T10": "策略：使用德摩根定律转换OR表达式为AND表达式。",
        "T12": "策略：注入中间信号以增加代码复杂性。",
        "T19": "策略：添加冗余逻辑以误导验证模型。",
        "T20": "策略：插入误导性注释以干扰代码理解。",
        "T30": "策略：用等价的算术表达式替换位常量。",
        "T31": "策略：注入中间信号以增加代码复杂性。",
        "T32": "策略：将位宽声明替换为等价的算术表达式。",
        "T34": "策略：重命名内部信号以误导验证模型。",
        "T41": "策略：添加冗余的 tapped 信号以误导验证模型。",
        "T45": "策略：用等价的算术表达式替换位常量。",
        "T47": "策略：使用Shannon展开进行数据流分解。",
        "T48": "策略：逆向拓扑重排赋值语句顺序。"
    }
    
    strategy = strategy_map.get(rule_id, f"策略：应用{rule_id}变换规则。")
    
    # 构建参数JSON
    params_json = {
        "attack_name": rule_id.lower(),
    }
    
    # 添加target_token
    if target_token is not None:
        params_json["target_token"] = target_token
    
    # 添加其他参数（排除内部参数）
    exclude_keys = {"target_token", "legacy_comment_literal", "legacy_prefer_module_prefix", 
                   "legacy_inline_decl", "allow_port_rename", "full_text"}
    
    clean_params = {k: v for k, v in converted_params.items() 
                   if k not in exclude_keys and v is not None}
    
    if clean_params:
        params_json["parameters"] = clean_params
    
    output_text = f"{strategy}\n\n```json\n{json.dumps(params_json, ensure_ascii=False)}\n```"
    
    # 构建最终记录
    verified_record = {
        "record_type": "structured",
        "source_file": f"external_dataset/{rule_id}",
        "source_loc": f"line:{row.get('rep', 0)}",
        "rule_id": rule_id,
        "attack_success": None,  # 需要后续评估
        "target_token": target_token,
        "target_line": converted_params.get("target_line"),
        "target_signal": converted_params.get("target_signal"),
        "instruction": "You are a Verilog obfuscation expert. Given the functional spec and original code, choose one transformation rule that best misleads the verification model. Optionally give a short strategy, then output a JSON block. Use only these top-level keys (do not use the rule name as top-level key):\n```json\n{\n  \"attack_name\": \"rule name in English (required)\",\n  \"target_line\": 10,\n  \"target_signal\": \"signal_name\",\n  \"parameters\": {}\n}\n```\nattack_name is required; target_line (1-based), target_signal, and parameters are optional. target_line must match the line number in the original code block (e.g. 1: means line 1). Omit keys you do not need; do not use null or empty string. Your reply must end with exactly one ```json ... ``` block; do not add any text after it.",
        "input": input_text,
        "output": output_text,
        "raw_excerpt": None,
        "transformed_rtl": transformed_code
    }
    
    return verified_record

def main():
    external_dataset = "/mnt/public/pqs/LLM_attack1/LLM_attack/data/all_rules_asr_success_fullinfo_dedup_trp.jsonl"
    verified_output = "/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/attack_success_samples.jsonl"
    conversion_log = "/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/conversion_log.txt"
    
    engine = create_engine()
    supported_rules = set(engine.registry.keys())
    
    # 读取现有的verified样本
    existing_samples = []
    if Path(verified_output).exists():
        with open(verified_output, "r", encoding="utf-8") as f:
            for line in f:
                if line.strip():
                    existing_samples.append(json.loads(line))
        print(f"Loaded {len(existing_samples)} existing verified samples")
    
    # 处理外部数据集
    converted_samples = []
    conversion_stats = {}
    
    with open(external_dataset, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
                
            try:
                row = json.loads(line)
                rule_id = row.get("rule_id", "")
                
                # 只处理支持的规则
                if rule_id not in supported_rules:
                    continue
                
                # 提取代码字段
                original, old_transformed, old_params = extract_code_fields(row)
                
                if not original or not old_transformed:
                    continue
                
                # 尝试重放
                replay_result = try_replay_exact(engine, original, old_transformed, rule_id, old_params, max_scan=128)
                
                if replay_result["matched"] == "exact":
                    # 转换为verified格式
                    verified_record = convert_external_sample_to_verified_format(
                        row, 
                        replay_result["converted_params"], 
                        replay_result["target_token"]
                    )
                    converted_samples.append(verified_record)
                    
                    # 统计
                    if rule_id not in conversion_stats:
                        conversion_stats[rule_id] = {"total": 0, "converted": 0}
                    conversion_stats[rule_id]["total"] += 1
                    conversion_stats[rule_id]["converted"] += 1
                    
                else:
                    # 统计未转换的
                    if rule_id not in conversion_stats:
                        conversion_stats[rule_id] = {"total": 0, "converted": 0}
                    conversion_stats[rule_id]["total"] += 1
                
                if line_num % 1000 == 0:
                    print(f"Processed {line_num} lines, converted {len(converted_samples)} samples")
                    
            except Exception as e:
                print(f"Error processing line {line_num}: {e}")
                continue
    
    # 合并样本
    all_samples = existing_samples + converted_samples
    
    # 写入输出文件
    with open(verified_output, "w", encoding="utf-8") as f:
        for sample in all_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    # 写入转换日志
    with open(conversion_log, "w", encoding="utf-8") as f:
        f.write(f"External Dataset Conversion Log\n")
        f.write(f"====================================\n")
        f.write(f"Existing samples: {len(existing_samples)}\n")
        f.write(f"Converted samples: {len(converted_samples)}\n")
        f.write(f"Total samples: {len(all_samples)}\n\n")
        
        f.write(f"Conversion Statistics by Rule:\n")
        for rule_id, stats in sorted(conversion_stats.items()):
            rate = stats["converted"] / stats["total"] * 100 if stats["total"] > 0 else 0
            f.write(f"  {rule_id}: {stats['converted']}/{stats['total']} ({rate:.1f}%)\n")
    
    print(f"Conversion completed!")
    print(f"  Existing samples: {len(existing_samples)}")
    print(f"  Converted samples: {len(converted_samples)}")
    print(f"  Total samples: {len(all_samples)}")
    print(f"  Output: {verified_output}")

if __name__ == "__main__":
    main()
