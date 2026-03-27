# 🚀 Verilog代码混淆攻击模型训练指南

## 📊 数据集准备

### 已完成
- ✅ 原始数据集: 12,267 样本
- ✅ 清洗后数据集: 7,598 样本 (推荐使用)
- ✅ 转换为LlamaFactory格式: `data/llamafactory_attack_strategy.json`

### 数据集特点
- **任务覆盖**: 4,544 个不同的Verilog设计任务
- **攻击规则**: 15种混淆规则，涵盖视觉、逻辑、结构等多种攻击手段
- **数据质量**: 
  - 平均置信度 0.9867
  - 100% testbench通过率
  - 消除了所有同一任务+同一规则的重复样本

---

## 🎯 训练方案

### 方案对比

| 方案 | 样本数 | Epoch | 方法 | 显存需求 | 训练时间 | 推荐场景 |
|------|--------|-------|------|----------|----------|----------|
| **Test** | 1,000 | 1 | LoRA | ~20GB | 15分钟 | 快速验证pipeline |
| **LoRA** | 7,598 | 5 | LoRA | ~25-30GB | 3-5小时 | 显存有限/快速迭代 |
| **Full** | 7,598 | 3 | 全参数 | ~40-45GB | 4-6小时 | 最佳效果 |

---

## 🚀 快速开始

### 前置要求

1. **安装LlamaFactory**
```bash
git clone https://github.com/hiyouga/LLaMA-Factory.git
cd LLaMA-Factory
pip install -e .
```

2. **环境变量** (可选)
```bash
export LLAMAFACTORY_PATH=/path/to/LLaMA-Factory
```

### 一键训练

```bash
cd /mnt/public/pqs/Veri_atack/project_up

# 方案1: 快速测试 (推荐第一次使用)
bash scripts/train_with_llamafactory.sh test

# 方案2: LoRA训练 (推荐)
bash scripts/train_with_llamafactory.sh lora

# 方案3: 全参数训练
bash scripts/train_with_llamafactory.sh full
```

脚本会自动完成:
- ✅ 检查并复制数据集
- ✅ 注册数据集到LlamaFactory
- ✅ 启动训练
- ✅ 保存模型

---

## 📝 手动训练步骤

如果不使用一键脚本，可以按以下步骤手动操作:

### Step 1: 转换数据集

```bash
python scripts/convert_to_llamafactory.py \
    data/sft_attack_strategy_cleaned.jsonl \
    data/llamafactory_attack_strategy.json
```

### Step 2: 注册数据集

```bash
python scripts/register_dataset_to_llamafactory.py
```

或手动编辑 `LLaMA-Factory/data/dataset_info.json`:

```json
{
  "verilog_attack_strategy": {
    "file_name": "verilog_attack_strategy.json",
    "formatting": "sharegpt",
    "columns": {
      "messages": "messages"
    },
    "tags": {
      "role_tag": "role",
      "content_tag": "content",
      "user_tag": "user",
      "assistant_tag": "assistant",
      "system_tag": "system"
    }
  }
}
```

### Step 3: 开始训练

```bash
cd /path/to/LLaMA-Factory

# 快速测试
llamafactory-cli train /mnt/public/pqs/Veri_atack/project_up/configs/llamafactory/sft_attack_test.yaml

# LoRA训练
llamafactory-cli train /mnt/public/pqs/Veri_atack/project_up/configs/llamafactory/sft_attack_lora.yaml

# 全参数训练
llamafactory-cli train /mnt/public/pqs/Veri_atack/project_up/configs/llamafactory/sft_attack_full.yaml
```

### Step 4: 合并LoRA权重 (仅LoRA训练)

```bash
llamafactory-cli export \
    /mnt/public/pqs/Veri_atack/project_up/configs/llamafactory/sft_attack_lora_export.yaml
```

---

## 📁 输出文件

### LoRA训练
```
saves/attack_lora_v1/
├── adapter_config.json      # LoRA配置
├── adapter_model.bin         # LoRA权重
├── training_args.bin         # 训练参数
├── trainer_state.json        # 训练状态
└── training_loss.png         # Loss曲线
```

### 合并后
```
saves/attack_lora_merged/
├── config.json
├── generation_config.json
├── model-00001-of-00002.safetensors
├── model-00002-of-00002.safetensors
├── model.safetensors.index.json
├── tokenizer.json
└── tokenizer_config.json
```

---

## 🎛️ 配置调优

### 显存不足 (OOM)

修改配置文件:
```yaml
per_device_train_batch_size: 1  # 减小batch size
gradient_accumulation_steps: 16  # 增加梯度累积
cutoff_len: 2048  # 减小最大长度
```

### 训练速度慢

```yaml
per_device_train_batch_size: 4  # 增大batch size
gradient_accumulation_steps: 4
use_flash_attn: true  # 使用flash attention (如果支持)
```

### 多GPU训练

```bash
CUDA_VISIBLE_DEVICES=0,1,2,3 llamafactory-cli train config.yaml
```

---

## 📊 监控训练

### 查看Loss曲线

训练完成后查看 `saves/*/training_loss.png`

### 实时监控

```bash
# 查看日志
tail -f saves/attack_lora_v1/trainer_log.jsonl

# 使用TensorBoard
tensorboard --logdir saves/
```

---

## ✅ 训练完成检查

- [ ] Loss稳定下降
- [ ] 没有OOM错误
- [ ] 模型文件已保存
- [ ] LoRA权重已合并 (如果使用LoRA)
- [ ] 可以正常加载模型

---

## 🧪 测试模型

### 启动vLLM服务

```bash
# LoRA合并后的模型
CUDA_VISIBLE_DEVICES=0,1 python -m vllm.entrypoints.openai.api_server \
    --model /mnt/public/pqs/Veri_atack/project_up/saves/attack_lora_merged \
    --host 0.0.0.0 \
    --port 8002 \
    --tensor-parallel-size 2 \
    --max-model-len 4096

# 或全参数训练的模型
CUDA_VISIBLE_DEVICES=0,1 python -m vllm.entrypoints.openai.api_server \
    --model /mnt/public/pqs/Veri_atack/project_up/saves/attack_full_v1 \
    --host 0.0.0.0 \
    --port 8002 \
    --tensor-parallel-size 2 \
    --max-model-len 4096
```

### 测试推理

```bash
curl http://localhost:8002/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{
    "model": "attack_model",
    "messages": [
      {"role": "system", "content": "你是一个Verilog代码混淆专家。"},
      {"role": "user", "content": "请选择一个攻击规则混淆以下代码: module test(input a, output b); assign b = a; endmodule"}
    ]
  }'
```

---

## 📈 预期效果

### 基线 (未训练)
- 随机选择规则
- ASR: ~45-50%

### LoRA训练后
- 能选择所有15种规则
- 参数生成合理
- ASR: ~55-60%

### 全参数训练后
- 优先选择高ASR规则 (T20, T45等)
- 参数生成更优化
- ASR: ~60-70%

---

## ⚠️ 常见问题

### Q1: 数据集加载失败

检查dataset_info.json是否正确注册:
```bash
python -c "from llamafactory.data import get_dataset_list; print(get_dataset_list())"
```

### Q2: 显存不足

使用test配置验证，然后调整batch size和gradient accumulation

### Q3: Loss不下降

检查学习率、数据集是否正确、增加warmup_steps

---

## 📚 参考资料

- [LlamaFactory文档](https://github.com/hiyouga/LLaMA-Factory)
- [Qwen2.5-Coder文档](https://qwenlm.github.io/blog/qwen2.5-coder/)
- [LoRA论文](https://arxiv.org/abs/2106.09685)
