# 数据集样本过滤功能说明

## 🎯 功能概述

新增 `--only-valid-samples` 参数，允许在生成数据集时**只保留高质量样本**（成功应用且通过testbench）。

---

## 📊 样本分类

### 生成过程中的样本状态

| 状态 | 说明 | testbench_passed | 是否保留 |
|------|------|------------------|----------|
| **success** | 攻击成功（判断模型被欺骗） | ✅ True | ✅ 保留 |
| **attack_failed** | 攻击失败（判断模型仍正确） | ✅ True | ✅ 保留 |
| **judge_error** | 判断模型调用失败 | ✅ True | ✅ 保留 |
| **no_change** | 变换未产生变化 | ❌ False | ❌ 过滤 |
| **testbench_failed** | testbench验证失败 | ❌ False | ❌ 过滤 |
| **testbench_error** | testbench运行错误 | ❌ False | ❌ 过滤 |
| **exception** | 处理异常 | ❌ False | ❌ 过滤 |

### 过滤规则

**启用 `--only-valid-samples` 后**：
- ✅ **保留**：`testbench_passed == True` 的样本
  - 包括：success, attack_failed, judge_error
  - 这些样本保证了代码变换是**功能等价**的

- ❌ **过滤**：`testbench_passed == False` 的样本
  - 包括：no_change, testbench_failed, testbench_error, exception
  - 这些样本存在质量问题，不应用于训练

---

## 🚀 使用方法

### 方式1：生成所有样本（默认）

```bash
python pipeline/6_generate_attack_dataset.py \
  --eval-file data/verilog_eval_correct_only.json \
  --output data/attack_dataset_all.jsonl \
  --max-samples 10 \
  --enable-llm-params
```

**结果**：保存所有样本（包括失败的），用于调试分析

---

### 方式2：只保留有效样本（推荐）⭐

```bash
python pipeline/6_generate_attack_dataset.py \
  --eval-file data/verilog_eval_correct_only.json \
  --output data/attack_dataset_valid.jsonl \
  --max-samples 10 \
  --enable-llm-params \
  --only-valid-samples
```

**结果**：只保存testbench通过的样本，用于训练

---

## 📈 效果对比

### 示例输出（不加 --only-valid-samples）

```
数据集生成完成！
  耗时: 59.8秒
  总样本数: 58
  成功样本数: 0
  失败样本数: 58
  已保存样本数: 58 (包含所有样本)
  输出文件: data/attack_dataset_all.jsonl

失败样本统计:
  no_change: 36
  attack_failed: 17
  testbench_failed: 2
  judge_error: 3
```

### 示例输出（加 --only-valid-samples）

```
数据集生成完成！
  耗时: 59.8秒
  总样本数: 58
  成功样本数: 0
  失败样本数: 58
  已保存样本数: 20 (只包含testbench通过的)  ← 过滤掉38个
  输出文件: data/attack_dataset_valid.jsonl

失败样本统计:
  no_change: 36        ← 被过滤
  attack_failed: 17    ← 保留（testbench通过）
  testbench_failed: 2  ← 被过滤
  judge_error: 3       ← 保留（testbench通过）
```

**过滤效果**：
- 总样本：58 → 保留：20
- 过滤率：65.5% (38/58)
- 保留的样本都是**功能等价**的代码变换

---

## 🎯 使用场景

### 场景1：调试分析
**不加** `--only-valid-samples`

**目的**：
- 分析失败原因
- 优化prompt
- 调试代码变换逻辑

**示例**：
```bash
# 生成小规模测试集，包含所有样本
python pipeline/6_generate_attack_dataset.py \
  --eval-file data/verilog_eval_correct_only.json \
  --output data/debug_dataset.jsonl \
  --max-samples 5 \
  --enable-llm-params \
  --verbose
```

然后分析失败样本：
```python
import json

with open('data/debug_dataset.jsonl') as f:
    samples = [json.loads(line) for line in f]

# 分析testbench失败的样本
failed = [s for s in samples if s['status'] == 'testbench_failed']
for s in failed:
    print(f"规则: {s['attack_rule']}")
    print(f"原因: {s['failure_reason']}")
    print(f"参数: {s['attack_params']}")
    print()
```

---

### 场景2：训练数据集
**加** `--only-valid-samples` ⭐

**目的**：
- 生成高质量训练数据
- 确保所有样本功能等价
- 减少存储空间

**示例**：
```bash
# 生成大规模训练集，只保留有效样本
python pipeline/6_generate_attack_dataset.py \
  --eval-file data/verilog_eval_correct_only.json \
  --output data/train_dataset_clean.jsonl \
  --max-samples 100 \
  --enable-llm-params \
  --only-valid-samples
```

