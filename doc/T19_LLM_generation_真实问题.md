# T19 LLM生成问题的真实根源

## 您的质疑是对的！ ✅

您说："不对啊，我一开始就想要用LLM生成上下文"。

经过代码审查，**T19确实配置了LLM参数生成**，而且exhaustive脚本也会调用。但只有3个成功样本的原因更复杂。

---

## LLM生成机制确认

### 1. Prompt配置存在 ✅

**`config/prompts.py` (第280-321行)**:
```python
ATTACK_T19_DEAD_CODE_PROMPT_TEMPLATE = """Generate misleading dead code...

**Strategy**: Generate code that implements what **SHOULD BE** in SPEC 
but is **ACTUALLY MISSING**, creating the illusion that the 
implementation is incomplete.

### Functional Specification
{task_prompt}

### Original RTL
```verilog
{code_snippet}
```"""

# 注册到LLM_PARAM_RULES
LLM_PARAM_RULES = {
    'T19': {
        'param_name': 'custom_dead_stmts',
        'prompt_template': ATTACK_T19_DEAD_CODE_PROMPT_TEMPLATE,
    },
}
```

**提示词要求**:
1. 从SPEC提取关键行为
2. 生成看起来符合这些行为的死代码
3. 实现语义反转（对抗性）
4. 使用可写/可读信号列表

### 2. Exhaustive脚本调用LLM ✅

**`pipeline/6_generate_attack_dataset_exhaustive.py` (第118-131行)**:
```python
# 准备参数 - 在执行时生成LLM参数
params = {}
if rule_id in LLM_PARAM_RULES:
    context = {}
    
    # 生成LLM参数
    llm_param = self.generate_llm_param(rule_id, rtl, spec=spec, **context)
    if llm_param:
        param_name = LLM_PARAM_RULES[rule_id]['param_name']
        params = {param_name: llm_param}
```

**关键**: **每个候选位置都会调用一次LLM**！

### 3. LLM参数生成函数

```python
def generate_llm_param(self, rule_id: str, code: str, spec: str = "", **context):
    """使用LLM生成规则参数"""
    prompt = format_attack_prompt(
        rule_id=rule_id,
        code_snippet=code,
        task_prompt=spec,
        writable_signals=writable_signals,  # 从代码中提取
        readable_signals=readable_signals,
    )
    
    response = attack_client.post(..., json={
        "model": self.attack_client.model,
        "messages": [
            {"role": "system", "content": "你是Verilog代码混淆专家。"},
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,  # ← 注意这个参数
        "max_tokens": 200,
    })
    
    # 解析返回结果...
```

---

## 真正的问题

### 问题1: 参数解析过于宽松 ⚠️

**解析逻辑** (`6_generate_attack_dataset.py` 第321-360行):

```python
elif rule_id == 'T19':
    result = content.strip()
    
    # 移除markdown代码块
    result = re.sub(r'```(?:json|verilog)?\s*', '', result).strip()
    
    # 验证Verilog代码
    if result and (';' in result or 'if' in result or 'case' in result or '<=' in result or '=' in result):
        logger.debug(f"T19: 直接使用Verilog语句 -> {result[:50]}")
        return result
    
    return result if result else None  # ← 这里是问题！
