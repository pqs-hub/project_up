# 使用示例

本文档提供详细的使用示例，帮助你快速上手规则组合协同效应验证实验。

## 场景1：快速验证（首次使用推荐）

### 目标
验证系统是否正常工作，快速查看协同效应。

### 步骤

```bash
# 1. 进入项目目录
cd /data3/pengqingsong/LLM_attack

# 2. 测试环境
python scripts/experiments/test_setup.py

# 3. 运行快速验证
bash scripts/experiments/quick_start.sh
# 选择选项 1（核心验证）

# 4. 查看结果
cat results/synergy_experiments/analysis/results_table.md
```

### 预期输出

```markdown
# 规则组合协同效应实验结果

## Signal_Affinity_T34_T32

| 模块 | ASR (单规则) | ASR (组合) | ASR提升 | 置信度提升 | 协同效应 |
|------|-------------|-----------|---------|-----------|---------|
| counter_8bit_simple | 0.0% | 50.0% | +50.0% | 0.8500 | ✓ |
| fsm_2state_simple | 5.0% | 45.0% | +40.0% | 0.7200 | ✓ |
| alu_4bit_simple | 10.0% | 55.0% | +45.0% | 0.8000 | ✓ |
| mux_4to1 | 0.0% | 60.0% | +60.0% | 0.9000 | ✓ |
| **平均** | **3.8%** | **52.5%** | **+48.8%** | - | **4/4** |
```

## 场景2：测试特定场景

### 目标
深入测试某个特定的协同模式。

### 示例：仅测试"掩体-弹头"组合

```bash
python scripts/experiments/run_synergy_experiment.py \
    --mode custom \
    --scenarios distractor_payload \
    --module-types alu \
    --config config.yaml \
    --output-dir results/distractor_test \
    --verbose
```

### 分析结果

```bash
python scripts/experiments/analyze_synergy_results.py \
    results/distractor_test/experiment_results.jsonl \
    --output-dir results/distractor_test/analysis \
    --all
```

## 场景3：对比多个场景

### 目标
对比不同协同模式的效果。

### 运行实验

```bash
python scripts/experiments/run_synergy_experiment.py \
    --mode custom \
    --scenarios signal_affinity,distractor_payload,semantic_hijacking \
    --module-types counter,alu \
    --output-dir results/comparison_test
```

### 生成对比报告

```bash
# 生成LaTeX表格（用于论文）
python scripts/experiments/analyze_synergy_results.py \
    results/comparison_test/experiment_results.jsonl \
    --latex \
    --output-dir results/comparison_test/analysis

# 查看LaTeX表格
cat results/comparison_test/analysis/results_table.tex
```

### 预期LaTeX输出

```latex
\begin{table}[htbp]
\centering
\caption{Synergistic Attack Effectiveness}
\label{tab:synergy}
\begin{tabular}{lccccc}
\hline
Scenario & Tests & ASR$_{single}$ & ASR$_{combined}$ & $\Delta$ASR & Synergy \\
\hline
Signal Affinity T34 T32 & 2 & 5.0\% & 52.5\% & +47.5\% & \checkmark \\
Distractor Payload T19 T47 & 2 & 12.5\% & 57.5\% & +45.0\% & \checkmark \\
Semantic Hijacking T20 T34 T31 & 2 & 7.5\% & 60.0\% & +52.5\% & \checkmark \\
\hline
\end{tabular}
\end{table}
```

## 场景4：完整实验（论文用）

### 目标
运行完整实验，生成所有论文所需材料。

### 步骤

```bash
# 1. 运行完整实验
python scripts/experiments/run_synergy_experiment.py \
    --mode full \
    --config config.yaml \
    --output-dir results/paper_experiment

# 2. 生成所有分析材料
python scripts/experiments/analyze_synergy_results.py \
    results/paper_experiment/experiment_results.jsonl \
    --output-dir results/paper_experiment/analysis \
    --all

# 3. 查看统计摘要
cat results/paper_experiment/analysis/statistical_summary.json
```

### 输出文件清单

```
results/paper_experiment/
├── experiment_results.jsonl          # 详细结果
├── experiment_report.json            # 汇总报告
└── analysis/
    ├── results_table.tex             # LaTeX表格
    ├── results_table.md              # Markdown表格
    ├── synergy_comparison.png        # ASR对比图
    ├── confidence_drop.png           # 置信度下降图
    └── statistical_summary.json      # 统计摘要
```