---

## 📊 数据质量保证

### testbench通过的样本保证

启用 `--only-valid-samples` 后，保存的每个样本都满足：

1. ✅ **功能等价性**
   - 原始代码和变换后代码通过相同的testbench
   - RefModule 和 TopModule 行为一致

2. ✅ **语法正确性**
   - 变换后的代码能够编译
   - 没有语法错误

3. ✅ **变换有效性**
   - 代码确实发生了变化（非 no_change）
   - 变换成功应用

### 不保证的内容

❌ **攻击成功率**
- 保留的样本中可能大部分是 `attack_failed`
- 判断模型未被欺骗
- 需要优化prompt提高攻击成功率

---

## 🔍 验证过滤结果

### 检查保存的样本状态

```python
import json
from collections import Counter

with open('data/attack_dataset_valid.jsonl') as f:
    samples = [json.loads(line) for line in f]

# 统计状态分布
status_count = Counter(s['status'] for s in samples)
print("状态分布:", dict(status_count))

# 验证所有样本都通过testbench
all_passed = all(s.get('testbench_passed', False) for s in samples)
print(f"所有样本testbench通过: {all_passed}")

# 统计各规则的样本数
rule_count = Counter(s['attack_rule'] for s in samples)
print("规则分布:", dict(rule_count))
```

**预期输出**：
```
状态分布: {'attack_failed': 17, 'judge_error': 3}
所有样本testbench通过: True
规则分布: {'T19': 2, 'T20': 5, 'T31': 5, 'T32': 1, 'T45': 2, ...}
```

---

## 💡 最佳实践

### 1. 迭代开发流程

```bash
# Step 1: 小规模测试（不过滤）
python pipeline/6_generate_attack_dataset.py \
  --max-samples 5 \
  --output data/test_all.jsonl \
  --enable-llm-params

# Step 2: 分析失败原因，优化prompt

# Step 3: 中等规模验证（过滤）
python pipeline/6_generate_attack_dataset.py \
  --max-samples 20 \
  --output data/test_valid.jsonl \
  --enable-llm-params \
  --only-valid-samples

# Step 4: 检查质量，确认有足够有效样本

# Step 5: 大规模生成（过滤）
python pipeline/6_generate_attack_dataset.py \
  --max-samples 100 \
  --output data/train_clean.jsonl \
  --enable-llm-params \
  --only-valid-samples
```

### 2. 存储优化

对于大规模数据集：
- ✅ 使用 `--only-valid-samples` 减少文件大小
- ✅ 定期清理调试用的完整数据集
- ✅ 只保留训练用的高质量数据

### 3. 质量监控

定期检查保留率：
```python
import json

# 读取完整数据集（不过滤）
with open('data/attack_dataset_all.jsonl') as f:
    all_samples = [json.loads(line) for line in f]

# 读取过滤后数据集
with open('data/attack_dataset_valid.jsonl') as f:
    valid_samples = [json.loads(line) for line in f]

retain_rate = len(valid_samples) / len(all_samples) * 100
print(f"样本保留率: {retain_rate:.1f}%")

# 如果保留率 < 20%，说明质量问题严重，需要优化
if retain_rate < 20:
    print("⚠️ 警告：保留率过低，请检查：")
    print("  1. LLM参数生成质量")
    print("  2. 代码变换逻辑")
    print("  3. testbench配置")
```

---

## 🐛 故障排查

### 问题1：保留率为0%

**症状**：
```
已保存样本数: 0 (只包含testbench通过的)
```

**可能原因**：
1. testbench runner未正确配置
2. 所有变换都导致功能错误
3. LLM生成的参数质量极差

**解决方案**：
```bash
# 不加过滤，查看原始样本
python pipeline/6_generate_attack_dataset.py \
  --max-samples 5 \
  --output data/debug.jsonl \
  --verbose

# 检查失败原因
python -c "
import json
with open('data/debug.jsonl') as f:
    samples = [json.loads(line) for line in f]
from collections import Counter
print(Counter(s['status'] for s in samples))
"
```

### 问题2：保留率过高（>80%）

**症状**：几乎所有样本都被保留

**可能原因**：
1. testbench太宽松
2. 缺少边界条件测试
3. 大量 `no_change` 样本（但这些会被过滤）

**解决方案**：检查testbench质量

---

## 📝 修改记录

| 日期 | 版本 | 修改内容 |
|------|------|----------|
| 2026-03-26 | v1.0 | 新增 `--only-valid-samples` 参数 |

---

**下一步优化方向**：
1. 添加 `--min-quality-score` 参数，过滤低质量样本
2. 添加样本去重逻辑
3. 支持按规则ID分别保存
