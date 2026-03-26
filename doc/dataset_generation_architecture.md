# 攻击数据集生成架构

## 核心概念澄清

### ❌ 常见误解
- "需要攻击模型来执行攻击" ← **错误**
- "attack-model是用来攻击的" ← **命名误导**

### ✅ 正确理解
攻击数据集生成**不需要模型来执行攻击**，攻击是由**代码规则**直接执行的！

## 三个关键组件

### 1️⃣ 攻击规则（代码，不是模型）⭐

**作用**：执行代码变换攻击

```python
# 示例：T03冗余逻辑注入
def ast_redundant_logic(code, target_signal="clk"):
    # 直接修改AST，插入冗余逻辑
    # 不需要任何模型！
    return transformed_code
```

**15个规则**：T03, T07, T09, T10, T12, T19, T20, T30, T31, T32, T34, T41, T45, T47, T48

### 2️⃣ 参数生成模型（LLM，可选）

**作用**：生成攻击参数（如注释文本、wire名等）

**命令行参数**：
```bash
--param-gen-base-url http://localhost:8002/v1
--param-gen-model "obfuscation_merged"
```

**示例**：
```python
# T20需要生成误导性注释
llm_prompt = "生成一个与代码功能相反的注释"
generated_comment = llm.generate(prompt)  # "This increments the counter"
# 但实际代码是递减counter

# T12需要生成wire名
llm_prompt = "为三元表达式的谓词生成一个合适的wire名"
generated_name = llm.generate(prompt)  # "condition_check"
```

**支持LLM参数的规则**：
- T12: wire名
- T19: 死代码语句
- T20: 注释文本
- T31: wire名
- T34: 信号重命名映射

### 3️⃣ 判断模型（Judge Model）

**作用**：判断代码是否正确

**配置位置**：`config/config.yaml`
```yaml
judge_model:
  base_url: "http://localhost:8001/v1"
  model_name: "Qwen2.5-Coder-7B"
  temperature: 0.0
```

**工作流程**：
```python
# 判断原始代码
verdict_original = judge_model.judge(spec, original_code)
# is_correct: True

# 判断变换后代码
verdict_transformed = judge_model.judge(spec, transformed_code)
# is_correct: False  ← 攻击成功！
```

## 完整工作流程

```
┌─────────────────────────────────────────────────────────────┐
│                    攻击数据集生成流程                          │
└─────────────────────────────────────────────────────────────┘

1. 读取任务
   ├─ eval_file: verilog_eval.json
   └─ 每个任务: {prompt, canonical_solution, test}

2. 验证原始代码（使用Judge模型）
   ├─ judge_model.judge(prompt, original_code)
   └─ 只保留is_correct=True的任务

3. 对每个任务×规则×位置：
   
   ┌─────────────────────────────────────────┐
   │ 3.1 生成攻击参数（可选，使用参数生成模型） │
   └─────────────────────────────────────────┘
   ├─ 如果规则支持LLM参数：
   │  ├─ param_gen_model.generate(prompt)
   │  └─ 得到：comment_text / wire_name / etc.
   └─ 否则使用默认参数
   
   ┌─────────────────────────────────────────┐
   │ 3.2 执行攻击（使用代码规则，不需要模型！）  │
   └─────────────────────────────────────────┘
   ├─ engine.apply_transform(code, rule_id, **params)
   └─ 得到：transformed_code
   
   ┌─────────────────────────────────────────┐
   │ 3.3 验证功能等价（使用Testbench）         │
   └─────────────────────────────────────────┘
   ├─ testbench.run(original_code, transformed_code)
   └─ 通过 → 继续；失败 → 丢弃
   
   ┌─────────────────────────────────────────┐
   │ 3.4 判断攻击效果（使用Judge模型）         │
   └─────────────────────────────────────────┘
   ├─ judge_model.judge(prompt, transformed_code)
   └─ is_correct=False → 攻击成功！保存样本

4. 保存成功样本
   └─ output.jsonl
```

## 模型配置总结

### 方式1：最小配置（不用参数生成模型）

```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/eval.json \
  --output data/dataset.jsonl \
  --param-gen-base-url http://localhost:8002/v1 \
  --param-gen-model "dummy" \  # 虽然required，但不会实际使用
  --use-cot
```

**说明**：
- 只需Judge模型（在config.yaml中配置）
- 所有规则使用默认参数（不生成LLM参数）
- 适合快速测试

### 方式2：完整配置（使用参数生成模型）

```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/eval.json \
  --output data/dataset.jsonl \
  --param-gen-base-url http://localhost:8002/v1 \
  --param-gen-model "obfuscation_merged" \
  --use-cot
```

**说明**：
- Judge模型（在config.yaml中配置）
- 参数生成模型（命令行指定）
- 为T12/T19/T20/T31/T34生成LLM参数
- 数据更多样化

## 命名对比

### 旧命名（容易混淆）❌
```bash
--attack-base-url     # 实际是参数生成模型
--attack-model        # 不是用来攻击的！
```

### 新命名（清晰）✅
```bash
--param-gen-base-url  # 参数生成模型
--param-gen-model     # 用于生成攻击参数
```

## 实际示例

### 示例1：T03冗余逻辑（不需要参数生成）

```python
# 攻击规则（代码）
transformed = ast_redundant_logic(code, target_signal="clk")
# 直接在AST中插入冗余逻辑，不需要任何模型

# Judge模型
verdict = judge_model.judge(spec, transformed)
# 判断是否被攻击混淆
```

### 示例2：T20误导性注释（需要参数生成）

```python
# 1. 参数生成模型
comment = param_gen_model.generate(
    "生成一个与实际功能相反的注释"
)
# → "This increments the counter"

# 2. 攻击规则（代码）
transformed = ast_flexible_comment(code, custom_text=comment)
# 插入误导性注释

# 3. Judge模型
verdict = judge_model.judge(spec, transformed)
# 判断是否被误导
```

## 资源需求

### GPU服务器配置

```bash
# Judge模型（必需）
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-7B \
  --port 8001 \
  --gpu-memory-utilization 0.5

# 参数生成模型（可选，用于高质量数据）
python -m vllm.entrypoints.openai.api_server \
  --model path/to/obfuscation_merged \
  --port 8002 \
  --gpu-memory-utilization 0.5
```

### 最小资源（只用Judge）
- 1个GPU（7B模型）
- Judge模型即可

### 推荐资源（完整功能）
- 2个GPU或1个大GPU
- Judge模型 + 参数生成模型

## 总结

✅ **正确理解**：

| 组件 | 类型 | 作用 | 必需? |
|------|------|------|-------|
| **攻击规则** | 代码 | 执行代码变换 | ✅ 是 |
| **参数生成模型** | LLM | 生成攻击参数 | ❌ 否（可用默认值） |
| **Judge模型** | LLM | 判断代码正确性 | ✅ 是 |

❌ **错误理解**：
- "需要攻击模型来执行攻击" ← 攻击是代码规则执行的！
- "`--attack-model`是攻击模型" ← 实际是参数生成模型！

**新命令示例**（更清晰）：
```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/eval.json \
  --output data/dataset.jsonl \
  --param-gen-base-url http://localhost:8002/v1 \  # 清晰！
  --param-gen-model "obfuscation_merged" \         # 清晰！
  --use-cot
```
