#!/usr/bin/env python3
"""
对 sft_clean_v_json.jsonl 和 sft_clean_v_cot.jsonl 进行 target_line 一致性修正＋引擎验证。

修正规则：
  1. 已一致            → 原样保留
  2. diff 为空         → 标记 _drop_reason='no_diff'（代码未改动，真正无效样本）
  3. diff 只有 1 行    → 用该行替换 target_line
  4. diff 有多行       → 取离原 target_line 最近的变化行替换
  5. 无 target_line   → 从 diff 假设补入最小变化行

引擎验证层（每条修正/补全后）：
  - 用变换引擎重跑： engine.apply_transform(orig, rule_id, target_line=X, **params)
  - 若重跑结果 == transformed_rtl → 验证通过
  - 若不一致 → 遍历所有候选 target_token（暴力搜索）找到能复现的那个，更新 target_line/signal
  - 找不到则标记 _verify_fail=True（保留样本，不 drop）

输出：
  sft_clean_v_json.fixed.jsonl   -- 修正后的 JSON 版
  sft_clean_v_cot.fixed.jsonl    -- 修正后的 COT 版
  fix_target_line_report.txt     -- 统计报告

用法：
  python test/fix_target_line.py [--dry-run] [--no-verify]
"""

import argparse
import difflib
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

BASE = Path("/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset")

# 引擎（懒加载，--no-verify 时不初始化）
_engine = None

def _get_engine():
    global _engine
    if _engine is None:
        from core.transforms import AST_TRANSFORM_REGISTRY, VerilogObfuscationEngine
        _engine = VerilogObfuscationEngine()
        _engine.registry = AST_TRANSFORM_REGISTRY
    return _engine


# ── 工具函数（与 build_canonical_sft.py 保持一致）────────────────────────────

def _extract_orig_rtl(input_str: str) -> list:
    lines = input_str.splitlines()
    in_block = False
    result = []
    for line in lines:
        if line.strip().startswith("### 原始代码"):
            in_block = True
            continue
        if in_block:
            if line.strip().startswith("###"):
                break
            result.append(line)
    return result


def _strip_lineno(line: str) -> str:
    parts = line.split("\t", 1)
    if len(parts) == 2 and parts[0].strip().isdigit():
        return parts[1]
    return line


def _get_changed_lines(orig_lines: list, adv_lines: list) -> set:
    sm = difflib.SequenceMatcher(None, orig_lines, adv_lines, autojunk=False)
    changed = set()
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        for ln in range(i1 + 1, i2 + 1):
            orig_stripped = orig_lines[ln - 1].strip() if ln - 1 < len(orig_lines) else ""
            if orig_stripped:
                changed.add(ln)
        if tag in ("replace", "insert") and i1 < len(orig_lines):
            adv_new = [adv_lines[k] for k in range(j1, j2) if k < len(adv_lines)]
            if any(l.strip() for l in adv_new):
                changed.add(i1 + 1)
    return changed


def _extract_orig_clean(input_str: str) -> str:
    """从 input 字段提取无行号的原始代码（供引擎使用）。"""
    # 优先从 ```verilog 代码块提取
    m = re.search(r"```verilog\s*\n(.*?)```", input_str, re.DOTALL)
    if m:
        numbered = m.group(1)
        lines = [re.sub(r"^\s*\d+:\s?", "", l) for l in numbered.split("\n")]
        return "\n".join(lines).strip()
    # 退回到 ### 原始代码 块
    raw_lines = _extract_orig_rtl(input_str)
    if raw_lines:
        return "\n".join(_strip_lineno(l) for l in raw_lines).strip()
    return ""


def _infer_signal(orig_clean: list, line_no: int) -> str | None:
    """从 orig 第 line_no 行（1-indexed）提取 Verilog 信号名。"""
    if not (1 <= line_no <= len(orig_clean)):
        return None
    line_text = orig_clean[line_no - 1]
    m = re.search(r"(?:input|output|inout|wire|reg|logic)\s+(?:\[.*?\]\s*)?(\w+)",
                  line_text)
    return m.group(1) if m else None


# sentinel：传给 _patch_json_str 表示"清除 target_signal 字段"
_SIGNAL_CLEAR = object()

# 版本兼容参数：旧数据生成时使用但未保存到 output JSON 的参数
# 格式：rule_id -> list of extra_params_dict (逐个尝试)
_COMPAT_PARAMS: dict[str, list[dict]] = {
    "T12": [{"legacy_inline_decl": True}],
    "T31": [{"legacy_inline_decl": True}],
}


