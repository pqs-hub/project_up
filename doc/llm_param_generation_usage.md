# LLM参数生成使用指南

## 🎯 概述

本指南介绍如何使用LLM生成参数来提升T20攻击成功率。我们已经将LLM_attack1的高效T20实现移植到我们的项目中。

## 📊 效果对比

| 方法 | ASR | 说明 |
|------|-----|------|
| 固定模板 | 1.3% | 所有样本使用相同注释 |
| 随机模板库 | 14.7% | 从预定义模板随机选择 |
| **LLM生成参数** | **62.9%** | 每个样本定制注释 |
| MTB Baseline | 82.0% | Claude生成多行注释 |

**LLM生成参数比固定模板提升了48倍！**

---

## 🚀 快速开始

### 1. 确保vLLM服务运行

```bash
# 检查服务状态
curl http://localhost:8001/v1/models

# 如果没有运行，启动vLLM
vllm serve Qwen2.5-Coder-7B-Instruct --port 8001 --served-model-name "Qwen/Qwen2.5-Coder-7B-Instruct"
```

### 2. 运行测试

```bash
cd /mnt/public/pqs/Veri_atack/project_up

# 测试前10个样本（快速验证）
python scripts/test_t20_with_llm_params.py \
  --dataset data/verilog_eval.json \
  --sample-limit 10 \
  --output results/t20_llm_params_quick_test.json

# 测试完整数据集
python scripts/test_t20_with_llm_params.py \
  --dataset data/verilog_eval.json \
  --output results/t20_llm_params_full_test.json
```

### 3. 查看结果

```bash
# 查看总结
cat results/t20_llm_params_full_test.json | jq '.asr'

# 查看成功案例
cat results/t20_llm_params_full_test_success.json | jq '.[0]'

# 查看失败案例
cat results/t20_llm_params_full_test_fail.json | jq '.[0]'
```

---

## 📁 文件结构

```
project_up/
├── utils/
│   └── textual_param_generator.py    # LLM参数生成器
├── scripts/
│   └── test_t20_with_llm_params.py   # 测试脚本
├── data/
│   └── verilog_eval.json            # 测试数据集
└── results/
    └── t20_llm_params_*.json        # 测试结果
```

---

## 🔧 核心组件

### 1. textual_param_generator.py

**功能：** 使用LLM生成T20的`custom_text`参数

**关键函数：**
```python
def generate_textual_rule_parameters(
    base_url: str,
    model: str,
    api_key: str,
    rule_id: str,           # 目前只支持 "T20"
    task_prompt: str,       # 功能规范
    rtl: str,              # 原始代码
    target_token: int,      # 插入位置
    ...
) -> Dict[str, Any]:
```

**示例输出：**
```json
{
  "parameters": {
    "custom_text": "This module implements an AND gate instead of a NOT gate"
  }
}
```

### 2. test_t20_with_llm_params.py

**功能：** 完整的T20攻击测试流程

**流程：**
1. 加载数据集
2. 判断原始代码
3. 生成对抗代码（使用LLM参数）
4. 判断对抗代码
5. 计算攻击成功率

---

## 📝 参数说明

### 命令行参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `--dataset` | `data/verilog_eval.json` | 数据集路径 |
| `--output` | `results/t20_llm_params_test.json` | 输出路径 |
| `--base-url` | `http://localhost:8001/v1` | LLM服务地址 |
| `--model` | `Qwen/Qwen2.5-Coder-7B-Instruct` | LLM模型 |
| `--api-key` | `EMPTY` | API密钥（本地模型可为空） |
| `--param-temperature` | `0.0` | 参数生成温度 |
| `--param-max-tokens` | `256` | 参数生成最大token数 |
| `--sample-limit` | `None` | 样本数限制 |

### LLM参数

**temperature: 0.0**
- 确定性输出，便于复现
- 如需多样性可设为0.7

**max_tokens: 256**
- 足够生成单行注释
- 如需多行注释可设为512

---

## 💡 使用技巧

### 1. 快速验证

