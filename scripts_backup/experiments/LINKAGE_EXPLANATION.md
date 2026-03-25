# 规则联动 vs 非联动对比

## 问题：当前实验有联动吗？

**答案：❌ 没有真正的联动**

当前的`strong_weak_combination_experiment.py`只是**顺序应用**两个规则，并没有实现真正的联动。

## 对比分析

### ❌ 非联动（当前实现）

```python
# 评估单规则
rule1_result = apply_transform(original_rtl, rule1, target_token=0)
rule2_result = apply_transform(original_rtl, rule2, target_token=0)

# 评估组合
step1 = apply_transform(original_rtl, rule1, target_token=0)
step2 = apply_transform(step1, rule2, target_token=0)  # ❌ 固定target_token=0
```

**问题**：
1. rule2总是选择第一个候选位置（target_token=0）
2. rule2不知道rule1做了什么变换
3. rule2的参数不会根据rule1的输出调整

### ✅ 真正的联动（新实现）

```python
# 1. 信号亲和力联动
step1 = apply_transform(rtl, "T34", custom_map={"clk": "uart_clk"})
# rule1重命名：clk -> uart_clk

rename_map = engine.get_last_rename_map()  # {"clk": "uart_clk"}
new_signal = rename_map["clk"]  # "uart_clk"

step2 = apply_transform(step1, "T32", target_signal=new_signal)
# ✅ rule2在被重命名的信号上应用位宽变换

# 2. 结构联动
step1 = apply_transform(rtl, "T19")  # 插入死代码，创建新always块
# rule1创建了新的结构

step2 = apply_transform(step1, "T47", target_token=0)
# ✅ rule2在新创建的always块中应用Shannon展开

# 3. 参数联动
step1 = apply_transform(rtl, "T20", custom_text="UART Transmitter")
# rule1插入注释暗示UART

step2 = apply_transform(step1, "T34", 
                       custom_map={"clk": "uart_clk"},  # ✅ 根据注释调整
                       fallback_prefix="uart_")
```

## 联动类型

### 1. 信号亲和力联动 (Signal Affinity)

**定义**：对同一信号进行多次变换

**示例**：
```verilog
// 原始
input clk;
output reg [7:0] count;

// Step 1: T34重命名
input uart_clk;  // clk -> uart_clk
output reg [7:0] count;

// Step 2: T32位宽变换（联动：在uart_clk上应用）
input uart_clk;
output reg [10-3:2-2] count;  // 在同一信号上变换
```

**联动机制**：
- rule1记录重命名映射：`{"clk": "uart_clk"}`
- rule2使用`target_signal="uart_clk"`指定目标

### 2. 结构联动 (Structure Linkage)

**定义**：第二个规则在第一个规则创建的新结构上应用

**示例**：
```verilog
// 原始
always @(posedge clk) begin
    count <= count + 1;
end

// Step 1: T19插入死代码
always @(posedge clk) begin
    count <= count + 1;
end

always @(*) case (1'b0)  // ← 新创建的结构
    1'b1: ;
    default: ;
endcase

// Step 2: T47在新结构中应用Shannon展开（联动）
// 优先选择新创建的always块作为目标
```

**联动机制**：
- rule1创建新的always块
- rule2优先在新结构中应用（target_token=0通常指向新结构）

### 3. 参数联动 (Parameter Linkage)

**定义**：第二个规则的参数根据第一个规则的输出自适应调整

**示例**：
```verilog
// Step 1: T20插入注释
// UART Transmitter - 9600 baud  ← 注释暗示UART
module counter(
    input clk,
    ...
);

// Step 2: T34重命名（联动：根据注释内容）
// UART Transmitter - 9600 baud
module counter(
    input uart_clk,  // ← 根据注释暗示重命名为uart_clk
    input uart_rst,
    output reg [7:0] tx_data
);
```

**联动机制**：
- rule1的注释内容包含"UART"
- rule2自动使用`uart_`前缀重命名信号

## 实验对比

### 实验1：非联动（已完成）

```bash
python scripts/experiments/strong_weak_combination_experiment.py
```

