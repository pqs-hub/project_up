# Verilog代码混淆SFT数据集使用指南

## 🎯 训练目标

**训练大模型学会生成混淆后的Verilog代码**

让模型理解各种代码混淆技术，并能够根据指定的混淆规则生成功能等价但难以理解的代码。

---

## 📊 数据集概览

### 基本信息

| 指标 | 数值 |
|------|------|
| **总样本数** | **44,246** |
| 涵盖规则数 | 15 |
| 涵盖任务数 | 16,141 |
| 文件大小 | 113.96 MB |
| 平均代码膨胀率 | 9.15% |

### 样本来源

所有样本都是**攻击成功**的样本：
- ✅ 功能等价（仿真通过）
- ✅ LLM被欺骗（说明混淆有效）

---

## 📝 数据格式

### SFT格式说明

```json
{
  "instruction": "系统提示词（教模型如何混淆代码）",
  "input": "原始代码 + 混淆规则描述",
  "output": "混淆后的代码",
  "metadata": {
    "rule_id": "规则ID",
    "task_id": "任务ID",
    "rule_description": "规则描述",
    "adversarial_confidence": "混淆效果（置信度）",
    "source": "obfuscation_training"
  },
  "original_code": "原始代码",
  "specification": "任务规范"
}
```

### Instruction（系统提示）

```
You are an expert Verilog code obfuscation assistant. Your task is to transform Verilog RTL code using adversarial obfuscation techniques while maintaining functional equivalence.

IMPORTANT:
- The transformed code MUST be functionally equivalent to the original code.
- Apply the specified obfuscation technique accurately.
- Maintain valid Verilog syntax.
- The obfuscated code should be harder for humans or LLMs to understand, but should pass the same testbench.
- Only output the obfuscated Verilog code, without any explanation.
```

### Input（用户输入）

```
Original Verilog Code:
```verilog
module RefModule(a, b, y);
  input a, b;
  output y;
  assign y = a & b;
endmodule
```

Obfuscation Technique: 假性组合逻辑环：插入永假的矛盾项（如 a & ~a）

Task: Apply the specified obfuscation technique to the above code while maintaining functional equivalence.
```

### Output（混淆后的代码）

```verilog
module RefModule(a, b, y);
  input a, b;
  output y;
  assign y = (a & ~a) ? ~y : a & b;  // 添加矛盾项
endmodule
```

---

## 🛠️ 15种混淆技术

| 规则 | 样本数 | 描述 | 示例 |
|------|--------|------|------|
| **T19** | 14,942 | 虚假模式注入 | 插入永不执行的死代码块 |
| **T20** | 8,519 | 误导性注释 | 添加误导性的注释 |
| **T34** | 6,679 | 通用重命名 | 将`enable`重命名为`disable` |
| **T45** | 6,199 | 假性组合逻辑环 | 插入`(a & ~a) ? ~y : expr` |
| T03 | 2,344 | 冗余逻辑注入 | `signal & 1'b1` |
| T32 | 1,724 | 位宽算术变换 | `[7:0]` → `[8-1:0]` |
| T31 | 1,005 | 中间信号注入 | 拆分赋值语句 |
| T41 | 695 | Case分支重排 | 重排case分支顺序 |
| T12 | 651 | 中间信号注入（三元） | 提取三元条件 |
| T48 | 420 | 逆向拓扑重排 | 反转assign顺序 |
| T07 | 383 | 赋值重排 | 交换独立assign |
| T30 | 289 | 常量恒等变换 | `1'b0` → `(1'b1 & 1'b0)` |
| T09 | 249 | 德摩根AND | `a & b` → `~(~a \| ~b)` |
| T10 | 136 | 德摩根OR | `a \| b` → `~(~a & ~b)` |
| T47 | 11 | 数据流破碎 | Shannon展开 |

---

## 🚀 训练示例

### 使用Hugging Face Transformers

