# 详尽攻击数据集生成 - 完整参数说明

## 必需参数

### 1. 输入输出参数

```bash
--eval-file <path>          # 评估数据文件路径（JSONL格式）
--output <path>             # 输出文件路径（JSONL格式）
```

**示例**：
```bash
--eval-file data/verilog_eval_cot_correct.json
--output data/attack_dataset.jsonl
```

### 2. 模型参数

```bash
--attack-base-url <url>     # LLM参数生成模型的base_url
--attack-model <name>       # LLM参数生成模型名称
```

**示例**：
```bash
--attack-base-url http://localhost:8002/v1
--attack-model "obfuscation_merged"
```

**说明**：
- 这些模型用于**生成攻击参数**（如LLM生成的注释、wire名等）
- 不是用于评判代码正确性的judge模型
- judge模型配置在`config.yaml`中

## 可选参数

### 3. 数据范围参数

```bash
--max-samples <int>         # 最多处理多少个任务（默认：全部）
--rules <str>               # 要测试的规则列表，逗号分隔（默认：所有15个规则）
```

**示例**：
```bash
--max-samples 100           # 只处理前100个任务
--rules T03,T07,T19         # 只测试这3个规则
```

### 4. 遍历策略参数 ⭐

```bash
--max-positions <int>       # 每个规则随机选择最多多少个候选位置（默认：10）
--random-seed <int>         # 随机种子，用于复现结果（默认：42）
```

**示例**：
```bash
--max-positions 5           # 每个规则最多遍历5个位置
--random-seed 42            # 固定随机种子
```

**说明**：
- `max-positions`越大，数据越详尽，但运行时间越长
- 设置`random-seed`可确保结果完全可复现
- 候选位置会先**随机打乱**再取前N个

### 5. 判断模式参数

```bash
--use-cot                   # 判断模型使用CoT（思维链）模式（默认：True）
```

**示例**：
```bash
--use-cot                   # 启用CoT模式（推荐）
```

**说明**：
- CoT模式让judge模型逐步推理，判断更准确
- 配置在`config.yaml`的`judge_model`部分

### 6. 并行参数

```bash
--workers <int>             # 并行worker数量（默认：8）
```

**示例**：
```bash
--workers 16                # 使用16个并行worker
```

**建议**：
- CPU核心数的1-2倍
- 考虑LLM服务器的并发限制

### 7. 调试参数

```bash
--verbose                   # 输出详细日志
```

## 完整命令示例

### 快速测试（10个任务）

```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/quick_test.jsonl \
  --max-samples 10 \
  --max-positions 3 \
  --random-seed 42 \
  --attack-base-url http://localhost:8002/v1 \
  --attack-model "obfuscation_merged" \
  --use-cot \
  --workers 4 \
  --verbose
```

### 中等规模（100个任务，每规则5个位置）

```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/medium_dataset.jsonl \
  --max-samples 100 \
  --max-positions 5 \
  --random-seed 42 \
  --attack-base-url http://localhost:8002/v1 \
  --attack-model "obfuscation_merged" \
  --use-cot \
  --workers 16
```

### 详尽模式（所有任务，每规则最多50个位置）

```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/exhaustive_dataset.jsonl \
  --max-positions 50 \
  --random-seed 42 \
  --attack-base-url http://localhost:8002/v1 \
  --attack-model "obfuscation_merged" \
  --use-cot \
  --workers 32 \
  --verbose
```

### 特定规则测试

```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/selected_rules.jsonl \
  --rules T03,T07,T19,T20,T34 \
  --max-positions 10 \
  --random-seed 42 \
  --attack-base-url http://localhost:8002/v1 \
  --attack-model "obfuscation_merged" \
  --use-cot \
  --workers 16
```

## 参数组合建议

### 开发/调试

```bash
--max-samples 10
--max-positions 3
--workers 4
--verbose
```

### 小规模实验

```bash
--max-samples 50
--max-positions 5
--random-seed 42
--workers 8
```

### 正式数据集生成

```bash
--max-positions 20
--random-seed 42
--workers 32
```

### 完全详尽（慎用，数据量大）

```bash
--max-positions 100
--random-seed 42
--workers 32
--verbose
```

## 配置文件位置

除了命令行参数，还需要配置：

### `config/config.yaml`

```yaml
judge_model:
  base_url: "http://localhost:8001/v1"     # judge模型URL
  model_name: "Qwen2.5-Coder-7B"           # judge模型名称
  temperature: 0.0

testbench:
  simulator: "iverilog"                     # 仿真器
  timeout: 30                               # 超时时间（秒）
```

## 数据量估算

假设配置：
- 100个任务
- 15个规则
- 每个规则平均5个候选位置

| max-positions | 实际尝试次数 | 预计成功样本* |
|--------------|-------------|--------------|
| 1 | 1,500 | 300-600 |
| 3 | 4,500 | 900-1,800 |
| 5 | 7,500 | 1,500-3,000 |
| 10 | 7,500† | 1,500-3,000 |
| 50 | 7,500† | 1,500-3,000 |

*假设20-40%的攻击成功率  
†候选数少于max-positions，实际使用min(候选数, max-positions)

## 注意事项

### 1. LLM服务器准备

确保攻击模型服务器已启动：
```bash
# 启动参数生成模型
python -m vllm.entrypoints.openai.api_server \
  --model path/to/obfuscation_merged \
  --port 8002
```

### 2. Judge模型配置

确保`config/config.yaml`中的judge模型配置正确：
```yaml
judge_model:
  base_url: "http://localhost:8001/v1"
  model_name: "Qwen2.5-Coder-7B"
```

### 3. 资源消耗

- **CPU**: workers × 1核
- **内存**: ~2GB per worker
- **时间**: 约0.5-2秒/样本（取决于LLM速度）

### 4. 并发控制

注意LLM服务器的并发限制：
```bash
# vLLM启动时可设置
--max-num-seqs 64  # 最大并发请求数
```

## 常见问题

### Q: 必需参数有哪些？

**A**: 5个必需参数
```bash
--eval-file
--output
--attack-base-url
--attack-model
# 以下虽有默认值，但建议显式指定：
--use-cot
```

### Q: random-seed有什么用？

**A**: 固定随机种子后，每次运行选择的候选位置完全相同，确保结果可复现。

### Q: max-positions设多大合适？

**A**: 
- 快速测试：3-5
- 平衡数据：10-20
- 详尽训练：50+

### Q: 如何只测试特定规则？

**A**: 使用`--rules`参数
```bash
--rules T03,T07,T19
```

### Q: 数据集会很大吗？

**A**: 
- 每个成功样本约2-5KB
- 1000个样本约2-5MB
- 建议先小规模测试

## 总结

**最小可运行命令**：
```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/eval.json \
  --output data/out.jsonl \
  --attack-base-url http://localhost:8002/v1 \
  --attack-model "model_name" \
  --use-cot
```

**推荐生产命令**：
```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/attack_dataset.jsonl \
  --max-positions 10 \
  --random-seed 42 \
  --attack-base-url http://localhost:8002/v1 \
  --attack-model "obfuscation_merged" \
  --use-cot \
  --workers 16
```
