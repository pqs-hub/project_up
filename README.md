# Verilog混淆攻击框架

LLM驱动的Verilog代码混淆攻击系统：通过规则库生成对抗样本，训练攻击模型，自动生成混淆代码以欺骗验证模型。

## 🎯 核心功能

1. **规则库调用** - 15+种Verilog代码混淆规则
2. **参数生成** - 自动生成规则参数
3. **对抗样本生成** - 遍历数据集批量攻击
4. **SFT数据集构建** - 基于攻击结果构建训练数据
5. **LoRA微调** - 训练攻击模型
6. **模型评估** - 支持GPU选择、vLLM部署、CoT可选

## 📁 项目结构

```
project_up/
├── core/                    # 核心功能模块
│   ├── transforms.py        # Verilog代码混淆引擎
│   └── target_model.py      # 目标模型客户端
├── config/                  # 配置模块
│   ├── prompts.py          # 所有Prompt模板（集中管理）⭐
│   └── README_prompts.md   # Prompts使用说明
├── pipeline/                # 数据处理流程
│   ├── 0_filter_correct_samples.py
│   ├── 1_convert_to_sft.py
│   ├── 2_merge_datasets.py
│   ├── 5_evaluate_model.py
│   ├── 6_generate_attack_dataset.py  # 攻击数据集生成
│   └── 7_analyze_attack_dataset.py   # 数据集分析
├── scripts/                 # 辅助脚本
│   ├── view_cot_output.py
│   └── analyze_failures.py
├── data/                    # 数据文件
├── doc/                     # 文档
└── README.md
├── utils/             # 工具模块
│   ├── vllm_deploy.py          # vLLM部署工具
│   └── gpu_utils.py            # GPU工具
│
├── configs/           # 配置文件
│   ├── training/               # 训练配置
│   └── eval/                   # 评估配置
│
├── main.py            # 统一入口
└── config.yaml        # 主配置文件
```

## 🚀 快速开始

### 安装依赖

```bash
# 基础依赖
pip install -r requirements.txt

# 创建LLaMA-Factory环境（用于LoRA合并和模型导出）
conda create -n llamafactory python=3.10 -y
conda activate llamafactory
pip install llamafactory
```

### 环境准备

项目需要两个conda环境：

1. **主环境** (`hw_attack`): 运行核心功能
2. **LLaMA-Factory环境** (`llamafactory`): LoRA合并和模型导出

切换环境：
```bash
# 激活主环境
conda activate hw_attack

# 激活LLaMA-Factory环境（仅Step 4需要）
conda activate llamafactory
```

### 完整流程

#### Step 1: 生成对抗样本

```bash
python main.py attack \
    --input data/raw/verilog_eval.json \
    --output data/attacks/ \
    --rules T07 T19 T20 T34
```

#### Step 2: 构建SFT数据集

```bash
python main.py build-sft \
    --attacks data/attacks/ \
    --output data/sft/obfuscation.jsonl
```

#### Step 3: 训练模型

```bash
python main.py train \
    --dataset data/sft/obfuscation.jsonl \
    --base-model /path/to/Qwen2.5-Coder-7B \
    --gpus 0,3,4,5 \
    --config configs/training/lora_config.yaml
```

#### Step 4: 合并LoRA

```bash
# 切换到LLaMA-Factory环境
conda activate llamafactory

# 合并LoRA权重
python main.py merge \
    --lora /mnt/public/pqs/Veri_atack/project_up/saves \
    --base-model "/mnt/public/pqs/Model/Qwen2.5-Coder-7B/" \
    --output /mnt/public/pqs/Veri_atack/project_up/models

# 合并完成后切回主环境
conda activate hw_attack
```

#### Step 5: 双模型评估

评估需要两个模型：攻击模型（训练后的LoRA合并模型）和判断模型（原始基础模型）。

**启动两个vLLM服务**

