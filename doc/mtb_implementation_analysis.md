# MTB (Misleading Task Bias) 实现详解

## 🎯 核心思想

MTB使用**Claude Haiku**模型来生成误导性注释，而不是手工规则。

---

## 📋 完整流程

### 1. 预处理原始代码

```python
def _strip_verilog_comments(code: str) -> str:
    # 移除所有原有注释（行注释和块注释）
    # 保留代码结构和空行
    return cleaned_code
```

**目的**：
- 移除原始代码中的所有注释
- 为添加误导性注释腾出空间
- 确保只有新注释是误导性的

---

### 2. 构建Prompt

**模板文件**：`mutant_template_MTB.txt`

```
Read the given problem description(Specification) and the Verilog code. 
Then insert exactly 2 or 3 English single-line comments into the code, 
each using Verilog's `//` comment syntax. 

The purpose is to mislead people to get a correct answer.

These comments must be intentionally incorrect about:
- actual RTL behavior
- signal semantics
- control logic
- timing behavior
- module functionality

However, they should still sound plausible and must each include 
at least one or two terms from the problem description, such as:
- module purpose
- input/output signals
- combinational logic
- sequential logic
- clock, reset, state
- output behavior

Do not change any executable code, identifiers, formatting structure, 
or functionality. Only add the misleading comments naturally at 
appropriate locations in the Verilog code.

Finally, output only the modified Verilog code with the inserted 
incorrect comments, and do not provide any explanation.

RTL problem description (this can help you understand the RTL code):
{$problem description$}

correct RTL code:
{$RTL code$}

reply format:
```verilog
(complete verilog code with the inserted incorrect comments)
```
```

---

### 3. 调用Claude Haiku生成

```python
def _generate_mutant_once(
    client: OpenAI,
    template_text: str,
    model: str,  # "claude-haiku-4-5"
    system_prompt: str,  # "You are a helpful coding assistant."
    temperature: float,  # 0.2
    description: str,
    cleaned_reference: str,
    ...
) -> str:
    prompt = _render_prompt(...)
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": prompt},
        ],
        temperature=temperature,
    )
    return extracted_code
```

**关键参数**：
- 模型：Claude Haiku 4.5
- 温度：0.2（较低，保证稳定性）
- System Prompt：简单的"helpful coding assistant"

---

### 4. 验证生成的代码

```python
def _validate_generated_mutant(
    original_reference: str,
    candidate_reference: str,
) -> str | None:
    # 检查1：不能有块注释
    if block_comment_count != 0:
        return "generated_code_contains_block_comments"
    
    # 检查2：必须恰好2-3个单行注释
    if len(line_comments) not in {2, 3}:
        return f"generated_code_contains_{len(line_comments)}_comments_instead_of_2_or_3"
    
    # 检查3：移除注释后代码必须完全一致
    if canonicalize(candidate) != canonicalize(original):
        return "generated_code_changed_executable_verilog"
    
    return None  # 验证通过
```

**严格约束**：
- ✅ 只能添加2-3个单行注释
- ✅ 不能有块注释
- ✅ 代码逻辑完全不变
- ✅ 只能改注释

---

### 5. Testbench验证

```python
def _mutate_task(...):
    # 生成变体
    candidate_reference = _generate_mutant_once(...)
    
    # 验证格式
    validation_error = _validate_generated_mutant(...)
    if validation_error:
        retry...
    
    # Testbench验证
    judge_results = Judge_RTL_Iverilog(
        candidate_reference,
        task["test"],
        timeout_seconds=30,
    )
    
    if judge_results[0] == "pass":
        return success
    else:
        retry...
```

**双重验证**：
1. 格式验证（注释数量、代码不变）
2. Testbench验证（功能正确性）

---

### 6. 重试机制

```python
max_retries = 3  # 默认最多重试3次
total_attempts = max_retries + 1  # 总共4次尝试

for attempt_index in range(1, total_attempts + 1):
    try:
        candidate = generate_mutant(...)
        if validate(candidate) and testbench_pass(candidate):
            return success
        else:
            last_error = ...
            continue  # 重试
    except Exception as e:
        last_error = str(e)
        continue
```

**每次重试会告诉模型上次失败的原因**：
```python
extra_lines.append(f"- The previous attempt was rejected because: {last_error}.")
```

---

## 🔑 关键成功因素

### 1. **使用LLM生成注释**

**不是手工规则，而是让Claude理解代码后生成误导性注释**

**优势**：
- ✅ 注释更自然、更可信
- ✅ 能理解代码语义，生成针对性的误导
- ✅ 能使用专业术语
- ✅ 能根据问题描述定制注释

### 2. **Prompt设计精妙**

**关键指令**：
```
The purpose is to mislead people to get a correct answer.