```

**Bug**: 第360行的fallback逻辑
- 即使不包含任何Verilog符号（`;`, `if`, `<=`等）
- 只要`result`非空，就会返回

**这就是"No"被接受的原因！**

```verilog
always @(*) begin
  if ((2'b00 & 2'b11) == 2'b11) begin
    No  // ← LLM输出被原样接受
  end
end
```

### 问题2: LLM生成质量不稳定 ❌

根据现有3个样本分析：

#### 样本1: 空死代码块（置信度0.77）
```verilog
always @(*) begin
  if (1'b0) begin
  end
end
```
**分析**: LLM可能返回空字符串，导致使用默认模板

#### 样本2/3: "No"语句（置信度0.65, 0.95）
```verilog
always @(*) begin
  if ((2'b00 & 2'b11) == 2'b11) begin
    No
  end
end
```
**分析**: LLM可能输出了"No"（意为"无操作"），被解析器接受

### 问题3: LLM生成失败的常见原因

#### 原因A: 语法错误导致testbench失败

LLM生成：
```verilog
if (enable && !rst) begin
  temp <= data_in;  // ← temp未声明！
end
```

流程：
```
LLM生成 → 插入到if(1'b0) → Iverilog编译失败 
→ testbench失败 → 样本被丢弃
```

#### 原因B: 没有对抗性，判断模型仍判对

LLM生成：
```verilog
if (rst) count <= 0;  // ← 这正是SPEC要求的！
```

流程：
```
LLM生成 → testbench通过 → 判断模型仍判断正确 
→ 攻击失败 → 样本被丢弃
```

#### 原因C: API调用失败

- 网络超时（30秒限制）
- 模型服务器崩溃或限流
- 并发请求过多

流程：
```
API失败 → generate_llm_param返回None → params为空
→ 使用默认死代码 → 判断模型容易识别 → 攻击失败
```

#### 原因D: 温度参数导致输出不稳定

```python
"temperature": 0.7,  # 较高，导致输出多样但不稳定
```

可能导致：
- 输出格式不一致（JSON vs 纯文本）
- 语法错误率上升
- 有时输出无关内容（如"No"）

---

## 数据对比验证

### 遍历式生成 vs 单规则评估

| 场景 | T19样本数 | 成功率 | LLM调用次数（估算） |
|------|----------|--------|-------------------|
| **单规则评估** | 17,483 | 90.5% LLM成功 | ~100,000+ |
| **详尽遍历** | 39,347总样本 | 每位置都调用 | ~200,000+ |
| **T19成功** | 仅3个 | ~0.01% | 99.99%失败！ |

**推测**: 
- LLM调用了成千上万次
- 但因为语法错误、无对抗性、解析失败等原因
- 99.99%的尝试都被丢弃了

### 为什么单规则评估成功率90.5%？

**关键差异**: 单规则评估可能使用了：

1. **预定义模板库**而非完全LLM生成
   ```python
   T19_TEMPLATES = [
       'if (enable && !enable) temp <= 0;',
       'if ((a & ~a) == 1) flag <= 1;',
       # ... 10+种经过验证的模板
   ]
   ```

2. **更宽松的成功条件**
   - 只要LLM误判即可
   - 不要求testbench通过

3. **后处理优化**
   - 自动修复常见语法错误
   - 验证信号声明
   - 添加必要的begin-end

---

## 解决方案

### 方案1: 收紧解析验证 🔧

```python
elif rule_id == 'T19':
    result = content.strip()
    # ... 清理 ...
    
    # 严格验证Verilog语法
    if not (';' in result or 'if' in result or 'case' in result):
        logger.warning(f"T19: LLM输出不像Verilog代码: {result[:50]}")
        return None  # ← 拒绝非法输出
    
    # 不再使用fallback
    return result
```

### 方案2: 降低temperature 🎯

```python
json={
    "temperature": 0.3,  # 从0.7降低到0.3
    "max_tokens": 200,
}
```

### 方案3: 添加语法验证 ✅

```python
def validate_verilog_syntax(stmt: str, writable_signals: List[str]) -> bool:
    """验证Verilog语句的语法正确性"""
    # 检查是否使用了未声明的信号
    assigned_signals = re.findall(r'(\w+)\s*<=', stmt)
    for sig in assigned_signals:
        if sig not in writable_signals:
            return False
    
    # 检查基本语法
    if not stmt.strip().endswith(';') and 'begin' not in stmt:
        return False
    
    return True
```

### 方案4: 使用混合策略 ⭐ **推荐**

```python
def get_T19_params(code, spec, llm_client):
    # 1. 先尝试LLM生成
    llm_output = llm_client.generate(...)
    
    if validate_verilog_syntax(llm_output):
        return {'custom_dead_stmts': llm_output}
    
    # 2. LLM失败，使用预定义模板库
    templates = [
        'if (enable && !enable) temp <= 0;',
        'if ((a & ~a) != 0) flag <= 1;',
        # ... 更多模板
    ]
    return {'custom_dead_stmts': random.choice(templates)}
```

### 方案5: 改进Prompt ✍️

```python
ATTACK_T19_DEAD_CODE_PROMPT_TEMPLATE = """
...existing prompt...

**CRITICAL OUTPUT REQUIREMENTS**:
1. Output ONLY Verilog statements (no markdown, no JSON)
2. Every statement MUST end with `;`
3. Use ONLY these signals: {writable_signals}
4. Example valid output: `if (enable && !enable) temp <= 0;`
5. Example INVALID output: "No" ← This will cause compilation error!

**EXAMPLES OF GOOD OUTPUT**:
```
if (rst && !rst) count <= 8'b0;
```
```
case (state) 2'b00: next <= 2'b01; endcase
```

Output your Verilog code directly (no explanation):
"""
```

---

## 推荐行动计划

### 短期（立即）🔥
1. **收紧解析验证**（移除第360行fallback）
2. **降低temperature到0.3**
3. **添加debug日志**记录LLM输出和失败原因

### 中期（1-2天）⚙️
4. **添加语法验证**确保LLM输出可编译
5. **创建模板库作为fallback**
6. **改进Prompt**添加明确示例

### 长期（1周）🎯
7. **分析LLM失败模式**（收集1000次调用的日志）
8. **优化writable/readable信号提取**
9. **考虑使用更强的LLM模型**（如GPT-4）

---

## 总结

### 您是对的！✅

- T19**确实**配置了LLM参数生成
- 每个位置**都会**调用LLM
- Prompt设计也是合理的

### 真正的问题 ❌

1. **解析太宽松**: 接受了"No"这样的无效输出
2. **LLM质量不稳定**: temperature太高，输出不可预测
3. **缺少验证**: 没有语法检查，编译时才发现错误
4. **没有fallback**: LLM失败后直接放弃

### 关键洞察 💡

```
调用次数: 数十万次
成功样本: 仅3个
转化率: 0.001%

→ 不是没用LLM，而是LLM生成的几乎全失败了！
```

**建议**: 实施方案4（混合策略），在LLM失败时使用验证过的模板库。