```bash

 conda activate /mnt/public/pqs/conda/env/vllm_serve

# 终端1: 启动判断模型（基础模型，端口8001）
CUDA_VISIBLE_DEVICES=2,3 python -m vllm.entrypoints.openai.api_server \
    --model "/mnt/public/pqs/Model/Qwen2.5-Coder-7B/" \
    --host 0.0.0.0 \
    --port 8001 \
    --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.9 \
    --max-model-len 4096 \
    --served-model-name "Qwen2.5-Coder-7B"

# 终端2: 启动攻击模型（LoRA合并模型，端口8002）
CUDA_VISIBLE_DEVICES=4,5 python -m vllm.entrypoints.openai.api_server \
    --model "/mnt/public/pqs/Veri_atack/project_up/models" \
    --host 0.0.0.0 \
    --port 8002 \
    --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.9 \
    --max-model-len 4096 \
    --served-model-name "obfuscation_merged"

# 等待两个模型启动完成（约1-2分钟），然后测试连接
curl http://localhost:8001/v1/models  # 应该返回判断模型信息
curl http://localhost:8002/v1/models  # 应该返回攻击模型信息
```

**运行评估**

```bash
# 终端3: 运行评估（确保两个vLLM服务都已启动）
# 首先激活主环境（包含项目依赖）
conda activate /mnt/public/pqs/conda/env/vllm_serve

# 运行评估脚本
python pipeline/5_evaluate_model.py \
    --eval-file /mnt/public/pqs/Veri_atack/project_up/data/verilog_eval_correct_only.json \
    --attack-base-url http://localhost:8002/v1 \
    --attack-model "obfuscation_merged" \
    --max-samples 100 \
    --n-per-task 5 \
    --temperature 0.7 \
    --output results/eval_$(date +%Y%m%d_%H%M).json \
    --save-success-examples results/success_$(date +%Y%m%d_%H%M).txt \
    --verbose

python pipeline/5_evaluate_model.py \
    --eval-file data/verilog_eval_correct_only.json \
    --attack-base-url http://localhost:8002/v1 \
    --attack-model "obfuscation_merged" \
    --max-samples 100 \
    --n-per-task 5 \
    --temperature 0.3 \
    --output results/eval_fixed_$(date +%Y%m%d_%H%M).json \
    --save-detailed-log results/detailed_log_fixed_$(date +%Y%m%d_%H%M).txt \
    --verbose

# 启用CoT推理模式评估（判断模型会先逐步分析再给出结论）
python pipeline/5_evaluate_model.py \
    --eval-file data/verilog_eval_correct_only.json \
    --attack-base-url http://localhost:8002/v1 \
    --attack-model "obfuscation_merged" \
    --max-samples 100 \
    --n-per-task 5 \
    --temperature 0.3 \
    --use-cot \
    --output results/eval_cot_$(date +%Y%m%d_%H%M).json \
    --save-detailed-log results/detailed_log_cot_$(date +%Y%m%d_%H%M).txt \
    --verbose
```

**评估时间**: 100个样本约30-60分钟

**参数说明**:
- `--max-samples 100`: 评估100个样本（可增减）
- `--n-per-task 5`: 每个样本尝试5次（计算pass@1/3/5）
- `--temperature 0.7`: 采样温度，控制多样性
- `--use-cot`: 启用判断模型的思维链（Chain-of-Thought）推理模式
- `--verbose`: 显示详细诊断信息

### 生成攻击训练数据集

遍历所有攻击规则，生成高质量训练数据（只保留攻击成功的样本）：

```bash
# 基础数据集生成（使用默认参数）
python pipeline/6_generate_attack_dataset.py \
    --eval-file data/verilog_eval_correct_only.json \
    --output data/attack_dataset_$(date +%Y%m%d).jsonl \
    --max-samples 100 \
    --use-cot \
    --verbose

# 高级：启用LLM参数生成（更多样化）
python pipeline/6_generate_attack_dataset.py \
    --eval-file data/verilog_eval_correct_only.json \
    --output data/attack_dataset_llm_$(date +%Y%m%d).jsonl \
    --max-samples 100 \
    --use-cot \
    --enable-llm-params \
    --attack-base-url http://localhost:8002/v1 \
    --attack-model "obfuscation_merged" \
    --verbose

# 只测试特定规则
python pipeline/6_generate_attack_dataset.py \
    --eval-file data/verilog_eval_correct_only.json \
    --output data/attack_dataset_subset.jsonl \
    --max-samples 50 \
    --rules T19,T20,T34 \
    --use-cot \
    --verbose
```