def _engine_verify_and_fix(
    orig_code: str, rule_id: str, params: dict,
    target_line: int | None, target_signal: str | None,
    expected_adv: str
) -> tuple[int | None, str | None, bool, dict]:
    """
    用引擎重跑，验证 (target_line, target_signal, params) 是否能复现 expected_adv。
    返回 (final_target_line, final_target_signal, verified:bool, extra_params:dict)
    - verified=True  → 找到可复现的参数组合
    - verified=False → 全部失败，extra_params={}
    - extra_params   → 需要写回 output JSON parameters 的额外兼容参数
    """
    engine = _get_engine()
    expected = expected_adv.strip()

    def _try(tl, ts, extra):
        merged = {**params, **extra}
        try:
            result = engine.apply_transform(
                orig_code, rule_id,
                target_line=tl, target_signal=ts,
                **merged
            )
            return result.strip() == expected
        except Exception:
            return False

    # 1. 先用原始参数重跑
    if _try(target_line, target_signal, {}):
        return target_line, target_signal, True, {}

    # 2. 尝试版本兼容参数
    for compat in _COMPAT_PARAMS.get(rule_id, []):
        if _try(target_line, target_signal, compat):
            return target_line, target_signal, True, compat

    # 3. 遍历所有候选 target_token（带兼容参数）
    try:
        candidates = engine._get_candidates_for_transform(orig_code, rule_id)
    except Exception:
        candidates = []

    compat_list = [{}] + _COMPAT_PARAMS.get(rule_id, [])
    for token_idx in range(len(candidates)):
        for compat in compat_list:
            merged = {**params, **compat}
            try:
                result = engine.apply_transform(orig_code, rule_id,
                                                target_token=token_idx, **merged)
                if result.strip() == expected:
                    tl, ts = engine.get_target_line_signal(orig_code, rule_id, token_idx)
                    return tl, ts, True, compat
            except Exception:
                continue

    # 4. 不带 target（全局规则）
    for compat in compat_list:
        merged = {**params, **compat}
        try:
            result = engine.apply_transform(orig_code, rule_id, **merged)
            if result.strip() == expected:
                return None, None, True, compat
        except Exception:
            continue

    # 5. T20/T04 特殊 fallback：从 adv vs orig 提取 legacy_comment_literal
    if rule_id in ("T20", "T04"):
        literal, insert_tl = _extract_t20_legacy_literal(orig_code, expected_adv)
        if literal is not None:
            try:
                result = engine.apply_transform(
                    orig_code, rule_id,
                    target_line=insert_tl,
                    legacy_comment_literal=literal,
                    **{k: v for k, v in params.items()
                       if k not in ("legacy_comment_literal",)}
                )
                if result.strip() == expected:
                    return insert_tl, None, True, {"legacy_comment_literal": literal}
            except Exception:
                pass

    return target_line, target_signal, False, {}


def _extract_t20_legacy_literal(orig_code: str, adv_code: str) -> tuple[str | None, int | None]:
    """
    从 adv_code 相比 orig_code 的第一处差异里提取 T20 注入的字面量文本及插入行号。
    返回 (literal_str, target_line_1based) 或 (None, None)。
    """
    orig_lines = orig_code.splitlines(keepends=True)
    adv_lines  = adv_code.strip().splitlines(keepends=True)
    sm = difflib.SequenceMatcher(None, orig_lines, adv_lines, autojunk=False)
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            continue
        orig_chunk = "".join(orig_lines[i1:i2])
        adv_chunk  = "".join(adv_lines[j1:j2])
        if tag == "replace" and i2 - i1 == 1 and j2 - j1 == 1:
            ol = orig_lines[i1].rstrip("\n")
            al = adv_lines[j1].rstrip("\n")
            # 找原行代码部分（// 之前）和 adv 行对应位置
            ol_code = ol.split("//")[0].rstrip()
            if len(ol_code) <= len(al):
                # adv 行在 ol_code 之后的内容（含空格+注释）就是 literal
                al_suffix = al[len(ol_code):]
                if al_suffix.lstrip().startswith("//"):
                    return al_suffix, i1 + 1
            # 原行代码部分相同，差在注释追加
            if al.startswith(ol):
                extra = al[len(ol):]
                if extra.strip():
                    return extra, i1 + 1
        elif tag == "insert":
            literal = "".join(adv_lines[j1:j2])
            return literal, i1 + 1
        break
    return None, None


