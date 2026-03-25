# 🚀 LLaMA-Factory 训练指南 - Verilog代码混淆

## ✅ 已完成的工作

### 1. 数据集转换完成
- ✅ `obfuscation_balanced.json` - 37,745样本（推荐）
- ✅ `obfuscation_dedup.json` - 16,126样本（快速测试）
- ✅ `obfuscation_full.json` - 44,246样本（完整版）

数据集位置: `/data3/pengqingsong/finetune/LLaMA-Factory/data/`

### 2. 训练配置创建完成
- ✅ `sft_obfuscation_balanced.yaml` - 全参数微调（推荐）
- ✅ `sft_obfuscation_lora.yaml` - LoRA微调（显存友好）
- ✅ `sft_obfuscation_test.yaml` - 快速测试

配置文件位置: `/data3/pengqingsong/LLM_attack/llamafactory_configs/`

---

## 📋 训练前准备

### Step 1: 注册数据集

**方法1: 修改 dataset_info.json（推荐）**

编辑 `/data3/pengqingsong/finetune/LLaMA-Factory/data/dataset_info.json`，添加：

```json
{
  "obfuscation_balanced": {
    "file_name": "obfuscation_balanced.json",
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
  },
  "obfuscation_dedup": {
    "file_name": "obfuscation_dedup.json",
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
  },
  "obfuscation_full": {
    "file_name": "obfuscation_full.json",
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

**方法2: 使用脚本自动添加**

```bash
cd /data3/pengqingsong/LLM_attack
python -c "
import json

# 读取现有配置
with open('/data3/pengqingsong/finetune/LLaMA-Factory/data/dataset_info.json', 'r') as f:
    dataset_info = json.load(f)

# 读取新数据集配置
with open('/data3/pengqingsong/finetune/LLaMA-Factory/data/obfuscation_datasets.json', 'r') as f:
    new_datasets = json.load(f)

# 合并
dataset_info.update(new_datasets)

# 保存
with open('/data3/pengqingsong/finetune/LLaMA-Factory/data/dataset_info.json', 'w') as f:
    json.dump(dataset_info, f, indent=2, ensure_ascii=False)

print('✓ 数据集注册完成！')
"
```

### Step 2: 验证数据集

```bash
cd /data3/pengqingsong/finetune/LLaMA-Factory

# 查看数据集列表
python -c "
from llamafactory.data import get_dataset_list
datasets = get_dataset_list()
print('可用数据集:', [d for d in datasets if 'obfuscation' in d])
"
```

---

## 🚀 开始训练

### 方案1: 快速测试（推荐第一次使用）

```bash
cd /data3/pengqingsong/finetune/LLaMA-Factory

# 使用测试配置（1000样本，1个epoch，约15分钟）
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_test.yaml
```

**预期结果**:
- 训练时间: 10-20分钟（A100）
- 显存占用: ~20GB
- 用途: 验证pipeline正常

### 方案2: LoRA微调（推荐显存<40GB）

```bash
cd /data3/pengqingsong/finetune/LLaMA-Factory

# 使用LoRA配置（37,745样本，5个epoch）
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora.yaml
```

**预期结果**:
- 训练时间: 3-5小时（A100）
- 显存占用: ~25-30GB
- 优势: 显存友好，训练快速

**训练后合并LoRA权重**:
```bash
llamafactory-cli export \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora_export.yaml
```

### 方案3: 全参数微调（推荐显存≥40GB，最佳效果）

```bash
cd /data3/pengqingsong/finetune/LLaMA-Factory

# 使用全参数配置（37,745样本，3个epoch）
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_balanced.yaml
```

**预期结果**:
- 训练时间: 4-6小时（A100）
- 显存占用: ~40-45GB
- 优势: 效果最佳

---

## 🎯 训练配置对比

| 配置 | 数据集 | 样本数 | Epoch | 方法 | 显存 | 时间 | 推荐场景 |
|------|--------|--------|-------|------|------|------|---------|
| test | dedup | 1,000 | 1 | LoRA | ~20GB | 15分钟 | 快速测试 |
| lora | balanced | 37,745 | 5 | LoRA | ~30GB | 3-5小时 | 显存有限 |
| balanced | balanced | 37,745 | 3 | Full | ~45GB | 4-6小时 | 最佳效果 |

---

## 📊 监控训练

### 查看训练日志

```bash
# 实时查看日志
tail -f /data3/pengqingsong/LLM_attack/saves/obfuscation_*/train.log

# 或者查看LLaMA-Factory的输出
```

### 使用TensorBoard

```bash
cd /data3/pengqingsong/finetune/LLaMA-Factory

# 启动TensorBoard
tensorboard --logdir /data3/pengqingsong/LLM_attack/saves/
```

### 查看Loss曲线

训练结束后会自动生成 `training_loss.png`

---

## 🔧 自定义配置

### 调整显存使用

**如果显存不足（OOM）**:
```yaml
# 修改配置文件
per_device_train_batch_size: 1  # 减小batch size
gradient_accumulation_steps: 16  # 增加梯度累积
cutoff_len: 1024  # 减小最大长度
```

**如果显存充足**:
```yaml
per_device_train_batch_size: 8  # 增大batch size
gradient_accumulation_steps: 2
```

### 调整学习率

```yaml
# 全参数微调
learning_rate: 2.0e-5  # 较小的学习率

