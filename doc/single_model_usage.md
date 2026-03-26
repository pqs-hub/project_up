# 使用单个模型（8001端口）生成数据集

## 配置说明

只需要一个模型服务器（8001端口），同时用于：
1. **判断代码正确性**
2. **生成攻击参数**

## 启动模型服务器

```bash
# 启动judge模型（8001端口）
python -m vllm.entrypoints.openai.api_server \
  --model Qwen/Qwen2.5-Coder-7B \
  --port 8001 \
  --gpu-memory-utilization 0.8 \
  --max-num-seqs 64
```

## 配置文件

`config/config.yaml`:
```yaml
judge_model:
  base_url: "http://localhost:8001/v1"
  model_name: "Qwen2.5-Coder-7B"
  temperature: 0.0
  timeout: 60

testbench:
  simulator: "iverilog"
  timeout: 30
```

## 运行命令

### 方式1：最简命令（自动复用judge模型）

```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/attack_dataset.jsonl \
  --max-positions 10 \
  --random-seed 42 \
  --use-cot \
  --workers 16 \
  --verbose
```

**说明**：
- 不指定`--param-gen-*`参数
- 自动使用8001端口的模型生成参数
- 日志会显示："复用judge模型作为参数生成模型"

### 方式2：显式指定（但仍是8001）

```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/attack_dataset.jsonl \
  --max-positions 10 \
  --random-seed 42 \
  --param-gen-base-url http://localhost:8001/v1 \  # 同一个端口
  --param-gen-model "Qwen2.5-Coder-7B" \            # 同一个模型
  --use-cot \
  --workers 16 \
  --verbose
```

### 方式3：使用旧参数名

```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/attack_dataset.jsonl \
  --max-positions 10 \
  --random-seed 42 \
  --attack-base-url http://localhost:8001/v1 \  # 旧的参数名
  --attack-model "Qwen2.5-Coder-7B" \            # 旧的参数名
  --use-cot \
  --workers 16 \
  --verbose
```

## 工作流程

```
┌─────────────────────────────────────────┐
│        单模型工作流程（8001端口）         │
└─────────────────────────────────────────┘

1. 读取任务
   └─ verilog_eval.json

2. 判断原始代码
   └─ judge_model(8001).judge(prompt, original_code)

3. 对每个攻击位置：
   
   ┌─────────────────────────────────────┐
   │ 3.1 生成参数（使用8001模型）         │
   └─────────────────────────────────────┘
   ├─ judge_model(8001).generate(prompt)
   └─ 得到：comment_text / wire_name
   
   ┌─────────────────────────────────────┐
   │ 3.2 执行攻击（代码规则）             │
   └─────────────────────────────────────┘
   ├─ engine.apply_transform(code, rule_id)
   └─ 得到：transformed_code
   
   ┌─────────────────────────────────────┐
   │ 3.3 判断攻击效果（使用8001模型）     │
   └─────────────────────────────────────┘
   └─ judge_model(8001).judge(prompt, transformed_code)

4. 保存成功样本
   └─ attack_dataset.jsonl
```

## 日志示例

```
INFO: 加载配置完成
INFO: 使用judge模型: http://localhost:8001/v1
INFO: 复用judge模型作为参数生成模型
INFO: 开始生成详尽攻击数据集...
INFO: 随机种子: 42
INFO: 总任务数: 1500
INFO: 生成攻击样本: 100%|████| 1500/1500 [00:45<00:00, 33.2job/s]
INFO: 完成！耗时: 45.2秒
INFO: 总尝试: 1500
INFO: 攻击成功: 423
INFO: 成功率: 28.2%
INFO: 结果保存到: data/attack_dataset.jsonl
```

## 参数生成示例

### T20 - 误导性注释

```
Judge模型（8001）生成参数：
输入: "生成一个与递减计数器功能相反的注释"
输出: "This increments the counter by 1"

实际代码: count <= count - 1;
攻击效果: 误导judge认为代码是递增的
```

### T12 - 中间信号抽取

```
Judge模型（8001）生成参数：
输入: "为三元表达式 condition ? a : b 生成合适的wire名"
输出: "mux_output"

实际代码: wire mux_output = condition ? a : b;
```

## 优势

### ✅ 简化部署
- 只需要启动一个模型服务
- 减少GPU内存占用
- 配置更简单

### ✅ 一致性
- 使用相同的模型风格生成参数和判断
- 避免不同模型间的差异

### ⚠️ 注意事项
- 单个模型需要处理更多请求
- 可能需要调整`--max-num-seqs`参数
- 生成参数的质量取决于模型能力

## 资源需求

### 最小配置
```bash
# 单个7B模型
--gpu-memory-utilization 0.8
--max-num-seqs 32
```

### 推荐配置
```bash
# 单个7B模型，高并发
--gpu-memory-utilization 0.8
--max-num-seqs 64
```

## 与双模型对比

| 方案 | 模型数量 | GPU需求 | 内存占用 | 部署复杂度 |
|------|---------|---------|---------|-----------|
| **单模型** | 1个 | 1×GPU | 较低 | 简单 |
| **双模型** | 2个 | 2×GPU | 较高 | 复杂 |

## 常见问题

### Q: 单模型会影响参数生成质量吗？

**A**: 可能会有一定影响。专门的参数生成模型可能更适合生成注释和命名，但使用judge模型也能获得不错的效果。

### Q: 如何提高单模型的并发能力？

**A**: 调整vLLM参数：
```bash
--max-num-seqs 64        # 增加并发数
--gpu-memory-utilization 0.9  # 充分利用GPU内存
```

### Q: 单模型和双模型的数据质量有差异吗？

**A**: 差异不大。judge模型本身就有很强的代码理解能力，生成参数的质量是可以接受的。

## 总结

使用单个模型（8001端口）生成数据集是一种**简化且有效**的方案：

1. ✅ 部署简单
2. ✅ 资源占用少  
3. ✅ 配置统一
4. ✅ 效果良好

**推荐命令**：
```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
  --eval-file data/verilog_eval_cot_correct.json \
  --output data/attack_dataset.jsonl \
  --max-positions 10 \
  --random-seed 42 \
  --use-cot \
  --workers 16
```
