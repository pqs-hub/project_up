# T19攻击成功率低的原因分析

## 问题现象

在 `attack_dataset_exhaustive.jsonl` 数据集中：
- **T19样本数**: 仅3个（占0.0%）
- **对比**: T20有10,796个样本，T45有10,018个样本

## T19规则说明

**规则名称**: 虚假模式注入（False Pattern / 死代码注入）  
**规则ID**: T19  
**攻击方式**: 注入永远不会执行的死代码块（如 `if (1'b0) begin ... end`）

### 代码示例

```verilog
// 原始代码
assign out = a & b;

// T19变换后
always @(*) begin
  if (1'b0) begin
    // 这段代码永远不会执行
    temp = a | b;
  end
end
assign out = a & b;
```

## 核心原因分析

### 1. **数据集生成的成功条件**

在 `6_generate_attack_dataset.py` 中，"攻击成功"需要**同时满足**：

```python
# 攻击成功的定义
success = (
    testbench_passed == True      # ✅ 功能正确（testbench通过）
    AND judge_fooled == True      # ✅ 判断模型被欺骗（判断为错误）
)
```

### 2. **T19的特殊性**

T19是**死代码注入**，具有以下特点：

| 特性 | T19表现 | 影响 |
|------|---------|------|
| **功能影响** | 无（死代码不执行） | ✅ testbench几乎总是通过 |
| **语法复杂度** | 低（简单的if条件） | ❌ 判断模型容易识别 |
| **LLM误导性** | 理论上高（90.5%） | 但实际生成时难以达到 |

### 3. **对比单规则评估数据**

根据 `SINGLE_RULE_ATTACK_SUMMARY_LATEST.md`：

| 指标 | 数值 | 说明 |
|------|------|------|
| T19总样本数 | 17,483 | 单规则评估时大量测试 |
| Ground Truth攻击成功 | 43个 (0.3%) | testbench失败的极少 |
| LLM攻击成功 | 14,945个 (90.5%) | **LLM很容易被误导** |
| LLM成功率排名 | 第2名 | 仅次于T45（98.2%） |

**关键发现**: T19在单规则评估中LLM攻击成功率高达90.5%，但在数据集生成时只有3个样本！

## 深层原因推测

### 原因1: 参数组合限制

```python
# 6_generate_attack_dataset.py 中的T19参数配置
DEFAULT_PARAM_SETS = {
    'T19': [
        {},  # 默认死代码
        {'custom_dead_stmts': 'temp_var = 0;'},  # 自定义死代码
    ],
}
```

- **只有2种参数组合**，而其他规则可能有更多变化
- 死代码模式固定，判断模型可能已"学会"识别这些模式

### 原因2: 判断模型的识别能力

当前使用的判断模型可能：
1. **已针对简单死代码优化**：能识别 `if (1'b0)` 这类明显的死代码
2. **训练数据包含死代码样本**：模型见过类似模式
3. **启用了CoT推理**：能通过逐步分析发现死代码

### 原因3: 测试样本选择

- 数据集生成时可能只测试了部分任务（`--max-samples` 限制）
- T19在某些任务类型上效果更好，但这些任务未被充分测试

### 原因4: 死代码复杂度不足

```verilog
// 简单死代码（容易识别）
if (1'b0) begin
  temp = a | b;
end

// 复杂死代码（更难识别，但当前未使用）
if (enable && !enable) begin
  // 矛盾条件
  result = complex_computation(...);
end
```

当前T19只使用简单的 `1'b0` 条件，判断模型容易识别。

## 数据对比

### 单规则评估 vs 数据集生成

| 场景 | T19样本数 | 成功条件 | 说明 |
|------|-----------|----------|------|
| **单规则评估** | 17,483 | testbench失败 OR LLM误判 | 只要一个条件满足即可 |
| **数据集生成** | 3 | testbench通过 AND LLM误判 | **两个条件必须同时满足** |

**差异**: 单规则评估中的14,945个"LLM攻击成功"样本，在数据集生成时被过滤掉了，因为：
- 它们可能testbench失败了（不符合"功能正确"要求）
- 或者在遍历生成时，使用的死代码模式被判断模型识破了

## 解决方案建议

### 方案1: 增加参数多样性 🌟

```python
# 扩展T19的参数组合
'T19': [
    {},  # 默认模板
    {'target_token': 0},  # 位置0
    {'target_token': 1},  # 位置1
    {'target_token': 2},  # 位置2
    {'custom_dead_stmts': 'temp_var = 0;'},
    {'custom_dead_stmts': 'dummy = a ^ a;'},  # 永远为0
    {'custom_dead_stmts': 'flag = enable && !enable;'},  # 矛盾条件
]
```

### 方案2: 使用LLM生成死代码内容 🔥

类似T20生成注释、T34生成重命名映射：

```python
# 让LLM生成更具迷惑性的死代码
LLM_PARAM_RULES = {
    'T19': {
        'param_name': 'custom_dead_stmts',
        'prompt_template': '生成一段看起来有意义但永远不会执行的Verilog代码...',
    }
}
```

### 方案3: 放宽筛选条件

修改数据集生成逻辑，允许部分testbench失败的样本：

```python
# 当前逻辑
if testbench_passed and judge_fooled:
    save_sample()

# 修改后（针对T19等特殊规则）
if (testbench_passed and judge_fooled) or \
   (rule_id == 'T19' and judge_fooled and confidence > 0.8):
    save_sample()
```

### 方案4: 从单规则评估中提取 ⭐ **推荐**

直接使用单规则评估中的14,945个LLM攻击成功样本：

```bash
# 从单规则评估结果中提取T19成功样本
python scripts/extract_from_single_rule_eval.py \
  --rule T19 \
  --eval-dir legacy/rule_eval/metrics_conf_v2_on_fullall_adv \
  --require-llm-attack-success \
  --output data/T19_from_single_rule.jsonl
```

优势：
- 已有14,945个现成的LLM攻击成功样本
- 避免重新生成的时间成本
- 可以选择高质量样本（高置信度、复杂度等）

## 实验验证

### 验证1: 检查现有3个T19样本的特征

```bash
# 提取T19样本查看
grep '"attack_rule": "T19"' data/attack_dataset_exhaustive.jsonl > /tmp/T19_samples.jsonl
cat /tmp/T19_samples.jsonl | jq .
```

### 验证2: 测试不同死代码模式的效果

```python
# 测试脚本
dead_code_patterns = [
    'temp = 0;',
    'dummy = a ^ a;',
    'flag = enable && !enable;',
    'if (1) begin end else begin temp = a; end',
]

for pattern in dead_code_patterns:
    test_attack_with_pattern('T19', {'custom_dead_stmts': pattern})
```

## 总结

### T19攻击成功率低的核心原因

1. ✅ **死代码不改变功能** → testbench容易通过
2. ❌ **简单死代码模式** → 判断模型容易识别
3. ❌ **参数组合有限** → 只有2种固定模式
4. ❌ **双重条件约束** → testbench通过 AND 判断模型误判

### 核心矛盾

```
单规则评估: 14,945个LLM攻击成功（90.5%成功率）
     ↓
数据集生成: 仅3个成功样本（0.0076%转化率）
```

**差距原因**: 
- 单规则评估使用多种死代码模板和位置
- 数据集生成只用了2种固定参数组合
- 判断模型可能在特定死代码模式上表现更好

### 推荐行动

🥇 **优先**: 从单规则评估结果中直接提取T19成功样本（14,945个现成资源）  
🥈 **中期**: 增加T19的参数多样性（位置、死代码内容）  
🥉 **长期**: 使用LLM生成更具迷惑性的死代码内容
