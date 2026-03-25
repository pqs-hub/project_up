# LLM参数生成功能说明

## ✅ 你的系统**已经支持**LLM生成参数！

位置：`/data3/pengqingsong/LLM_attack/scripts/eval/textual_param_generator.py`

## 📋 功能概述

### 支持的规则

你的系统已经实现了**5个文本类规则**的LLM参数生成：

| 规则 | 参数 | LLM生成内容 |
|------|------|------------|
| **T12** | `wire_name` | 中间信号名（语义反转） |
| **T31** | `wire_name` | 简单中间信号名（语义反转） |
| **T34** | `custom_map`, `fallback_prefix` | 重命名映射（语义反转） |
| **T20** | `custom_text` | 误导性注释 |
| **T19** | `custom_dead_stmts` | 死代码语句（结合spec定向误导） |

### 核心设计思想

**对抗性参数生成**：让LLM生成的参数与spec的语义**直觉相反**，从而误导验证模型

```python
# 例如：spec说 enable=1 时为真
# LLM生成的参数：
{
    "wire_name": "disabled",      # T12
    "custom_map": {               # T34
        "enable": "disable_n",
        "valid": "invalid"
    },
    "custom_text": "active low enable signal"  # T20（实际是高有效）
}
```

## 🎯 LLM生成的优势

### 1. **语义对抗性强**

```python
# T20: 误导性注释生成
prompt = f"""
规则：T20（Misleading Comment）。
请生成一段误导性注释 custom_text。
注释应当"听起来合理"，但在关键信息上与 spec 的直觉相反。
注释内容尽量使用 spec 中出现的关键词/术语（但要做语义反转）。

### 功能规范
{task_prompt}

### 原始 RTL
{rtl}
"""

# LLM输出示例：
# {"parameters": {"custom_text": "UART Receiver - parity check disabled"}}
# （实际spec可能是UART Transmitter with parity）
```

### 2. **上下文自适应**

LLM会根据**spec + RTL**生成针对性的参数：

```python
# T19: 死代码生成（结合spec）
prompt = f"""
结合 SPEC 的定向误导：
1) 从 SPEC 里提取至少 2 条"关键行为/条件"
2) 在 custom_dead_stmts 里写一段"看起来符合这些关键行为"的控制逻辑
3) 把 SPEC 中对"应当成立/应当增加/应当清零"的直觉方向反过来写

SPEC={spec}
可写信号：{writable_signals}
可读信号：{readable_signals}
"""

# LLM会生成与spec行为相反但看起来合理的死代码
```

### 3. **多样性高**

不受预定义模板限制，每次生成都可能不同

## 🔧 使用方式

### 在 `evaluate_rules.py` 中使用

```python
from textual_param_generator import generate_textual_rule_parameters

# 为文本类规则生成参数
if rule_id in ["T12", "T31", "T34", "T20", "T19"]:
    params = generate_textual_rule_parameters(
        base_url="http://localhost:8001/v1",
        model="qwen2.5-coder-7b",  # 或其他模型
        api_key="EMPTY",
        rule_id=rule_id,
        task_prompt=spec,
        rtl=rtl,
        target_token=k,
        target_line=target_line,
        target_signal=target_signal,
        t34_old_name=old_name,  # T34专用
        t19_writable_signals=writable,  # T19专用
        t19_readable_signals=readable,  # T19专用
        temperature=0.0,
        max_tokens=256
    )
    # params = {"wire_name": "...", ...}
```

### 配置模型

```python
# 使用不同的模型生成参数
params = generate_textual_rule_parameters(
    base_url="http://localhost:8001/v1",
    model="qwen2.5-coder-7b",  # 基础模型
    # model="deepseek-coder-33b",  # 更强的模型
    # model="gpt-4o",  # 闭源模型
    ...
)
```

## 📊 Prompt设计亮点

### 1. **明确的对抗性目标**

```python
common = """
你是 Verilog 代码混淆/变换专家。
目标（对抗性）：你生成的 parameters 会被用于执行指定 rule 后，
让变换后的 RTL 更"误导"验证模型的直觉/模式匹配。
也就是说：parameters 应当尽量与功能规范（spec）中描述的行为"直觉相反"。
"""
```

### 2. **硬约束保证可编译性**

```python
硬约束：
1) parameters 必须满足该 rule 的类型与字段要求
2) 若 rule 涉及标识符，请选择合法且不容易与关键字冲突的名字
3) 变换参数应尽量保证"确实发生代码变化"（不让重命名退化为原名）
```

### 3. **Schema引导输出格式**

```python
# T34示例
schema = '{"parameters":{"custom_map":{"<old_name>":"<new_name>"},"fallback_prefix":"<str>"}}'
body = f"""
输出 schema 例如：{schema}
"""
```

### 4. **T19的特殊设计**

最复杂的prompt，结合spec生成定向误导的死代码：

