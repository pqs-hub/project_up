#!/usr/bin/env python3
"""
文本类规则参数生成器

使用LLM生成高质量的攻击参数，特别是T20（误导性注释）。

移植自：/mnt/public/pqs/LLM_attack1/LLM_attack_back/LLM_attack/scripts/eval/textual_param_generator.py
"""

import json
import re
from typing import Dict, Any, List, Optional
import requests
import logging

logger = logging.getLogger(__name__)

def call_openai_chat(
    base_url: str,
    model: str,
    api_key: str,
    prompt: str,
    temperature: float = 0.0,
    max_tokens: int = 256,
) -> str:
    """调用OpenAI兼容的API"""
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }
    data = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, timeout=30)
        response.raise_for_status()
        result = response.json()
        return result["choices"][0]["message"]["content"]
    except Exception as e:
        logger.error(f"API调用失败: {e}")
        raise

def parse_parameters_json(raw: str) -> Optional[Dict[str, Any]]:
    """从LLM返回中解析JSON参数"""
    # 尝试找到JSON块
    json_match = re.search(r'```json\s*(.*?)\s*```', raw, re.DOTALL)
    if json_match:
        json_str = json_match.group(1)
    else:
        # 尝试找到{...}块
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if json_match:
            json_str = json_match.group(0)
        else:
            return None
    
    try:
        return json.loads(json_str)
    except json.JSONDecodeError:
        return None

def build_prompt_for_rule_parameters(
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
    """为特定规则构建prompt"""
    
    # 通用部分
    common = (
        "你是 Verilog 代码混淆/变换专家。\n"
        "目标（对抗性）：你生成的 parameters 会被用于执行指定 rule 后，\n"
        "让变换后的 RTL 更'误导'验证模型的直觉/模式匹配。\n\n"
        "也就是说：parameters 应当尽量与功能规范（spec）中描述的行为'直觉相反'，\n"
        "但不破坏可编译性。\n"
    )
    
    # T20 - 误导性注释
    if rule_id == "T20":
        schema = '{"parameters":{"custom_text":"<comment_text>"}}'
        body = (
            f"规则：T20（Misleading Comment）。\n\n"
            f"请生成一段误导性注释 custom_text（不要包含 JSON/反引号）。\n"
            f"注释应当'听起来合理'，但在关键信息上与 spec 的直觉相反，诱导验证模型走偏。\n"
            f"注释内容尽量使用 spec 中出现的关键词/术语（但要做语义反转），以增强误导性。\n"
            f"{common}\n"
            f"输出 schema 例如：{schema}\n\n"
            f"### 功能规范\n{task_prompt}\n\n"
            f"### 原始 RTL\n```verilog\n{rtl[:500] if len(rtl) > 500 else rtl}\n```"
        )
        return body
    
    # 其他规则暂时不支持
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
    """生成文本类规则的参数"""
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

if __name__ == "__main__":
    # 测试代码
    import sys
    
    if len(sys.argv) < 2:
        print("用法: python textual_param_generator.py <rule_id>")
        sys.exit(1)
    
    rule_id = sys.argv[1]
    
    # 示例数据
    task_prompt = "Build a circuit that outputs LOW signal."
    rtl = """module RefModule (
  output zero
);
  assign zero = 1'b0;
endmodule"""
    
    try:
        params = generate_textual_rule_parameters(
            base_url="http://localhost:8001/v1",
            model="Qwen/Qwen2.5-Coder-7B-Instruct",
            api_key="EMPTY",
            rule_id=rule_id,
            task_prompt=task_prompt,
            rtl=rtl,
            target_token=0,
        )
        print(f"生成的参数: {params}")
    except Exception as e:
        print(f"错误: {e}")
