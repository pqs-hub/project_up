# 🎯 模型评估完整指南

## 评估系统架构

评估需要**两个模型**同时运行：

```
攻击模型 (vLLM)          判断模型 (vLLM)
GPU 0,1                  GPU 2,3
端口 8002               端口 8001
↓                        ↓
生成混淆规则  ──→  应用规则  ──→  验证功能等价  ──→  判断是否正确
                                              ↓
                                        攻击成功？
```

---

## 🚀 方法1: 手动部署（推荐，更灵活）

### Step 1: 启动攻击模型（训练后的模型）

```bash
# 终端1: 攻击模型 (GPU 0,1，端口8002)
CUDA_VISIBLE_DEVICES=0,1 python -m vllm.entrypoints.openai.api_server \
    --model /data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged \
    --host 0.0.0.0 \
    --port 8002 \
    --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.9 \
    --max-model-len 4096
```

### Step 2: 启动判断模型（验证模型）

```bash
# 终端2: 判断模型 (GPU 2,3，端口8001)
CUDA_VISIBLE_DEVICES=2,3 python -m vllm.entrypoints.openai.api_server \
    --model /data3/pengqingsong/Model/Qwen2.5-Coder-7B \
    --host 0.0.0.0 \
    --port 8001 \
    --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.9 \
    --max-model-len 4096
```

### Step 3: 等待服务启动（1-2分钟）

```bash
# 测试攻击模型
curl http://localhost:8002/v1/models

# 测试判断模型  
curl http://localhost:8001/v1/models
```

### Step 4: 运行评估

```bash
# 终端3: 运行评估
python pipeline/5_evaluate_model.py \
    --eval-file data/verilog_eval.json \
    --attack-base-url http://localhost:8002/v1 \
    --attack-model obfuscation_lora_merged \
    --max-samples 100 \
    --n-per-task 5 \
    --temperature 0.7 \
    --output results/eval_$(date +%Y%m%d_%H%M).json \
    --save-success-examples results/success_$(date +%Y%m%d_%H%M).txt \
    --verbose
```

**参数说明**:
- `--eval-file`: 评估数据集
- `--attack-base-url`: 攻击模型API地址
- `--attack-model`: 攻击模型名称
- `--max-samples`: 评估样本数（100个约30-60分钟）
- `--n-per-task`: 每个任务采样次数（5次可计算pass@1/3/5）
- `--temperature`: 采样温度（0.7推荐）
- `--output`: 结果JSON文件
- `--save-success-examples`: 成功样例文本文件
- `--verbose`: 详细诊断信息

**判断模型配置**: 在 `config.yaml` 中：
```yaml
target_model:
  base_url: http://localhost:8001/v1  # 判断模型地址
  model: Qwen2.5-Coder-7B              # 判断模型名称
  use_cot: false                       # 是否使用CoT
```

---

## 🤖 方法2: 使用自动部署脚本（开发中）

创建一个自动部署脚本：

```bash
# 创建脚本
cat > auto_eval.sh << 'EOF'
#!/bin/bash
# 自动部署并评估

# 配置
ATTACK_MODEL="/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged"
JUDGE_MODEL="/data3/pengqingsong/Model/Qwen2.5-Coder-7B"
ATTACK_GPUS="0,1"
JUDGE_GPUS="2,3"
EVAL_DATA="data/verilog_eval.json"

# 启动攻击模型
echo "启动攻击模型..."
CUDA_VISIBLE_DEVICES=$ATTACK_GPUS nohup python -m vllm.entrypoints.openai.api_server \
    --model $ATTACK_MODEL \
    --port 8002 \
    --tensor-parallel-size 2 \
    > attack_model.log 2>&1 &
ATTACK_PID=$!

# 启动判断模型
echo "启动判断模型..."
CUDA_VISIBLE_DEVICES=$JUDGE_GPUS nohup python -m vllm.entrypoints.openai.api_server \
    --model $JUDGE_MODEL \
    --port 8001 \
    --tensor-parallel-size 2 \
    > judge_model.log 2>&1 &
JUDGE_PID=$!

# 等待服务启动
echo "等待服务启动..."
sleep 60

# 测试连接
curl http://localhost:8002/v1/models >/dev/null 2>&1 && echo "✓ 攻击模型就绪"
curl http://localhost:8001/v1/models >/dev/null 2>&1 && echo "✓ 判断模型就绪"

# 运行评估
echo "开始评估..."
python pipeline/5_evaluate_model.py \
    --eval-file $EVAL_DATA \
    --attack-base-url http://localhost:8002/v1 \
    --attack-model $ATTACK_MODEL \
    --max-samples 100 \
    --n-per-task 5 \
    --temperature 0.7 \
    --output results/eval_$(date +%Y%m%d_%H%M).json \
    --verbose

# 清理
echo "评估完成！是否停止vLLM服务？(y/n)"
read -r response
if [ "$response" = "y" ]; then
    kill $ATTACK_PID $JUDGE_PID
    echo "服务已停止"
fi
EOF

chmod +x auto_eval.sh
./auto_eval.sh
```

