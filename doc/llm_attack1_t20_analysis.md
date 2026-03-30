# LLM_attack1的T20实现分析

## 🎯 核心策略

### 1. 位置采样策略

**代码位置：** `AttackConfigGenerator.py` 第212-213行

```python
elif transform.id == "T20":
    candidates = extract_comment_insert_points(vs.code, vs)
```

**位置采样：** 第240-252行

```python
# 多样采样：首、1/4、1/2、3/4、尾，避免仅默认位置
if self.max_positions == 2:
    indices = [0, n - 1]  # 首尾两个位置
else:
    indices = [
        0,                    # 首
        max(0, n // 4),      # 1/4处
        n // 2,              # 中间
        min(n - 1, (3 * n) // 4),  # 3/4处
        n - 1,               # 尾
    ]
    indices = list(dict.fromkeys(indices))[:self.max_positions]  # 去重并截断
```

**关键发现：**
- ✅ **不是遍历所有位置**
- ✅ 而是**采样代表性位置**（首、1/4、1/2、3/4、尾）
- ✅ 默认`max_positions=2`，即只测试**首尾两个位置**

---

### 2. 参数采样策略

**代码位置：** `AttackConfigGenerator.py` 第267-272行

```python
if tid == 'T20' and name == 'custom_text':
    samples = list(MISLEADING_COMMENT_SAMPLES)
    if len(samples) > self.max_params * 2:
        samples = random.sample(samples, self.max_params * 2)
    param_grids.append([(name, v) for v in samples])
    continue
```

**注释文案库：** 第17-30行

```python
MISLEADING_COMMENT_SAMPLES = [
    "UART Transmitter - 9600 baud",
    "SPI Master Controller",
    "I2C Slave Interface",
    "Clock Divider - ratio 4",
    "PWM Generator - 8bit resolution",
    "active low reset",
    "clock enable signal",
    "data valid strobe",
    "Sequential logic - register update",
    "reset condition",
    "overflow detected",
    "Verified: simulation passed all test vectors",
]
```

**关键发现：**
- ✅ 使用**预定义的注释文案库**
- ✅ 从库中**随机采样**（默认`max_params * 2`个）
- ✅ 这些文案与我们之前看到的LLM_attack的T20实现**完全一致**

---

### 3. 配置生成策略

**代码位置：** `AttackConfigGenerator.py` 第166-173行

```python
# 组合位置和参数
for token in target_tokens:
    for params in param_sets:
        configs.append(AttackConfig(
            transform_id=transform.id,
            target_token=token,
            parameters=params
        ))
```

**关键发现：**
- ✅ **笛卡尔积组合**：位置 × 参数
- ✅ 例如：2个位置 × 12个注释文案 = 24个配置

---

### 4. 总体采样上限

**代码位置：** `AttackConfigGenerator.py` 第100-103行

```python
# 采样（如果超过上限）
if len(all_configs) > self.max_attacks:
    all_configs = random.sample(all_configs, self.max_attacks)
```

**默认配置：** 第74行

```python
max_attacks_per_sample: int = 30,
```

**关键发现：**
- ✅ 每个样本最多生成**30个攻击配置**
- ✅ 如果所有规则的配置总数超过30，会随机采样

---

## 📊 与我们的对比

### 我们的方法（遍历所有位置）

```python
# 获取所有可能的位置
max_positions = get_max_positions(rtl, engine)  # ~100个

# 遍历所有位置
for position_idx in range(max_positions):
    transformed = engine.apply_transform(
        code=rtl,
        transform_id='T20',
        target_token=position_idx,
    )
```

**特点：**
- 测试所有~100个位置
- 每个位置使用固定参数
- 总测试次数：~100次/样本

---

### LLM_attack1的方法（采样代表性位置）

```python
# 采样代表性位置
if max_positions == 2:
    indices = [0, n - 1]  # 首尾
else:
    indices = [0, n//4, n//2, 3*n//4, n-1]  # 5个代表性位置

# 采样注释文案
comment_samples = random.sample(MISLEADING_COMMENT_SAMPLES, max_params * 2)

# 组合
for position in indices:
    for comment in comment_samples:
        configs.append(...)
```

**特点：**
- 只测试2-5个代表性位置
- 每个位置测试多个注释文案
- 总测试次数：2-5个位置 × 12个文案 = 24-60次/样本

---

## 💡 关键洞察

### 1. LLM_attack1不遍历所有位置

**原因：**
- 成本太高（~100个位置）
- 收益有限（位置差异小）
- 采样代表性位置即可

**策略：**
- 首尾位置（覆盖边界）
- 1/4、1/2、3/4位置（覆盖中间）
- 总共2-5个位置

---

### 2. 更关注参数多样性

**LLM_attack1的重点：**
- ✅ 位置：2-5个代表性位置
- ✅ 参数：12个不同的注释文案

