# 🐛 LLM参数解析Bug修复

## 问题背景

用户运行数据集生成命令后发现：
```bash
python pipeline/6_generate_attack_dataset.py \
    --max-samples 5 \
    --enable-llm-params
```

结果统计：
- **总样本数**: 55
- **成功样本数**: 0 ❌
- **失败样本数**: 55

### 失败类型分布
```
no_change: 36
attack_failed: 11
testbench_failed: 5  ← T19全部失败
judge_error: 3
```

---

## 🔍 根本原因

### 问题1: T19的JSON参数未正确解析

**现象**：
```python
# LLM输出
{
  "parameters": {
    "custom_dead_stmts": "if (enable) counter <= counter + 1;"
  }
}

# 实际解析结果
params['custom_dead_stmts'] = '{\n  "parameters": {...}\n}'  # ❌ 整个JSON字符串
```

**根因**：
- T19的prompt要求输出JSON格式：`{"parameters":{"custom_dead_stmts":"..."}}`
- 但解析逻辑只是简单的`content.strip('"').strip("'")`
- 导致将整个JSON字符串作为参数值，而非提取`parameters.custom_dead_stmts`

**影响**：
- T19生成的代码变为：`always @(*) begin if (1'b0) begin {\n  "parameters": {...}\n} end end`
- 语法错误 → testbench全部失败

---

### 问题2: JSON正则表达式不支持嵌套

**原有正则**：
```python
json_match = re.search(r'\{[^}]+\}', content)
```

**问题**：
- `[^}]+` 不能匹配包含`}`的内容
- 对于嵌套JSON如`{"parameters":{"wire_name":"xxx"}}`会失败
- 只能提取到`{"parameters":`，后续JSON解析报错

---

## ✅ 修复方案

### 改进1: 为T19/T20/T12/T31添加专门的JSON解析

```python
elif rule_id == 'T19':
    # T19: 尝试解析JSON，提取custom_dead_stmts
    try:
        import re
        json_match = re.search(r'\{.*\}', content, re.DOTALL)  # ← 支持嵌套
        if json_match:
            parsed = json.loads(json_match.group())
            # 标准格式：{"parameters":{"custom_dead_stmts":"..."}}
            if 'parameters' in parsed and 'custom_dead_stmts' in parsed['parameters']:
                return parsed['parameters']['custom_dead_stmts']
            # 简化格式：{"custom_dead_stmts":"..."}
            elif 'custom_dead_stmts' in parsed:
                return parsed['custom_dead_stmts']
    except:
        pass
    # 回退：直接返回文本
    return content.strip('"').strip("'").strip()
```

### 改进2: 使用宽松正则匹配嵌套JSON

**修改前**：
```python
json_match = re.search(r'\{[^}]+\}', content)
```

**修改后**：
```python
json_match = re.search(r'\{.*\}', content, re.DOTALL)
```

**优点**：
- `.*` 可以匹配任意内容（包括`}`）
- `re.DOTALL` 使`.`匹配换行符
- 支持多层嵌套JSON

---

## 📊 修复后预期效果

### T19参数解析

| 场景 | LLM输出 | 解析结果（修复前） | 解析结果（修复后） |
|------|---------|-------------------|-------------------|
| **标准JSON** | `{"parameters":{"custom_dead_stmts":"x=1;"}}` | ❌ 整个字符串 | ✅ `"x=1;"` |
| **简化JSON** | `{"custom_dead_stmts":"x=1;"}` | ❌ 整个字符串 | ✅ `"x=1;"` |
| **纯文本** | `x=1;` | ✅ `"x=1;"` | ✅ `"x=1;"` |

### T12/T31参数解析

| 场景 | LLM输出 | 解析结果（修复前） | 解析结果（修复后） |
|------|---------|-------------------|-------------------|
| **标准JSON** | `{"parameters":{"wire_name":"disabled"}}` | ❌ 失败 | ✅ `"disabled"` |
| **简化JSON** | `{"wire_name":"disabled"}` | ✅ `"disabled"` | ✅ `"disabled"` |
| **纯文本** | `disabled` | ✅ `"disabled"` | ✅ `"disabled"` |

---

## 🧪 测试验证

### 单元测试

```python
# 测试T19解析
def test_t19_parsing():
    # 标准格式
    content = '{"parameters":{"custom_dead_stmts":"x <= 1;"}}'
    result = parse_llm_param('T19', content)
    assert result == "x <= 1;"
    
    # 简化格式
    content = '{"custom_dead_stmts":"x <= 1;"}'
    result = parse_llm_param('T19', content)
    assert result == "x <= 1;"
    
    # 纯文本
    content = 'x <= 1;'
    result = parse_llm_param('T19', content)
    assert result == "x <= 1;"
```

### 集成测试

```bash
# 重新运行数据集生成
python pipeline/6_generate_attack_dataset.py \
    --max-samples 5 \
    --enable-llm-params \
    --verbose
```

**预期结果**：
- T19 testbench失败率：5/5 → 0-2/5
- T20/T31攻击成功率：0/10 → 1-3/10（取决于prompt质量）

---

## 📝 相关文件

### 修改的文件
- `pipeline/6_generate_attack_dataset.py`
  - 行205-256：改进`generate_llm_param`方法的参数解析逻辑

### 影响的规则
- ✅ T12（Intermediate Signal）
- ✅ T19（False Pattern Injection）
- ✅ T20（Misleading Comment）
- ✅ T31（Simple Intermediate）
- ✅ T34（Signal Rename）- 已有正确的JSON解析

---

## 🎯 下一步优化

### 1. Prompt优化

**问题**：T20/T31攻击成功率低（判断仍正确）

**原因**：
- LLM生成的参数对抗性不足
- 注释/wire名不够误导性

**改进方向**：
1. 在prompt中添加更多反例（什么是**不够对抗的**）
2. 强调"功能替换"而非"功能描述"
3. 提供失败案例和成功案例对比

### 2. 采样策略优化

**问题**：前5个样本都没有三元表达式 → T12无候选

**改进方向**：
- 按规则类型分层采样
- 对每个规则选择适合的样本
- 提高样本多样性

### 3. 参数验证

**问题**：LLM生成的参数可能不合法（如Verilog关键字）

**改进方向**：
```python
def validate_wire_name(name: str) -> bool:
    """验证wire名是否合法"""
    # 检查Verilog关键字
    if name in VERILOG_KEYWORDS:
        return False
    # 检查标识符格式
    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', name):
        return False
    return True
```

---

## ✅ 总结

### 修复内容
- ✅ 修复T19/T20的JSON参数解析bug
- ✅ 改进T12/T31/T34的正则表达式，支持嵌套JSON
- ✅ 统一所有规则的参数解析逻辑

### 预期效果
- T19 testbench失败率：**100% → 0-40%**
- 整体攻击成功率：**0% → 3-5%**（小样本测试）

### 后续工作
1. 重新运行实验，验证修复效果
2. 优化T20/T31的prompt，提高对抗性
3. 添加参数验证机制

---

**修复时间**: 2026-03-26  
**影响规则**: T12, T19, T20, T31  
**修复类型**: 🐛 Bugfix
