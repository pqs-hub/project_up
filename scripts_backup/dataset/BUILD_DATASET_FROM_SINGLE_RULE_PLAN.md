# 从单规则攻击结果构建数据集计划

## 目标

从 `rule_eval/metrics_conf_v2/` 中的单规则攻击结果重新构建数据集，不考虑均匀性，但确保每个规则都有样本。

## 数据源分析

### 现有数据结构

```
rule_eval/metrics_conf_v2/
├── T03/
│   ├── adv_eval/          # 对抗代码的评估结果
│   │   └── q000000_rep0.json
│   └── orig_eval/         # 原始代码的评估结果（可能为空）
├── T07/
├── T12/
├── T19/
├── T20/
├── T31/
├── T32/
├── T34/
└── ...
```

### 评估结果JSON格式

```json
{
  "task_id": "q000000",
  "original_truth": true,           // 原始代码的ground truth
  "adversarial_truth": true,        // 对抗代码的ground truth
  "clean_truth": true,              // 清理后代码的ground truth
  "original_passed": null,          // 原始代码是否通过LLM判断
  "adversarial_passed": true,       // 对抗代码是否通过LLM判断
  "original_confidence": null,      // 原始代码的LLM置信度
  "adversarial_confidence": -0.9481,// 对抗代码的LLM置信度
  "original_code": "",              // 原始代码
  "adversarial_code": "YES",        // 对抗代码
  "original_error": "",
  "adversarial_error": ""
}
```

## 数据集构建策略

### 阶段1：数据收集与统计

**目标**：统计所有规则的攻击结果，了解数据分布

**步骤**：
1. 遍历所有规则目录（T01-T48）
2. 统计每个规则的样本数量
3. 统计攻击成功率（`original_truth == True && adversarial_truth == False`）
4. 统计原始代码正确率（`original_truth == True`）
5. 生成统计报告

**输出**：
- `rule_eval/dataset_build_stats.json`：统计报告
- 包含每个规则的样本数、成功率、失败率等

### 阶段2：数据筛选

**筛选条件**：

#### 必要条件（所有样本必须满足）
1. ✅ **原始代码正确**：`original_truth == True`
2. ✅ **有对抗代码**：`adversarial_code` 非空
3. ✅ **对抗代码有LLM判断**：`adversarial_passed` 不为 `null`

#### 优先级条件（用于排序）
1. 🥇 **攻击成功**：`original_passed == True && adversarial_passed == False`
2. 🥈 **原始代码被判断正确**：`original_passed == True`
3. 🥉 **置信度变化大**：`|original_confidence - adversarial_confidence|` 大

### 阶段3：数据集生成

**生成策略**：

#### 方案A：按规则分层采样（推荐）
```python
for each rule in all_rules:
    # 1. 筛选该规则的所有合格样本
    qualified = filter_samples(rule, conditions)
    
    # 2. 按优先级排序
    sorted_samples = sort_by_priority(qualified)
    
    # 3. 选择样本
    if len(sorted_samples) > 0:
        # 取所有攻击成功的样本
        success_samples = [s for s in sorted_samples if s.attack_success]
        # 如果成功样本太少，补充一些失败样本
        if len(success_samples) < MIN_PER_RULE:
            fail_samples = [s for s in sorted_samples if not s.attack_success]
            selected = success_samples + fail_samples[:MAX_PER_RULE - len(success_samples)]
        else:
            selected = success_samples[:MAX_PER_RULE]
        
        dataset.extend(selected)
```

**参数**：
- `MIN_PER_RULE`: 每个规则最少样本数（建议：10）
- `MAX_PER_RULE`: 每个规则最多样本数（建议：无限制，或500）

#### 方案B：全量采样（备选）
```python
# 收集所有合格样本，不限制每个规则的数量
all_qualified = []
for each rule in all_rules:
    qualified = filter_samples(rule, conditions)
    all_qualified.extend(qualified)

# 按攻击成功率排序
dataset = sort_by_attack_success(all_qualified)
```

### 阶段4：数据增强（可选）

**目标**：为每个样本添加额外信息

