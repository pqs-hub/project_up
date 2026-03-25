# 其他规则修复计划

## 需要关注的规则（6个）

基于功能改变率分析，以下规则需要检查和可能的修复：

| 规则 | 改变率 | 优先级 | 问题类型 |
|------|--------|--------|----------|
| **T12** | 20.88% | 🔥 高 | 与T31相同问题 |
| **T10** | 36.59% | 🔥 高 | 位宽/类型问题 |
| **T48** | 25.06% | 🔥 高 | 数据依赖问题 |
| **T09** | 20.40% | ⚠️ 中 | 位宽/类型问题 |
| **T18** | 26.69% | ⚠️ 中 | 数据依赖问题 |
| **T03** | 15.63% | ⚠️ 中 | default分支问题 |
| **T39** | 13.52% | ℹ️ 低 | 需要查看实现 |

---

## 详细分析

### 🔥 T12 - 中间信号注入（20.88%）

**当前实现**：
```python
def ast_intermediate_signal(code, vs, target, wire_name=''):
    # ...
    wire_decl = f'{indent}wire {tmp_name} = {expr.predicate};\n'  # ❌ 问题！
    new_assign = f'{indent}assign {target.lhs} = {tmp_name} ? {expr.true_expr} : {expr.false_expr};'
    return code[:line_start] + wire_decl + new_assign + code[target.end:]
```

**问题**：
1. ❌ 使用了`wire tmp = expr;`语法（与T31相同）
2. ❌ 缺少位宽声明
3. ❌ 可能导致位宽推断错误

**修复方案**（与T31相同）：
```python
def ast_intermediate_signal(code, vs, target, wire_name=''):
    # ...
    
    # 1. 获取predicate的位宽（通常是1位）
    # 对于三元表达式的predicate，通常是1位
    wire_decl = f'{indent}wire {tmp_name};\n'  # predicate通常是1位
    
    # 2. 使用assign语句
    wire_assign = f'{indent}assign {tmp_name} = {expr.predicate};\n'
    new_assign = f'{indent}assign {target.lhs} = {tmp_name} ? {expr.true_expr} : {expr.false_expr};'
    
    return code[:line_start] + wire_decl + wire_assign + new_assign + code[target.end:]
```

**预期改进**：20.88% → < 5%

---

### 🔥 T10 - DeMorgan OR（36.59%）

**当前实现**：
```python
def ast_demorgan_or(code, vs, target):
    """T10: a | b → ~(~a & ~b)"""
    def smart_negate(s):
        s = s.strip()
        return s[1:].strip() if s.startswith('~') else f'~{s}'
    
    neg_a = smart_negate(target.left_text)
    neg_b = smart_negate(target.right_text)
    new_expr = f'~({neg_a} & {neg_b})'
    return _replace_range(code, target.start, target.end, new_expr)
```

**问题**：
1. ❌ 没有检查位宽匹配
2. ❌ 可能在位宽不同时产生错误结果
3. ❌ 未定义值（X/Z）处理可能不同

**示例问题**：
```verilog
// 原始代码
wire [7:0] a;
wire [3:0] b;
assign out = a | b;  // Verilog会自动扩展b到8位

// T10变换后
assign out = ~(~a & ~b);  // 可能行为不同
```

**修复方案**：
```python
def ast_demorgan_or(code, vs, target):
    """T10: a | b → ~(~a & ~b)，仅在位宽匹配时应用"""
    
    # 1. 提取操作数名称
    a_name = extract_signal_name(target.left_text)
    b_name = extract_signal_name(target.right_text)
    
    # 2. 检查位宽
    if a_name and b_name:
        a_width = vs.get_width(a_name)
        b_width = vs.get_width(b_name)
        
        if a_width != b_width:
            # 位宽不匹配，不应用变换
            return code
    
    # 3. 应用DeMorgan
    def smart_negate(s):
        s = s.strip()
        return s[1:].strip() if s.startswith('~') else f'~{s}'
    
    neg_a = smart_negate(target.left_text)
    neg_b = smart_negate(target.right_text)
    new_expr = f'~({neg_a} & {neg_b})'
    return _replace_range(code, target.start, target.end, new_expr)
```

**预期改进**：36.59% → < 10%

---

### 🔥 T48 - 反拓扑排序（25.06%）

**当前实现**：
```python
def ast_anti_topological_shuffle(code, target_token=None):
    """T48: 逆向拓扑并发重排 (颠倒赋值语句顺序)"""
    vs = analyze(code)
    assigns = [a for a in vs.assignments if a.kind == 'continuous']
    if len(assigns) < 2: 
        return code
    
    # 收集所有assign语句的文本
    assign_texts = [code[a.start:a.end] for a in assigns]
    # 反转顺序
    reversed_texts = list(reversed(assign_texts))
    
    # 从后向前替换
    result = code
    for i in range(len(assigns) - 1, -1, -1):
        a = assigns[i]
        new_text = reversed_texts[i]
        result = result[:a.start] + new_text + result[a.end:]
    
    return result
```

**问题**：
1. ❌ 没有检查数据依赖
2. ❌ 可能破坏依赖关系

**示例问题**：
```verilog
// 原始代码
assign a = x;
assign b = y;
assign c = a + b;  // 依赖a和b

// T48反转后
assign c = a + b;  // ❌ a和b还未定义！
assign b = y;
assign a = x;
```

