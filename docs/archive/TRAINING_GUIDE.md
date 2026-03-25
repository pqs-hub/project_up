# 🚀 训练指南 - Verilog代码混淆SFT模型

## 📋 前置要求

### 安装依赖
```bash
pip install transformers>=4.36.0 datasets accelerate torch
```

### 检查GPU
```bash
nvidia-smi
```

---

## ⚡ 快速开始

### 1. 基础训练（推荐）

```bash
python train.py \
    --data data/sft_attack_success_balanced.jsonl \
    --model Qwen/Qwen2.5-Coder-7B-Instruct \
    --epochs 3 \
    --batch_size 4 \
    --gradient_accumulation_steps 4 \
    --learning_rate 2e-5 \
    --output_dir ./obfuscation_model_v1
```

**说明**:
- 使用平衡去重数据集（37,745样本）
- 3个epoch足够收敛
- 有效batch size = 4 × 4 = 16

### 2. 快速验证

```bash
# 使用更小的数据集快速测试
python train.py \
    --data data/sft_attack_success_dedup.jsonl \
    --model Qwen/Qwen2.5-Coder-7B-Instruct \
    --epochs 2 \
    --batch_size 4 \
    --output_dir ./obfuscation_model_test
```

### 3. 完整训练（最佳效果）

```bash
python train.py \
    --data data/sft_attack_success_balanced.jsonl \
    --model Qwen/Qwen2.5-Coder-7B-Instruct \
    --epochs 5 \
    --batch_size 4 \
    --gradient_accumulation_steps 8 \
    --learning_rate 2e-5 \
    --warmup_steps 200 \
    --bf16 \
    --output_dir ./obfuscation_model_final
```

**说明**:
- 5个epoch充分训练
- 更大的有效batch size（4×8=32）
- 使用BF16混合精度（需要A100/H100）
- 更多warmup步数

---

## 🎯 参数说明

### 必选参数

| 参数 | 说明 | 示例 |
|------|------|------|
| `--data` | 训练数据路径 | `data/sft_attack_success_balanced.jsonl` |
| `--model` | 基础模型 | `Qwen/Qwen2.5-Coder-7B-Instruct` |

### 训练参数

| 参数 | 默认值 | 说明 | 推荐值 |
|------|--------|------|--------|
| `--epochs` | 3 | 训练轮数 | 3-5 |
| `--batch_size` | 4 | 每GPU的batch size | 2-8（取决于显存）|
| `--gradient_accumulation_steps` | 4 | 梯度累积步数 | 4-8 |
| `--learning_rate` | 2e-5 | 学习率 | 1e-5 ~ 5e-5 |
| `--warmup_steps` | 100 | warmup步数 | 100-500 |
| `--max_length` | 2048 | 最大序列长度 | 2048 |

### 优化参数

| 参数 | 说明 | 推荐 |
|------|------|------|
| `--fp16` | 使用FP16混合精度 | V100/RTX GPU使用 |
| `--bf16` | 使用BF16混合精度 | A100/H100使用 |
| `--output_dir` | 模型输出目录 | `./obfuscation_model` |

---

## 💾 显存需求

### 7B模型（Qwen2.5-Coder-7B）

| Batch Size | 梯度累积 | 有效BS | FP16显存 | BF16显存 | 推荐GPU |
|-----------|---------|--------|---------|---------|---------|
| 1 | 8 | 8 | ~18GB | ~16GB | RTX 3090/4090 |
| 2 | 4 | 8 | ~24GB | ~22GB | A6000/A5000 |
| 4 | 4 | 16 | ~40GB | ~36GB | A100 40GB |
| 8 | 2 | 16 | ~80GB | ~72GB | A100 80GB |

### 如果显存不足

```bash
# 方法1: 减小batch size
python train.py \
    --batch_size 1 \
    --gradient_accumulation_steps 16

# 方法2: 减小max_length
python train.py \
    --max_length 1024

# 方法3: 使用LoRA（需要peft库）
# （待实现）
```

---

## 📊 监控训练

### 训练日志

训练时会输出：
```
Step 10: loss=2.345
Step 20: loss=1.987
Step 30: loss=1.654
...
```

### 检查点

模型会定期保存在 `{output_dir}/checkpoint-{step}/`

### TensorBoard（可选）

```bash
# 在training_args中设置report_to="tensorboard"
tensorboard --logdir {output_dir}/logs
```

---

## 🎓 训练策略建议

### 策略1: 标准训练（推荐新手）

```bash
# 第1步：快速验证（30分钟）
python train.py \
    --data data/sft_attack_success_dedup.jsonl \
    --epochs 1 \
    --batch_size 4 \
    --output_dir ./test_model

# 第2步：完整训练（3-5小时）
python train.py \
    --data data/sft_attack_success_balanced.jsonl \
    --epochs 3 \
    --batch_size 4 \
    --gradient_accumulation_steps 4 \
    --output_dir ./obfuscation_model
```

### 策略2: 分阶段训练（推荐高级用户）