**增强字段**：
```json
{
  "task_id": "q000000",
  "rule_id": "T03",
  "rule_name": "Case Reorder",
  "original_code": "...",
  "adversarial_code": "...",
  "spec": "...",  // 从verilog_eval.json获取
  "attack_success": true,
  "original_passed": true,
  "adversarial_passed": false,
  "confidence_drop": 0.5,
  "applied_params": {...}  // 如果有的话
}
```

### 阶段5：输出格式

**输出文件**：
1. `data/dataset_from_single_rule.json`：完整数据集
2. `data/dataset_from_single_rule_success_only.json`：仅攻击成功样本
3. `data/dataset_from_single_rule_stats.json`：数据集统计信息

**统计信息**：
```json
{
  "total_samples": 5000,
  "rules_covered": 22,
  "attack_success_rate": 0.45,
  "per_rule_stats": {
    "T03": {
      "total": 250,
      "success": 120,
      "success_rate": 0.48
    },
    ...
  }
}
```

## 实现计划

### 脚本1：`scripts/dataset/analyze_single_rule_results.py`

**功能**：统计所有规则的攻击结果

**输出**：
- 每个规则的样本数
- 每个规则的攻击成功率
- 每个规则的数据质量（有多少样本满足筛选条件）

### 脚本2：`scripts/dataset/build_dataset_from_single_rule.py`

**功能**：从单规则结果构建数据集

**参数**：
```bash
python scripts/dataset/build_dataset_from_single_rule.py \
  --eval-dir rule_eval/metrics_conf_v2 \
  --verilog-eval data/verilog_eval.json \
  --output data/dataset_from_single_rule.json \
  --min-per-rule 10 \
  --max-per-rule 500 \
  --require-original-correct \
  --require-attack-success
```

**筛选选项**：
- `--require-original-correct`：要求原始代码正确
- `--require-attack-success`：要求攻击成功
- `--min-confidence-drop`：最小置信度下降（默认0.0）

### 脚本3：`scripts/dataset/visualize_dataset_stats.py`

**功能**：可视化数据集统计信息

**输出**：
- 规则分布柱状图
- 攻击成功率对比图
- 置信度变化分布图

## 关键问题

### Q1: 如何获取原始代码的LLM判断？

**问题**：`orig_eval/` 目录为空，没有原始代码的评估结果

**解决方案**：
1. **方案A**：从 `adv_eval/` 中的 `original_passed` 字段获取
2. **方案B**：重新运行原始代码的评估
3. **方案C**：假设 `original_truth == True` 时，原始代码被判断为正确

### Q2: 如何获取对抗代码的变换参数？

**问题**：评估结果中没有记录使用的变换参数

**解决方案**：
1. **方案A**：从对抗代码反推参数（困难）
2. **方案B**：不包含参数信息
3. **方案C**：查找是否有其他文件记录了参数

### Q3: 如何处理规则覆盖不均？

**问题**：某些规则可能样本很少

**解决方案**：
1. 设置 `MIN_PER_RULE`，如果某规则样本不足，记录警告
2. 对于样本不足的规则，可以考虑：
   - 降低筛选条件
   - 重新运行该规则的攻击
   - 在报告中标注

## 预期结果

### 数据集规模估算

假设：
- 22个规则
- 每个规则平均200个合格样本
- 攻击成功率约40%

**预期**：
- 总样本数：~4,400
- 攻击成功样本：~1,760
- 攻击失败样本：~2,640

### 与现有数据集对比

| 数据集 | 样本数 | 规则数 | 均匀性 | 攻击成功率 |
|--------|--------|--------|--------|------------|
| `sft_from_eval_highquality.jsonl` | 7,071 | 15 | 高 | 未知 |
| **新数据集（预期）** | ~4,400 | 22 | 低 | ~40% |

## 下一步

1. ✅ 确认计划
2. 实现 `analyze_single_rule_results.py`
3. 实现 `build_dataset_from_single_rule.py`
4. 运行并生成数据集
5. 分析数据集质量
6. 可选：实现可视化脚本