**修复方案**：
```python
def ast_anti_topological_shuffle(code, target_token=None):
    """T48: 逆向拓扑并发重排，仅反转无依赖的语句"""
    vs = analyze(code)
    assigns = [a for a in vs.assignments if a.kind == 'continuous']
    if len(assigns) < 2:
        return code
    
    # 1. 构建依赖图
    deps = {}
    for i, asgn in enumerate(assigns):
        deps[i] = set()
        # 检查rhs中使用的信号
        rhs_signals = extract_signals_from_expr(asgn.rhs)
        for j, other in enumerate(assigns):
            if i != j and other.lhs_name in rhs_signals:
                deps[i].add(j)  # i依赖j
    
    # 2. 检查是否有依赖关系
    has_deps = any(len(d) > 0 for d in deps.values())
    
    if has_deps:
        # 有依赖关系，不应用变换
        return code
    
    # 3. 无依赖，可以安全反转
    assign_texts = [code[a.start:a.end] for a in assigns]
    reversed_texts = list(reversed(assign_texts))
    
    result = code
    for i in range(len(assigns) - 1, -1, -1):
        a = assigns[i]
        new_text = reversed_texts[i]
        result = result[:a.start] + new_text + result[a.end:]
    
    return result
```

**预期改进**：25.06% → < 5%

---

### ⚠️ T09 - DeMorgan AND（20.40%）

**问题**：与T10类似，需要位宽检查

**修复方案**：与T10相同

**预期改进**：20.40% → < 10%

---

### ⚠️ T18 - 语句重排序（26.69%）

**问题**：可能与T48类似，需要查看具体实现

**建议**：添加依赖检查

---

### ⚠️ T03 - Case重排序（15.63%）

**问题**：可能与default分支有关

**建议**：只在没有default分支时重排

---

### ℹ️ T39（13.52%）

**状态**：需要查看具体实现

---

## 修复优先级

### 立即修复（高优先级）

1. **T12**（20.88%）
   - 问题明确：与T31相同
   - 修复简单：复制T31的修复
   - 预期效果好：降到<5%

2. **T10**（36.59%）
   - 问题明确：缺少位宽检查
   - 修复中等：需要添加位宽检查逻辑
   - 预期效果好：降到<10%

3. **T48**（25.06%）
   - 问题明确：缺少依赖检查
   - 修复复杂：需要实现依赖分析
   - 预期效果好：降到<5%

### 可选修复（中优先级）

4. **T09**（20.40%）
   - 与T10类似

5. **T18**（26.69%）
   - 需要查看实现

6. **T03**（15.63%）
   - 改变率相对较低

### 暂缓（低优先级）

7. **T39**（13.52%）
   - 改变率可接受

---

## 修复计划

### 第1步：修复T12（最简单）

```python
# 位置：ast_transforms.2.py，ast_intermediate_signal函数
# 修改：使用标准wire声明 + assign语句
```

**预期时间**：10分钟  
**预期效果**：20.88% → < 5%

### 第2步：修复T10和T09（中等）

```python
# 位置：ast_transforms.2.py，ast_demorgan_or和ast_demorgan_and函数
# 修改：添加位宽检查
```

**预期时间**：30分钟  
**预期效果**：
- T10: 36.59% → < 10%
- T09: 20.40% → < 10%

### 第3步：修复T48（较复杂）

```python
# 位置：ast_transforms.2.py，ast_anti_topological_shuffle函数
# 修改：添加依赖分析
```

**预期时间**：1小时  
**预期效果**：25.06% → < 5%

---

## 修复后的预期结果

### 当前状态（19个规则）

| 分类 | 数量 | 规则 |
|------|------|------|
| 功能等价（<5%） | 10 | T07, T19, T20, T30, T32, T34, T41, T45, T46, T07b |
| 需要修复（5%-40%） | 6 | T03, T09, T10, T12, T18, T48 |
| 高改变率（>40%） | 3 | T31✅, T47✅, T39 |

### 修复后预期（19个规则）

| 分类 | 数量 | 规则 |
|------|------|------|
| 功能等价（<5%） | 14+ | T07, T19, T20, T30, T32, T34, T41, T45, T46, T07b, **T12✅, T31✅, T48✅** |
| 可接受（5%-15%） | 4 | T03, T09✅, T10✅, T39 |
| 高改变率（>15%） | 1 | T18, T47✅ |

**改进**：
- 功能等价规则：10 → 14+ （+40%）
- 高改变率规则：6 → 1-2 （-70%）

---

## 建议

### 短期（本次会话）

1. ✅ 修复T31和T47（已完成）
2. 🔥 修复T12（最简单，立即可做）
3. 🔥 修复T10（中等难度，建议做）

### 中期（下次会话）

4. 修复T48（较复杂）
5. 修复T09（与T10类似）
6. 评估T18和T03是否需要修复

### 长期

7. 为所有规则添加前置条件检查
8. 建立自动化测试框架
9. 确保所有规则都能保持功能等价

---

## 总结

**可以立即修复的规则**：
- T12（20.88%）- 与T31相同问题，复制修复即可

**建议修复的规则**：
- T10（36.59%）- 添加位宽检查
- T48（25.06%）- 添加依赖检查
- T09（20.40%）- 添加位宽检查

**修复后预期**：
- 14+个功能等价规则（<5%改变率）
- 大幅提升数据集质量

**需要我帮你修复T12吗？**（最简单，5分钟即可完成）
