# 🚀 训练命令速查

## ⚡ 快速开始（3步）

### Step 1: 激活环境
```bash
conda activate hw_attack
```

### Step 2: 进入目录
```bash
cd /data3/pengqingsong/finetune/LLaMA-Factory
```

### Step 3: 运行训练

#### 选项1: 快速测试（15分钟）⭐ 推荐首次使用
```bash
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_test.yaml
```

#### 选项2: LoRA训练（3-5小时）⭐ 推荐
```bash
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora.yaml
```

#### 选项3: 全参数训练（4-6小时）
```bash
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_balanced.yaml
```

---

## 📋 完整命令示例

### 快速测试（验证pipeline）
```bash
# 1. 激活环境并进入目录
conda activate hw_attack
cd /data3/pengqingsong/finetune/LLaMA-Factory

# 2. 运行快速测试（1000样本，1 epoch）
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_test.yaml

# 预计时间: 10-20分钟
# 显存需求: ~20GB
```

### LoRA训练（推荐）
```bash
# 1. 激活环境
conda activate hw_attack
cd /data3/pengqingsong/finetune/LLaMA-Factory

# 2. 运行LoRA训练（37,745样本，5 epochs）
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora.yaml

# 预计时间: 3-5小时（A800 80GB）
# 显存需求: ~25-30GB
```

### 全参数训练
```bash
# 1. 激活环境
conda activate hw_attack
cd /data3/pengqingsong/finetune/LLaMA-Factory

# 2. 运行全参数训练（37,745样本，3 epochs）
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_balanced.yaml

# 预计时间: 4-6小时（A800 80GB）
# 显存需求: ~40-45GB
```

---

## 🔧 后台运行（推荐）

### 使用 nohup
```bash
conda activate hw_attack
cd /data3/pengqingsong/finetune/LLaMA-Factory

# 后台运行，输出保存到日志
nohup llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora.yaml \
    > /data3/pengqingsong/LLM_attack/training.log 2>&1 &

# 查看进程
ps aux | grep llamafactory

# 实时查看日志
tail -f /data3/pengqingsong/LLM_attack/training.log
```

### 使用 screen
```bash
# 创建新会话
screen -S obfuscation_training

# 在screen中运行训练
conda activate hw_attack
cd /data3/pengqingsong/finetune/LLaMA-Factory
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora.yaml

# 退出screen（训练继续运行）：Ctrl+A, D

# 重新连接
screen -r obfuscation_training

# 查看所有screen会话
screen -ls
```

---

## 📊 监控训练

### 实时查看GPU使用
```bash
watch -n 1 nvidia-smi
```

### 查看训练日志
```bash
# 查看LLaMA-Factory的输出
tail -f /data3/pengqingsong/LLM_attack/saves/obfuscation_lora_v1/trainer_log.jsonl

# 或者查看训练loss
grep "loss" /data3/pengqingsong/LLM_attack/saves/obfuscation_lora_v1/trainer_log.jsonl
```

---

## 🎯 训练后导出（仅LoRA需要）

### 合并LoRA权重
```bash
conda activate hw_attack
cd /data3/pengqingsong/finetune/LLaMA-Factory

llamafactory-cli export \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora_export.yaml
```

**注意**: 需要先修改 `sft_obfuscation_lora_export.yaml` 中的路径：
- `adapter_name_or_path`: 指向你的LoRA checkpoint
- `export_dir`: 合并后模型的保存路径

---

## ⚠️ 常见问题

### Q1: llamafactory-cli: command not found
**解决**:
```bash
# 确保激活了正确的环境
conda activate hw_attack

# 验证安装
which llamafactory-cli
pip show llamafactory
```

### Q2: CUDA out of memory
**解决**:
```bash
# 使用更小的batch size配置
# 编辑配置文件，修改:
per_device_train_batch_size: 1
gradient_accumulation_steps: 16
```

### Q3: 依赖冲突警告
**说明**: 
- numpy、pydantic、transformers 版本冲突通常不影响训练
- 如果训练正常进行，可以忽略这些警告
- 如果遇到实际错误，再根据错误信息解决

### Q4: 指定GPU
```bash
# 使用特定GPU
CUDA_VISIBLE_DEVICES=0 llamafactory-cli train config.yaml

# 使用多GPU
CUDA_VISIBLE_DEVICES=0,1 llamafactory-cli train config.yaml
```

---

## 📝 配置文件位置

所有配置文件位于: `/data3/pengqingsong/LLM_attack/llamafactory_configs/`

```
├── sft_obfuscation_test.yaml       # 快速测试
├── sft_obfuscation_lora.yaml       # LoRA训练 ⭐
├── sft_obfuscation_balanced.yaml   # 全参数训练
└── sft_obfuscation_lora_export.yaml # LoRA导出
```

---

## 🚀 推荐工作流程

```bash
# 第1步: 激活环境
conda activate hw_attack

# 第2步: 快速测试（验证pipeline，15分钟）
cd /data3/pengqingsong/finetune/LLaMA-Factory
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_test.yaml

# 第3步: 如果测试通过，开始正式训练（后台运行）
nohup llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora.yaml \
    > ~/obfuscation_training.log 2>&1 &

# 第4步: 监控训练
tail -f ~/obfuscation_training.log
watch -n 1 nvidia-smi

# 第5步: 训练完成后，合并LoRA权重（如果使用LoRA）
llamafactory-cli export \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora_export.yaml
```

---

**现在可以开始训练了！建议先运行快速测试验证环境正常。** 🚀
