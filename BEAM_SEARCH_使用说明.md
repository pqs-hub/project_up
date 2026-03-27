# 束搜索攻击引擎 - 快速使用说明

## 🚀 3 步快速开始

### 1️⃣ 启动模型服务
```bash
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-7B-Instruct \
  --port 8001
```

### 2️⃣ 运行束搜索攻击
```bash
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json \
  --beam-width 3 \
  --max-depth 3
```

### 3️⃣ 查看结果
```bash
# 统计信息
python -c "
import json
with open('data/beam_search_attacks.json') as f:
    data = json.load(f)
print(f'成功攻击数: {len(data)}')
"
```

---

## 📖 核心概念

**束搜索攻击引擎** 通过在多个规则组合空间中搜索，找到能够使 Judge 模型判决翻转的最优攻击路径。

### 关键特性
- ✨ 启发式束搜索（可配置深度和宽度）
- 🎯 动态语义追踪（自动追踪信号修改）
- ✅ 闭环 TB 验证（确保功能等效性）
- 🧠 多步逻辑合成（生成推理链）

---

## 📁 核心文件

```
pipeline/adversarial_collector_v2.py  # 核心引擎
scripts/sft/run_beam_search_attack.py # 运行脚本
test/quick_demo_beam_search.py        # 快速演示
test/test_beam_search_collector.py    # 单元测试
```

---

## 🎯 常用命令

### 快速演示（单样本）
```bash
python test/quick_demo_beam_search.py
```

### 批量处理（小规模测试）
```bash
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/test_output.json \
  --limit 10
```

### 生产配置（高质量数据）
```bash
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json \
  --beam-width 5 \
  --max-depth 4 \
  --limit 500
```

### 完整工作流
```bash
bash scripts/sft/complete_beam_search_workflow.sh
```

---

## ⚙️ 参数说明

| 参数 | 说明 | 推荐值 |
|-----|------|--------|
| `--beam-width` | 束搜索宽度 | 3-5 |
| `--max-depth` | 最大搜索深度 | 3-4 |
| `--limit` | 处理样本数 | 100-500 |
| `--confidence-threshold` | 置信度阈值 | 0.8-0.9 |

---

## 📊 性能参考

| 配置 | 成功率 | 耗时 (100样本) |
|------|--------|---------------|
| 宽=2, 深=2 | ~35% | 15min |
| 宽=3, 深=3 | ~52% | 35min |
| 宽=5, 深=4 | ~68% | 80min |

---

## 🔧 运行测试

```bash
# 单元测试
python test/test_beam_search_collector.py

# 快速演示
python test/quick_demo_beam_search.py
```

---

## 📚 详细文档

- 📖 [快速开始](doc/BEAM_SEARCH_QUICKSTART.md)
- 📘 [详细指南](doc/BEAM_SEARCH_ATTACK_GUIDE.md)
- 🔧 [集成说明](doc/BEAM_SEARCH_INTEGRATION.md)
- ✅ [集成总结](doc/BEAM_SEARCH_集成完成总结.md)

---

## ❓ 常见问题

**Q: 没有成功翻转？**  
A: 增加 `--beam-width 5 --max-depth 4`

**Q: TB 验证失败？**  
A: 检查 iverilog: `iverilog -V`

**Q: 模型超时？**  
A: 增加 `--timeout 300`

---

## 💡 API 使用

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
results = collector.process_sample(sample)
```

---

**集成完成**: 2026-03-27  
**状态**: ✅ 生产就绪