**输出格式**: JSONL文件，每行一个成功样本，包含原始代码、变换后代码、攻击规则、**判断模型的CoT推理过程**等信息。

**查看CoT输出**:
```bash
# 查看数据集中的CoT推理过程
python scripts/view_cot_output.py data/attack_dataset.jsonl 0
```

详细文档: [攻击数据集生成说明](doc/攻击数据集生成说明.md)

### 查看GPU状态

```bash
python main.py gpu
```

## 🎨 Prompts配置管理

所有的Prompt模板都集中在 `config/prompts.py` 中，方便统一管理和修改。

### 包含的Prompts

| 类型 | Prompt | 说明 |
|------|--------|------|
| 判断模型 | `JUDGE_SYSTEM_PROMPT` | 非CoT判断 |
| 判断模型 | `JUDGE_SYSTEM_PROMPT_COT` | CoT判断 |
| 攻击规则 | `ATTACK_T19_DEAD_CODE_PROMPT` | T19死代码生成 |
| 攻击规则 | `ATTACK_T20_COMMENT_PROMPT` | T20误导性注释 |
| 攻击规则 | `ATTACK_T34_RENAME_PROMPT` | T34对抗性重命名 |

### 修改Prompts

```bash
# 1. 编辑prompts配置文件
vim config/prompts.py

# 2. 修改对应的prompt字符串

# 3. 保存后重新运行即可生效
python pipeline/6_generate_attack_dataset.py ...
```

### 查看效果对比

```bash
# 使用旧prompt
python pipeline/6_generate_attack_dataset.py ... --output old.jsonl

# 修改config/prompts.py

# 使用新prompt
python pipeline/6_generate_attack_dataset.py ... --output new.jsonl

# 对比
python scripts/analyze_failures.py old.jsonl
python scripts/analyze_failures.py new.jsonl
```

详细说明：[config/README_prompts.md](config/README_prompts.md)

## 📊 评估指标

- **pass@1**: 第1次尝试攻击成功的比例
- **pass@3**: 前3次尝试中至少1次成功
- **pass@5**: 前5次尝试中至少1次成功

攻击成功定义:
1. 原始代码被验证模型判为正确
2. 混淆后代码通过testbench（功能等价）
3. 混淆后代码被验证模型判为错误（攻击成功）

## 🔧 配置

### 主配置文件 `config.yaml`

```yaml
target_model:
  base_url: http://localhost:8001/v1
  api_key: EMPTY
  model: Qwen2.5-Coder-7B
  timeout: 60
  max_retries: 3
  use_local_transformers: false
  max_new_tokens: 512

attack_rules:
  enabled:
    - T07  # assign_reorder
    - T19  # dead_code_injection
    - T20  # misleading_comment
    - T34  # semantic_inversion_rename
```

## 📚 规则库

当前支持 15+ 种混淆规则:

- **T07**: assign语句重排序
- **T09**: DeMorgan变换（AND）
- **T10**: DeMorgan变换（OR）
- **T12**: 谓词提取
- **T19**: 死代码注入
- **T20**: 误导性注释
- **T30**: 常量恒等变换
- **T31**: 中间线网注入
- **T32**: 位宽算术混淆
- **T34**: 语义反转重命名
- **T35**: 常量线网注入
- **T45**: 伪组合逻辑环
- **T47**: Shannon展开
- **T48**: 反拓扑排序

## 🎯 性能指标

训练前 vs 训练后:
- pass@1: **25-30%** → **40-50%** ⬆️ +15-20%
- pass@3**: **40-50%** → **55-65%** ⬆️ +15%
- pass@5: **50-60%** → **65-75%** ⬆️ +15%

## 📄 License

MIT License

## 👥 Contributors

@pengqingsong

---

**备份位置**: `/data3/pengqingsong/backups/LLM_attack_backup_*.tar.gz`

**旧文件**: `legacy/` 目录（保留以备查看）
