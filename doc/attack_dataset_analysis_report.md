# 攻击数据集分析报告

**数据集**: `attack_dataset_exhaustive.jsonl`  
**分析时间**: 2026-03-27  
**总样本数**: 39,347

---

## 📊 数据集概览

### 基本统计
- **总样本数**: 39,347
- **唯一任务数**: 12,254
- **平均置信度**: 0.7768 (77.68%)
- **Testbench通过率**: 100.00%

### 覆盖率
- 平均每个任务有 **~3.2** 个攻击变体
- 所有样本均通过了功能验证测试

---

## 🎯 攻击规则分布

| 规则编号 | 样本数 | 占比 | 说明 |
|---------|--------|------|------|
| T20 | 10,796 | 27.4% | 主导规则 |
| T45 | 10,018 | 25.5% | 第二大规则 |
| T03 | 8,364 | 21.3% | 第三大规则 |
| T32 | 5,276 | 13.4% | |
| T48 | 1,797 | 4.6% | |
| T07 | 1,429 | 3.6% | |
| T31 | 544 | 1.4% | |
| T30 | 323 | 0.8% | |
| T34 | 297 | 0.8% | |
| T09 | 284 | 0.7% | |
| T10 | 123 | 0.3% | |
| T12 | 93 | 0.2% | |
| T19 | 3 | 0.0% | 稀有规则 |

### 分布特征
- **高频规则** (T20, T45, T03): 占总样本的 74.2%
- **中频规则** (T32, T48, T07): 占总样本的 21.6%
- **低频规则** (其余): 占总样本的 4.2%
- **T19规则极少**: 仅3个样本，可能需要更多数据

---

## ⚠️ 数据质量问题

### 重复变换检测
- **重复组数**: 728组
- **影响**: 部分样本存在相同的原始代码和变换代码组合

#### 示例问题
- 样本 [54, 3525]: 2个重复
- 样本 [88, 89, 90]: 3个重复
- 样本 [113, 114, 115, 116]: 4个重复
- 还有725组其他重复

### 质量评估
✅ **无缺失字段**  
✅ **所有样本通过Testbench**  
✅ **置信度良好** (平均77.68%)  
⚠️ **存在重复变换** (728组)

---

## 💡 建议与后续操作

### 1. 去重处理
```bash
# 可以考虑添加去重逻辑，保留每组重复中置信度最高的样本
python3 pipeline/7_analyze_attack_dataset.py \
  data/attack_dataset_exhaustive.jsonl \
  --min-confidence 0.8
```

### 2. 规则平衡
- 考虑增加T19、T12、T10等低频规则的样本数
- 或在训练时对低频规则进行过采样

### 3. 数据转换

#### 转换为SFT格式
```bash
python3 pipeline/7_analyze_attack_dataset.py \
  data/attack_dataset_exhaustive.jsonl \
  --to-sft data/attack_dataset_sft.jsonl
```

#### 转换为Alpaca格式
```bash
python3 pipeline/7_analyze_attack_dataset.py \
  data/attack_dataset_exhaustive.jsonl \
  --to-alpaca data/attack_dataset_alpaca.jsonl
```

#### 按规则过滤
```bash
# 只保留特定规则
python3 pipeline/7_analyze_attack_dataset.py \
  data/attack_dataset_exhaustive.jsonl \
  --filter-rules "T20,T45,T03" \
  --to-sft data/attack_dataset_top3_sft.jsonl
```

#### 按置信度过滤
```bash
# 只保留高置信度样本
python3 pipeline/7_analyze_attack_dataset.py \
  data/attack_dataset_exhaustive.jsonl \
  --min-confidence 0.85 \
  --to-alpaca data/attack_dataset_high_conf.jsonl
```

---

## 📈 数据集优势

1. **大规模**: 近4万个样本，涵盖1.2万+任务
2. **高质量**: 100%通过功能测试，平均置信度78%
3. **多样性**: 13种不同的攻击规则
4. **完整性**: 无缺失字段

## 🔍 潜在改进

1. **去重优化**: 处理728组重复变换
2. **规则平衡**: 增加低频规则样本
3. **置信度提升**: 优化低置信度样本（<50%）
4. **规则文档**: 补充各规则的详细说明

---

**报告生成工具**: `7_analyze_attack_dataset.py`