```python
from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments
from datasets import Dataset
import json

# 加载数据
with open('data/obfuscation_sft.json', 'r') as f:
    data = json.load(f)

# 格式化为训练格式
def format_obfuscation_sample(example):
    """格式化为instruction-following格式"""
    conversation = [
        {"role": "system", "content": example['instruction']},
        {"role": "user", "content": example['input']},
        {"role": "assistant", "content": example['output']}
    ]
    return {"messages": conversation}

dataset = Dataset.from_list(data)
dataset = dataset.map(format_obfuscation_sample)

# 加载模型
model_name = "Qwen/Qwen2.5-Coder-7B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

# 训练
training_args = TrainingArguments(
    output_dir="./obfuscation_model",
    num_train_epochs=3,
    per_device_train_batch_size=2,
    learning_rate=2e-5,
    warmup_steps=500,
    logging_steps=100,
)

trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
)

trainer.train()
```

### 分阶段训练策略

```python
# 阶段1: 训练简单的混淆技术（T07, T41, T48）
train_on_rules(['T07', 'T41', 'T48'], epochs=2)

# 阶段2: 训练逻辑等价变换（T09, T10, T30）
train_on_rules(['T09', 'T10', 'T30'], epochs=3)

# 阶段3: 训练结构变换（T03, T12, T31, T32）
train_on_rules(['T03', 'T12', 'T31', 'T32'], epochs=3)

# 阶段4: 训练高级混淆（T19, T20, T34, T45, T47）
train_on_rules(['T19', 'T20', 'T34', 'T45', 'T47'], epochs=5)

# 阶段5: 全量微调
train_on_all(epochs=2)
```

---

## 💡 数据增强策略

### 1. 样本平衡

```python
from collections import defaultdict
import random

# T19样本太多，进行欠采样
rule_samples = defaultdict(list)
for sample in dataset:
    rule_samples[sample['metadata']['rule_id']].append(sample)

# 设置每个规则的最大样本数
MAX_SAMPLES_PER_RULE = 3000

balanced_dataset = []
for rule_id, samples in rule_samples.items():
    if len(samples) > MAX_SAMPLES_PER_RULE:
        # 欠采样
        balanced_dataset.extend(random.sample(samples, MAX_SAMPLES_PER_RULE))
    else:
        # 保留所有样本
        balanced_dataset.extend(samples)

print(f"原始样本: {len(dataset)}, 平衡后: {len(balanced_dataset)}")
```

### 2. 规则组合

```python
def combine_obfuscations(code, rules):
    """组合多个混淆规则"""
    obfuscated = code
    for rule_id in rules:
        # 应用规则（需要调用混淆引擎）
        obfuscated = apply_rule(obfuscated, rule_id)
    return obfuscated

# 示例：组合T03（冗余逻辑）+ T20（误导注释）
combined_sample = {
    'input': f"Original Code:\n{original_code}\n\n"
             f"Obfuscation Techniques: T03 (冗余逻辑) + T20 (误导注释)",
    'output': combine_obfuscations(original_code, ['T03', 'T20'])
}
```

### 3. 参数变化

```python
# 对T20（误导性注释）生成多种变体
comments = [
    "// This is a SPI master controller",
    "// UART transmitter implementation",
    "// Clock divider circuit",
    "// Fibonacci sequence generator"
]

for comment in comments:
    # 生成使用不同注释的样本
    ...
```

---

## 📈 评估指标

### 1. 功能等价性

```python
def test_functional_equivalence(original, obfuscated, testbench):
    """测试混淆代码是否功能等价"""
    orig_result = simulate(original, testbench)
    obf_result = simulate(obfuscated, testbench)
    return orig_result == obf_result
```

### 2. 混淆效果（ASR）

```python
def evaluate_obfuscation_effectiveness(obfuscated_codes, llm_judge):
    """评估混淆代码对LLM的欺骗效果"""
    fooled_count = 0
    for code in obfuscated_codes:
        llm_verdict = llm_judge(code)
        if llm_verdict == "NO":  # LLM被欺骗
            fooled_count += 1
    return fooled_count / len(obfuscated_codes)  # ASR
```

### 3. 代码质量