**结果**：
- 强强组合ASR: 22.9%
- 强弱组合ASR: 2.1%
- **问题**：没有真正利用规则间的协同

### 实验2：联动（新实验）

```bash
python scripts/experiments/linked_combination_experiment.py \
    --n-samples 50 \
    --output-dir results/linked_experiment
```

**预期**：
- 联动组合ASR应该显著高于非联动
- 信号亲和力联动效果最明显
- 联动使用率应该>50%

## 联动的学术价值

### 1. 证明协同效应的来源

**非联动**：
```
ASR(A+B) ≈ max(ASR(A), ASR(B))  # 简单叠加
```

**联动**：
```
ASR(A→B) >> max(ASR(A), ASR(B))  # 非线性增益
```

### 2. 为MCTS提供搜索策略

**非联动策略**：
- 独立评估每个规则
- 贪心选择最强规则

**联动策略**：
- 考虑规则间的依赖关系
- 构建规则链：A→B→C
- 优化联动参数

### 3. 论文写作

**Methodology章节**：
```latex
\subsection{Linked Rule Combination}

Unlike naive sequential application where each rule independently 
selects its target location, our \textit{linked combination} 
strategy enables the second rule to adapt based on the first 
rule's transformation. For instance, in signal affinity linkage, 
after T34 renames \texttt{clk} to \texttt{uart\_clk}, T32 
specifically targets the renamed signal for bitwidth obfuscation, 
creating a cohesive semantic deception.
```

**Results章节**：
```latex
Table~\ref{tab:linkage} demonstrates that linked combinations 
achieve XX\% higher ASR compared to non-linked sequential 
application. The linkage mechanism was successfully utilized in 
YY\% of test cases, validating the feasibility of adaptive rule 
orchestration.
```

## 技术实现

### 关键API

```python
# 1. 获取重命名映射
rename_map = engine.get_last_rename_map()
# 返回: {"old_name": "new_name"}

# 2. 指定目标信号
engine.apply_transform(
    code=rtl,
    transform_id="T32",
    target_signal="uart_clk"  # ← 联动关键
)

# 3. 指定目标行
engine.apply_transform(
    code=rtl,
    transform_id="T47",
    target_line=15  # ← 在特定行应用
)
```

### 联动检测

```python
linkage_info = {
    "rule1_applied": True,
    "rule2_applied": True,
    "linkage_used": True,  # ← 是否使用了联动
    "details": {
        "rename_map": {"clk": "uart_clk"},
        "target_signal": "uart_clk",
        "linkage_type": "signal_affinity"
    }
}
```

## 运行新实验

### 1. 运行联动实验

```bash
conda run -p /data3/pengqingsong/software/miniconda3/envs/hw_attack \
    python scripts/experiments/linked_combination_experiment.py \
    --config config.yaml \
    --n-samples 50 \
    --output-dir results/linked_experiment
```

### 2. 对比分析

```bash
# 对比联动 vs 非联动
python scripts/experiments/compare_linkage.py \
    --linked results/linked_experiment/linked_results.jsonl \
    --non-linked results/strong_weak_experiment/combination_results.jsonl
```

## 预期发现

### 假设1：联动显著提升ASR

```
联动ASR: 45%
非联动ASR: 23%
提升: +22%
```

### 假设2：信号亲和力联动最有效

```
信号亲和力: +35% ASR
结构联动: +20% ASR
参数联动: +15% ASR
```

### 假设3：联动使用率与ASR正相关

```
联动使用率 > 80%: ASR = 50%
联动使用率 < 20%: ASR = 15%
```

## 总结

| 特性 | 非联动 | 联动 |
|------|--------|------|
| 规则应用 | 独立 | 协同 |
| target选择 | 固定（0） | 自适应 |
| 参数调整 | 静态 | 动态 |
| ASR | 较低 | 较高 |
| 复杂度 | 简单 | 中等 |
| 学术价值 | 基础 | 高 |

**建议**：运行联动实验，对比两种策略的效果差异，为论文提供更强的证据。
