# 随机遍历攻击位置策略

## 策略概述

**随机采样而非顺序遍历**，确保数据多样性和避免位置偏差。

## 工作原理

### 传统顺序遍历 ❌

```python
# 假设T03有5个端口候选: [clk, rst, data_in, count, valid]
# max_positions = 3

# 顺序遍历：总是选择前3个
selected = [clk, rst, data_in]  # 索引 0, 1, 2

# 问题：
# - count和valid永远不会被选中
# - 总是偏向靠前的候选
# - 数据缺乏多样性
```

### 随机遍历 ✅

```python
# 同样的5个候选
candidates = [clk, rst, data_in, count, valid]  # 索引 0-4
indices = [0, 1, 2, 3, 4]

# 随机打乱
random.shuffle(indices)  # → [2, 4, 0, 1, 3]

# 取前3个
selected_indices = [2, 4, 0]  # data_in, valid, clk

# 优势：
# ✅ 每次运行可能选择不同的候选
# ✅ 所有候选都有机会被选中
# ✅ 数据更加多样化
```

## 实际示例

### 场景：100个任务，T03规则（每个任务5个端口候选）

#### 不设置随机种子（每次不同）

```bash
# 第一次运行
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data.json \
  --output run1.jsonl \
  --max-positions 3

# 可能的选择（每个任务）:
Task001: [2, 4, 0]  # data_in, valid, clk
Task002: [1, 3, 2]  # rst, count, data_in
Task003: [4, 1, 0]  # valid, rst, clk
...

# 第二次运行（选择不同）
# 可能的选择:
Task001: [1, 0, 3]  # rst, clk, count
Task002: [4, 2, 1]  # valid, data_in, rst
Task003: [0, 3, 2]  # clk, count, data_in
...
```

#### 设置随机种子（可复现）

```bash
# 第一次运行
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data.json \
  --output run1.jsonl \
  --max-positions 3 \
  --random-seed 42  # ← 固定种子

# 选择:
Task001: [2, 4, 0]
Task002: [1, 3, 2]
Task003: [4, 1, 0]

# 第二次运行（相同种子）
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data.json \
  --output run2.jsonl \
  --max-positions 3 \
  --random-seed 42  # ← 相同种子

# 选择完全相同:
Task001: [2, 4, 0]  # ✅ 相同
Task002: [1, 3, 2]  # ✅ 相同
Task003: [4, 1, 0]  # ✅ 相同
```

## 代码实现

```python
# 获取候选位置
candidates = engine._get_candidates_for_transform(rtl, rule_id)

# ===== 随机打乱 =====
candidate_indices = list(range(len(candidates)))
random.shuffle(candidate_indices)

# 取前max_positions个
selected_indices = candidate_indices[:max_positions_per_rule]

# 为每个选中的位置创建攻击任务
for pos_idx in selected_indices:
    jobs.append((task, rule_id, pos_idx))
```

## 数据量估算

### 示例：100个任务，15个规则

```python
# 假设各规则的平均候选数
平均候选数 = {
    'T03': 5,   # 5个端口
    'T07': 4,   # 4对可交换assign
    'T09': 2,   # 2个AND表达式
    'T10': 2,   # 2个OR表达式
    'T12': 1,   # 1个三元表达式
    'T19': 3,   # 3个插入位置
    'T20': 8,   # 8个注释插入点
    'T30': 2,   # 2个包含常量的assign
    'T31': 4,   # 4个assign
    'T32': 6,   # 6个声明
    'T34': 1,   # 1个内部信号
    'T41': 1,   # 1个case块
    'T45': 4,   # 4个assign
    'T47': 2,   # 2个表达式
    'T48': 4,   # 4个assign
}

# max_positions = 3
实际采样数 = {
    'T03': min(5, 3) = 3,  # 随机选3个
    'T07': min(4, 3) = 3,
    'T09': min(2, 3) = 2,  # 只有2个，全选
    'T10': min(2, 3) = 2,
    'T12': min(1, 3) = 1,
    ...
}

# 总尝试次数
总次数 = 100任务 × Σ(每个规则的采样数)
      ≈ 100 × 35
      = 3,500 次尝试

# 对比顺序遍历（只用第一个）
顺序遍历 = 100 × 15 = 1,500 次

# 提升: 3,500 / 1,500 = 2.3倍
```

## 优势分析

### 1. 避免位置偏差 ✅

```python
# 顺序遍历：总是偏向前面的候选
端口候选: [clk, rst, data_in, count, valid]
顺序选择: 总是 clk, rst, data_in  # ❌ count和valid被忽略

# 随机遍历：每个候选概率相等
随机选择: 
  - Run1: data_in, valid, clk
  - Run2: rst, count, data_in
  - Run3: valid, rst, count
  # ✅ 所有候选都有机会
```

### 2. 数据多样性 ✅

```python
# 多次运行可以覆盖不同的候选组合
总候选组合数 = C(5, 3) = 10种组合
随机采样: 每次运行得到不同的组合
多次运行: 可以覆盖更多组合
```

### 3. 可复现性 ✅

```python
# 设置种子后，选择完全可复现
random.seed(42)
# 每次运行得到相同的随机顺序
```

## 使用建议

### 场景1: 快速探索（不设种子）

```bash
# 开发/调试阶段
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/dev_test.jsonl \
  --max-samples 10 \               # 只处理10个任务
  --max-positions 3 \              # 每个规则只测试3个位置
  --attack-base-url http://localhost:8002/v1 \
  --attack-model "obfuscation_merged" \
  --use-cot \
  --workers 4
```

### 场景2: 可复现实验（设种子）

```bash
# 详尽模式：一次性生成完整数据
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/final_dataset.jsonl \
  --max-positions 50 \             # 覆盖所有候选
  --random-seed 42 \               # 固定种子
  --attack-base-url http://localhost:8002/v1 \
  --attack-model "obfuscation_merged" \
  --use-cot \
  --workers 32 \
  --verbose
```

### 场景3: 详尽遍历（设大值）

```bash
# 详尽模式：一次性生成完整数据
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/final_dataset.jsonl \
  --max-positions 50 \             # 覆盖所有候选
  --random-seed 42 \               # 固定种子
  --attack-base-url http://localhost:8002/v1 \
  --attack-model "obfuscation_merged" \
  --use-cot \
  --workers 32 \
  --verbose
```

## 参数调优建议

| 场景 | max-positions | random-seed | 说明 |
|------|--------------|-------------|------|
| **快速验证** | 1-3 | 42 | 每个规则只测试少量位置 |
| **平衡数据** | 5-10 | 不设置 | 每次运行生成不同数据 |
| **详尽训练** | 20+ | 42 | 尽可能多的候选位置 |
| **科学实验** | 任意 | 固定值 | 确保可复现 |

## 总结

✅ **随机遍历优于顺序遍历**：
1. 避免总是选择前面的候选
2. 增加数据多样性
3. 所有候选位置都有机会被选中
4. 支持可复现（通过random_seed）

**推荐配置**：
```bash
--max-positions 10 --random-seed 42
```

这样既有足够的数据量，又保证结果可复现！