```bash
# 阶段1: 高ASR规则（T45, T19）
cat data/sft_attack_success_by_rule/sft_T45.jsonl \
    data/sft_attack_success_by_rule/sft_T19.jsonl \
    > data/stage1_high_asr.jsonl

python train.py \
    --data data/stage1_high_asr.jsonl \
    --epochs 3 \
    --output_dir ./model_stage1

# 阶段2: 中ASR规则（T20, T34, T12, T30）
cat data/sft_attack_success_by_rule/sft_T20.jsonl \
    data/sft_attack_success_by_rule/sft_T34.jsonl \
    data/sft_attack_success_by_rule/sft_T12.jsonl \
    data/sft_attack_success_by_rule/sft_T30.jsonl \
    > data/stage2_mid_asr.jsonl

python train.py \
    --data data/stage2_mid_asr.jsonl \
    --model ./model_stage1 \
    --epochs 2 \
    --output_dir ./model_stage2

# 阶段3: 全量微调
python train.py \
    --data data/sft_attack_success_balanced.jsonl \
    --model ./model_stage2 \
    --epochs 1 \
    --learning_rate 1e-5 \
    --output_dir ./model_final
```

### 策略3: 数据增强

```bash
# 合并现有数据集
cat data/sft_from_eval_highquality.jsonl \
    data/sft_attack_success_balanced.jsonl \
    > data/sft_combined.jsonl

python train.py \
    --data data/sft_combined.jsonl \
    --epochs 3 \
    --output_dir ./obfuscation_model_augmented
```

---

## 🔍 训练后评估

### 1. 测试模型推理

```python
from transformers import AutoTokenizer, AutoModelForCausalLM

# 加载训练好的模型
model_path = "./obfuscation_model"
tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForCausalLM.from_pretrained(model_path)

# 测试推理
instruction = "You are a Verilog obfuscation expert..."
input_text = "### 功能规范\n...\n### 原始代码\n..."

prompt = f"""<|im_start|>system
{instruction}<|im_end|>
<|im_start|>user
{input_text}<|im_end|>
<|im_start|>assistant
"""

inputs = tokenizer(prompt, return_tensors="pt")
outputs = model.generate(**inputs, max_new_tokens=512)
print(tokenizer.decode(outputs[0]))
```

### 2. 评估ASR

```bash
# 使用训练好的模型生成混淆代码，然后评估
python evaluate.py \
    --model ./obfuscation_model \
    --dataset data/test_set.json \
    --output results/eval_trained_model.json
```

### 3. 规则多样性分析

检查模型是否学会了所有15个规则

---

## ⚠️ 常见问题

### Q1: CUDA out of memory

**解决**:
```bash
# 减小batch size
python train.py --batch_size 1 --gradient_accumulation_steps 16

# 或减小max_length
python train.py --max_length 1024

# 或使用FP16
python train.py --fp16
```

### Q2: 训练速度慢

**解决**:
```bash
# 使用混合精度
python train.py --bf16  # 或 --fp16

# 检查是否使用了GPU
nvidia-smi

# 增大batch size（如果显存够）
python train.py --batch_size 8
```

### Q3: 模型不收敛

**解决**:
```bash
# 调整学习率
python train.py --learning_rate 1e-5  # 或 5e-5

# 增加warmup
python train.py --warmup_steps 500

# 增加训练轮数
python train.py --epochs 5
```

### Q4: 找不到模型文件

**解决**:
```bash
# 确保已下载模型，或者指定本地路径
python train.py --model /path/to/local/model

# 或使用Hugging Face镜像
export HF_ENDPOINT=https://hf-mirror.com
```

---

## 📈 预期效果

### 基线（未训练）
- ASR: ~48%
- 规则选择: 随机或偏向简单规则
- 参数生成: 默认值

### 训练后（3 epochs）
- ASR: 55-65%
- 规则选择: 能选择15个规则
- 参数生成: 多样化参数

### 训练后（5 epochs + 数据增强）
- ASR: 60-70%
- 规则选择: 优先选择高ASR规则
- 参数生成: 针对性参数

---

## ✅ 检查清单

训练前:
- [ ] GPU可用 (`nvidia-smi`)
- [ ] 依赖已安装 (`pip list | grep transformers`)
- [ ] 数据集存在 (`ls data/sft_attack_success_balanced.jsonl`)
- [ ] 显存足够（参考上面的显存需求表）

训练中:
- [ ] loss在下降
- [ ] 没有CUDA OOM错误
- [ ] checkpoint正常保存

训练后:
- [ ] 模型文件存在 (`ls {output_dir}`)
- [ ] 能加载模型推理
- [ ] ASR有提升

---

## 🚀 现在开始训练！

```bash
# 推荐配置（适合大多数场景）
python train.py \
    --data data/sft_attack_success_balanced.jsonl \
    --model Qwen/Qwen2.5-Coder-7B-Instruct \
    --epochs 3 \
    --batch_size 4 \
    --gradient_accumulation_steps 4 \
    --learning_rate 2e-5 \
    --bf16 \
    --output_dir ./obfuscation_model

# 预计训练时间: 3-5小时（A100 40GB）
```

🎉 **祝训练顺利！**
