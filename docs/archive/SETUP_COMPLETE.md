# ✅ LLaMA-Factory 训练环境配置完成

## 🎉 已完成的工作

### 1. ✅ 数据集准备
- **转换完成**: 3个数据集已转换为LLaMA-Factory格式
- **文件位置**: `/data3/pengqingsong/finetune/LLaMA-Factory/data/`
  - `obfuscation_balanced.json` - 37,745样本（推荐）
  - `obfuscation_dedup.json` - 16,126样本
  - `obfuscation_full.json` - 44,246样本

### 2. ✅ 数据集注册
- **已注册**: 3个数据集已添加到 `dataset_info.json`
- **可用名称**:
  - `obfuscation_balanced`
  - `obfuscation_dedup`
  - `obfuscation_full`

### 3. ✅ 训练配置创建
配置文件位置: `/data3/pengqingsong/LLM_attack/llamafactory_configs/`

| 配置文件 | 用途 | 样本数 | 方法 | 推荐场景 |
|---------|------|--------|------|---------|
| `sft_obfuscation_test.yaml` | 快速测试 | 1,000 | LoRA | 验证pipeline |
| `sft_obfuscation_lora.yaml` | LoRA训练 | 37,745 | LoRA | 显存<40GB |
| `sft_obfuscation_balanced.yaml` | 全参数训练 | 37,745 | Full | 显存≥40GB |
| `sft_obfuscation_lora_export.yaml` | LoRA导出 | - | - | 合并权重 |

### 4. ✅ 工具脚本
- `convert_to_llamafactory.py` - 数据集格式转换
- `register_datasets_to_llamafactory.py` - 自动注册数据集
- `quick_start_training.sh` - 一键启动训练

### 5. ✅ 文档
- `LLAMAFACTORY_TRAINING_GUIDE.md` - 完整训练指南
- `SETUP_COMPLETE.md` - 本文档

---

## 🚀 现在可以开始训练了！

### 方式1: 使用快速启动脚本（推荐）

```bash
cd /data3/pengqingsong/LLM_attack
./quick_start_training.sh

# 然后选择训练配置:
#   1 - 快速测试（15分钟）
#   2 - LoRA训练（3-5小时）
#   3 - 全参数训练（4-6小时）
```

### 方式2: 直接使用LLaMA-Factory命令

```bash
cd /data3/pengqingsong/finetune/LLaMA-Factory

# 快速测试（推荐第一次使用）
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_test.yaml

# LoRA训练（推荐显存<40GB）
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora.yaml

# 全参数训练（推荐显存≥40GB）
llamafactory-cli train \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_balanced.yaml
```

---

## 📊 训练配置详情

### 快速测试（推荐第一次使用）
```yaml
数据集: obfuscation_dedup (1000样本)
方法: LoRA
Epochs: 1
Batch Size: 4 × 2 = 8
学习率: 5e-4
预计时间: 10-20分钟
显存需求: ~20GB
用途: 验证pipeline是否正常
```

### LoRA训练（推荐）
```yaml
数据集: obfuscation_balanced (37,745样本)
方法: LoRA (rank=8)
Epochs: 5
Batch Size: 4 × 4 = 16
学习率: 5e-4
预计时间: 3-5小时（A100）
显存需求: ~25-30GB
优势: 显存友好，训练快速
```

### 全参数训练
```yaml
数据集: obfuscation_balanced (37,745样本)
方法: Full Fine-tuning
Epochs: 3
Batch Size: 2 × 8 = 16
学习率: 2e-5
预计时间: 4-6小时（A100）
显存需求: ~40-45GB
优势: 效果最佳
```

---

## 📖 重要提示

### 训练前检查
- [ ] GPU可用 (`nvidia-smi`)
- [ ] LLaMA-Factory已安装
- [ ] 数据集已转换并注册
- [ ] 选择合适的配置（根据显存）