# LoRA微调
learning_rate: 5.0e-4  # 较大的学习率（通常是全参数的10-20倍）
```

### 使用DeepSpeed（多GPU）

```yaml
# 添加到配置文件
deepspeed: examples/deepspeed/ds_z3_config.json
```

```bash
# 使用多GPU训练
CUDA_VISIBLE_DEVICES=0,1,2,3 llamafactory-cli train config.yaml
```

---

## 📦 训练后导出

### LoRA模型合并

创建导出配置 `sft_obfuscation_lora_export.yaml`:

```yaml
model_name_or_path: Qwen/Qwen2.5-Coder-7B-Instruct
adapter_name_or_path: /data3/pengqingsong/LLM_attack/saves/obfuscation_lora_v1
template: qwen
finetuning_type: lora
export_dir: /data3/pengqingsong/LLM_attack/saves/obfuscation_merged
export_size: 2
export_device: auto
export_legacy_format: false
```

运行导出:
```bash
llamafactory-cli export \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora_export.yaml
```

### 测试模型

```bash
# 使用LLaMA-Factory的Chat界面
llamafactory-cli chat \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_chat.yaml
```

或使用Python:
```python
from transformers import AutoTokenizer, AutoModelForCausalLM

model_path = "/data3/pengqingsong/LLM_attack/saves/obfuscation_balanced_v1"
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForCausalLM.from_pretrained(model_path)

# 测试推理...
```

---

## 🎓 训练建议

### 推荐工作流程

```bash
# 第1步: 快速测试（15分钟）
llamafactory-cli train llamafactory_configs/sft_obfuscation_test.yaml

# 第2步: LoRA训练（3-5小时）
llamafactory-cli train llamafactory_configs/sft_obfuscation_lora.yaml

# 第3步: 评估效果
python evaluate_model.py --model saves/obfuscation_lora_v1

# 第4步（可选）: 全参数微调（4-6小时）
llamafactory-cli train llamafactory_configs/sft_obfuscation_balanced.yaml
```

### 超参数调优建议

| 参数 | 默认值 | 调优建议 |
|------|--------|---------|
| learning_rate | 2e-5 (Full) / 5e-4 (LoRA) | 如果loss不下降，尝试降低10倍 |
| num_train_epochs | 3-5 | 观察loss曲线，过拟合则减少 |
| lora_rank | 8 | 可尝试16/32提升效果 |
| cutoff_len | 2048 | 代码较长，建议保持2048 |
| warmup_steps | 100-200 | 数据集大可增加至500 |

---

## ⚠️ 常见问题

### Q1: CUDA out of memory

**解决**:
```yaml
# 使用LoRA + 小batch size
finetuning_type: lora
per_device_train_batch_size: 1
gradient_accumulation_steps: 16
gradient_checkpointing: true
```

### Q2: 数据集加载失败

**检查**:
```bash
# 验证数据集是否注册
python -c "from llamafactory.data import get_dataset_list; print(get_dataset_list())"

# 验证JSON格式
python -c "import json; json.load(open('/data3/pengqingsong/finetune/LLaMA-Factory/data/obfuscation_balanced.json'))"
```

### Q3: 训练速度慢

**优化**:
```yaml
# 使用bf16（A100/H100）
bf16: true
fp16: false

# 增大batch size
per_device_train_batch_size: 4

# 使用flash attention（如果支持）
use_flash_attn: true
```

### Q4: Loss不下降

**检查**:
1. 学习率是否过大/过小
2. 是否有梯度爆炸（检查grad_norm）
3. 数据是否正确加载
4. 增加warmup_steps

---

## 📈 预期效果

### 基线（未训练）
- ASR: ~48%
- 规则选择: 随机

### LoRA训练后（5 epochs）
- ASR: 55-60%
- 规则选择: 能选择所有15个规则
- 训练时间: 3-5小时

### 全参数训练后（3 epochs）
- ASR: 60-70%
- 规则选择: 优先高ASR规则
- 训练时间: 4-6小时

---

## ✅ 检查清单

训练前:
- [ ] 数据集已转换并复制到LLaMA-Factory/data/
- [ ] dataset_info.json已更新
- [ ] 选择合适的配置文件
- [ ] 确认GPU显存充足

训练中:
- [ ] Loss在稳定下降
- [ ] 没有OOM错误
- [ ] 定期查看日志

训练后:
- [ ] 模型文件已保存
- [ ] LoRA权重已合并（如果使用LoRA）
- [ ] 模型能正常推理
- [ ] ASR有提升

---

## 🚀 立即开始

```bash
# 推荐：先快速测试
cd /data3/pengqingsong/finetune/LLaMA-Factory
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_test.yaml

# 然后LoRA训练
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora.yaml
```

🎉 **祝训练顺利！**