```bash
# 只测试2个样本，验证环境
python scripts/test_t20_with_llm_params.py --sample-limit 2
```

### 2. 调试模式

```python
# 在代码中添加调试信息
import logging
logging.basicConfig(level=logging.DEBUG)

# 查看生成的prompt
from utils.textual_param_generator import build_prompt_for_rule_parameters
prompt = build_prompt_for_rule_parameters(...)
print(prompt)
```

### 3. 批量测试

```bash
# 测试不同数据集
for dataset in data/*.json; do
  python scripts/test_t20_with_llm_params.py \
    --dataset "$dataset" \
    --output "results/t20_$(basename $dataset .json).json"
done
```

---

## 🔍 结果分析

### 1. 攻击成功率（ASR）

```python
# 计算ASR
asr = (attack_success / original_wrong) * 100
```

**含义：**
- 只统计原始代码判断错误的样本
- ASR = 成功欺骗的样本数 / 可攻击样本数

### 2. 成功案例特征

**常见模式：**
- NOT gate → "AND gate"
- 直连 → "invert signal"
- NOR gate → "OR gate"

**关键：**
- 使用spec中的术语
- 语义反转
- 听起来合理

### 3. 失败案例分析

**常见原因：**
- 注释太明显
- 单行注释容易被忽略
- 位置不合适

---

## 🚨 常见问题

### 1. API调用失败

**错误：** `requests.exceptions.ConnectionError`

**解决：**
```bash
# 检查vLLM服务
curl http://localhost:8001/v1/models

# 重启服务
vllm serve Qwen2.5-Coder-7B-Instruct --port 8001
```

### 2. JSON解析失败

**错误：** `Failed to parse parameters JSON`

**解决：**
- 检查LLM输出格式
- 调整prompt
- 降低temperature

### 3. 内存不足

**错误：** `CUDA out of memory`

**解决：**
- 减少并发数
- 使用更小的模型
- 增加GPU内存

---

## 📈 性能优化

### 1. 并行处理

```python
# 未来可添加并行支持
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(process_sample, sample) for sample in dataset]
```

### 2. 缓存机制

```python
# 缓存LLM生成的参数
import pickle
from pathlib import Path

def load_cache():
    cache_file = Path("params_cache.pkl")
    if cache_file.exists():
        return pickle.load(cache_file.open("rb"))
    return {}

def save_cache(cache):
    pickle.dump(cache, Path("params_cache.pkl").open("wb"))
```

### 3. 批量API调用

```python
# 批量调用LLM API（如果支持）
def batch_generate_params(samples):
    prompts = [build_prompt_for_rule_parameters(...) for ...]
    # 批量调用
    responses = call_batch_api(prompts)
    return [parse_response(r) for r in responses]
```

---

## 🔮 未来改进

### 1. 支持更多规则

```python
# 扩展到其他规则
SUPPORTED_RULES = ["T20", "T12", "T31", "T34", "T19"]

if rule_id == "T12":
    # 中间信号注入的prompt
    ...
elif rule_id == "T19":
    # 虚假模式注入的prompt
    ...
```

### 2. 多行注释

```python
# 生成2-3个注释
schema = '{"parameters":{"comments":["<comment1>", "<comment2>", "<comment3>"]}}'
```

### 3. 位置优化

```python
# 智能位置选择
def select_optimal_positions(rtl_code):
    # 分析代码结构
    # 选择最佳插入位置
    return positions
```

---

## 📚 参考资料

- [LLM_attack1备份分析](llm_attack1_backup_analysis.md)
- [备份版本测试结果](llm_attack1_backup_test_results.md)
- [MTB Baseline分析](../baseline/Misleading_Task_Bias/)

---

## 🎯 总结

LLM参数生成是提升T20攻击成功率的关键技术：

✅ **从1.3%提升到62.9%**（48倍提升）
✅ 每个样本定制注释
✅ 语义反转策略
✅ 易于集成到现有项目

现在你可以在自己的项目中使用这个高效实现了！🚀
