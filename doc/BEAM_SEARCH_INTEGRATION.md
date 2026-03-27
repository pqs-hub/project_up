# 束搜索攻击引擎集成说明

## 概述

本文档说明如何将**语义锚定束搜索攻击引擎**集成到 VeriObf-RL 框架中。

## 集成内容

### 1. 核心模块

#### `pipeline/adversarial_collector_v2.py`
主引擎实现，包含：
- `AttackState`: 搜索树节点数据结构
- `AdversarialCollectorV2`: 束搜索核心算法

**核心功能**:
- 启发式束搜索（可配置宽度和深度）
- 动态语义追踪（信号重命名映射）
- 闭环 TB 验证（确保功能等效）
- 多步推理合成（生成训练数据）

**依赖**:
```python
from core.transforms import create_engine, analyze
from core.testbench import simulate_verilog
from core.target_model import TargetModelClient
from config.prompts import JUDGE_SYSTEM_PROMPT_COT
```

### 2. 运行脚本

#### `scripts/sft/run_beam_search_attack.py`
命令行工具，用于批量处理数据集

**基本用法**:
```bash
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json
```

**完整参数**:
- `--dataset`: 输入数据集
- `--output`: 输出路径
- `--beam-width`: 束宽度（默认 3）
- `--max-depth`: 最大深度（默认 3）
- `--confidence-threshold`: 置信度阈值（默认 0.8）
- `--base-url`: 模型 API URL
- `--model`: 模型名称
- `--workers`: 并行数（建议保持 1）

### 3. 测试与演示

#### `test/test_beam_search_collector.py`
单元测试脚本

**运行测试**:
```bash
python test/test_beam_search_collector.py
```

**测试覆盖**:
- AttackState 数据结构
- 协同规则链
- 默认参数获取
- 动作空间探测
- 数据合成

#### `test/quick_demo_beam_search.py`
快速演示脚本

**运行演示**:
```bash
python test/quick_demo_beam_search.py
```

### 4. 配置文件

#### `configs/beam_search_config.json`
配置模板，包含：
- 搜索参数配置
- 模型配置
- 数据配置
- 协同规则链
- 执行参数

### 5. 文档

#### `doc/BEAM_SEARCH_ATTACK_GUIDE.md`
详细使用指南，包含：
- 快速开始
- 参数说明
- 输出格式
- 性能优化
- 问题排查
- 高级用法

## 与现有框架的集成点

### 1. Transform 系统集成

束搜索引擎完全兼容现有的 Transform 系统：

```python
# 使用现有的 create_engine()
self.engine = create_engine()

# 使用标准的 apply_transform()
new_code = self.engine.apply_transform(
    code, rule_id, target_token=idx, **params
)

# 获取重命名映射
renames = self.engine.get_last_rename_map()
```

### 2. Testbench 验证集成

使用现有的 testbench 模拟器：

```python
from core.testbench import simulate_verilog

# 验证功能等效性
if simulate_verilog(new_code, tb):
    # 变换成功
    pass
```

### 3. Target Model 集成

使用现有的 TargetModelClient：

```python
from core.target_model import TargetModelClient

# 初始化客户端
target_client = TargetModelClient(
    base_url=args.base_url,
    api_key="EMPTY",
    model=args.model
)

# 调用判断
result = target_client.judge(spec, code, use_cot=True)
```

### 4. Prompts 系统集成

使用现有的 prompt 配置：

```python
from config.prompts import JUDGE_SYSTEM_PROMPT_COT

# 在对抗评估中使用
system_prompt = JUDGE_SYSTEM_PROMPT_COT
```

## 数据流程图

```
输入数据集 (qualified_dataset.json)
    ↓
[过滤高置信度样本]
    ↓
┌─────────────────────────────┐
│ AdversarialCollectorV2      │
│  ┌─────────────────────┐    │
│  │ 1. 探测动作空间      │    │
│  │   - 基于协同规则     │    │
│  │   - 语义锚定         │    │
│  └─────────────────────┘    │
│           ↓                  │
│  ┌─────────────────────┐    │
│  │ 2. 执行变换         │    │
│  │   - apply_transform │    │
│  │   - TB 验证         │    │
│  └─────────────────────┘    │
│           ↓                  │
│  ┌─────────────────────┐    │
│  │ 3. 对抗评估         │    │
│  │   - 调用 Judge      │    │
│  │   - 获取置信度      │    │
│  └─────────────────────┘    │
│           ↓                  │
│  ┌─────────────────────┐    │
│  │ 4. 束搜索剪枝       │    │
│  │   - 选择 Top-K      │    │
│  │   - 深度递增        │    │
│  └─────────────────────┘    │
│           ↓                  │
│  [判决翻转?]                │
│     Yes → 合成数据           │
│     No  → 继续搜索           │
└─────────────────────────────┘
    ↓
输出数据集 (gold_multi_rule_attacks.json)
```

