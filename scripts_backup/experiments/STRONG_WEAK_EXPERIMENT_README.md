# 强强组合 vs 强弱组合实验

## 研究问题

**核心假设**：最强的两个规则组合是否一定效果最好？

**探索方向**：
1. 强规则 + 强规则（强强组合）
2. 强规则 + 弱规则（强弱组合）
3. 中等规则组合
4. 弱规则组合

**关键问题**：是否存在"互补效应"，使得强弱组合超过强强组合？

## 实验设计

### 规则分类

基于单规则ASR（来自`rule_eval/metrics_full_all_rules/`）：

- **强规则（Top 5）**：ASR最高的5个规则
  - 例如：T45 (ASR=0.975), T19 (ASR=0.903), T30 (ASR=0.607)
  
- **中等规则（6-15名）**：ASR中等的10个规则
  - 例如：T20, T31, T34等
  
- **弱规则（16名+）**：ASR较低的规则
  - 例如：T03, T07, T32等

### 组合策略

| 组合类型 | 说明 | 数量 |
|---------|------|------|
| strong_strong | 强规则×强规则 | 10对（C(5,2)） |
| strong_medium | 强规则×中等规则 | 15对 |
| strong_weak | 强规则×弱规则 | 10对 |
| medium_medium | 中等×中等 | 10对 |
| medium_weak | 中等×弱 | 10对 |
| weak_weak | 弱×弱 | 5对 |

### 测试样本

- 从`qualified_dataset.normalized.json`随机选择100个样本
- 每种组合类型分配约16个样本
- 每个样本测试3对规则组合

### 评估指标

1. **单规则ASR**：每个规则单独应用的攻击成功率
2. **组合ASR**：两个规则顺序应用的攻击成功率
3. **ASR提升**：`组合ASR - max(单规则ASR)`
4. **置信度提升**：`max(单规则置信度) - 组合置信度`
5. **协同效应**：ASR提升>20% 或 置信度提升>0.15

## 使用方法

### 运行实验

```bash
conda run -p /data3/pengqingsong/software/miniconda3/envs/hw_attack \
    python scripts/experiments/strong_weak_combination_experiment.py \
    --config config.yaml \
    --n-samples 100 \
    --output-dir results/strong_weak_experiment
```

### 参数说明

- `--config`：配置文件路径（默认：config.yaml）
- `--n-samples`：测试样本数（默认：100）
- `--output-dir`：输出目录（默认：results/strong_weak_experiment）
- `--seed`：随机种子（默认：42）

### 分析结果

```bash
python scripts/experiments/analyze_strong_weak.py \
    results/strong_weak_experiment/combination_results.jsonl \
    --output-dir results/strong_weak_experiment/analysis \
    --all
```

## 输出文件

### 实验结果

- `combination_results.jsonl`：详细结果（每行一个测试）
- `combination_report.json`：汇总报告

### 分析输出

- `comparison_table.md`：对比表格（Markdown格式）
- `comparison_plot.png`：ASR和协同率对比图
- `insights.json`：关键发现和建议

## 预期结果

### 场景1：强强组合最优（符合预期）

```
强强组合平均ASR: 85%
强弱组合平均ASR: 70%
结论：强规则的高ASR具有累加效应
```

### 场景2：强弱组合优于强强（互补效应）

```
强弱组合平均ASR: 80%
强强组合平均ASR: 75%
结论：弱规则在某些维度上补充了强规则的不足
```

### 场景3：中等组合表现突出

```
中等组合平均ASR: 78%
可能原因：中等规则覆盖面更广，组合后适用性更强
```

## 论文价值

### Methodology章节

```latex
\subsection{Rule Combination Strategy Analysis}

We investigate whether combining the two strongest individual 
rules always yields the best attack performance. We categorize 
rules into three tiers based on their single-rule ASR: strong 
(top 5), medium (6-15), and weak (16+). We then evaluate all 
possible combination strategies across 100 test samples.
```

### Results章节

```latex
Table~\ref{tab:strong_weak} shows that [strong-strong/strong-weak] 
combinations achieve the highest ASR of XX\%. Interestingly, we 
observe that [finding], suggesting that [explanation]. This has 
important implications for MCTS-based search strategies.
```

### 关键发现

1. **互补效应存在性**：如果强弱>强强，证明规则间存在互补
2. **搜索策略优化**：为MCTS提供组合策略指导
3. **非线性增益**：验证规则组合的协同效应

## 技术细节

### 规则应用顺序

```python
# 先应用rule1
transformed = engine.apply_transform(rtl, rule1, target_token=0)

# 再应用rule2
transformed = engine.apply_transform(transformed, rule2, target_token=0)
```

### 协同判断标准

```python
is_synergistic = (
    (combined_asr - max_single_asr > 0.2) or
    (max_single_conf - combined_conf > 0.15)
)
```

### 可用规则

引擎当前支持的规则：
```
['T03', 'T07', 'T09', 'T10', 'T12', 'T19', 'T20', 
 'T30', 'T31', 'T32', 'T34', 'T41', 'T45', 'T47', 'T48']
```

## 扩展实验

### 1. 三规则组合

测试强+强+强 vs 强+中+弱的效果

### 2. 顺序敏感性

测试 (R1→R2) vs (R2→R1) 的差异

### 3. 模块类型分析

不同类型模块（计数器、状态机、ALU）的最优组合策略

### 4. 大规模验证

在1000+样本上验证发现的规律

## 故障排查

### 问题1：规则ID不存在

```
错误: 未知的规则 ID: T04
解决: 检查引擎支持的规则列表，过滤掉不可用的规则
```

### 问题2：变换失败

```
现象: transformed == rtl
原因: 规则在该样本上找不到候选位置
处理: 返回ASR=0，不影响统计
```

### 问题3：模型查询超时

```
解决: 增加timeout参数，或减少并发数
```

## 参考文献

- 单规则评估数据：`rule_eval/metrics_full_all_rules/`
- 协同效应框架：`synergy_validator.py`
- 变换引擎：`ast_transforms.2.py`

---

**实验时间**：约1-2小时（100样本）  
**状态**：运行中  
**版本**：1.0
