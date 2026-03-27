# 语义锚定束搜索攻击引擎使用指南

## 概述

**语义锚定束搜索攻击引擎** (Semantic-Anchored Beam Search Engine) 是 VeriObf-RL 框架中用于高质量多规则攻击数据收集的工业级组件。

### 核心特性

1. **启发式束搜索** (Heuristic Beam Search)
   - 深度可配置（默认 3 层）
   - 宽度可配置（默认 3 分支）
   - 以置信度下降幅度 (ΔC) 为导航

2. **动态语义追踪** (Dynamic Semantic Tracking)
   - 自动追踪规则 A 修改的信号
   - 在规则 B 中精准定位相关位置
   - 维护信号重命名映射

3. **闭环 TB 验证** (Closed-loop Testbench)
   - 每步变换必须通过功能等效验证
   - 使用 iverilog 仿真确保正确性

4. **多步逻辑合成** (Multi-step Reasoning Synthesis)
   - 成功翻转后自动合成推理链
   - 生成高质量 SFT/RL 训练数据

## 架构设计

### 核心组件

```
pipeline/adversarial_collector_v2.py
├── AttackState          # 搜索树节点状态
├── AdversarialCollectorV2  # 主引擎
│   ├── process_sample()           # 处理单个样本
│   ├── _probe_valid_actions()     # 动作空间探测
│   ├── _execute_step()            # 变换执行 + TB验证
│   ├── _evaluate_adversarial_impact()  # 对抗评估
│   └── _synthesize_final_data()   # 数据合成
```

### 协同规则矩阵

引擎内置专家协同规则链，优化搜索效率：

| 前一步规则 | 优先尝试的后续规则 | 协同策略 |
|-----------|-------------------|---------|
| T34 (重命名) | T20, T12, T31 | 命名混淆 + 注释误导 |
| T12 (反义变量) | T19, T31, T45 | 逻辑矛盾 + 死代码 |
| T32 (声明混淆) | T47, T48, T07 | 结构打碎 |
| T20 (注释误导) | T19, T34, T12 | 语义夯实 |

## 快速开始

### 1. 准备数据集

数据集格式要求（JSON 列表）：

```json
[
  {
    "task_id": "q000001",
    "prompt": "Design a 4-bit adder...",
    "canonical_solution": "module top_module(...);\n...\nendmodule",
    "test": "module testbench;\n...\nendmodule",
    "judge_verdict": {
      "is_correct": true,
      "confidence": 0.95
    }
  }
]
```

### 2. 启动目标模型服务

```bash
# 使用 vLLM 部署目标 Judge 模型
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-7B-Instruct \
  --port 8001 \
  --served-model-name Qwen/Qwen2.5-Coder-7B-Instruct
```

### 3. 运行束搜索攻击

#### 基础用法

```bash
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json
```

#### 自定义参数

```bash
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json \
  --beam-width 5 \
  --max-depth 4 \
  --limit 100 \
  --confidence-threshold 0.85
```

#### 完整参数说明

| 参数 | 说明 | 默认值 |
|-----|------|--------|
| `--dataset` | 输入数据集路径 | **必需** |
| `--output` | 输出结果路径 | `data/gold_multi_rule_attacks.json` |
| `--limit` | 限制处理样本数 | None (全部) |
| `--confidence-threshold` | 置信度过滤阈值 | 0.8 |
| `--beam-width` | 束搜索宽度 | 3 |
| `--max-depth` | 最大搜索深度 | 3 |
| `--base-url` | 模型 API URL | `http://localhost:8001/v1` |
| `--model` | 模型名称 | `Qwen/Qwen2.5-Coder-7B-Instruct` |
| `--timeout` | 请求超时时间(秒) | 120 |
| `--workers` | 并行 worker 数 | 1 |

## 输出数据格式

成功攻击的输出数据格式：

```json
{
  "task_id": "q000001",
  "original_code": "module top_module...",
  "adversarial_code": "module top_module...",
  "thought": "Multi-step attack analysis:\n...",
  "original_confidence": 0.95,
  "final_confidence": 0.35,
  "attack_chain": [
    {
      "rule": "T34",
      "line": 5,
      "signal": "sum",
      "params": {},
      "victim_reasoning": "FINAL_ANSWER: yes\n..."
    },
    {
      "rule": "T20",
      "line": 5,
      "signal": "mul_result",
      "params": {},
      "victim_reasoning": "FINAL_ANSWER: no\n..."
    }
  ],
  "verdict_flip": true,
  "search_depth": 2
}
```

