# 🎯 模型评估命令速查

## ✅ 已完成的准备工作

1. ✅ LoRA权重已合并
   - 合并后模型: `/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged/`
   
2. ✅ 评估脚本已更新
   - 支持 pass@1、pass@3、pass@5、pass@10
   - 每个任务采样 5 次（足够计算 pass@1/3/5）

---

## 🚀 方式1: 一键评估（推荐）

```bash
cd /data3/pengqingsong/LLM_attack
./eval_finetuned_model.sh
```

**评估配置**:
- 样本数: 100
- 采样次数: 5
- 指标: pass@1、@3、@5、@10
- 预计时间: 20-40分钟

---

## 🔧 方式2: 手动步骤

### Step 1: 启动API服务

```bash
# 激活环境
conda activate hw_attack

# 启动vLLM API（端口8002）
cd /data3/pengqingsong/LLM_attack
nohup python -m vllm.entrypoints.openai.api_server \
    --model /data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged \
    --host 0.0.0.0 \
    --port 8002 \
    --tensor-parallel-size 1 \
    > ~/api_eval.log 2>&1 &

echo $! > /tmp/api_eval.pid
```

### Step 2: 等待服务启动（1-2分钟）

```bash
# 检查服务状态
tail -f ~/api_eval.log

# 测试API
curl http://localhost:8002/v1/models
```

### Step 3: 运行评估

```bash
cd /data3/pengqingsong/LLM_attack

python scripts/eval/eval_attack_success.py \
    --eval-file data/verilog_eval.json \
    --attack-base-url http://localhost:8002/v1 \
    --attack-model /data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged \
    --max-samples 100 \
    --n-per-task 5 \
    --temperature 0.7 \
    --output results/eval_finetuned_$(date +%Y%m%d_%H%M).json \
    --save-success-examples results/eval_success_$(date +%Y%m%d_%H%M).txt \
    --verbose
```

### Step 4: 评估完成后关闭API

```bash
kill $(cat /tmp/api_eval.pid)
```

---

## 📊 评估输出说明

### 主要指标
- **pass@1**: 第1次尝试成功的比例（最重要）
- **pass@3**: 前3次至少1次成功
- **pass@5**: 前5次至少1次成功
- **pass@10**: 前10次至少1次成功（需要 n-per-task=10）

### 诊断信息
```
=== 攻击成功率（在「原判正确」的样本上）===
  原判正确任务数: 95 / 100
  pass@1:  45/95 = 47.37%
  pass@3:  60/95 = 63.16%
  pass@5:  68/95 = 71.58%
  pass@10: N/A (需要10次采样)

=== 攻击失败原因分解 ===
  · 因「变换后代码未通过 testbench」而失败: 120 (25.3%)
  · 因「testbench 通过但验证模型仍判对」而失败: 180 (37.9%)
  · 其他（解析失败或变换无变化）: 100 (21.1%)
  · 攻击成功: 75 (15.8%)

=== 攻击成功规则分布 ===
  T20: 25 (33.3%)
  T34: 18 (24.0%)
  T19: 12 (16.0%)
  ...
```

### 输出文件
- `results/eval_finetuned_*.json` - 完整评估结果（JSON）
- `results/eval_success_*.txt` - 攻击成功样例（可读）
- `~/api_eval.log` - API服务日志

---

## 🎯 预期效果对比

| 指标 | 基线（未训练） | 训练后（期望） | 提升 |
|------|---------------|---------------|------|
| pass@1 | ~25-30% | **40-50%** | +15-20% |
| pass@3 | ~40-50% | **55-65%** | +15% |
| pass@5 | ~50-60% | **65-75%** | +15% |

---

## ⚠️ 常见问题

### Q1: API启动失败
```bash
# 检查端口占用
lsof -i:8002

# 杀掉占用进程
lsof -ti:8002 | xargs kill -9
```

### Q2: 显存不足
```bash
# 使用更小的模型长度
python -m vllm.entrypoints.openai.api_server \
    --model /data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged \
    --gpu-memory-utilization 0.8 \
    --max-model-len 2048 \
    --port 8002
```

### Q3: 评估速度慢
- 减少样本数: `--max-samples 50`
- 降低采样次数: `--n-per-task 3`（只计算 pass@1/3）

---

## 📈 查看结果

### 查看JSON结果
```bash
cat results/eval_finetuned_*.json | jq '.pass_at_1, .pass_at_3, .pass_at_5'
```

### 查看成功样例
```bash
less results/eval_success_*.txt
```

### 统计规则分布
```bash
cat results/eval_success_*.txt | grep "规则:" | sort | uniq -c | sort -rn
```

---

## ✅ 快速开始

```bash
# 一键评估（最简单）
cd /data3/pengqingsong/LLM_attack
./eval_finetuned_model.sh
```

评估大约需要 **20-40分钟**（100个样本 × 5次采样）