```python
def evaluate_code_quality(obfuscated_code):
    """评估生成代码的质量"""
    metrics = {
        'syntax_valid': check_syntax(obfuscated_code),
        'compilable': check_compile(obfuscated_code),
        'length_ratio': len(obfuscated_code) / len(original_code),
    }
    return metrics
```

---

## 📊 预期效果

### 训练前（基线模型）
- 不会混淆代码
- 只能生成标准的Verilog代码

### 训练后（目标）
- 掌握15种混淆技术
- 能根据指令生成混淆代码
- 混淆代码ASR > 30%（能欺骗LLM）
- 功能等价率 > 95%

---

## 🔍 示例应用场景

### 场景1: 代码保护

```python
# 用户输入
user_input = """
Original Code:
```verilog
module AES_Encrypt(key, plaintext, ciphertext);
  input [127:0] key, plaintext;
  output [127:0] ciphertext;
  // ... AES加密逻辑 ...
endmodule
```

Obfuscation Technique: 组合使用T34（重命名）+ T19（死代码）+ T45（假性环）

Task: 对AES加密模块进行深度混淆以保护知识产权。
"""

# 模型输出：混淆后的AES代码
```

### 场景2: 对抗训练数据生成

```python
# 批量生成对抗样本
for original_code in code_corpus:
    for rule_id in OBFUSCATION_RULES:
        prompt = f"""
        Original Code: {original_code}
        Obfuscation Technique: {RULE_DESCRIPTIONS[rule_id]}
        Task: Apply obfuscation.
        """
        obfuscated = model.generate(prompt)
        # 用于对抗训练...
```

### 场景3: 多样性生成

```python
# 为同一代码生成多个混淆版本
for i in range(10):
    prompt = f"""
    Original Code: {code}
    Obfuscation Technique: 随机选择并组合多种技术
    Task: Generate a unique obfuscated version (variation {i+1}).
    """
    variant = model.generate(prompt)
```

---

## 📁 文件列表

### 数据集文件
```
data/
├── obfuscation_sft.json              # 完整版（114 MB）
├── obfuscation_sft_lite.json         # 轻量版（不含specification）
└── obfuscation_sft_by_rule/          # 按规则拆分
    ├── obfuscation_T03.json          # T03规则样本
    ├── obfuscation_T07.json
    ├── ...
    └── obfuscation_T48.json
```

### 工具脚本
```
build_obfuscation_sft_dataset.py      # 数据集构建脚本
view_sft_samples.py                   # 查看样本工具
```

---

## 🆚 对比：两种SFT数据集

### 1. 识别混淆代码（sft_attack_success.json）

**目标**: 训练模型**识别**混淆代码，提高鲁棒性

| 项 | 内容 |
|---|------|
| Input | 规范 + 混淆代码 |
| Output | YES（正确识别为功能等价） |
| 用途 | 防御对抗攻击 |

### 2. 生成混淆代码（obfuscation_sft.json）✅

**目标**: 训练模型**生成**混淆代码

| 项 | 内容 |
|---|------|
| Input | 原始代码 + 混淆规则 |
| Output | 混淆后的代码 |
| 用途 | 代码混淆、保护知识产权 |

---

## 💪 训练建议

### 1. 数据平衡

- T19/T20样本过多，建议欠采样到3000-5000
- T47样本太少（11个），建议数据增强或过采样

### 2. 课程学习

- 先训练简单规则（T07, T41, T48）
- 再训练复杂规则（T19, T20, T34, T45）
- 最后训练规则组合

### 3. 质量控制

- 每轮训练后测试功能等价性
- 确保生成的代码可编译
- 测试混淆效果（ASR）

---

## ✅ 总结

**成功构建了44,246条代码混淆训练样本！**

- ✅ 涵盖15种混淆技术
- ✅ 所有样本功能等价且混淆有效
- ✅ 提供完整版、轻量版、按规则拆分版本
- ✅ 适合训练Verilog代码混淆生成模型

**这个数据集可用于训练一个能够自动生成混淆代码的AI助手！**