### 数据字段说明

- **task_id**: 任务标识符
- **original_code**: 原始正确代码
- **adversarial_code**: 攻击后的混淆代码
- **thought**: 攻击策略分析（用于 SFT 训练）
- **original_confidence**: 原始判决置信度
- **final_confidence**: 最终判决置信度
- **attack_chain**: 攻击步骤序列
- **verdict_flip**: 是否成功翻转判决
- **search_depth**: 搜索深度

## 性能优化建议

### 1. 搜索参数调优

**高效率（快速收集）**:
```bash
--beam-width 2 --max-depth 2
```

**高质量（深度攻击）**:
```bash
--beam-width 5 --max-depth 4
```

**平衡配置**:
```bash
--beam-width 3 --max-depth 3  # 默认推荐
```

### 2. 样本过滤策略

只处理高置信度样本能提高成功率：

```bash
# 严格过滤（置信度 > 0.9）
--confidence-threshold 0.9

# 宽松过滤（置信度 > 0.7）
--confidence-threshold 0.7
```

### 3. 并行处理

**注意**: 并行处理可能导致模型 API 竞争，建议保持 `--workers 1`

如需并行，确保：
- 模型服务器有足够容量
- 适当增加 `--timeout`
- 监控 GPU 内存使用

## 与现有框架集成

### 集成到 SFT 训练流程

```bash
# 1. 生成束搜索攻击数据
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json \
  --limit 500

# 2. 转换为 SFT 格式（使用现有工具）
python pipeline/2_build_sft_dataset.py \
  --input data/beam_search_attacks.json \
  --output data/sft_beam_search.jsonl

# 3. 训练模型
llamafactory-cli train configs/llamafactory/sft_attack_lora.yaml
```

### 作为 GRPO 数据源

束搜索生成的多步攻击路径特别适合 GRPO（Group Relative Policy Optimization）训练：

```python
# 使用 attack_chain 字段构建中间奖励
for step in attack_chain:
    reward = original_confidence - step['confidence']
    # 用于 GRPO 训练...
```

## 调试与日志

### 日志文件

```
logs/beam_search_attack.log  # 主日志文件
```

### 日志级别

修改 `pipeline/adversarial_collector_v2.py` 中的日志级别：

```python
logging.basicConfig(
    level=logging.DEBUG,  # 改为 DEBUG 获取详细信息
    ...
)
```

### 常见问题排查

**问题 1**: "TB verification failed"
- **原因**: 变换破坏了功能等效性
- **解决**: 检查 testbench 是否正确，或调整规则参数

**问题 2**: "No successful flips"
- **原因**: 目标模型太强或样本太简单
- **解决**: 
  - 增加 `--max-depth`
  - 增加 `--beam-width`
  - 降低 `--confidence-threshold`

**问题 3**: "Evaluation timeout"
- **原因**: 模型推理太慢
- **解决**: 增加 `--timeout` 或优化模型服务

## 高级用法

### 自定义协同规则

编辑 `pipeline/adversarial_collector_v2.py`:

```python
self.synergy_chains = {
    "T34": ["T20", "T12", "T31"],
    # 添加你的自定义链
    "T09": ["T10", "T30"],
}
```

### 集成自定义参数生成

修改 `_get_default_params` 方法：

```python
def _get_default_params(self, rule: str) -> Dict:
    if rule == "T20":
        return {"comment_style": "misleading"}
    return {}
```

### 使用更强的 Teacher 模型

修改 `_synthesize_final_data` 方法，调用 GPT-4 等强模型生成更详细的 `thought`。

## 性能基准

在典型配置下的性能参考：

| 配置 | 样本数 | 成功率 | 平均深度 | 耗时 |
|-----|--------|--------|---------|------|
| 宽度=2, 深度=2 | 100 | 35% | 1.8 | 15min |
| 宽度=3, 深度=3 | 100 | 52% | 2.3 | 35min |
| 宽度=5, 深度=4 | 100 | 68% | 2.9 | 80min |

*基于 Qwen2.5-Coder-7B-Instruct，单 GPU RTX 4090*

## 参考资料

- [VeriObf-RL 框架文档](../README.md)
- [Transform 规则说明](../docs/TRANSFORM_RULES.md)
- [SFT 训练指南](./SFT_TRAINING_GUIDE.md)
