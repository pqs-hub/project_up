# 束搜索攻击引擎 - 快速开始

## 5 分钟快速上手

### 前置条件

1. **安装依赖**
```bash
# 确保已安装项目依赖
pip install -r requirements.txt

# 确保安装了 iverilog（用于 testbench 验证）
sudo apt-get install iverilog  # Ubuntu/Debian
# 或
brew install icarus-verilog    # macOS
```

2. **启动目标模型服务**
```bash
# 使用 vLLM 启动 Judge 模型
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-7B-Instruct \
  --port 8001 \
  --served-model-name Qwen/Qwen2.5-Coder-7B-Instruct
```

### 快速演示

#### 方式 1: 使用演示脚本

```bash
# 运行单样本快速演示
python test/quick_demo_beam_search.py
```

这会：
- 创建一个简单的 4-bit 加法器样本
- 运行束搜索攻击（宽度=3, 深度=3）
- 显示攻击路径和统计信息
- 保存结果到 `test/output/demo_beam_search_result.json`

#### 方式 2: 处理真实数据集

```bash
# 处理小规模数据集
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json \
  --limit 10 \
  --beam-width 3 \
  --max-depth 3
```

### 预期输出

```
===================================================================
开始束搜索攻击数据收集...
===================================================================
2026-03-27 19:34:52 [INFO] 载入 10 个样本
2026-03-27 19:34:52 [INFO] 过滤后得到 8 个高置信度样本 (阈值 > 0.8)
2026-03-27 19:34:52 [INFO] >>> Starting Attack Search on [q000001] (Init Conf: 0.92)
2026-03-27 19:34:55 [INFO]   Depth 1: 8 candidates, keeping top 3
2026-03-27 19:34:58 [INFO]   Depth 2: 12 candidates, keeping top 3
2026-03-27 19:35:01 [INFO] 🔥 [SUCCESS] Task q000001 flipped at depth 2!
2026-03-27 19:35:01 [INFO] <<< Finished [q000001]: 1 successful traces
...
===================================================================
收集完成！成功攻击数: 5
成功率: 62.50%
结果保存至: data/beam_search_attacks.json
===================================================================
```

## 核心概念

### 1. 束搜索 (Beam Search)

在每个深度保留 Top-K 最有希望的分支：

```
深度 0:  [原始代码, confidence=0.95]
           ↓
深度 1:  [候选1: 0.80]  [候选2: 0.75]  [候选3: 0.70]
           ↓                ↓              ↓
深度 2:  [子节点1: 0.65]  [子节点2: 0.60]  [子节点3: 0.55]
           ↓
深度 3:  [翻转! verdict=no, confidence=0.35] ✓
```

### 2. 语义锚定

自动追踪信号修改并在后续步骤中定位：

```verilog
步骤 1 (T34): 
  原始: assign out = a & b;
  重命名: assign mul_result = a & b;
  ↓
步骤 2 (T20):
  自动锚定到 'mul_result' 信号
  添加误导注释: // product of a and b
```

### 3. 闭环验证

每一步都通过 testbench 验证功能等效：

```
变换代码 → TB仿真 → 通过? → 继续 ✓
                    ↓
                   失败 → 丢弃 ✗
```

## 参数调优指南

### 快速探索（适合原型开发）
```bash
--beam-width 2 --max-depth 2 --limit 50
# 预期: ~30% 成功率, 10-15 分钟
```

### 标准配置（推荐）
```bash
--beam-width 3 --max-depth 3 --limit 100
# 预期: ~50% 成功率, 30-40 分钟
```

### 深度挖掘（高质量数据）
```bash
--beam-width 5 --max-depth 4 --limit 200
# 预期: ~70% 成功率, 80-120 分钟
```

## 输出数据结构

```json
{
  "task_id": "q000001",
  "original_code": "module top_module...",
  "adversarial_code": "module top_module...",
  "thought": "攻击策略分析...",
  "original_confidence": 0.95,
  "final_confidence": 0.35,
  "attack_chain": [
    {
      "rule": "T34",
      "line": 5,
      "signal": "sum",
      "params": {},
      "victim_reasoning": "..."
    }
  ],
  "verdict_flip": true,
  "search_depth": 2
}
```

## 下一步

### 转换为 SFT 训练数据

```bash
python pipeline/2_build_sft_dataset.py \
  --input data/beam_search_attacks.json \
  --output data/sft_dataset.jsonl
```

### 训练攻击模型

```bash
llamafactory-cli train configs/llamafactory/sft_attack_lora.yaml
```

### 分析攻击模式

```bash
python scripts/analysis/analyze_attack_patterns.py \
  --input data/beam_search_attacks.json
```

## 常见问题速查

| 问题 | 解决方案 |
|------|---------|
| 没有成功翻转 | 增加 `--beam-width` 和 `--max-depth` |
| TB 验证失败 | 检查 iverilog 安装: `iverilog -V` |
| 模型超时 | 增加 `--timeout 300` |
| 内存不足 | 减少 `--beam-width` 或 `--limit` |
| API 连接失败 | 确认模型服务运行: `curl http://localhost:8001/v1/models` |

## 运行测试

```bash
# 运行单元测试
python test/test_beam_search_collector.py

# 运行快速演示
python test/quick_demo_beam_search.py

# 验证安装
python -c "from pipeline.adversarial_collector_v2 import AdversarialCollectorV2; print('✓ 安装成功')"
```

## 完整示例

```bash
#!/bin/bash
# complete_workflow.sh - 完整的束搜索攻击工作流

# 1. 启动模型服务（在后台）
echo "启动模型服务..."
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-7B-Instruct \
  --port 8001 &

# 等待服务启动
sleep 30

# 2. 运行束搜索攻击
echo "运行束搜索攻击..."
python scripts/sft/run_beam_search_attack.py \
  --dataset data/qualified_dataset.json \
  --output data/beam_search_attacks.json \
  --beam-width 3 \
  --max-depth 3 \
  --limit 100

# 3. 转换为 SFT 格式
echo "转换为 SFT 格式..."
python pipeline/2_build_sft_dataset.py \
  --input data/beam_search_attacks.json \
  --output data/sft_beam_search.jsonl

# 4. 查看统计信息
echo "统计信息:"
python -c "
import json
with open('data/beam_search_attacks.json') as f:
    data = json.load(f)
print(f'总攻击数: {len(data)}')
depths = [d['search_depth'] for d in data]
print(f'平均深度: {sum(depths)/len(depths):.2f}')
print(f'成功翻转: {sum(1 for d in data if d[\"verdict_flip\"])}')
"

echo "完成！"
```

## 更多资源

- 📖 [详细使用指南](./BEAM_SEARCH_ATTACK_GUIDE.md)
- 🔧 [集成说明](./BEAM_SEARCH_INTEGRATION.md)
- 📊 [性能基准](./BEAM_SEARCH_ATTACK_GUIDE.md#性能基准)
- 🐛 [问题排查](./BEAM_SEARCH_ATTACK_GUIDE.md#调试与日志)