def _patch_json_str(raw_out: str, new_target_line: int | None,
                    new_target_signal: str | None,
                    extra_params: dict | None = None) -> tuple[str, bool]:
    """修正 output 字符串（纯 JSON 或 ```json...``` 格式）中的 target_line/target_signal/parameters。
    extra_params 非空时合并写入 parameters 字段（用于版本兼容参数回写）。
    返回 (new_output_str, patched:bool)。
    """
    text = raw_out.strip()
    has_fence = text.startswith("```")
    try:
        if has_fence:
            fence_lines = text.splitlines()
            lang = fence_lines[0][3:].strip()
            inner = "\n".join(fence_lines[1:]).rstrip("`").strip()
        else:
            inner = text
            lang = ""
        data = json.loads(inner)
        if new_target_line is not None:
            data["target_line"] = new_target_line
        if new_target_signal is _SIGNAL_CLEAR:
            data.pop("target_signal", None)  # 显式清除
        elif new_target_signal is not None:
            data["target_signal"] = new_target_signal
        if extra_params:
            if "parameters" not in data or not isinstance(data["parameters"], dict):
                data["parameters"] = {}
            data["parameters"].update(extra_params)
        data["_target_line_corrected"] = True
        new_inner = json.dumps(data, ensure_ascii=False, indent=2)
        if has_fence:
            return f"```{lang}\n{new_inner}\n```", True
        return new_inner, True
    except Exception:
        return raw_out, False


def _patch_cot_output(cot_out: str, new_target_line: int | None,
                      new_target_signal: str | None,
                      extra_params: dict | None = None) -> tuple[str, bool]:
    """COT output 格式：策略文本 + ```json...``` 块。
    找到 JSON 块并修正其中的 target_line/target_signal/parameters。
    """
    pattern = re.compile(r"(```(?:json)?\s*\n)(.*?)(```)", re.DOTALL)
    m = pattern.search(cot_out)
    if not m:
        new_out, ok = _patch_json_str(cot_out, new_target_line, new_target_signal, extra_params)
        return new_out, ok
    try:
        inner = m.group(2).strip()
        data = json.loads(inner)
        if new_target_line is not None:
            data["target_line"] = new_target_line
        if new_target_signal is _SIGNAL_CLEAR:
            data.pop("target_signal", None)
        elif new_target_signal is not None:
            data["target_signal"] = new_target_signal
        if extra_params:
            if "parameters" not in data or not isinstance(data["parameters"], dict):
                data["parameters"] = {}
            data["parameters"].update(extra_params)
        data["_target_line_corrected"] = True
        new_inner = json.dumps(data, ensure_ascii=False, indent=2)
        new_block = m.group(1) + new_inner + "\n" + m.group(3)
        new_out = cot_out[:m.start()] + new_block + cot_out[m.end():]
        return new_out, True
    except Exception:
        return cot_out, False


# ── 核心修正逻辑 ──────────────────────────────────────────────────────────────

class FixResult:
    CONSISTENT   = "consistent"    # 已一致，无需修正
    CORRECTED    = "corrected"     # target_line 已修正（原有字段填错）
    FILLED       = "filled"        # target_line 已补全（原来缺失）
    NO_DIFF      = "no_diff"       # 代码未改动，无效样本
    NO_TARGET    = "no_target"     # 无 target_line 且无法从 diff 推断
    PARSE_FAIL   = "parse_fail"    # output 解析失败
    VERIFY_FAIL  = "verify_fail"   # 引擎重跑无法复现 transformed_rtl（保留样本）


def _parse_output_json(raw_out: str) -> dict | None:
    """解析 output 字段中的 JSON 数据（支持 ```json...``` 和裸 JSON）。"""
    try:
        text = raw_out.strip()
        if text.startswith("```"):
            text = "\n".join(text.splitlines()[1:]).rstrip("`").strip()
        return json.loads(text)
    except Exception:
        return None


