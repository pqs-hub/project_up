# 束搜索攻击引擎（添加到主 README）

## 语义锚定束搜索攻击引擎

### 概述

**语义锚定束搜索攻击引擎** (Semantic-Anchored Beam Search Engine) 是一个工业级的多规则攻击数据收集框架，用于生成高质量的 SFT/RL 训练数据。

### 核心特性

- ✨ **启发式束搜索**: 深度/宽度可配置，以置信度下降为导航
- 🎯 **动态语义追踪**: 自动追踪信号修改，精准定位相关位置
- ✅ **闭环 TB 验证**: 每步变换必须通过功能等效验证
- 🧠 **多步逻辑合成**: 自动合成攻击策略推理链

### 快速开始

#### 1. 启动模型服务

```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-7B-Instruct \
  --port 8001
```

#### 2. 运行束搜索攻击

```bash
# 基础用法
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json

# 自定义配置
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json \
  --beam-width 5 \
  --max-depth 4 \
  --limit 100
```

#### 3. 快速演示

```bash
# 单样本演示
python test/quick_demo_beam_search.py

# 单元测试
python test/test_beam_search_collector.py
```

### 核心组件

```
pipeline/
└── adversarial_collector_v2.py  # 束搜索核心引擎

scripts/sft/
└── run_beam_search_attack.py    # 命令行工具

configs/
└── beam_search_config.json      # 配置模板

doc/
├── BEAM_SEARCH_QUICKSTART.md    # 快速开始
├── BEAM_SEARCH_ATTACK_GUIDE.md  # 详细指南
└── BEAM_SEARCH_INTEGRATION.md   # 集成说明

test/
├── test_beam_search_collector.py # 单元测试
└── quick_demo_beam_search.py     # 快速演示
```

### 工作原理

```
输入样本 (confidence=0.95)
    ↓
[束搜索: 宽度=3, 深度=3]
    ↓
深度 1: 探测 10 个动作 → 选择 Top-3
    ↓
深度 2: 每个分支探测动作 → 选择 Top-3
    ↓
深度 3: 继续搜索
    ↓
发现翻转 (confidence=0.35, verdict=no)
    ↓
合成训练数据 ✓
```

### 协同规则矩阵

| 规则 | 优先后续规则 | 策略 |
|------|-------------|------|
| T34 (重命名) | T20, T12, T31 | 命名 + 注释混淆 |
| T12 (反义) | T19, T31, T45 | 逻辑矛盾 + 死代码 |
| T32 (声明) | T47, T48, T07 | 结构打碎 |
| T20 (注释) | T19, T34, T12 | 语义夯实 |

### 输出数据格式

```json
{
  "task_id": "q000001",
  "original_code": "module...",
  "adversarial_code": "module...",
  "thought": "Multi-step attack analysis...",
  "original_confidence": 0.95,
  "final_confidence": 0.35,
  "attack_chain": [
    {"rule": "T34", "line": 5, "signal": "sum"},
    {"rule": "T20", "line": 5, "signal": "mul_result"}
  ],
  "verdict_flip": true,
  "search_depth": 2
}
```

### 性能基准

| 配置 | 成功率 | 平均深度 | 耗时 (100样本) |
|------|--------|---------|---------------|
| 宽度=2, 深度=2 | ~35% | 1.8 | 15min |
| 宽度=3, 深度=3 | ~52% | 2.3 | 35min |
| 宽度=5, 深度=4 | ~68% | 2.9 | 80min |

*基于 Qwen2.5-Coder-7B-Instruct, RTX 4090*

### 集成到训练流程

```bash
# 1. 生成束搜索攻击数据
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json

# 2. 转换为 SFT 格式
python pipeline/2_build_sft_dataset.py \
  --input data/beam_search_attacks.json \
  --output data/sft_beam_search.jsonl

# 3. 训练模型
llamafactory-cli train configs/llamafactory/sft_attack_lora.yaml
```

### 文档

- 📚 [快速开始指南](doc/BEAM_SEARCH_QUICKSTART.md)
- 📖 [详细使用手册](doc/BEAM_SEARCH_ATTACK_GUIDE.md)
- 🔧 [集成说明](doc/BEAM_SEARCH_INTEGRATION.md)

### API 使用示例

```python
from pipeline.adversarial_collector_v2 import AdversarialCollectorV2
from core.target_model import TargetModelClient

# 初始化
target_client = TargetModelClient(
    base_url="http://localhost:8001/v1",
    model="Qwen/Qwen2.5-Coder-7B-Instruct"
)

collector = AdversarialCollectorV2(
    target_model_client=target_client,
    beam_width=3,
    max_depth=3
)

# 处理样本
sample = {
    "task_id": "test_001",
    "prompt": "Design a 4-bit adder...",
    "canonical_solution": "module...",
    "test": "module testbench...",
    "judge_verdict": {"confidence": 0.95}
}

results = collector.process_sample(sample)

# 批量处理
all_results = collector.process_dataset(
    samples,
    save_path="data/output.json"
)
```

### 常见问题

**Q: 没有成功翻转怎么办？**

A: 增加搜索深度和宽度：
```bash
--beam-width 5 --max-depth 4
```

**Q: TB 验证失败？**

A: 确保安装 iverilog：
```bash
sudo apt-get install iverilog
iverilog -V
```

**Q: 如何调优性能？**

A: 参考 [性能优化指南](doc/BEAM_SEARCH_ATTACK_GUIDE.md#性能优化建议)
