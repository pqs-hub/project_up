# LLM_attack1备份版本分析

## 🎯 核心发现

**LLM_attack1使用`evaluate_rules.py`脚本，结合LLM生成参数，达到了51.6%的T20攻击成功率！**

---

## 📋 完整流程

### 1. 评估脚本：`evaluate_rules.py`

**位置：** `/mnt/public/pqs/LLM_attack1/LLM_attack_back/LLM_attack/scripts/eval/evaluate_rules.py`

**核心流程：**

```python
# 1. 遍历数据集，对每条规则：
for task in dataset:
    for rule_id in rules:
        # 2. 对于文本类规则（T20, T12, T31, T34, T19），使用LLM生成参数
        if rule_id in {"T20", "T12", "T31", "T34", "T19"}:
            params_used = generate_textual_rule_parameters(
                base_url=param_base_url,
                model=param_model,  # Qwen2.5-Coder-7B
                api_key=param_api_key,
                rule_id=rule_id,
                task_prompt=task.get("prompt", ""),
                rtl=code,
                target_token=k,
                target_line=target_line,
                target_signal=target_signal,
                temperature=args.param_temperature,
                max_tokens=args.param_max_tokens,
            )
        
        # 3. 应用变换
        new_code = engine.apply_transform(code, rule_id, target_token=k, **params_used)
        
        # 4. 评估攻击成功率
        # - 原始代码：LLM判断
        # - 对抗代码：LLM判断
        # - 计算ASR = (LLM判错数) / (功能等价样本数)
```

---

## 🔑 关键参数

### 命令行参数

```bash
python scripts/eval/evaluate_rules.py \
  --rules T20 \
  --dataset data/qualified_dataset.json \
  --results-root rule_eval/results_full_all_rules \
  --eval-output rule_eval/metrics_conf_v2_on_fullall_adv \
  --provider local \
  --model Qwen2.5-Coder-7B \
  --base-url http://localhost:8000/v1 \
  --param-model Qwen2.5-Coder-7B \
  --param-base-url http://localhost:8000/v1 \
  --param-temperature 0.0 \
  --param-max-tokens 256
```

### 参数说明

| 参数 | 值 | 说明 |
|------|-----|------|
| `--rules` | T20 | 要测试的规则 |
| `--dataset` | qualified_dataset.json | 数据集 |
| `--provider` | local | 使用本地模型 |
| `--model` | Qwen2.5-Coder-7B | 判断模型 |
| `--param-model` | Qwen2.5-Coder-7B | 参数生成模型 |
| `--param-temperature` | 0.0 | 参数生成温度 |
| `--param-max-tokens` | 256 | 参数生成最大token数 |

---

## 📊 T20的51.6%成功率是如何达到的？

### 1. 数据集规模

```
功能等价样本: 16,499个
LLM判对: 7,980个 (48.4%)
LLM判错(攻击成功): 8,519个 (51.6%)
```

**关键：** 大规模数据集，不是100个样本！

### 2. LLM生成参数

**对于每个样本：**
```python
# 调用Qwen2.5-Coder生成误导性注释
params = generate_textual_rule_parameters(
    rule_id="T20",
    task_prompt="Build a circuit...",  # 功能规范
    rtl="module top_module...",         # 原始代码
    target_token=k,                      # 插入位置
    ...
)

# params = {"custom_text": "This sequential logic uses clock..."}
```

**每个样本都有定制的误导性注释！**

### 3. 位置采样策略

**来自`AttackConfigGenerator.py`：**
```python
# 采样代表性位置
if max_positions == 2:
    indices = [0, n-1]  # 首尾
else:
    indices = [0, n//4, n//2, 3*n//4, n-1]  # 5个代表性位置
```

**不是遍历所有位置，而是采样2-5个代表性位置！**

### 4. 评估流程

```python
# 1. 生成对抗代码
for k in sampled_positions:
    params = generate_textual_rule_parameters(...)
    adv_code = engine.apply_transform(code, "T20", target_token=k, **params)
    if adv_code != code:
        break  # 只取第一个成功的

# 2. 评估
orig_verdict = llm_judge(spec, orig_code)  # 原始代码
adv_verdict = llm_judge(spec, adv_code)    # 对抗代码

# 3. 计算ASR
if orig_verdict == True and adv_verdict == False:
    attack_success += 1
```

---

## 💡 为什么51.6%比我们的1.3%高这么多？

### 差异对比

| 维度 | LLM_attack1 (51.6%) | 我们 (1.3%) |
|------|---------------------|-------------|
| **数据集** | 16,499个样本 | 100个样本 |
| **参数生成** | LLM生成（Qwen2.5-Coder） | 固定模板 |
| **位置策略** | 采样2-5个代表性位置 | 固定位置或遍历所有 |
| **注释内容** | 每个样本定制 | 所有样本相同 |
| **判断模型** | Qwen2.5-Coder-7B | TargetModelClient |

### 关键差异

#### 1. LLM生成参数 vs 固定模板