**我们的重点：**
- ✅ 位置：~100个所有位置
- ❌ 参数：固定的注释文案

**对比：**
```
LLM_attack1: 少量位置 × 多样参数 = 24-60次测试
我们:        所有位置 × 固定参数 = ~100次测试
```

---

### 3. 采样策略更高效

**LLM_attack1的优势：**
1. **覆盖代表性位置**
   - 首尾（边界情况）
   - 1/4、1/2、3/4（中间情况）

2. **参数多样性**
   - 12种不同的注释文案
   - 覆盖不同的误导类型

3. **总体效率**
   - 测试次数少（24-60 vs ~100）
   - 覆盖面广（位置+参数）

---

## 📋 测试结果对比

### LLM_attack1的T20结果

**来自：** `rule_eval/metrics/T20_report.json`

```json
{
  "rule_id": "T20",
  "num_samples": 17581,
  "applicable_samples": 17581,
  "coverage": 1.0,
  "success_rate": 1.0,
  "acc_orig": 0.938,
  "acc_adv": 0.8891,
  "gain": 0.0489,
  "asr": 0.058,
  "strength": 0.0489
}
```

**解读：**
- `acc_orig`: 原始代码准确率 93.8%
- `acc_adv`: 攻击后准确率 88.91%
- `gain`: 准确率下降 4.89%
- `asr`: 攻击成功率 5.8%

**注意：** 这个5.8%的ASR与我们测试的成功率（10-16.7%）接近！

---

### 我们的T20结果

**遍历所有位置：**
```
最佳位置: 16.7% (位置0, 1, 5, 10, 18)
平均位置: ~10%
前1/3位置: 10.5%
中1/3位置: 9.5%
后1/3位置: 8.4%
```

**LLM_attack1采样策略（估算）：**
```
位置0 (首): 16.7%
位置n-1 (尾): ~8.4%
平均: ~12.5%
```

**对比：**
- 遍历所有位置：平均10%
- LLM_attack1采样：估计12.5%
- **差异很小！**

---

## 🎯 结论

### 1. LLM_attack1的策略更合理

**不遍历所有位置，而是：**
- ✅ 采样2-5个代表性位置
- ✅ 每个位置测试多个参数
- ✅ 总测试次数更少，覆盖面更广

### 2. 遍历所有位置价值有限

**我们的测试证明：**
- 所有位置的成功率都很接近（8-17%）
- 位置差异远小于参数差异
- 遍历所有位置成本高，收益低

### 3. 应该学习LLM_attack1的策略

**建议采用：**
```python
# 采样代表性位置
n = len(candidates)
if n <= 5:
    positions = list(range(n))
else:
    positions = [0, n//4, n//2, 3*n//4, n-1]

# 采样多个参数
comment_samples = random.sample(COMMENT_LIBRARY, 10)

# 组合测试
for pos in positions:
    for comment in comment_samples:
        test(pos, comment)
```

**预期效果：**
- 测试次数：5 × 10 = 50次（vs 我们的~100次）
- 覆盖面：更好（多样参数）
- 成功率：相近（12-15%）

---

## 🚀 优化建议

### 方案1：采用LLM_attack1的采样策略

```python
# 位置采样
positions = [0, n//4, n//2, 3*n//4, n-1]  # 5个代表性位置

# 参数采样
comments = random.sample(COMMENT_LIBRARY, 10)  # 10个注释文案

# 组合
configs = [(pos, comment) for pos in positions for comment in comments]
# 总共50个配置
```

**优势：**
- 测试次数减半（50 vs 100）
- 覆盖面更广（多样参数）
- 效率更高

### 方案2：改进T20实现（更重要）

**参考MTB：**
- 使用Claude生成注释
- 多行注释
- 混淆组合/时序逻辑

**预期提升：**
- 当前：10-16.7%
- 改进后：50-80%

### 方案3：减少T20，增加T45

**训练数据调整：**
```
当前: T20(25%) + T45(20%)
建议: T20(10%) + T45(70%)
```

**预期整体成功率：**
- 当前：47%
- 优化后：60%+

---

## 📊 总结

### LLM_attack1的T20实现

1. **不遍历所有位置**
   - 只采样2-5个代表性位置
   - 首、1/4、1/2、3/4、尾

2. **关注参数多样性**
   - 12种不同的注释文案
   - 随机采样组合

3. **高效的采样策略**
   - 少量位置 × 多样参数
   - 覆盖面广，成本低

### 我们应该学习的

1. **采样代表性位置**
   - 不需要遍历所有~100个位置
   - 5个代表性位置即可

2. **增加参数多样性**
   - 测试多个注释文案
   - 而不是固定文案

3. **优化总体策略**
   - 改进T20实现（参考MTB）
   - 或减少T20比例，增加T45

---

生成时间：2026-03-28
分析对象：LLM_attack1代码库
关键文件：AttackConfigGenerator.py, AdversarialDatasetGenerator.py