```python
# 提取spec关键行为
"1) 从 SPEC 里提取至少 2 条"关键行为/条件"，例如：复位/使能/握手/保持/更新规则。"

# 生成反向逻辑
"2) 在 custom_dead_stmts 里写一段"看起来符合这些关键行为"的控制逻辑"
"3) 把 SPEC 中对"应当成立/应当增加/应当清零"的直觉方向反过来写"

# 约束可编译性
"- 如果你需要写左值赋值，请只把左值写成下列可写信号之一：{writable}"
"- 右侧表达式可以使用下列可读信号：{readable}"
```

## 🆚 LLM vs 模板对比

| 方面 | 模板（AttackConfigGenerator） | LLM（textual_param_generator） |
|------|------------------------------|-------------------------------|
| **速度** | 极快（<1ms） | 慢（~100ms） |
| **多样性** | 受限于预定义列表 | 无限多样性 |
| **上下文感知** | ❌ 不感知spec/RTL | ✅ 根据spec/RTL生成 |
| **对抗性** | 中等（预设误导方向） | 强（语义反转） |
| **可控性** | 高（可预测） | 中（需解析验证） |
| **资源消耗** | 无 | 需要LLM推理 |
| **适用规则** | 所有规则 | 仅文本类规则 |

## 💡 为什么不默认启用？

### 当前策略：**混合使用**

1. **数值类规则**（T32位宽、T47 Shannon宽度等）：使用模板
   - 原因：数值参数空间小，模板足够
   - 优势：速度快

2. **文本类规则**（T12/T31/T34/T20/T19）：**可选LLM生成**
   - 在 `evaluate_rules.py` 中使用
   - 用于生成高质量攻击样本
   - 需要时启用

### 性能考虑

```python
# 假设生成30个攻击配置
# 模板模式：30 × 1ms = 30ms
# LLM模式：30 × 100ms = 3000ms（慢100倍）

# 对于大规模数据集（16000+样本），LLM生成会成为瓶颈
```

## 🚀 如何在你的实验中使用

### 选项1：在规则评估时使用

```bash
# 运行 evaluate_rules.py 时会自动使用LLM生成参数
python scripts/eval/evaluate_rules.py \
    --rules T12 T31 T34 T20 T19 \
    --llm-base-url http://localhost:8001/v1 \
    --llm-model qwen2.5-coder-7b
```

### 选项2：集成到AttackConfigGenerator

修改 `AttackConfigGenerator.py`，添加LLM生成选项：

```python
class AttackConfigGenerator:
    def __init__(self, ..., use_llm_for_textual=False):
        self.use_llm_for_textual = use_llm_for_textual
        if use_llm_for_textual:
            from textual_param_generator import generate_textual_rule_parameters
            self.llm_generator = generate_textual_rule_parameters
    
    def _sample_parameters(self, transform, rtl, vs):
        # 文本类规则使用LLM
        if self.use_llm_for_textual and transform.id in ["T12", "T31", "T34", "T20", "T19"]:
            return self._llm_sample_parameters(transform, rtl, vs)
        
        # 其他规则使用模板
        return self._template_sample_parameters(transform)
```

### 选项3：在联动实验中使用

```python
# 在 linked_combination_experiment.py 中
from textual_param_generator import generate_textual_rule_parameters

# 为联动组合生成更强的参数
if scenario.rule1 == "T20":  # 注释
    params1 = generate_textual_rule_parameters(
        base_url="http://localhost:8001/v1",
        model="qwen2.5-coder-7b",
        rule_id="T20",
        task_prompt=spec,
        rtl=rtl,
        target_token=0
    )

if scenario.rule2 == "T34":  # 重命名（根据注释）
    params2 = generate_textual_rule_parameters(
        base_url="http://localhost:8001/v1",
        model="qwen2.5-coder-7b",
        rule_id="T34",
        task_prompt=spec,
        rtl=transformed,  # 使用变换后的代码
        target_token=0
    )
```

## 📈 实验建议

### 对比实验：LLM vs 模板

```python
# 实验设计
1. 在100个样本上，分别用模板和LLM生成T20参数
2. 对比ASR和置信度下降
3. 分析LLM生成的参数质量

# 预期结果
- LLM生成的注释更具针对性
- ASR可能提升5-10%
- 但速度慢100倍
```

### 最佳实践

1. **训练数据生成**：使用模板（速度优先）
2. **高质量攻击**：使用LLM（质量优先）
3. **论文实验**：对比两种方法的效果差异

## 📝 总结

### 你的系统已经有LLM生成参数功能！

- ✅ 位置：`scripts/eval/textual_param_generator.py`
- ✅ 支持5个文本类规则
- ✅ 设计精良的对抗性prompt
- ✅ 在 `evaluate_rules.py` 中使用

### 为什么看起来"没启用"？

因为采用了**混合策略**：
- 数值类规则：模板（快）
- 文本类规则：LLM（质量高）
- 大规模生成：模板（效率）
- 高质量攻击：LLM（效果）

### 下一步建议

1. **查看使用示例**：`scripts/eval/evaluate_rules.py`
2. **运行对比实验**：模板 vs LLM的ASR差异
3. **集成到联动实验**：在联动组合中使用LLM生成参数
4. **论文写作**：强调LLM生成参数的对抗性设计

你的系统设计非常完善！🎉