## 场景5：调试单个测试

### 目标
调试某个特定的规则组合。

### 手动测试

```python
# 创建测试脚本 test_single.py
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from scripts.experiments.synergy_validator import SynergyValidator
from scripts.experiments.attack_scenarios import SCENARIO_SIGNAL_AFFINITY
from scripts.experiments.test_modules import COUNTER_MODULES

# 创建验证器
validator = SynergyValidator('config.yaml')

# 测试单个场景+模块
result = validator._evaluate_scenario(
    SCENARIO_SIGNAL_AFFINITY,
    COUNTER_MODULES[0]
)

# 打印结果
print(f"协同效应: {result.synergy_metrics.get('is_synergistic')}")
print(f"ASR提升: {result.synergy_metrics.get('asr_boost'):.2%}")
print(f"置信度提升: {result.synergy_metrics.get('confidence_boost'):.4f}")
```

运行：

```bash
python test_single.py
```

## 场景6：批量实验（多配置对比）

### 目标
测试不同模型或配置下的协同效应。

### 脚本

```bash
#!/bin/bash
# batch_experiment.sh

MODELS=("deepseek-coder-33b" "qwen-coder-7b" "gpt-4o")

for model in "${MODELS[@]}"; do
    echo "Testing model: $model"
    
    # 修改配置
    sed -i "s/model: .*/model: \"$model\"/" config.yaml
    
    # 运行实验
    python scripts/experiments/run_synergy_experiment.py \
        --mode core \
        --output-dir results/model_comparison/$model
    
    # 分析结果
    python scripts/experiments/analyze_synergy_results.py \
        results/model_comparison/$model/experiment_results.jsonl \
        --output-dir results/model_comparison/$model/analysis \
        --all
done

echo "All experiments completed!"
```

## 场景7：增量实验（添加新场景）

### 目标
添加自定义场景并测试。

### 步骤

1. **定义新场景**

编辑 `scripts/experiments/attack_scenarios.py`：

```python
SCENARIO_CUSTOM_TRIPLE = AttackScenario(
    name="Custom_Triple_Attack",
    description="自定义三重攻击：注释+重命名+位宽",
    rule_chain=[
        {
            "rule_id": "T20",
            "params": {"custom_text": "UART Transmitter - 9600 baud"},
            "target_token": 0
        },
        {
            "rule_id": "T34",
            "params": {
                "custom_map": {"clk": "uart_clk", "data": "tx_data"},
                "fallback_prefix": "uart_"
            },
            "target_token": None
        },
        {
            "rule_id": "T32",
            "params": {"offset": 7, "use_multiply": False},
            "target_token": 0
        }
    ],
    target_module_type="counter",
    hypothesis="三层语义劫持：注释暗示UART，重命名强化，位宽混淆"
)

# 添加到列表
ALL_SCENARIOS.append(SCENARIO_CUSTOM_TRIPLE)
```

2. **运行测试**

```bash
python scripts/experiments/run_synergy_experiment.py \
    --mode custom \
    --scenarios custom_triple_attack \
    --module-types counter \
    --output-dir results/custom_test
```

## 场景8：结果可视化定制

### 目标
生成自定义的可视化图表。

### 脚本

```python
# custom_plot.py
import json
import matplotlib.pyplot as plt

# 加载结果
results = []
with open('results/synergy_experiments/experiment_results.jsonl', 'r') as f:
    for line in f:
        results.append(json.loads(line))

# 提取数据
scenarios = []
asr_boosts = []
conf_boosts = []

for r in results:
    if r['synergy_metrics'].get('is_synergistic'):
        scenarios.append(r['scenario_name'])
        asr_boosts.append(r['synergy_metrics']['asr_boost'])
        conf_boosts.append(r['synergy_metrics']['confidence_boost'])

# 绘制散点图
plt.figure(figsize=(10, 6))
plt.scatter(asr_boosts, conf_boosts, alpha=0.6, s=100)

for i, scenario in enumerate(scenarios):
    plt.annotate(scenario, (asr_boosts[i], conf_boosts[i]), 
                fontsize=8, alpha=0.7)

plt.xlabel('ASR Boost', fontsize=12)
plt.ylabel('Confidence Boost', fontsize=12)
plt.title('Synergistic Effects: ASR vs Confidence', fontsize=14)
plt.grid(alpha=0.3)
plt.savefig('custom_scatter.png', dpi=300, bbox_inches='tight')
print("图表已保存: custom_scatter.png")
```

