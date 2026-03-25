# 规则组合协同效应验证实验

## 概述

本实验旨在验证多维度联动攻击的协同效应，证明规则组合的攻击力存在**非线性增益**。

### 核心假设

1. **信号亲和力联动** (Signal Affinity)：对同一信号进行语义重命名和结构变换，导致模型认知崩溃
2. **掩体-弹头组合** (Distractor-Payload)：使用死代码掩体吸引注意力，掩护深层逻辑变换
3. **语义一致性劫持** (Semantic Consistency Hijacking)：通过注释、重命名和结构变换构建完整的语义假象

### 学术价值

- **Non-linear Potency Addition**：证明 ASR(A+B) >> ASR(A) + ASR(B)
- **Cognitive Resource Saturation**：观察CoT推理长度与错误率的关系
- **Cross-layer Coherence Requirement**：证明成功的混淆必须具备"逻辑自洽的欺骗性"

## 实验设计

### 测试集

- **4类模块**：计数器、状态机、ALU、多路复用器
- **每类5个样本**，共20个测试用例
- **核心验证集**：每类1个，共4个（快速验证用）

### 攻击场景

1. **Signal_Affinity_T34_T32**：重命名 + 位宽变换
2. **Distractor_Payload_T19_T47**：死代码 + Shannon展开
3. **Semantic_Hijacking_T20_T34_T31**：注释 + 重命名 + 中间信号
4. **Enhanced_Affinity_T34_T32_T35**：三重打击（扩展验证）
5. **Logic_Confusion_T09_T12_T20**：逻辑变换 + 误导注释（扩展验证）
6. **Deep_Distractor_T19_T19_T47**：双层掩体（扩展验证）

### 对比组设计

- **Group S (Single)**：仅应用单个规则
- **Group C (Combined)**：应用联动组合

### 评估指标

- **ASR (Attack Success Rate)**：攻击成功率
- **Confidence Drop**：模型置信度下降
- **ASR Boost**：组合规则相比单规则的ASR提升
- **Synergy Ratio**：协同效应比率

## 快速开始

### 1. 环境准备

```bash
# 确保已安装依赖
pip install -r requirements.txt

# 启动目标模型（vLLM）
bash scripts/ops/run_vllm.sh

# 确保config.yaml中的模型配置正确
```

### 2. 运行核心验证实验（推荐首次运行）

```bash
cd /data3/pengqingsong/LLM_attack

# 核心场景（3个） × 核心模块（4个） = 12个测试
python scripts/experiments/run_synergy_experiment.py --mode core
```

预计耗时：约10-20分钟（取决于模型推理速度）

### 3. 运行完整实验

```bash
# 所有场景（6个） × 所有模块（20个） = 120个测试
python scripts/experiments/run_synergy_experiment.py --mode full
```

预计耗时：约1-2小时

### 4. 自定义实验

```bash
# 仅测试信号亲和力场景
python scripts/experiments/run_synergy_experiment.py \
    --mode custom \
    --scenarios signal_affinity \
    --module-types counter,alu

# 测试多个场景
python scripts/experiments/run_synergy_experiment.py \
    --mode custom \
    --scenarios signal_affinity,distractor_payload,semantic_hijacking \
    --module-types counter
```

### 5. 分析结果

```bash
# 生成所有分析输出（表格 + 图表 + 统计）
python scripts/experiments/analyze_synergy_results.py \
    results/synergy_experiments/experiment_results.jsonl \
    --all

# 仅生成LaTeX表格（用于论文）
python scripts/experiments/analyze_synergy_results.py \
    results/synergy_experiments/experiment_results.jsonl \
    --latex

# 仅生成图表
python scripts/experiments/analyze_synergy_results.py \
    results/synergy_experiments/experiment_results.jsonl \
    --plots
```

## 输出文件

### 实验结果

- `results/synergy_experiments/experiment_results.jsonl`：详细结果（每行一个测试）
- `results/synergy_experiments/experiment_report.json`：汇总报告

### 分析输出