## 使用工作流

### 工作流 1: 生成 SFT 训练数据

```bash
# 步骤 1: 准备高质量数据集
python pipeline/0_filter_correct_samples.py \
  --input data/verilog_eval_17k.json \
  --output data/qualified_dataset.json

# 步骤 2: 运行束搜索攻击
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json \
  --beam-width 3 \
  --max-depth 3 \
  --limit 500

# 步骤 3: 转换为 SFT 格式
python pipeline/2_build_sft_dataset.py \
  --input data/beam_search_attacks.json \
  --output data/sft_beam_search.jsonl

# 步骤 4: 训练模型
llamafactory-cli train configs/llamafactory/sft_attack_lora.yaml
```

### 工作流 2: 生成 GRPO 训练数据

束搜索生成的多步攻击路径特别适合 GRPO 训练：

```python
# 使用攻击链构建轨迹
for result in beam_search_results:
    trajectory = []
    for step in result['attack_chain']:
        state = {
            'code': step['code'],
            'confidence': step['confidence'],
            'rule': step['rule']
        }
        trajectory.append(state)
    
    # 计算轨迹奖励
    reward = calculate_reward(trajectory)
    grpo_data.append({
        'trajectory': trajectory,
        'reward': reward
    })
```

### 工作流 3: 对抗样本分析

```bash
# 生成对抗样本
python scripts/sft/run_beam_search_attack.py \
  --dataset data/test_set.json \
  --output data/adversarial_samples.json

# 分析攻击模式
python scripts/analysis/analyze_attack_patterns.py \
  --input data/adversarial_samples.json \
  --output results/attack_analysis.json
```

## 性能调优建议

### 搜索参数调优

| 场景 | beam_width | max_depth | 预期成功率 | 预期耗时 |
|------|-----------|-----------|-----------|---------|
| 快速原型 | 2 | 2 | ~30% | 快 |
| 平衡配置 | 3 | 3 | ~50% | 中等 |
| 高质量 | 5 | 4 | ~70% | 慢 |

### 样本过滤策略

```bash
# 严格过滤（高成功率）
--confidence-threshold 0.9

# 标准过滤（平衡）
--confidence-threshold 0.8

# 宽松过滤（更多样本）
--confidence-threshold 0.7
```

### 并行处理

**注意**: 由于模型 API 限制，建议保持 `--workers 1`

如需并行：
1. 确保模型服务器支持并发
2. 增加超时时间
3. 监控 GPU 显存

## 常见问题

### Q1: "No successful flips" 怎么办？

**可能原因**:
- 目标模型太强
- 搜索深度/宽度不够
- 样本置信度阈值太低

**解决方案**:
```bash
# 增加搜索空间
--beam-width 5 --max-depth 4

# 降低置信度阈值
--confidence-threshold 0.85
```

### Q2: TB 验证频繁失败？

**可能原因**:
- testbench 有误
- 规则参数不当
- iverilog 未安装

**解决方案**:
```bash
# 检查 iverilog
iverilog -V

# 单独测试 TB
python test/debug_testbench.py
```

### Q3: 模型请求超时？

**解决方案**:
```bash
# 增加超时时间
--timeout 300

# 或优化模型服务
# 使用更快的推理引擎（如 vLLM）
```

### Q4: 如何自定义协同规则？

编辑 `pipeline/adversarial_collector_v2.py`:

```python
self.synergy_chains = {
    "T34": ["T20", "T12", "T31"],
    # 添加自定义规则链
    "T09": ["T10", "T30"],
}
```

## 扩展建议

### 1. 集成强化学习

```python
# 使用 RL 学习最优搜索策略
class RLGuidedBeamSearch(AdversarialCollectorV2):
    def _probe_valid_actions(self, state):
        actions = super()._probe_valid_actions(state)
        # 使用 RL 策略网络排序
        scores = self.policy_net(state, actions)
        return sorted(actions, key=lambda a: scores[a], reverse=True)
```

### 2. 多目标优化

```python
# 同时优化多个目标
def _beam_search_multi_objective(self, state):
    # 目标 1: 置信度下降
    # 目标 2: 代码复杂度最小
    # 目标 3: 攻击步数最少
    pass
```

### 3. 知识蒸馏

使用强模型（如 GPT-4）生成更详细的 `thought`:

```python
def _synthesize_final_data(self, sample, final_state):
    # 调用强模型生成深度分析
    thought = self.teacher_model.analyze(
        sample, final_state.attack_chain
    )
    return {...}
```

## 参考资料

- [VeriObf-RL 主文档](../README.md)
- [Transform 规则文档](../docs/TRANSFORM_RULES.md)
- [束搜索使用指南](./BEAM_SEARCH_ATTACK_GUIDE.md)
- [SFT 训练指南](./SFT_TRAINING_GUIDE.md)