### 训练中监控
```bash
# 查看实时日志
tail -f /data3/pengqingsong/LLM_attack/saves/*/train*.log

# 查看GPU使用
watch -n 1 nvidia-smi
```

### 训练后操作

**如果使用LoRA**:
```bash
# 合并LoRA权重
llamafactory-cli export \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora_export.yaml
```

**测试模型**:
```python
from transformers import AutoTokenizer, AutoModelForCausalLM

# 全参数模型
model_path = "/data3/pengqingsong/LLM_attack/saves/obfuscation_balanced_v1"

# LoRA合并后的模型
# model_path = "/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged"

tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForCausalLM.from_pretrained(model_path)
```

---

## 🎯 预期效果

| 阶段 | ASR | 规则选择 | 参数生成 |
|------|-----|---------|---------|
| 基线（未训练） | ~48% | 随机 | 默认值 |
| LoRA训练后 | 55-60% | 15个规则 | 多样化 |
| 全参数训练后 | 60-70% | 优先高ASR | 针对性 |

---

## 🔧 常见问题

### Q1: 显存不足
**解决**: 使用LoRA配置 + 减小batch size
```yaml
per_device_train_batch_size: 1
gradient_accumulation_steps: 16
```

### Q2: 数据集加载失败
**检查**: 
```bash
# 验证注册
python -c "from llamafactory.data import get_dataset_list; print('obfuscation_balanced' in get_dataset_list())"
```

### Q3: 训练速度慢
**优化**:
- 使用BF16（A100/H100）: `bf16: true`
- 增大batch size（如果显存够）
- 检查是否启用了gradient_checkpointing

---

## 📚 相关文档

- **详细训练指南**: `LLAMAFACTORY_TRAINING_GUIDE.md`
- **数据集使用**: `FINAL_DATASET_GUIDE.md`
- **参数修复总结**: `PARAMETERS_FIXED_SUMMARY.md`
- **数据集对比**: `DATASET_FINAL_COMPARISON.md`

---

## ✅ 文件清单

### 数据文件
```
/data3/pengqingsong/finetune/LLaMA-Factory/data/
├── obfuscation_balanced.json      # 37,745样本
├── obfuscation_dedup.json         # 16,126样本
├── obfuscation_full.json          # 44,246样本
└── dataset_info.json              # 已更新（包含上述3个数据集）
```

### 配置文件
```
/data3/pengqingsong/LLM_attack/llamafactory_configs/
├── sft_obfuscation_test.yaml      # 快速测试
├── sft_obfuscation_lora.yaml      # LoRA训练
├── sft_obfuscation_balanced.yaml  # 全参数训练
└── sft_obfuscation_lora_export.yaml  # LoRA导出
```

### 原始数据集
```
/data3/pengqingsong/LLM_attack/data/
├── sft_attack_success_balanced.jsonl   # 37,745样本
├── sft_attack_success_dedup.jsonl      # 16,126样本
└── sft_attack_success_registry.jsonl   # 44,246样本
```

---

## 🚀 推荐训练流程

```bash
# 第1步: 快速测试（15分钟）
cd /data3/pengqingsong/LLM_attack
./quick_start_training.sh
# 选择选项 1

# 第2步: 如果测试通过，开始正式训练
./quick_start_training.sh
# 选择选项 2（LoRA）或 3（全参数）

# 第3步: 评估效果
python evaluate_model.py --model saves/obfuscation_lora_v1

# 第4步（可选）: 合并LoRA权重
cd /data3/pengqingsong/finetune/LLaMA-Factory
llamafactory-cli export \
    /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_lora_export.yaml
```

---

**🎉 一切准备就绪！现在可以开始训练了！**

建议第一次运行快速测试配置，验证整个pipeline正常后，再进行完整训练。

```bash
cd /data3/pengqingsong/LLM_attack
./quick_start_training.sh
```

祝训练顺利！🚀