def fix_sample(json_sample: dict, cot_sample: dict,
               use_verify: bool = True) -> tuple[dict, dict, str]:
    """
    对一对 (json_sample, cot_sample) 执行 target_line 修正/补全。
    use_verify=True 时调用引擎重跑验证。
    返回 (fixed_json, fixed_cot, FixResult)。
    """
    raw_out = json_sample.get("output", "")

    # 解析 output JSON
    data = _parse_output_json(raw_out)
    if data is None:
        return json_sample, cot_sample, FixResult.PARSE_FAIL

    target_line = data.get("target_line")
    has_target_line = target_line is not None
    if has_target_line:
        try:
            target_line = int(target_line)
        except Exception:
            has_target_line = False
            target_line = None

    # 提取原始代码 & 攻击后代码
    orig_lines_raw = _extract_orig_rtl(json_sample.get("input", ""))
    adv_raw = json_sample.get("transformed_rtl", "")
    if not orig_lines_raw or not adv_raw:
        return json_sample, cot_sample, FixResult.NO_TARGET

    orig_clean = [_strip_lineno(l) for l in orig_lines_raw]
    adv_clean  = [_strip_lineno(l) for l in adv_raw.splitlines()]

    changed = _get_changed_lines(orig_clean, adv_clean)

    # 代码完全未改动 → 唯一真正无效的情况
    if not changed:
        rj = dict(json_sample); rj["_drop_reason"] = "no_diff"
        rc = dict(cot_sample);  rc["_drop_reason"] = "no_diff"
        return rj, rc, FixResult.NO_DIFF

    # 提取无行号原始代码（引擎需要）
    orig_code = _extract_orig_clean(json_sample.get("input", ""))
    rule_id   = json_sample.get("rule_id", "")
    params    = data.get("parameters", {}) or {}
    adv_code  = json_sample.get("transformed_rtl", "")

    def _apply_and_write(correct_line, new_signal, fix_status):
        """验证 correct_line 后写入 output 并返回结果。"""
        final_line, final_signal, extra = correct_line, new_signal, {}
        if use_verify and orig_code and rule_id:
            final_line, final_signal, verified, extra = _engine_verify_and_fix(
                orig_code, rule_id, dict(params),
                correct_line, new_signal, adv_code
            )
            if not verified:
                final_line, final_signal = correct_line, new_signal
                extra = {}
                fix_status = FixResult.VERIFY_FAIL

        new_json_out, ok_j = _patch_json_str(raw_out, final_line, final_signal, extra or None)
        rj = dict(json_sample)
        if ok_j:
            rj["output"] = new_json_out
            if fix_status == FixResult.VERIFY_FAIL:
                rj["_verify_fail"] = True
        new_cot_out, ok_c = _patch_cot_output(cot_sample["output"], final_line, final_signal, extra or None)
        rc = dict(cot_sample)
        if ok_c:
            rc["output"] = new_cot_out
            if fix_status == FixResult.VERIFY_FAIL:
                rc["_verify_fail"] = True
        return rj, rc, fix_status

    # T32/T07/T09 特殊处理：旧数据 target_line/target_signal 可能指向错误候选
    # 用 SequenceMatcher 直接找第一个真正变化行，从引擎候选列表找对应 signal
    if rule_id in ("T32", "T07", "T09"):
        sm_direct = difflib.SequenceMatcher(None, orig_clean, adv_clean, autojunk=False)
        diff_line = None
        for tag, i1, i2, j1, j2 in sm_direct.get_opcodes():
            if tag != "equal" and i1 < len(orig_clean) and orig_clean[i1].strip():
                diff_line = i1 + 1
                break
        if diff_line is None:
            diff_line = target_line or min(changed)
        # 从引擎候选列表找行号最近的 signal
        diff_signal = None
        if orig_code and rule_id != "T32":  # T32 候选 signal 为 None，不需要查
            try:
                from core.transforms import _item_line_range, _item_signal
                candidates = engine._get_candidates_for_transform(orig_code, rule_id)
                best_dist = 999
                for c in candidates:
                    lo, _ = _item_line_range(orig_code, c)
                    sig = _item_signal(c)
                    if lo is not None and abs(lo - diff_line) < best_dist:
                        best_dist = abs(lo - diff_line)
                        diff_signal = sig or None
            except Exception:
                pass
        new_json_out, ok_j = _patch_json_str(raw_out, diff_line,
                                              _SIGNAL_CLEAR if diff_signal is None else diff_signal,
                                              None)
        rj = dict(json_sample)
        if ok_j:
            rj["output"] = new_json_out
        new_cot_out, ok_c = _patch_cot_output(cot_sample["output"], diff_line,
                                               _SIGNAL_CLEAR if diff_signal is None else diff_signal,
                                               None)
        rc = dict(cot_sample)
        if ok_c:
            rc["output"] = new_cot_out
        old_tl = target_line; old_ts = data.get("target_signal")
        fix_status = FixResult.CONSISTENT if (diff_line == old_tl and diff_signal == old_ts) else FixResult.CORRECTED
        return rj, rc, fix_status

    # 情况A：已有 target_line
    if has_target_line:
        # 已一致 —— 也要过引擎验证（可能需要补写兼容参数）
        if target_line in changed:
            if use_verify and orig_code and rule_id:
                _, _, verified, extra = _engine_verify_and_fix(
                    orig_code, rule_id, dict(params),
                    target_line, data.get("target_signal"), adv_code
                )
                if not verified:
                    rj = dict(json_sample); rj["_verify_fail"] = True
                    rc = dict(cot_sample);  rc["_verify_fail"] = True
                    return rj, rc, FixResult.VERIFY_FAIL
                if extra:
                    # 兼容参数需要写回，状态升级为 CORRECTED；signal 保持不变（传 None）
                    new_json_out, ok_j = _patch_json_str(raw_out, target_line,
                                                         None, extra)
                    rj = dict(json_sample)
                    if ok_j:
                        rj["output"] = new_json_out
                    new_cot_out, ok_c = _patch_cot_output(cot_sample["output"], target_line,
                                                           None, extra)
                    rc = dict(cot_sample)
                    if ok_c:
                        rc["output"] = new_cot_out
                    return rj, rc, FixResult.CORRECTED
            return json_sample, cot_sample, FixResult.CONSISTENT
        # 不一致 → 修正：取离原值最近的变化行
        correct_line = min(changed, key=lambda ln: abs(ln - target_line))
        new_signal = _infer_signal(orig_clean, correct_line)
        return _apply_and_write(correct_line, new_signal, FixResult.CORRECTED)

    # 情况B：无 target_line → 从 diff 反推补全
    correct_line = min(changed)
    new_signal = _infer_signal(orig_clean, correct_line)
    return _apply_and_write(correct_line, new_signal, FixResult.FILLED)


