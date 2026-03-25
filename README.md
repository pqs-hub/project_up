# Verilog混淆攻击框架

LLM驱动的Verilog代码混淆攻击系统：通过规则库生成对抗样本，训练攻击模型，自动生成混淆代码以欺骗验证模型。

## 🎯 核心功能

1. **规则库调用** - 15+种Verilog代码混淆规则
2. **参数生成** - 自动生成规则参数
3. **对抗样本生成** - 遍历数据集批量攻击
4. **SFT数据集构建** - 基于攻击结果构建训练数据
5. **LoRA微调** - 训练攻击模型
6. **模型评估** - 支持GPU选择、vLLM部署、CoT可选

## 📂 项目结构

```
LLM_attack/
├── core/              # 核心库
│   ├── transforms.py           # 规则库
│   ├── transform_loader.py     # 规则加载器
│   ├── param_generator.py      # 参数生成器
│   ├── target_model.py         # 验证模型客户端
│   └── testbench.py            # 测试台运行器
│
├── pipeline/          # 核心流程
│   ├── 1_generate_attacks.py   # 生成对抗样本
│   ├── 2_build_sft_dataset.py  # 构建SFT数据集
│   ├── 3_train_model.py        # 训练模型（LoRA）
│   ├── 4_merge_lora.py         # 合并LoRA权重
│   └── 5_evaluate_model.py     # 评估模型
│
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
pip install -r requirements.txt
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
python main.py merge \
    --lora models/checkpoints/obfuscation_lora \
    --base-model /path/to/Qwen2.5-Coder-7B \
    --output models/merged/obfuscation_model
```

#### Step 5: 评估模型

```bash
# 先启动vLLM服务
python -m vllm.entrypoints.openai.api_server \
    --model models/merged/obfuscation_model \
    --port 8002 \
    --gpu-memory-utilization 0.9

# 运行评估
python main.py eval \
    --model models/merged/obfuscation_model \
    --eval-data data/eval/verilog_eval.json \
    --attack-gpus 0,1 \
    --judge-gpus 2,3 \
    --use-cot \
    --output results/evaluation/eval_results.json
```

### 查看GPU状态

```bash
python main.py gpu
```

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