## 场景9：持续监控

### 目标
定期运行实验，监控模型更新后的效果。

### Cron任务

```bash
# 添加到crontab
# 每天凌晨2点运行
0 2 * * * cd /data3/pengqingsong/LLM_attack && bash scripts/experiments/quick_start.sh --mode core --auto-yes >> logs/daily_synergy.log 2>&1
```

### 自动报告脚本

```bash
#!/bin/bash
# auto_report.sh

DATE=$(date +%Y%m%d)
OUTPUT_DIR="results/daily_reports/$DATE"

# 运行实验
python scripts/experiments/run_synergy_experiment.py \
    --mode core \
    --output-dir $OUTPUT_DIR

# 生成报告
python scripts/experiments/analyze_synergy_results.py \
    $OUTPUT_DIR/experiment_results.jsonl \
    --output-dir $OUTPUT_DIR/analysis \
    --all

# 发送邮件（可选）
# mail -s "Daily Synergy Report $DATE" your@email.com < $OUTPUT_DIR/analysis/statistical_summary.json
```

## 场景10：论文图表生成

### 目标
生成高质量的论文图表。

### 完整流程

```bash
# 1. 运行实验
python scripts/experiments/run_synergy_experiment.py --mode full

# 2. 生成基础图表
python scripts/experiments/analyze_synergy_results.py \
    results/synergy_experiments/experiment_results.jsonl \
    --plots \
    --output-dir results/paper_figures

# 3. 生成LaTeX表格
python scripts/experiments/analyze_synergy_results.py \
    results/synergy_experiments/experiment_results.jsonl \
    --latex \
    --output-dir results/paper_tables

# 4. 在论文中引用
# \includegraphics{results/paper_figures/synergy_comparison.png}
# \input{results/paper_tables/results_table.tex}
```

## 常见问题解答

### Q1: 如何加速实验？

```bash
# 方法1：增加并发数（修改config.yaml）
parallelism:
  num_workers: 16  # 根据GPU数量调整

# 方法2：使用核心模式
python scripts/experiments/run_synergy_experiment.py --mode core

# 方法3：仅测试部分场景
python scripts/experiments/run_synergy_experiment.py \
    --mode custom \
    --scenarios signal_affinity \
    --module-types counter
```

### Q2: 如何保存中间结果？

实验会自动保存中间结果到 `experiment_results.jsonl`，每完成一个测试就追加一行。

### Q3: 如何恢复中断的实验？

目前不支持自动恢复，但可以：
1. 查看已完成的测试：`wc -l results/synergy_experiments/experiment_results.jsonl`
2. 手动排除已完成的场景/模块
3. 重新运行剩余部分

### Q4: 如何自定义协同判断标准？

编辑 `synergy_validator.py` 中的阈值：

```python
# 在 _compute_synergy 方法中
is_synergistic = (asr_boost > 0.3) or (conf_boost > 0.2)  # 更严格的标准
```

## 最佳实践

1. **首次使用**：先运行 `test_setup.py` 确保环境正确
2. **快速验证**：使用 `--mode core` 快速查看效果
3. **完整实验**：论文用时使用 `--mode full`
4. **调试**：使用 `--verbose` 查看详细日志
5. **备份**：定期备份 `results/` 目录
6. **版本控制**：记录实验时的代码版本和配置

## 进阶技巧

### 并行运行多个实验

```bash
# 终端1：测试场景A
python scripts/experiments/run_synergy_experiment.py \
    --scenarios signal_affinity \
    --output-dir results/exp_a &

# 终端2：测试场景B
python scripts/experiments/run_synergy_experiment.py \
    --scenarios distractor_payload \
    --output-dir results/exp_b &
```

### 结果合并

```bash
# 合并多个实验结果
cat results/exp_a/experiment_results.jsonl \
    results/exp_b/experiment_results.jsonl \
    > results/merged_results.jsonl

# 分析合并结果
python scripts/experiments/analyze_synergy_results.py \
    results/merged_results.jsonl \
    --all
```

---

更多示例和技巧，请参考 README.md 和 IMPLEMENTATION_SUMMARY.md。
