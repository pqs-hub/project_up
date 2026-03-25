#!/usr/bin/env python3
"""
联动感知的LLM参数生成器

核心思想：
1. 第二个规则的参数生成会考虑第一个规则的变换
2. Prompt中明确告知：哪些代码是规则变换后的、用了什么参数
3. 生成的参数与前序规则形成语义联动
"""

import json
import requests
from typing import Dict, List, Optional, Any
from dataclasses import dataclass


@dataclass
class TransformHistory:
    """变换历史记录"""
    rule_id: str
    params_used: Dict[str, Any]
    transformed_code: str
    rename_map: Optional[Dict[str, str]] = None
    description: str = ""  # 人类可读的变换描述


class LinkedParamGenerator:
    """联动感知的参数生成器"""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8001/v1",
        model: str = "verilog_attack_merged_bal500",
        api_key: str = "EMPTY",
        timeout: int = 60
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
    
    def _call_llm(self, prompt: str, temperature: float = 0.7, max_tokens: int = 512) -> str:
        """调用LLM"""
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": temperature,
                    "max_tokens": max_tokens
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                return response.json()["choices"][0]["message"]["content"]
            else:
                raise RuntimeError(f"LLM调用失败: {response.status_code}")
        
        except Exception as e:
            print(f"LLM调用异常: {e}")
            return ""
    
    def _parse_json_response(self, text: str) -> Optional[Dict]:
        """解析JSON响应"""
        # 提取JSON对象
        start = text.find("{")
        if start < 0:
            return None
        
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i+1])
                        # 兼容两种格式
                        if "parameters" in obj:
                            return obj["parameters"]
                        return obj
                    except:
                        return None
        return None
    
    def generate_linked_params(
        self,
        rule_id: str,
        spec: str,
        original_rtl: str,
        current_rtl: str,
        transform_history: List[TransformHistory],
        target_token: int = 0,
        target_signal: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        生成联动参数
        
        Args:
            rule_id: 当前要应用的规则
            spec: 功能规范
            original_rtl: 原始RTL
            current_rtl: 当前（已变换）的RTL
            transform_history: 之前的变换历史
            target_token: 目标位置
            target_signal: 目标信号
        
        Returns:
            参数字典
        """
        
        # 构建联动感知的prompt
        prompt = self._build_linked_prompt(
            rule_id=rule_id,
            spec=spec,
            original_rtl=original_rtl,
            current_rtl=current_rtl,
            transform_history=transform_history,
            target_token=target_token,
            target_signal=target_signal
        )
        
        # 调用LLM
        response = self._call_llm(prompt, temperature=0.7)
        
        # 解析参数
        params = self._parse_json_response(response)
        
        if params is None:
            print(f"警告: 无法解析LLM响应，使用默认参数")
            return self._get_default_params(rule_id)
        
        return params
    
    def _build_linked_prompt(
        self,
        rule_id: str,
        spec: str,
        original_rtl: str,
        current_rtl: str,
        transform_history: List[TransformHistory],
        target_token: int,
        target_signal: Optional[str]
    ) -> str:
        """构建联动感知的prompt"""
        
        # 基础指令
        base_instruction = """你是Verilog代码重构专家，擅长生成代码变换参数。

**核心目标**：
生成的参数要让代码看起来像是在实现一个**不同的硬件功能**，同时保持专业性和自然性。

**关键要求**：
1. 参数必须暗示一个**明确不同**的硬件模块类型（如：将加法器改为乘法器，将计数器改为移位寄存器）
2. 如果有前序变换，你的参数要与之形成**一致的功能暗示**
3. 保持Verilog代码的专业命名规范和注释风格

**禁止**：
- 不要生成与原始spec功能相同或过于接近的参数
- 不要使用明显的测试/调试标记词（如test_, debug_, dummy_）
- 不要在注释中直接说明"这是误导"或"这是错误的"

**输出格式**：
只输出一个JSON对象，格式：{"parameters": {...}}
不要输出任何其他文字。
"""
        
        # 变换历史描述
        history_desc = self._format_transform_history(transform_history)
        
        # 规则特定的prompt
        rule_specific = self._get_rule_specific_prompt(
            rule_id=rule_id,
            spec=spec,
            original_rtl=original_rtl,
            current_rtl=current_rtl,
            transform_history=transform_history,
            target_token=target_token,
            target_signal=target_signal
        )
        
        # 组合完整prompt
        prompt = f"""{base_instruction}

{history_desc}

{rule_specific}

### 功能规范（Spec）
{spec[:1000]}

### 原始RTL
```verilog
{original_rtl[:2000]}
```

### 当前RTL（已应用前序规则）
```verilog
{current_rtl[:2000]}
```

请生成参数："""
        
        return prompt
    
    def _format_transform_history(self, history: List[TransformHistory]) -> str:
        """格式化变换历史"""
        if not history:
            return "**变换历史**：无（这是第一个规则）"
        
        lines = ["**变换历史**："]
        for i, h in enumerate(history, 1):
            lines.append(f"\n{i}. 规则 {h.rule_id}")
            
            if h.description:
                lines.append(f"   - 变换说明: {h.description}")
            
            if h.params_used:
                lines.append(f"   - 使用参数: {json.dumps(h.params_used, ensure_ascii=False)}")
            
            if h.rename_map:
                lines.append(f"   - 重命名映射: {json.dumps(h.rename_map, ensure_ascii=False)}")
        
        return "\n".join(lines)
    
    def _get_rule_specific_prompt(
        self,
        rule_id: str,
        spec: str,
        original_rtl: str,
        current_rtl: str,
        transform_history: List[TransformHistory],
        target_token: int,
        target_signal: Optional[str]
    ) -> str:
        """获取规则特定的prompt"""
        
        if rule_id == "T20":  # 误导性注释
            return self._prompt_t20_linked(transform_history, spec)
        
        elif rule_id == "T34":  # 重命名
            return self._prompt_t34_linked(transform_history, spec, current_rtl)
        
        elif rule_id == "T12":  # 中间信号
            return self._prompt_t12_linked(transform_history, spec, target_signal)
        
        elif rule_id == "T31":  # 简单中间信号
            return self._prompt_t31_linked(transform_history, spec)
        
        elif rule_id == "T19":  # 死代码
            return self._prompt_t19_linked(transform_history, spec, current_rtl)
        
        else:
            return f"**当前规则**: {rule_id}\n请生成合适的参数。"
    
    def _prompt_t20_linked(self, history: List[TransformHistory], spec: str) -> str:
        """T20联动prompt：注释要与前序变换一致"""
        
        prompt = """**当前规则**: T20（误导性注释）

**参数**: `custom_text` - 要插入的注释文本

**生成要求**：
"""
        
        if not history:
            prompt += """- 生成一段**简洁的**误导性注释（**仅限1-2行**）
- 注释应当“听起来合理”，但在关键信息上与spec的直觉相反
- 必须选择一个明确的替代功能类型，例如：
  * 加法器 → 乘法器/移位器
  * 计数器 → 移位寄存器/LFSR
  * MUX → 解码器/编码器
  * FIFO → 移位寄存器
  * UART → SPI/I2C接口
- 注意：不要过度解释技术细节（如多项式、算法步骤）
- 使用标准的硬件术语，保持专业性
"""
        else:
            # 检查是否有重命名
            rename_rules = [h for h in history if h.rule_id == "T34" and h.rename_map]
            if rename_rules:
                last_rename = rename_rules[-1]
                prompt += f"""- 前序规则已重命名信号: {json.dumps(last_rename.rename_map, ensure_ascii=False)}
- 你的注释必须**简洁地解释这些新信号名**（**仅限1-2行**）
- 注释应当“听起来合理”，但与spec的直觉相反
- 例如：
  * 如果信号名包含 uart_ → 注释说"UART串口通信模块"
  * 如果信号名包含 spi_ → 注释说"SPI主控制器"
  * 如果信号名包含 mul_ → 注释说"乘法器单元"
- 注释要与信号名形成自洽的功能描述
- 不要过度解释技术细节
"""
            else:
                prompt += """- 生成一段**简洁的**误导性注释（**仅限1-2行**）
- 注释应当“听起来合理”，但与spec的直觉相反
- 选择一个明确的替代功能类型
"""
        
        prompt += """
**输出格式**: {"parameters": {"custom_text": "<注释内容>"}}
"""
        return prompt
    
    def _prompt_t34_linked(self, history: List[TransformHistory], spec: str, current_rtl: str) -> str:
        """T34联动prompt：重命名要延续前序的暗示方向"""
        
        prompt = """**当前规则**: T34（信号重命名）

**参数**: 
- `custom_map`: 信号重命名映射 {"old_name": "new_name"}
- `fallback_prefix`: 兜底前缀

**生成要求**：
"""
        
        if not history:
            prompt += """- 生成暗示**不同硬件功能**的信号重命名
- 选择一个明确的功能主题，例如：
  * 通信接口：uart_tx, spi_mosi, i2c_sda
  * 算术运算：mul_result, product, quotient
  * 存储控制：fifo_wr, ram_addr, cache_hit
  * 状态机：fsm_state, next_state, state_reg
- 所有重命名要遵循同一主题
- fallback_prefix也要与主题一致
"""
        else:
            # 检查是否有注释
            comment_rules = [h for h in history if h.rule_id == "T20"]
            if comment_rules:
                last_comment = comment_rules[-1]
                comment_text = last_comment.params_used.get("custom_text", "")
                prompt += f"""- 前序规则插入了注释: "{comment_text}"
- **关键**：你的重命名必须与注释描述的功能完全匹配
- 从注释中提取功能关键词，用于信号命名：
  * 注释提到"UART" → 用 uart_clk, uart_tx, uart_rx, tx_data 等
  * 注释提到"SPI" → 用 spi_clk, spi_mosi, spi_miso, spi_cs 等
  * 注释提到"乘法器" → 用 mul_a, mul_b, product, mul_valid 等
  * 注释提到"FIFO" → 用 fifo_din, fifo_dout, fifo_full, wr_en 等
- 让代码看起来像是在实现注释描述的功能
- fallback_prefix也要与功能主题一致
"""
            
            # 检查是否有其他重命名
            rename_rules = [h for h in history if h.rule_id == "T34" and h.rename_map]
            if rename_rules:
                prompt += f"""- 前序规则已有重命名，避免冲突
- 延续相同的功能主题和命名风格
"""
        
        prompt += """
**输出格式**: {"parameters": {"custom_map": {"clk": "uart_clk", "data": "tx_data"}, "fallback_prefix": "uart_"}}
"""
        return prompt
    
    def _prompt_t12_linked(self, history: List[TransformHistory], spec: str, target_signal: Optional[str]) -> str:
        """T12联动prompt：中间信号名要与重命名后的信号一致"""
        
        prompt = """**当前规则**: T12（中间信号）

**参数**: `wire_name` - 中间wire的名字

**联动要求**：
"""
        
        # 检查目标信号是否被重命名过
        if target_signal:
            rename_rules = [h for h in history if h.rule_id == "T34" and h.rename_map]
            for h in rename_rules:
                if target_signal in h.rename_map.values():
                    # 找到原始名字
                    original = [k for k, v in h.rename_map.items() if v == target_signal][0]
                    prompt += f"""- 目标信号 `{target_signal}` 是由 `{original}` 重命名而来
- 你的 wire_name 应该延续这个命名风格
- 例如：如果信号是 uart_clk，wire可以叫 uart_clk_valid 或 uart_enable
"""
                    break
        
        if "延续" not in prompt:
            prompt += "- 生成一个与spec语义相反的wire名字\n"
        
        prompt += """
**输出格式**: {"parameters": {"wire_name": "uart_clk_valid"}}
"""
        return prompt
    
    def _prompt_t31_linked(self, history: List[TransformHistory], spec: str) -> str:
        """T31联动prompt：简单中间信号"""
        
        prompt = """**当前规则**: T31（简单中间信号）

**参数**: `wire_name` - 中间wire的名字

**联动要求**：
"""
        
        rename_rules = [h for h in history if h.rule_id == "T34" and h.rename_map]
        if rename_rules:
            last_rename = rename_rules[-1]
            prompt += f"""- 前序规则已重命名: {json.dumps(last_rename.rename_map, ensure_ascii=False)}
- 你的wire_name应该延续这个命名风格
"""
        else:
            prompt += "- 生成一个与spec语义相反的wire名字\n"
        
        prompt += """
**输出格式**: {"parameters": {"wire_name": "tmp_wire"}}
"""
        return prompt
    
    def _prompt_t19_linked(self, history: List[TransformHistory], spec: str, current_rtl: str) -> str:
        """T19联动prompt：死代码要结合前序变换"""
        
        prompt = """**当前规则**: T19（死代码注入）

**参数**: `custom_dead_stmts` - 死代码语句（会被放入if(1'b0)中）

**联动要求**：
"""
        
        if not history:
            prompt += "- 生成与spec行为相反的控制逻辑\n"
        else:
            # 检查重命名
            rename_rules = [h for h in history if h.rule_id == "T34" and h.rename_map]
            if rename_rules:
                last_rename = rename_rules[-1]
                prompt += f"""- 前序规则已重命名信号: {json.dumps(last_rename.rename_map, ensure_ascii=False)}
- 你的死代码应该使用这些新名字
- 例如：如果重命名为 uart_tx，死代码可以写 uart_tx <= 1'b0;
- 这样看起来更"真实"，增强误导性
"""
            
            # 检查注释
            comment_rules = [h for h in history if h.rule_id == "T20"]
            if comment_rules:
                last_comment = comment_rules[-1]
                comment_text = last_comment.params_used.get("custom_text", "")
                prompt += f"""- 前序规则插入了注释: "{comment_text}"
- 你的死代码应该"实现"注释暗示的功能
- 形成"注释+死代码"的双重欺骗
"""
        
        prompt += """
**硬约束**：
- 不要输出 always/module/endmodule 等外层关键字
- 只输出语句本体（if/case/赋值等）
- 每条语句以分号结尾

**输出格式**: {"parameters": {"custom_dead_stmts": "uart_tx <= 1'b0; uart_en <= 1'b1;"}}
"""
        return prompt
    
    def _get_default_params(self, rule_id: str) -> Dict[str, Any]:
        """获取默认参数（LLM失败时的回退）"""
        defaults = {
            "T20": {"custom_text": "UART Transmitter - 9600 baud"},
            "T34": {"custom_map": {"clk": "clk_g"}, "fallback_prefix": "obf_"},
            "T12": {"wire_name": "tmp_wire"},
            "T31": {"wire_name": "mid_wire"},
            "T19": {"custom_dead_stmts": "// dead code"}
        }
        return defaults.get(rule_id, {})


# 使用示例
if __name__ == '__main__':
    generator = LinkedParamGenerator(
        base_url="http://localhost:8001/v1",
        model="verilog_attack_merged_bal500"
    )
    
    # 模拟场景：先T20注释，再T34重命名
    spec = "Design a counter that increments on each clock cycle and resets when reset is high."
    
    original_rtl = """
module counter(
    input clk,
    input rst,
    output reg [7:0] count
);
    always @(posedge clk) begin
        if (rst)
            count <= 0;
        else
            count <= count + 1;
    end
endmodule
"""
    
    # Step 1: 生成T20参数（无历史）
    params_t20 = generator.generate_linked_params(
        rule_id="T20",
        spec=spec,
        original_rtl=original_rtl,
        current_rtl=original_rtl,
        transform_history=[]
    )
    print("T20参数:", params_t20)
    
    # 模拟应用T20后的代码
    current_rtl_after_t20 = f"""
// {params_t20.get('custom_text', 'UART Transmitter')}
{original_rtl}
"""
    
    # Step 2: 生成T34参数（有T20历史）
    history = [
        TransformHistory(
            rule_id="T20",
            params_used=params_t20,
            transformed_code=current_rtl_after_t20,
            description="插入误导性注释"
        )
    ]
    
    params_t34 = generator.generate_linked_params(
        rule_id="T34",
        spec=spec,
        original_rtl=original_rtl,
        current_rtl=current_rtl_after_t20,
        transform_history=history
    )
    print("T34参数（联动）:", params_t34)