**LLM_attack1：**
```python
# 样本1: "Build a circuit that outputs LOW"
params = {"custom_text": "This sequential logic transitions to HIGH on reset"}

# 样本2: "Build a 4-bit counter"
params = {"custom_text": "This combinational logic uses clock signal to count"}
```

**我们：**
```python
# 所有样本都用相同的模板
params = {"custom_text": "UART Transmitter - 9600 baud"}
```

**效果差异：**
- LLM生成：每个样本都有针对性的误导
- 固定模板：大部分样本不相关

#### 2. 数据集规模

**LLM_attack1：**
- 16,499个功能等价样本
- 来自`qualified_dataset.json`
- 经过筛选和验证

**我们：**
- 100个样本
- 来自`verilog_eval.json`
- 可能包含不适合T20的样本

#### 3. 位置采样策略

**LLM_attack1：**
```python
# 只测试2-5个代表性位置
positions = [0, n//4, n//2, 3*n//4, n-1]

# 每个位置都用LLM生成不同的注释
for pos in positions:
    params = generate_textual_rule_parameters(target_token=pos, ...)
    adv_code = apply_transform(..., **params)
    if success:
        break
```

**我们：**
```python
# 要么固定位置，要么遍历所有位置
# 但都用相同的固定模板
```

---

## 🚀 如何复现51.6%的成功率？

### 方案1：使用LLM_attack1的完整流程

```bash
cd /mnt/public/pqs/LLM_attack1/LLM_attack_back/LLM_attack

# 1. 准备数据集
# 使用 qualified_dataset.json

# 2. 启动参数生成模型（Qwen2.5-Coder-7B）
# vllm serve Qwen2.5-Coder-7B --port 8000

# 3. 运行评估
python scripts/eval/evaluate_rules.py \
  --rules T20 \
  --dataset data/qualified_dataset.json \
  --results-root rule_eval/results \
  --eval-output rule_eval/metrics \
  --provider local \
  --model Qwen2.5-Coder-7B \
  --base-url http://localhost:8000/v1 \
  --param-model Qwen2.5-Coder-7B \
  --param-base-url http://localhost:8000/v1 \
  --param-temperature 0.0 \
  --param-max-tokens 256
```

### 方案2：移植到我们的项目

**需要做的：**

1. **复制参数生成器**
   ```bash
   cp /mnt/public/pqs/LLM_attack1/LLM_attack_back/LLM_attack/scripts/eval/textual_param_generator.py \
      /mnt/public/pqs/Veri_atack/project_up/utils/
   ```

2. **修改测试脚本**
   ```python
   # 在 test_llm_attack_t20.py 中
   from utils.textual_param_generator import generate_textual_rule_parameters
   
   # 对每个样本
   for sample in dataset:
       # 生成参数
       params = generate_textual_rule_parameters(
           base_url="http://localhost:8000/v1",
           model="Qwen2.5-Coder-7B",
           api_key="EMPTY",
           rule_id="T20",
           task_prompt=sample['prompt'],
           rtl=sample['canonical_solution'],
           target_token=0,  # 或采样多个位置
       )
       
       # 应用变换
       transformed = engine.apply_transform(
           code=sample['canonical_solution'],
           transform_id='T20',
           target_token=0,
           **params
       )
   ```

3. **使用相同的数据集**
   - 获取`qualified_dataset.json`
   - 或使用更大的数据集

---

## 📈 预期效果

### 如果使用LLM生成参数

**当前：**
- 固定模板：1.3%
- 随机模板库：14.7%

**使用LLM生成：**
- 小数据集（100样本）：20-30%
- 大数据集（16,499样本）：40-60%

### 如果结合其他优化

**MTB的策略：**
- 多行注释（2-3个）
- 位置灵活
- 混淆组合/时序逻辑

**预期：**
- LLM生成 + MTB策略：60-80%

---

## 🎯 总结

### LLM_attack1的51.6%成功率来自：

1. **✅ LLM生成参数**
   - 使用Qwen2.5-Coder
   - 每个样本定制注释
   - 结合spec和code

2. **✅ 大规模数据集**
   - 16,499个功能等价样本
   - 经过筛选和验证

3. **✅ 智能位置采样**
   - 不遍历所有位置
   - 采样2-5个代表性位置

4. **✅ 完整的评估流程**
   - 原始代码判断
   - 对抗代码判断
   - 计算ASR

### 我们要达到51.6%需要：

1. **使用LLM生成参数**
   - 复制`textual_param_generator.py`
   - 集成到测试脚本

2. **使用更大的数据集**
   - 获取`qualified_dataset.json`
   - 或生成更多样本

3. **采用位置采样策略**
   - 不要遍历所有位置
   - 采样代表性位置

4. **优化prompt**
   - 参考MTB的多行注释策略
   - 明确混淆组合/时序逻辑

---

生成时间：2026-03-28
分析对象：LLM_attack1备份版本
关键文件：`scripts/eval/evaluate_rules.py`, `scripts/eval/textual_param_generator.py`
核心发现：使用LLM生成参数 + 大规模数据集 = 51.6% ASR
