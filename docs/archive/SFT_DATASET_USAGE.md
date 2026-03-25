# SFT数据集使用指南

## 📦 数据集文件

```
data/
├── sft_attack_success.json          # 完整版（321 MB）
├── sft_attack_success_lite.json     # 轻量版（~150 MB）
└── sft_by_rule/                     # 按规则拆分
    ├── sft_T03.json                 # T03规则样本（2,344条）
    ├── sft_T07.json                 # T07规则样本（383条）
    ├── sft_T09.json                 # T09规则样本（249条）
    ├── ...
    └── sft_T48.json                 # T48规则样本（420条）
```

## 🔍 查看数据集

### 1. 查看统计信息

```bash
python view_sft_samples.py --stats
```

输出:
```
总样本数: 44,246
涵盖规则数: 15
涵盖任务数: 16,141

各规则样本分布:
  T03: 2,344 (5.3%)
  T07: 383 (0.9%)
  T09: 249 (0.6%)
  ...
  T45: 6,199 (14.0%)
  T19: 14,942 (33.8%)
```

### 2. 查看特定规则的样本

```bash
# 查看T45规则的前5个样本
python view_sft_samples.py --rule T45 --num 5

# 查看T19规则的随机10个样本
python view_sft_samples.py --rule T19 --random 10
```

### 3. 查看特定任务的样本

```bash
# 查看任务q007000的所有样本（可能有多个规则）
python view_sft_samples.py --task q007000
```

### 4. 随机浏览样本

```bash
# 随机查看20个样本
python view_sft_samples.py --random 20
```

## 📊 数据格式

### JSON结构

```json
{
  "instruction": "系统提示词（所有样本相同）",
  "input": "任务描述 + 对抗代码",
  "output": "YES（所有样本都是YES）",
  "metadata": {
    "rule_id": "T45",
    "task_id": "q014599",
    "llm_wrong_output": "NO",
    "adversarial_confidence": 0.9908,
    "source": "adversarial_attack_success"
  },
  "original_code": "原始代码（仅完整版）",
  "adversarial_code": "对抗代码（仅完整版）",
  "testbench": "测试平台（仅完整版）"
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `instruction` | string | 系统提示词，指导模型如何判断RTL正确性 |
| `input` | string | 用户输入，包含任务描述和对抗代码 |
| `output` | string | 正确答案（全部为"YES"，因为功能等价） |
| `metadata.rule_id` | string | 使用的对抗规则ID（T03-T48） |
| `metadata.task_id` | string | 原始任务ID |
| `metadata.llm_wrong_output` | string | LLM的错误输出（全部为"NO"） |
| `metadata.adversarial_confidence` | float | LLM的置信度 |
| `original_code` | string | 原始代码（仅完整版） |
| `adversarial_code` | string | 对抗代码（仅完整版） |
| `testbench` | string | 测试平台（仅完整版） |

## 🚀 训练示例

### 使用Hugging Face Transformers

```python
from transformers import AutoTokenizer, AutoModelForCausalLM, Trainer, TrainingArguments
from datasets import Dataset
import json

# 加载数据
with open('data/sft_attack_success_lite.json', 'r') as f:
    data = json.load(f)

# 转换为Dataset格式
dataset = Dataset.from_list(data)

# 格式化为训练格式
def format_sample(example):
    return {
        'text': f"{example['instruction']}\n\n{example['input']}\n\n{example['output']}"
    }

dataset = dataset.map(format_sample)

# 加载模型和tokenizer
model_name = "Qwen/Qwen2.5-Coder-7B-Instruct"
tokenizer = AutoTokenizer.from_pretrained(model_name)
model = AutoModelForCausalLM.from_pretrained(model_name)

# 训练参数
training_args = TrainingArguments(
    output_dir="./sft_model",
    num_train_epochs=3,
    per_device_train_batch_size=4,
    learning_rate=2e-5,
    warmup_steps=100,
    logging_steps=10,
)

# 训练
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=dataset,
)

trainer.train()
```

### 使用LLaMA Factory

```bash
# 准备配置文件
cat > sft_config.yaml << EOF
model_name_or_path: Qwen/Qwen2.5-Coder-7B-Instruct
dataset: sft_attack_success
template: qwen
output_dir: ./sft_model
num_train_epochs: 3
per_device_train_batch_size: 4
learning_rate: 2e-5
EOF

# 运行训练
llamafactory-cli train sft_config.yaml
```

### 按规则分阶段训练

```python
import json
from pathlib import Path

# 优先训练高ASR规则
high_asr_rules = ['T45', 'T19', 'T30', 'T12', 'T20']

for rule_id in high_asr_rules:
    print(f"训练规则 {rule_id}...")
    
    # 加载该规则的数据
    with open(f'data/sft_by_rule/sft_{rule_id}.json', 'r') as f:
        data = json.load(f)
    
    # 训练（代码略）
    # train_on_data(data, f'model_stage_{rule_id}')
