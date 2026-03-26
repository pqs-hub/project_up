# ✅ Prompts v2.0 专业版升级总结

## 🎯 升级目标

参考 `scripts/eval/textual_param_generator.py` 的专业设计风格，重构所有prompt模板，提升攻击效果和代码质量。

## 📦 主要改进

### 1. **专业版Prompt模板** ⭐

所有攻击规则都升级为专业版prompt，包含：

#### T20 - 误导性注释
```python
ATTACK_T20_COMMENT_PROMPT_TEMPLATE
```

**特点**：
- ✅ 详细的功能替换示例（加法器→乘法器，计数器→LFSR等）
- ✅ 明确的注释长度限制（1-2行）
- ✅ 专业术语和格式要求
- ✅ 禁止明显的测试标记

#### T34 - 对抗性信号重命名
```python
ATTACK_T34_RENAME_PROMPT_TEMPLATE
```

**特点**：
- ✅ 功能主题选择（通信接口、算术运算、存储控制、状态机）
- ✅ 要求所有重命名遵循同一主题
- ✅ 支持fallback_prefix
- ✅ 严格的Verilog命名规范检查

#### T19 - 死代码生成
```python
ATTACK_T19_DEAD_CODE_PROMPT_TEMPLATE
```

**特点**：
- ✅ 详细的语法约束（不要always/initial等）
- ✅ 赋值约束（只使用可写信号）
- ✅ SPEC定向误导策略
- ✅ 明确的不可达条件说明

### 2. **通用组件提取** 🔧

```python
COMMON_ATTACK_REQUIREMENTS = """
你是Verilog代码重构专家...

**核心目标**：
生成的参数要让代码看起来像是在实现一个**不同的硬件功能**...

**关键要求**：
1. 暗示明确不同的硬件模块类型
2. 保持专业性和自然性
3. 满足规则类型要求

**禁止**：
- 不要使用test_, debug_等标记
- 不要直接说明\"这是误导\"
...
"""
```

**优势**：
- ✅ 统一的要求描述
- ✅ 避免重复
- ✅ 易于维护

### 3. **简化版保持兼容** 📦

每个规则都提供两个版本：

| 版本 | 变量名后缀 | 用途 |
|------|-----------|------|
| 专业版 | `_TEMPLATE` | 默认，详细约束和示例 |
| 简化版 | `_SIMPLE` | 向后兼容，快速测试 |

```python
LLM_PARAM_RULES = {
    'T20': {
        'param_name': 'custom_text',
        'prompt_template': ATTACK_T20_COMMENT_PROMPT_TEMPLATE,  # 默认
        'prompt_simple': ATTACK_T20_COMMENT_PROMPT_SIMPLE,      # 兼容
    },
    ...
}
```

### 4. **智能格式化函数** 🚀

新增 `format_attack_prompt()` 辅助函数：

```python
def format_attack_prompt(
    rule_id: str,
    code_snippet: str,
    task_prompt: str = "",
    signal_names: str = "",
    writable_signals: str = "<unknown>",
    readable_signals: str = "<unknown>",
    use_simple: bool = False,
) -> str:
    """智能格式化攻击规则prompt"""
    ...
```

**功能**：
- ✅ 自动选择专业版/简化版
- ✅ 自动处理参数替换
- ✅ 代码长度截断（8000字符）
- ✅ 规则特定参数处理

## 🔧 集成到生成流程

### 修改的文件

#### 1. `pipeline/6_generate_attack_dataset.py`

**修改1**: `generate_llm_param` 方法
```python
# 之前
def generate_llm_param(self, rule_id: str, code: str, **context):
    prompt = config['prompt_template'].format(code_snippet=code[:500])
    ...

# 之后
def generate_llm_param(self, rule_id: str, code: str, spec: str = "", **context):
    prompt = format_attack_prompt(
        rule_id=rule_id,
        code_snippet=code,
        task_prompt=spec,
        signal_names=signal_names,
        use_simple=False,  # 使用专业版
    )
    ...
```

**修改2**: `get_param_sets` 方法
```python
# 添加spec参数
def get_param_sets(self, rule_id: str, code: str, spec: str = ""):
    llm_param = self.generate_llm_param(rule_id, code, spec=spec)
    ...
```

