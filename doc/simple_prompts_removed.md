# ✅ 删除简化版Prompts完成

## 📊 删除统计

| 项目 | 删除前 | 删除后 | 减少 |
|------|--------|--------|------|
| **prompts.py行数** | 389行 | **304行** | **-85行 (-22%)** |
| **Prompt模板数** | 10个 | **5个** | -50% |
| **LLM_PARAM_RULES字段** | 每规则3个 | **每规则2个** | -33% |
| **导出符号数** | 15个 | **10个** | -33% |

## 🗑️ 删除的内容

### 1. 简化版Prompt模板（-85行）
```python
# 删除了以下5个简化版：
❌ ATTACK_T12_INTERMEDIATE_SIGNAL_PROMPT_SIMPLE
❌ ATTACK_T19_DEAD_CODE_PROMPT_SIMPLE
❌ ATTACK_T20_COMMENT_PROMPT_SIMPLE
❌ ATTACK_T31_SIMPLE_INTERMEDIATE_PROMPT_SIMPLE
❌ ATTACK_T34_RENAME_PROMPT_SIMPLE
```

### 2. LLM_PARAM_RULES配置简化
**删除前**：
```python
'T12': {
    'param_name': 'wire_name',
    'prompt_template': xxx,
    'prompt_simple': xxx,  # ← 删除
}
```

**删除后**：
```python
'T12': {
    'param_name': 'wire_name',
    'prompt_template': xxx,
}
```

### 3. format_attack_prompt函数简化
**删除前**：
```python
def format_attack_prompt(
    ...,
    use_simple: bool = False,  # ← 删除
) -> str:
    config = LLM_PARAM_RULES[rule_id]
    template = config['prompt_simple'] if use_simple else config['prompt_template']  # ← 删除
```

**删除后**：
```python
def format_attack_prompt(...) -> str:
    template = LLM_PARAM_RULES[rule_id]['prompt_template']
```

### 4. Pipeline中的fallback逻辑（-10行）
**删除前**：
```python
try:
    prompt = format_attack_prompt(..., use_simple=False)
except Exception as e:
    logger.warning(f"回退到简单版")
    config = LLM_PARAM_RULES[rule_id]
    prompt = config.get('prompt_simple', config['prompt_template']).format(...)
```

**删除后**：
```python
prompt = format_attack_prompt(...)
```

## ✅ 验证测试

### 1. 语法检查
```bash
✅ config/prompts.py 语法正确
✅ pipeline/6_generate_attack_dataset.py 语法正确
✅ config/__init__.py 语法正确
```

### 2. 导入测试
```python
✅ 导入成功
✅ LLM规则数: 5
✅ 支持的规则: ['T12', 'T19', 'T20', 'T31', 'T34']
✅ 所有规则配置正确（无prompt_simple）
✅ format_attack_prompt签名正确（无use_simple参数）
```

### 3. 功能测试
```bash
python pipeline/6_generate_attack_dataset.py --help  # ✅ 正常
```

## 📝 修改的文件

1. **config/prompts.py**
   - 删除5个简化版prompt模板
   - 简化`LLM_PARAM_RULES`配置（移除`prompt_simple`字段）
   - 简化`format_attack_prompt()`函数（移除`use_simple`参数）
   - 更新`__all__`导出列表

2. **config/__init__.py**
   - 删除5个简化版的导入
   - 更新`__all__`导出列表

3. **pipeline/6_generate_attack_dataset.py**
   - 删除fallback到简化版的逻辑
   - 删除`use_simple=False`参数

## 🎯 删除原因

### 为什么有简化版？
原本设计为**备用方案**：
- 当专业版格式化失败时，回退到简化版
- 简化版prompt更短、更简单，理论上更不容易出错

### 为什么删除？
1. **从未主动使用**
   - 代码中`use_simple`始终为`False`
   - 只在异常时才fallback

2. **Fallback几乎不会触发**
   - `format_attack_prompt()`格式化失败极少见
   - 如果缺少必要参数，简化版也会失败

3. **增加维护负担**
   - 代码量翻倍（10个prompt vs 5个）
   - 每次修改需要同步两个版本
   - 配置字典和导出列表都重复

4. **效果可能更差**
   - 简化版prompt质量低
   - 可能导致LLM生成效果变差
   - 违背了"使用专业版prompt"的初衷

## 📈 总体精简效果

从最初的565行到现在的304行：

| 阶段 | 行数 | 累计减少 |
|------|------|----------|
| **原始版本** | 565行 | - |
| 删除文档字符串 | 389行 | -176行 (-31%) |
| **删除简化版** | **304行** | **-261行 (-46%)** |

### 代码质量提升
- ✅ **更简洁**：代码量减半
- ✅ **更清晰**：只有一个prompt版本
- ✅ **更易维护**：修改不需要同步两个版本
- ✅ **更可靠**：删除了几乎不会触发的fallback逻辑
- ✅ **功能完整**：所有核心功能保持不变

## 🚀 后续建议

### 1. 如果需要prompt变体
不要用`prompt_simple`，而是：
- 在`prompt_template`中用条件分支
- 或创建独立的规则ID（如`T20_SHORT`）

### 2. 错误处理
格式化失败应该：
- 直接抛出异常并记录日志
- 由上层决定如何处理（跳过或重试）
- 不要悄悄切换到低质量的备选方案

---

**删除时间**: 2026-03-26  
**删除类型**: 🧹 代码清理  
**影响范围**: config/, pipeline/  
**风险等级**: 🟢 低（简化版从未被实际使用）
