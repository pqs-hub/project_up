# 攻击位置记录设计

## 问题描述

在生成攻击数据集时，需要：
1. **攻击时**：在候选位置中选择一个位置进行攻击（用索引）
2. **记录时**：保存有语义的位置信息（用信号名或行号）

## 为什么需要语义信息？

### ❌ 只记录target_token的问题

```json
{
    "attack_rule": "T34",
    "attack_params": {
        "target_token": 2,  // 第3个候选？哪个信号？
        "custom_map": {"enable": "disable"}
    }
}
```

**问题**：
- 无法直接看出攻击了哪个信号
- 代码改动后，候选列表可能变化，target_token=2可能对应不同的信号
- 无法准确复现攻击

### ✅ 记录语义信息的优势

```json
{
    "attack_rule": "T34",
    "attack_params": {
        "target_signal": "enable",  // 清晰：攻击的是enable信号
        "target_line": 9,           // 明确：在第9行
        "custom_map": {"enable": "disable"}
    }
}
```

**优势**：
- ✅ 一眼看出攻击了哪个信号
- ✅ 即使代码结构改变，仍能通过信号名找到对应位置
- ✅ 可以准确复现攻击
- ✅ 便于分析和调试

## 双向转换机制

### 1️⃣ 攻击时：索引选择

```python
# 遍历所有候选位置进行攻击
for target_token in range(len(candidates)):
    transformed = engine.apply_transform(
        code, 'T34',
        target_token=target_token,  # 用索引遍历
        custom_map={"enable": "disable"}
    )
```

### 2️⃣ 记录时：自动转换为语义信息

```python
# 应用变换后，自动提取语义信息
candidates = engine.get_target_line_signal(code, 'T34')
target_obj = candidates[target_token]  # 获取实际对象

# 提取信号名
if hasattr(target_obj, 'name'):
    params['target_signal'] = target_obj.name  # "enable"

# 提取行号
if hasattr(target_obj, 'start'):
    params['target_line'] = code[:target_obj.start].count('\n') + 1  # 9

# 移除无语义的索引
del params['target_token']
```

### 3️⃣ 复现时：语义转换回索引

```python
# 使用记录的语义信息复现攻击
transformed = engine.apply_transform(
    code, 'T34',
    target_signal="enable",  # 自动找到enable信号的位置
    custom_map={"enable": "disable"}
)

# 内部自动处理：
# target_signal="enable" → 查找候选列表 → target_token=2
```

## 实现示例

### 数据集记录格式

```json
{
    "task_id": "Prob001_mux",
    "attack_rule": "T34",
    "attack_params": {
        "target_signal": "enable",
        "target_line": 9,
        "custom_map": {"enable": "disable"}
    },
    "original_code": "...",
    "transformed_code": "...",
    "status": "success"
}
```

### 不同规则的语义信息

| 规则 | 优先提取 | 备选 | 示例 |
|------|---------|------|------|
| **T03** | `target_signal` (端口名) | `target_line` | `{"target_signal": "clk", "target_line": 3}` |
| **T07** | `target_signal` (第一个assign的lhs) | `target_line` | `{"target_signal": "temp", "target_line": 11}` |
| **T12** | `target_signal` (assign的lhs) | `target_line` | `{"target_signal": "out", "target_line": 15}` |
| **T19** | `target_line` (插入位置行号) | 无 | `{"target_line": 20}` |
| **T20** | `target_line` (插入位置行号) | 无 | `{"target_line": 8}` |
| **T34** | `target_signal` (信号名) | `target_line` | `{"target_signal": "enable", "target_line": 9}` |
| **T45** | `target_signal` (assign的lhs) | `target_line` | `{"target_signal": "data", "target_line": 12}` |

## 代码实现

### 数据集生成脚本中的转换逻辑

```python
# 应用变换（内部使用target_token）
transformed = engine.apply_transform(rtl, rule_id, 
    target_token=0,  # 使用第一个候选
    **llm_params)

# 转换为语义信息用于记录
try:
    candidates = engine.get_target_line_signal(rtl, rule_id)
    if candidates and len(candidates) > 0:
        target_obj = candidates[0]
        
        # 提取target_signal
        if hasattr(target_obj, 'name'):
            record_params['target_signal'] = target_obj.name
        elif hasattr(target_obj, 'lhs_name'):
            record_params['target_signal'] = target_obj.lhs_name
        
        # 提取target_line
        if hasattr(target_obj, 'start'):
            record_params['target_line'] = rtl[:target_obj.start].count('\n') + 1
        
        # 不记录target_token
        if 'target_token' in record_params:
            del record_params['target_token']
except Exception:
    pass  # 如果提取失败，保留原始params
```

## 对比示例

### 场景：对enable信号应用T34重命名

#### 代码
```verilog
module test(
    input clk,
    output valid
);
    reg enable;          // ← 第9行
    assign valid = enable;
endmodule
```

#### ❌ 旧方式：只记录索引

```json
{
    "attack_params": {
        "target_token": 0,
        "custom_map": {"enable": "disable"}
    }
}
```

**问题**：
- 不知道target_token=0对应哪个信号
- 如果代码添加了其他wire，候选顺序可能改变

#### ✅ 新方式：记录语义信息

```json
{
    "attack_params": {
        "target_signal": "enable",
        "target_line": 9,
        "custom_map": {"enable": "disable"}
    }
}
```

**优势**：
- 清晰看出攻击的是enable信号
- 即使代码结构改变，仍能找到enable
- 可以精确复现攻击

## 总结

通过**索引选择 + 语义记录**的双向转换机制：

1. ✅ **攻击时高效**：用索引遍历所有候选位置
2. ✅ **记录时清晰**：保存有意义的信号名和行号
3. ✅ **复现时准确**：通过语义信息精确定位
4. ✅ **分析时直观**：一眼看出攻击位置和目标

这是位置参数设计的核心改进！