---

## 📊 config.yaml 配置

确保 `config.yaml` 正确配置判断模型：

```yaml
target_model:
  base_url: http://localhost:8001/v1    # 判断模型API地址
  api_key: EMPTY
  model: Qwen2.5-Coder-7B                # 判断模型名称
  timeout: 60
  max_retries: 3
  use_local_transformers: false
  max_new_tokens: 512
  
  # CoT配置（可选）
  use_cot: false                         # 是否使用思维链
  cot_prompt: "Let's think step by step..." # CoT提示词
```

---

## 🎯 评估指标

评估脚本会输出：

### 主要指标
```
=== 攻击成功率（在「原判正确」的样本上）===
  原判正确任务数: 95 / 100
  pass@1:  45/95 = 47.37%
  pass@3:  60/95 = 63.16%
  pass@5:  68/95 = 71.58%
```

### 诊断信息
```
=== 攻击失败原因分解 ===
  · 因「变换后代码未通过 testbench」而失败: 120 (25.3%)
  · 因「testbench 通过但验证模型仍判对」而失败: 180 (37.9%)
  · 其他（解析失败或变换无变化）: 100 (21.1%)
  · 攻击成功: 75 (15.8%)
```

### 成功规则分布
```
=== 攻击成功规则分布 ===
  T20: 25 (33.3%)   # 误导性注释
  T34: 18 (24.0%)   # 语义反转重命名
  T19: 12 (16.0%)   # 死代码注入
  ...
```

---

## 🔧 GPU使用建议

### 8张GPU推荐分配

| 任务 | GPU | 说明 |
|------|-----|------|
| 攻击模型 | 0,1 | 2张GPU，TP=2 |
| 判断模型 | 2,3 | 2张GPU，TP=2 |
| 备用 | 4,5,6,7 | 可用于其他任务 |

### 查看GPU状态
```bash
python main.py gpu
```

---

## ⚠️ 常见问题

### Q1: 端口被占用
```bash
# 查看占用
lsof -i:8001
lsof -i:8002

# 杀掉进程
lsof -ti:8001 | xargs kill -9
```

### Q2: 显存不足
```bash
# 减少GPU memory utilization
--gpu-memory-utilization 0.8

# 减少max-model-len
--max-model-len 2048

# 或使用单GPU
--tensor-parallel-size 1
```

### Q3: 服务启动慢
- 第一次加载模型需要1-2分钟
- 查看日志：`tail -f attack_model.log`

---

## 🎯 完整示例

```bash
# 1. 查看GPU状态
python main.py gpu

# 2. 启动攻击模型（终端1）
CUDA_VISIBLE_DEVICES=0,1 python -m vllm.entrypoints.openai.api_server \
    --model saves/obfuscation_lora_merged \
    --port 8002 --tensor-parallel-size 2

# 3. 启动判断模型（终端2）
CUDA_VISIBLE_DEVICES=2,3 python -m vllm.entrypoints.openai.api_server \
    --model /data3/pengqingsong/Model/Qwen2.5-Coder-7B \
    --port 8001 --tensor-parallel-size 2

# 4. 运行评估（终端3）
python pipeline/5_evaluate_model.py \
    --eval-file data/verilog_eval.json \
    --attack-base-url http://localhost:8002/v1 \
    --max-samples 100 \
    --n-per-task 5 \
    --output results/eval_results.json \
    --verbose
```

---

**评估时间**: 100个样本 × 5次采样 ≈ **30-60分钟**

查看实时进度：
```bash
tail -f results/eval_*.json
```
