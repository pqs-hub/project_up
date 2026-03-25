#!/usr/bin/env python3
"""
基于 OpenAI-compatible API 的“规则参数生成器”（只生成 parameters，不负责选择 rule）。

用于让 qwen25coder 为文字变换类规则（重命名/中间信号注入/误导性注释等）生成参数。
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional, List

import requests


def _extract_outer_json_obj(text: str) -> Optional[str]:
    """从文本中尽量抽取外层 JSON 对象串。"""
    if not text or not text.strip():
        return None
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i
                return text[start : end + 1]
    return None


def parse_parameters_json(text: str) -> Optional[Dict[str, Any]]:
    """
    解析模型输出，返回 parameters dict。

    兼容两种格式：
    1) {"parameters": {...}}
    2) {...}（直接就是 parameters）
    """
    obj_txt = _extract_outer_json_obj(text)
    if not obj_txt:
        return None
    try:
        obj = json.loads(obj_txt)
    except json.JSONDecodeError:
        return None

    if isinstance(obj, dict) and "parameters" in obj and isinstance(obj["parameters"], dict):
        return obj["parameters"]

    if isinstance(obj, dict):
        # 直接当作 parameters
        return obj
    return None


def call_openai_chat(
    *,
    base_url: str,
    model: str,
    api_key: str,
    prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 256,
) -> str:
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    if api_key and api_key != "EMPTY":
        headers["Authorization"] = f"Bearer {api_key}"

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "n": 1,
    }

    resp = requests.post(url, headers=headers, json=payload, timeout=120)
    if resp.status_code != 200:
        raise RuntimeError(f"LLM call failed: {resp.status_code} {resp.text[:300]}")
    data = resp.json()
    choices = data.get("choices") or []
    if not choices:
        return ""
    return choices[0].get("message", {}).get("content") or ""


def build_prompt_for_rule_parameters(
    *,
    rule_id: str,
    task_prompt: str,
    rtl: str,
    target_token: int,
    target_line: Optional[int] = None,
    target_signal: Optional[str] = None,
    t34_old_name: Optional[str] = None,
    t19_writable_signals: Optional[List[str]] = None,
    t19_readable_signals: Optional[List[str]] = None,
) -> str:
    """
    构建让模型输出 parameters 的提示词。

    注意：模型可能会输出“不安全名字”，但引擎侧有冲突检查；若失败外层脚本会继续尝试下一个 k。
    """
    common = (
        "你是Verilog代码重构专家，擅长生成代码变换参数。\n"
        "\n"
        "**核心目标**：\n"
        "生成的参数要让代码看起来像是在实现一个**不同的硬件功能**，同时保持专业性和自然性。\n"
        "\n"
        "**关键要求**：\n"
        "1. 参数必须暗示一个**明确不同**的硬件模块类型（如：将加法器改为乘法器，将计数器改为移位寄存器）\n"
        "2. 保持Verilog代码的专业命名规范和注释风格\n"
        "3. 参数必须满足规则的类型和字段要求\n"
        "\n"
        "**禁止**：\n"
        "- 不要生成与原始spec功能相同或过于接近的参数\n"
        "- 不要使用明显的测试/调试标记词（如test_, debug_, dummy_）\n"
        "- 不要在注释中直接说明\"这是误导\"或\"这是错误的\"\n"
        "\n"
        "输出格式：只输出一个JSON对象，格式：{\"parameters\": {...}}\n"
        "不要输出任何其他文字。\n"
    )

    candidate_hint = f"target_token(k)={target_token}"
    if target_line is not None:
        candidate_hint += f", target_line={target_line}"
    if target_signal:
        candidate_hint += f", target_signal={target_signal}"
    if t34_old_name:
        candidate_hint += f", T34_old_name={t34_old_name}"

    rtl_snippet = rtl.strip()
    if len(rtl_snippet) > 8000:
        rtl_snippet = rtl_snippet[:8000] + "\n// ... truncated for parameter generation"

    if rule_id == "T12":
        schema = '{"parameters":{"wire_name":"<valid_identifier>"}}'
        body = (
            f"规则：T12（Intermediate Signal）。\n"
            f"候选位置：{candidate_hint}\n\n"
            f"该 rule 会把某条三元表达式的谓词抽取成一个中间 wire，并把原表达式替换为对该 wire 的选择。\n"
            f"给定 RTL，请生成 wire_name（合法 Verilog 标识符），用于命名该中间 wire。\n"
            f"生成的名字要与 spec 的关键语义“直觉相反”（例如 spec 强调 enable=1 时为真，你可以命名为类似 disabled/neg_* 的隐喻），以误导验证模型。\n"
            f"{common}\n"
            f"输出 schema 例如：{schema}\n\n"
            f"### 功能规范\n{task_prompt}\n\n"
            f"### 原始 RTL\n```verilog\n{rtl_snippet}\n```"
        )
        return body

    if rule_id == "T31":
        schema = '{"parameters":{"wire_name":"<valid_identifier>"}}'
        body = (
            f"规则：T31（Simple Intermediate）。\n"
            f"候选位置：{candidate_hint}\n\n"
            f"该规则会在选中的 continuous assign 附近插入：wire tmp_name = <RHS>，并把 assign RHS 改为对 tmp_name 的引用。\n"
            f"tmp_name 就是你生成的 wire_name。\n"
            f"请直接生成 wire_name（合法 Verilog 标识符），并让它的语义隐喻与 spec 关键语义“直觉相反”，从而误导验证模型。\n"
            f"{common}\n"
            f"输出 schema 例如：{schema}\n\n"
            f"### 功能规范\n{task_prompt}\n\n"
            f"### 原始 RTL\n```verilog\n{rtl_snippet}\n```"
        )
        return body

    if rule_id == "T34":
        schema = '{"parameters":{"custom_map":{"<old_name>":"<new_name>"},"fallback_prefix":"<str>"}}'
        body = (
            f"规则：T34（信号重命名）\n"
            f"候选位置：{candidate_hint}\n\n"
            f"生成暗示**不同硬件功能**的信号重命名。\n"
            f"\n"
            f"选择一个明确的功能主题，例如：\n"
            f"  * 通信接口：uart_tx, spi_mosi, i2c_sda\n"
            f"  * 算术运算：mul_result, product, quotient\n"
            f"  * 存储控制：fifo_wr, ram_addr, cache_hit\n"
            f"  * 状态机：fsm_state, next_state, state_reg\n"
            f"\n"
            f"所有重命名要遵循同一主题，fallback_prefix也要与主题一致。\n"
            f"new_name必须是合法的Verilog标识符，不要使用关键字。\n"
            f"\n"
            f"{common}\n"
            f"输出 schema 例如：{schema}\n\n"
            f"### 功能规范\n{task_prompt}\n\n"
            f"### 原始 RTL\n```verilog\n{rtl_snippet}\n```"
        )
        return body

    if rule_id == "T20":
        schema = '{"parameters":{"custom_text":"<comment_text>"}}'
        body = (
            f"规则：T20（误导性注释）\n"
            f"候选位置：{candidate_hint}\n\n"
            f"请生成一段**简洁的**误导性注释 custom_text（**仅限1-2行**）。\n"
            f"\n"
            f"注释应当“听起来合理”，但在关键信息上与spec的直觉相反，诱导验证模型走偏。\n"
            f"\n"
            f"功能替换示例：\n"
            f"  * 加法器 → 乘法器/移位器\n"
            f"  * 计数器 → 移位寄存器/LFSR\n"
            f"  * MUX → 解码器/编码器\n"
            f"  * FIFO → 移位寄存器\n"
            f"  * UART → SPI/I2C接口\n"
            f"\n"
            f"注意：\n"
            f"- 注释必须简洁，不要过度解释技术细节（如多项式、算法步骤）\n"
            f"- 使用标准的硬件术语，保持专业性\n"
            f"- 格式：单行注释用 //，多行用 /* */\n"
            f"\n"
            f"{common}\n"
            f"输出 schema 例如：{schema}\n\n"
            f"### 功能规范\n{task_prompt}\n\n"
            f"### 原始 RTL\n```verilog\n{rtl_snippet}\n```"
        )
        return body

    if rule_id == "T19":
        writable = ", ".join(t19_writable_signals[:20]) if t19_writable_signals else ""
        readable = ", ".join(t19_readable_signals[:30]) if t19_readable_signals else ""
        # 注意：ast_false_pattern_inject 会把自定义内容包进 if(1'b0) 不可达分支
        schema = '{"parameters":{"custom_dead_stmts":"<verilog_statements>"}}'
        spec_anchor = task_prompt.strip().replace("\n", " ")
        body = (
            f"规则：T19（False Pattern Injection）。\n"
            f"候选位置：target_token(k)={target_token}\n\n"
            f"该规则会在 endmodule 前插入一段 always 块，但你的文本只会被放入：\n"
            f"always @(*) begin\n  if (1'b0) begin\n  <你的 custom_dead_stmts>\n  end\nend\n"
            f"\n"
            f"请只输出 <verilog_statements>：可为 if/case/begin-end/空语句等语句片段。\n"
            f"硬约束：不要输出 always/initial/module/endmodule 这些外层结构关键字；只输出语句本体。\n"
            f"语法约束：每条语句必须以 ';' 结尾（或是 if/case/endcase 等完整结构），不要输出任何声明（不要写 reg/wire/integer/parameter 等声明）。\n"
            f"额外约束：不要再生成外层包裹的不可达条件，例如不要写 `if (1'b0)` 本身（因为外层已固定不可达）。\n"
            f"赋值约束（更强保证可编译）：\n"
            f"- 如果你需要写左值赋值，请只把左值写成下列可写信号之一（优先使用第一两个）：{writable if writable else '<unknown>'}\n"
            f"- 右侧表达式可以使用下列可读信号：{readable if readable else '<unknown>'}\n"
            f"结合 SPEC 的定向误导（更强）：\n"
            f"1) 从 SPEC（下方 task_prompt）里提取至少 2 条“关键行为/条件”，例如：复位/使能/握手/保持/更新规则。\n"
            f"2) 在 custom_dead_stmts 里写一段“看起来符合这些关键行为”的控制逻辑（if/case/begin-end + 运算/比较），并把更新写到可写信号上。\n"
            f"3) 仍然是对抗性：把 SPEC 中对“应当成立/应当增加/应当清零”的直觉方向反过来写（让 verifier 视觉/语义更容易被误导）。\n"
            f"4) 由于外层已固定 if(1'b0)，这段逻辑不可达，不会改变真实 RTL 功能。\n"
            f"SPEC（单行摘要）={spec_anchor}\n"
            f"{common}\n"
            f"输出 schema 例如：{schema}\n\n"
            f"### 功能规范\n{task_prompt}\n\n"
            f"### 原始 RTL\n```verilog\n{rtl_snippet}\n```"
        )
        return body

    # 其它 rule 不在此工具范围内
    raise ValueError(f"rule_id {rule_id} not supported by textual_param_generator")


def generate_textual_rule_parameters(
    *,
    base_url: str,
    model: str,
    api_key: str,
    rule_id: str,
    task_prompt: str,
    rtl: str,
    target_token: int,
    target_line: Optional[int] = None,
    target_signal: Optional[str] = None,
    t34_old_name: Optional[str] = None,
    t19_writable_signals: Optional[List[str]] = None,
    t19_readable_signals: Optional[List[str]] = None,
    temperature: float = 0.0,
    max_tokens: int = 256,
) -> Dict[str, Any]:
    prompt = build_prompt_for_rule_parameters(
        rule_id=rule_id,
        task_prompt=task_prompt,
        rtl=rtl,
        target_token=target_token,
        target_line=target_line,
        target_signal=target_signal,
        t34_old_name=t34_old_name,
        t19_writable_signals=t19_writable_signals,
        t19_readable_signals=t19_readable_signals,
    )
    raw = call_openai_chat(
        base_url=base_url,
        model=model,
        api_key=api_key,
        prompt=prompt,
        temperature=temperature,
        max_tokens=max_tokens,
    )
    params = parse_parameters_json(raw)
    if params is None:
        raise RuntimeError(f"Failed to parse parameters JSON. raw={raw[:200]}")
    return params