# ── 主流程 ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true",
                        help="只统计，不写输出文件")
    parser.add_argument("--input-json", type=str,
                        default=str(BASE / "sft_clean_v_json.jsonl"))
    parser.add_argument("--input-cot", type=str,
                        default=str(BASE / "sft_clean_v_cot.jsonl"))
    parser.add_argument("--output-json", type=str,
                        default=str(BASE / "sft_clean_v_json.fixed.jsonl"))
    parser.add_argument("--output-cot", type=str,
                        default=str(BASE / "sft_clean_v_cot.fixed.jsonl"))
    parser.add_argument("--report", type=str,
                        default=str(BASE / "fix_target_line_report.txt"))
    parser.add_argument("--no-verify", action="store_true",
                        help="跳过引擎验证层（速度更快，但不保证参数与引擎一致）")
    args = parser.parse_args()
    use_verify = not args.no_verify

    in_json = Path(args.input_json)
    in_cot  = Path(args.input_cot)

    print(f"读取: {in_json}  ({in_json.stat().st_size//1024} KB)")
    print(f"读取: {in_cot}   ({in_cot.stat().st_size//1024} KB)")

    json_lines = []
    cot_lines  = []
    with open(in_json) as fj, open(in_cot) as fc:
        for lj, lc in zip(fj, fc):
            if lj.strip():
                json_lines.append(json.loads(lj))
                cot_lines.append(json.loads(lc))

    total = len(json_lines)
    print(f"总样本数: {total}")

    # 统计容器
    result_counter   = Counter()           # FixResult -> count
    rule_counter     = defaultdict(Counter) # rule_id -> Counter
    corrected_detail = []                  # [(rule_id, orig_tl, new_tl)]

    fixed_json = []
    fixed_cot  = []

    for i, (sj, sc) in enumerate(zip(json_lines, cot_lines)):
        rj, rc, status = fix_sample(sj, sc, use_verify=use_verify)
        fixed_json.append(rj)
        fixed_cot.append(rc)

        result_counter[status] += 1
        rid = sj.get("rule_id", "?")
        rule_counter[rid][status] += 1

        if status == FixResult.CORRECTED:
            # 提取原始和修正后的 target_line 用于报告
            try:
                orig_tl = json.loads(sj["output"].strip().lstrip("`").split("\n")[0] if not sj["output"].strip().startswith("{") else sj["output"])
            except Exception:
                orig_tl = "?"
            try:
                new_out = rj["output"].strip()
                if new_out.startswith("```"):
                    new_out = "\n".join(new_out.splitlines()[1:]).rstrip("`").strip()
                new_tl = json.loads(new_out).get("target_line", "?")
            except Exception:
                new_tl = "?"
            corrected_detail.append((rid, i))

        if (i + 1) % 5000 == 0:
            print(f"  处理 {i+1}/{total} ...", flush=True)

    print(f"处理完成: {total} 条")

    # ── 统计报告 ──────────────────────────────────────────────────────────────
    lines = []
    lines.append("=" * 60)
    lines.append("target_line 修正报告")
    lines.append("=" * 60)
    n_consistent = result_counter[FixResult.CONSISTENT]
    n_corrected  = result_counter[FixResult.CORRECTED]
    n_filled     = result_counter[FixResult.FILLED]
    n_no_diff    = result_counter[FixResult.NO_DIFF]
    n_no_target  = result_counter[FixResult.NO_TARGET]
    n_parse_fail = result_counter[FixResult.PARSE_FAIL]
    n_verify_fail = result_counter[FixResult.VERIFY_FAIL]
    n_valid      = total - n_no_diff  # 有效（保留）样本数
    verify_label = "" if use_verify else " [引擎验证已禁用]"
    lines.append(f"总样本数:              {total}{verify_label}")
    lines.append(f"  已一致 (consistent): {n_consistent:>6}  ({n_consistent/total*100:.1f}%)")
    lines.append(f"  行号修正 (corrected):{n_corrected:>6}  ({n_corrected/total*100:.1f}%)  ← 有字段但填错")
    lines.append(f"  行号补全 (filled):   {n_filled:>6}  ({n_filled/total*100:.1f}%)  ← 无字段从diff补入")
    lines.append(f"  代码未改动(no_diff): {n_no_diff:>6}  ({n_no_diff/total*100:.1f}%)  ← 唯一真正无效")
    lines.append(f"  无法处理(no_target): {n_no_target:>6}  ({n_no_target/total*100:.1f}%)")
    lines.append(f"  解析失败(parse_fail):{n_parse_fail:>6}  ({n_parse_fail/total*100:.1f}%)")
    lines.append(f"  引擎验证失败(vfy_fail):{n_verify_fail:>6}  ({n_verify_fail/total*100:.1f}%)  ← 保留但标记_verify_fail")
    lines.append(f"保留有效样本数:        {n_valid}  ({n_valid/total*100:.1f}%)")
    lines.append("")
    lines.append("── 规则级分布 ──")
    hdr = f"{'规则':<6} {'total':>6} {'一致':>6} {'修正':>6} {'补全':>6} {'no_diff':>8} {'vfy_fail':>9} {'修正+补全率':>11}"
    lines.append(hdr)
    lines.append("-" * len(hdr))
    for rid in sorted(rule_counter.keys()):
        rc_r = rule_counter[rid]
        n = sum(rc_r.values())
        n_ok  = rc_r[FixResult.CONSISTENT]
        n_fix = rc_r[FixResult.CORRECTED]
        n_fil = rc_r[FixResult.FILLED]
        n_nd  = rc_r[FixResult.NO_DIFF]
        n_vf  = rc_r[FixResult.VERIFY_FAIL]
        fix_rate = (n_fix + n_fil) / n * 100 if n else 0
        lines.append(f"{rid:<6} {n:>6} {n_ok:>6} {n_fix:>6} {n_fil:>6} {n_nd:>8} {n_vf:>9} {fix_rate:>10.1f}%")

    report_text = "\n".join(lines)
    print("\n" + report_text)

    with open(args.report, "w") as f:
        f.write(report_text)
    print(f"\n报告已写入: {args.report}")

    if args.dry_run:
        print("--dry-run 模式，跳过写出文件")
        return

    # ── 写出修正后的文件 ──────────────────────────────────────────────────────
    out_json = Path(args.output_json)
    out_cot  = Path(args.output_cot)

    with open(out_json, "w") as f:
        for s in fixed_json:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    with open(out_cot, "w") as f:
        for s in fixed_cot:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"已写出: {out_json}  ({out_json.stat().st_size//1024} KB)")
    print(f"已写出: {out_cot}   ({out_cot.stat().st_size//1024} KB)")


if __name__ == "__main__":
    main()