These comments must be intentionally incorrect about:
- actual RTL behavior
- signal semantics
- control logic
- timing behavior

However, they should still sound plausible and must each include 
at least one or two terms from the problem description
```

**效果**：
- 注释听起来专业、可信
- 但实际上是错误的
- 使用问题描述中的术语增加可信度

### 3. **严格的验证**

**三重检查**：
1. 格式检查（2-3个注释）
2. 代码不变检查（移除注释后完全一致）
3. Testbench检查（功能正确）

**确保**：
- 只改注释
- 功能100%正确
- 注释数量合适

### 4. **利用问题描述**

```python
prompt = prompt.replace("{$problem description$}", description.strip())
```

**Claude可以**：
- 理解问题要求
- 知道哪些概念是关键的
- 针对性地误导这些概念

**例如**：
```
问题：Build a circuit that always outputs a LOW.
代码：assign zero = 1'b0;

Claude生成的误导：
// This combinational logic uses a clock signal to synchronize the output
// The sequential logic ensures the output transitions to HIGH on reset
```

注意到：
- 使用了"clock"、"sequential logic"等术语
- 这些术语在问题描述中可能出现
- 但实际代码是组合逻辑，不需要时钟

---

## 💡 为什么MTB比我们的T20有效？

### 我们的T20

```python
# 简单的字符串替换
custom_text = 'This implements XOR operation'
code_with_comment = f"{code}  // {custom_text}"
```

**问题**：
- ❌ 固定的模板
- ❌ 不理解代码语义
- ❌ 注释太简单
- ❌ 不使用问题描述

### MTB

```python
# 使用Claude理解代码后生成
prompt = f"""
Problem: {description}
Code: {code}
Generate 2-3 misleading comments that:
- Sound plausible
- Use terms from problem description
- Are intentionally incorrect about behavior
"""
```

**优势**：
- ✅ Claude理解代码
- ✅ 生成针对性的误导
- ✅ 使用专业术语
- ✅ 结合问题描述

---

## 📊 效果对比

| 方法 | 实现 | 成功率 |
|------|------|--------|
| 我们的T20 | 固定模板 | 1.3% |
| MTB | Claude生成 | 82.0% |
| **差距** | - | **+80.7%** |

---

## 🚀 对我们的启示

### 方案1：直接使用MTB的方法

**优点**：
- 已经验证有效（82%）
- 实现简单（调用API）

**缺点**：
- 需要调用外部API（Claude）
- 成本较高
- 速度较慢

### 方案2：改进T20，模仿MTB的策略

**核心改进**：
1. **多行注释**
   ```python
   comment_before = "// This combinational logic uses clock signal..."
   comment_after = "// The sequential logic ensures state transitions..."
   ```

2. **混淆组合/时序逻辑**
   ```python
   if is_combinational_logic(code):
       misleading_type = "sequential logic"
       misleading_terms = ["clock", "reset", "registered"]
   else:
       misleading_type = "combinational logic"
       misleading_terms = ["asynchronous", "immediate"]
   ```

3. **使用专业术语库**
   ```python
   MISLEADING_TERMS = {
       'combinational': ['clock edge', 'synchronize', 'registered output'],
       'sequential': ['combinational', 'asynchronous', 'immediate'],
   }
   ```

4. **结合代码分析**
   ```python
   # 分析代码类型
   has_always_posedge = '@(posedge' in code
   has_assign = 'assign' in code
   
   # 生成相反的描述
   if has_assign and not has_always_posedge:
       comment = "// This sequential logic uses clock signal..."
   ```

### 方案3：混合方法

**训练数据**：
- 50% MTB生成的数据（高质量）
- 30% T45（Pseudo Loop）
- 20% 其他规则

**预期效果**：
- 整体成功率：70%+

---

## 📋 总结

### MTB的核心创新

1. **使用LLM生成注释**而不是手工规则
2. **结合问题描述**生成针对性误导
3. **严格验证**确保功能正确
4. **专业术语**增加可信度

### 成功的关键

**不是注释本身，而是注释的质量**：
- 简单的注释（我们的T20）：1.3%
- 高质量的注释（MTB）：82.0%

### 下一步

**立即可行**：
1. 改进T20实现，采用MTB的策略
2. 或直接使用MTB的数据训练

**预期提升**：
- 当前成功率：47%
- 改进后：70%+

---

生成时间：2026-03-28
基于：MTB源代码分析