```

## 📈 评估方法

### 1. 计算ASR（攻击成功率）

```python
def evaluate_asr(model, dataset):
    """评估模型在对抗样本上的ASR"""
    correct = 0
    total = 0
    
    for sample in dataset:
        # 模型预测
        prediction = model.predict(sample['input'])
        
        # 正确答案应该是YES
        if prediction == "YES":
            correct += 1
        total += 1
    
    asr = 1 - (correct / total)  # ASR = 判错率
    return asr
```

### 2. 按规则评估

```python
from collections import defaultdict

def evaluate_by_rule(model, dataset):
    """按规则评估ASR"""
    results = defaultdict(lambda: {'correct': 0, 'total': 0})
    
    for sample in dataset:
        rule_id = sample['metadata']['rule_id']
        prediction = model.predict(sample['input'])
        
        results[rule_id]['total'] += 1
        if prediction == "YES":
            results[rule_id]['correct'] += 1
    
    # 计算各规则的ASR
    for rule_id, stats in results.items():
        asr = 1 - (stats['correct'] / stats['total'])
        print(f"{rule_id}: ASR = {asr:.2%}")
```

## 💡 训练建议

### 1. 数据平衡

**问题**: T19占比过大（33.8%），可能导致过拟合

**解决方案**:
```python
# 欠采样T19
t19_samples = [s for s in dataset if s['metadata']['rule_id'] == 'T19']
t19_sampled = random.sample(t19_samples, min(5000, len(t19_samples)))

# 过采样小规则
t47_samples = [s for s in dataset if s['metadata']['rule_id'] == 'T47']
t47_oversampled = t47_samples * 100  # 重复100次

# 组合
balanced_dataset = other_samples + t19_sampled + t47_oversampled
```

### 2. 负样本

**问题**: 所有样本答案都是YES，缺少负样本

**解决方案**:
- 从原始数据集中添加功能不等价的样本（答案为NO）
- 确保正负样本比例平衡（建议1:1或2:1）

### 3. 渐进式训练

```python
# 第1阶段：高ASR规则（T45, T19, T30, T12, T20）
train_on_rules(['T45', 'T19', 'T30', 'T12', 'T20'], epochs=5)

# 第2阶段：中等ASR规则（T34, T09, T31, T41）
train_on_rules(['T34', 'T09', 'T31', 'T41'], epochs=3)

# 第3阶段：低ASR规则（其余）
train_on_rules(['T48', 'T47', 'T10', 'T07', 'T03', 'T32'], epochs=2)

# 第4阶段：全量微调
train_on_all(epochs=1)
```

### 4. 数据增强

```python
# 1. 改变注释内容（针对T20）
# 2. 改变重命名映射（针对T34）
# 3. 组合多个规则
# 4. 改变代码风格（保持功能等价）
```

## 📊 预期结果

### 训练前（基线）
```
总体ASR: 48.15%
  T45: 99.1%
  T19: 90.8%
  T30: 60.5%
  T12: 56.5%
  T20: 51.6%
  ...
```

### 训练后（目标）
```
总体ASR: < 10%
  T45: < 20%
  T19: < 15%
  T30: < 10%
  T12: < 10%
  T20: < 10%
  ...
```

**预期提升**: ASR降低**80%以上**

## 🔧 工具脚本

### 构建数据集
```bash
python build_sft_dataset.py
```

### 查看样本
```bash
python view_sft_samples.py --stats
python view_sft_samples.py --rule T45 --num 5
python view_sft_samples.py --random 10
```

### 生成报告
```bash
python correct_asr_calculation.py  # ASR统计
cat SFT_DATASET_REPORT.md          # 数据集报告
cat REGISTRY_RULES_ASR_REPORT.md   # 规则ASR报告
```

## ❓ FAQ

### Q1: 为什么所有样本的答案都是YES？
**A**: 因为所有样本都是功能等价的（adversarial_truth == True），仿真通过，所以正确答案应该是YES。LLM错误输出NO，说明被对抗代码欺骗了。

### Q2: 如何添加负样本（答案为NO）？
**A**: 可以从原始数据集中筛选功能不等价的样本，或者手动构造功能错误的代码。

### Q3: T19样本太多，会导致过拟合吗？
**A**: 可能会。建议对T19进行欠采样，或者使用类别权重平衡。

### Q4: 训练后ASR应该降到多少？
**A**: 目标是降到10%以下。如果ASR仍然很高，可能需要：
- 增加训练轮数
- 调整学习率
- 添加更多数据增强
- 平衡样本分布

### Q5: 训练后原始准确率会下降吗？
**A**: 理论上不应该下降。如果下降，可能是：
- 过拟合到对抗样本
- 需要添加更多正常样本
- 调整训练策略

## 📞 技术支持

如有问题，请查看：
- `SFT_DATASET_REPORT.md` - 数据集详细报告
- `REGISTRY_RULES_ASR_REPORT.md` - 规则ASR分析
- `ACCURATE_METRICS_REPORT.md` - 评估指标说明