**修改3**: `try_attack_with_rule` 调用
```python
# 传入spec以支持专业版prompt
param_sets = self.get_param_sets(rule_id, rtl, spec=spec)
```

## 📊 Prompt对比

### T20示例

#### 简化版
```
请为以下Verilog代码生成一个误导性的注释。
代码：...
只输出注释内容，不要其他解释：
```

#### 专业版
```
规则：T20（误导性注释）

请生成一段**简洁的**误导性注释 custom_text（**仅限1-2行**）。

注释应当"听起来合理"，但在关键信息上与spec的直觉相反...

功能替换示例：
  * 加法器 → 乘法器/移位器
  * 计数器 → 移位寄存器/LFSR
  * MUX → 解码器/编码器
  ...

注意：
- 注释必须简洁，不要过度解释技术细节
- 使用标准的硬件术语，保持专业性
- 格式：单行注释用 //，多行用 /* */

{通用要求...}

输出 schema 例如：{"parameters":{"custom_text":"<comment_text>"}}

### 功能规范
{task_prompt}

### 原始 RTL
```verilog
{code_snippet}
```
```

**改进点**：
- ✅ 明确规则说明
- ✅ 详细的功能替换示例
- ✅ 清晰的约束条件
- ✅ 标准的输出格式
- ✅ 包含功能规范上下文

## 🎯 预期效果提升

### 1. 更高的语义误导性
- 专业的功能替换（而非简单的语义反转）
- 一致的主题（T34的所有重命名遵循同一主题）

### 2. 更好的代码质量
- 符合Verilog规范
- 避免语法错误
- 不使用明显的测试标记

### 3. 降低失败率
- T19 testbench失败率预计降低60%+（明确约束）
- T34 判断失败率预计降低（主题一致性）

### 4. 更强的对抗性
- 结合SPEC的定向误导（T19）
- 功能级别的替换（而非字面级别）

## 📖 使用方法

### 查看所有Prompts
```bash
python scripts/view_prompts.py
```

### 使用专业版（默认）
```bash
python pipeline/6_generate_attack_dataset.py \
    --eval-file data/verilog_eval_correct_only.json \
    --output data/attack_dataset.jsonl \
    --max-samples 10 \
    --use-cot \
    --enable-llm-params \
    --attack-base-url http://localhost:8002/v1 \
    --attack-model "obfuscation_merged"
```

### 切换到简化版（测试用）
编辑 `pipeline/6_generate_attack_dataset.py`：
```python
prompt = format_attack_prompt(
    ...,
    use_simple=True,  # 切换到简化版
)
```

### 修改Prompt
```bash
# 1. 编辑配置文件
vim config/prompts.py

# 2. 找到对应的_TEMPLATE变量
# 例如：ATTACK_T20_COMMENT_PROMPT_TEMPLATE

# 3. 修改内容并保存

# 4. 重新运行，立即生效
```

## ✅ 完成清单

- ✅ 重构所有攻击规则prompt（T19/T20/T34）
- ✅ 添加通用组件 `COMMON_ATTACK_REQUIREMENTS`
- ✅ 提供简化版保持向后兼容
- ✅ 新增 `format_attack_prompt()` 辅助函数
- ✅ 集成到 `pipeline/6_generate_attack_dataset.py`
- ✅ 更新 `__all__` 导出列表
- ✅ 更新版本历史到 v2.0
- ✅ 测试prompt格式化功能

## 🚀 下一步

### 短期
1. 使用专业版prompt生成数据集
2. 对比专业版 vs 简化版的效果
3. 根据效果调整prompt

### 中期
1. 添加更多规则的专业版prompt（T12, T31, T45等）
2. 建立prompt效果追踪系统
3. 收集最佳实践

### 长期
1. 基于效果数据优化prompt
2. 建立prompt模板库
3. 自动化A/B测试不同prompt版本

## 📚 相关文档

- [config/prompts.py](../config/prompts.py) - Prompt配置文件
- [config/README_prompts.md](../config/README_prompts.md) - 使用说明
- [scripts/eval/textual_param_generator.py](../scripts/eval/textual_param_generator.py) - 参考实现
- [pipeline/6_generate_attack_dataset.py](../pipeline/6_generate_attack_dataset.py) - 数据集生成

---

**升级日期**: 2026-03-26  
**版本**: v2.0  
**状态**: ✅ 完成并集成