- `results/synergy_experiments/analysis/results_table.tex`：LaTeX表格（论文用）
- `results/synergy_experiments/analysis/results_table.md`：Markdown表格（可读性）
- `results/synergy_experiments/analysis/synergy_comparison.png`：ASR对比图
- `results/synergy_experiments/analysis/confidence_drop.png`：置信度下降图
- `results/synergy_experiments/analysis/statistical_summary.json`：统计摘要

## 预期结果

### 成功标准

实验成功的标志：

1. **协同率 > 50%**：超过一半的测试显示协同效应
2. **平均ASR提升 > 20%**：组合规则显著优于单规则
3. **置信度提升 > 0.15**：模型置信度显著下降

### 典型输出示例

```
实验报告摘要
================================================================
总场景数: 3
总测试数: 12
协同案例数: 9
协同率: 75.00%

各场景表现:

  Signal_Affinity_T34_T32:
    平均 ASR 提升: 35.00%
    平均置信度提升: 0.7500
    协同率: 75.00%

  Distractor_Payload_T19_T47:
    平均 ASR 提升: 40.00%
    平均置信度提升: 0.6000
    协同率: 75.00%

  Semantic_Hijacking_T20_T34_T31:
    平均 ASR 提升: 50.00%
    平均置信度提升: 0.8000
    协同率: 75.00%
================================================================
```

## 论文写作建议

### Methodology 章节

```latex
\subsection{Cross-tier Synergistic Attack Orchestration}

We formulate a \textbf{Distractor-Payload} strategy to exploit the 
limited reasoning buffer of CoT-based verifiers. Our attack agent is 
trained to orchestrate multi-step trajectories where \textit{Lexical 
Layer} perturbations (the distractor) serve to exhaust the model's 
cognitive resources, while \textit{Logical Layer} transformations 
(the payload) execute the final functional subversion.

By enforcing \textit{Semantic Affinity}---where renaming (Tier III) 
and structural refactoring (Tier II) are applied to the same symbolic 
anchor---we create a cohesive but deceptive semantic context. This 
forces the neural verifier into a state of \textbf{Confirmation Bias}, 
where its reasoning trace is anchored to the misleading metadata, 
causing it to disregard the formal underlying hardware logic.
```

### Results 章节

使用生成的LaTeX表格和图表：

```latex
\subsection{Synergistic Effect Validation}

Table~\ref{tab:synergy} demonstrates the non-linear potency addition 
of combined attacks. Across all scenarios, the combined attack ASR 
significantly exceeds the sum of individual rule ASRs, with an average 
boost of XX\%. This validates our hypothesis that cross-layer semantic 
consistency hijacking creates emergent vulnerabilities that cannot be 
detected by analyzing individual transformations in isolation.

Figure~\ref{fig:synergy_comparison} illustrates the dramatic gap 
between single-rule and combined-rule effectiveness...
```

## 故障排查

### 常见问题

1. **模型判题失败**
   - 检查vLLM是否正常运行：`curl http://localhost:8001/v1/models`
   - 检查config.yaml中的模型名称是否与vLLM一致

2. **Testbench验证失败**
   - 确保iverilog已安装：`iverilog -v`
   - 检查testbench代码是否正确

3. **内存不足**
   - 减少并发数：修改config.yaml中的`num_workers`
   - 使用核心模式而非完整模式

4. **结果为空**
   - 检查原始RTL是否通过判题
   - 检查规则变换是否成功应用

## 扩展实验

### 添加新场景

编辑 `attack_scenarios.py`：

```python
SCENARIO_CUSTOM = AttackScenario(
    name="Custom_Scenario",
    description="你的场景描述",
    rule_chain=[
        {"rule_id": "Txx", "params": {...}, "target_token": 0},
        {"rule_id": "Tyy", "params": {...}, "target_token": 1},
    ],
    target_module_type="counter",  # 或 state_machine, alu, mux
    hypothesis="你的假设"
)
```

### 添加新测试模块

编辑 `test_modules.py`，在对应的列表中添加：

```python
{
    "id": "your_module_id",
    "type": "counter",  # 或其他类型
    "spec": "功能规范",
    "rtl": "Verilog代码",
    "testbench": "测试代码（可选）"
}
```

## 参考文献

- MCTS for Adversarial Search
- CoT Reasoning in LLMs
- Hardware Verification with LLMs

## 联系方式

如有问题，请查看主项目README或提交Issue。
