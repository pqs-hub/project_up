# 🎯 项目重组方案 - 核心功能精简

## 当前问题
- 文件过多，结构混乱
- 大量临时/调试脚本
- 核心流程不清晰
- 缺少统一入口

## 核心功能流程

```
1. 规则库调用与参数生成
   ↓
2. 遍历数据集生成对抗样本  
   ↓
3. 基于攻击结果构建SFT数据集
   ↓
4. 使用SFT数据集微调模型（LoRA）
   ↓
5. 合并LoRA权重
   ↓
6. 评估模型（支持GPU选择、vLLM部署、CoT可选）
```

---

## 🗂️ 新的目录结构

```
LLM_attack/
├── core/                          # 核心库
│   ├── __init__.py
│   ├── transforms.py             # 规则库（合并 ast_transforms*.py）
│   ├── transform_loader.py       # 规则加载器
│   ├── param_generator.py        # 参数生成器
│   ├── testbench.py              # 测试台运行器
│   └── target_model.py           # 验证模型客户端
│
├── pipeline/                      # 核心流程
│   ├── __init__.py
│   ├── 1_generate_attacks.py     # Step1: 生成对抗样本
│   ├── 2_build_sft_dataset.py    # Step2: 构建SFT数据集
│   ├── 3_train_model.py          # Step3: 微调模型
│   ├── 4_merge_lora.py           # Step4: 合并LoRA
│   └── 5_evaluate_model.py       # Step5: 评估模型
│
├── utils/                         # 工具函数
│   ├── __init__.py
│   ├── vllm_deploy.py            # vLLM部署工具
│   ├── gpu_utils.py              # GPU选择工具
│   └── data_utils.py             # 数据处理工具
│
├── configs/                       # 配置文件
│   ├── default_config.yaml       # 默认配置
│   ├── training/                 # 训练配置
│   │   ├── lora_config.yaml
│   │   └── full_config.yaml
│   └── eval/                     # 评估配置
│       ├── eval_config.yaml
│       └── cot_config.yaml
│
├── data/                          # 数据目录
│   ├── raw/                      # 原始数据
│   ├── attacks/                  # 对抗样本
│   ├── sft/                      # SFT数据集
│   └── eval/                     # 评估数据
│
├── models/                        # 模型目录
│   ├── checkpoints/              # LoRA checkpoints
│   └── merged/                   # 合并后的模型
│
├── results/                       # 结果目录
│   ├── attacks/                  # 攻击结果
│   ├── training/                 # 训练日志
│   └── evaluation/               # 评估结果
│
├── scripts/                       # 辅助脚本（保留分析工具）
│   ├── analysis/                 # 数据分析
│   └── tools/                    # 实用工具
│
├── main.py                        # 统一入口
├── config.yaml                    # 主配置文件
├── requirements.txt               # 依赖
└── README.md                      # 使用文档
```

---

## 📋 核心文件保留清单

### ✅ 必须保留（核心功能）

#### 1. 规则库（core/）
- `ast_transforms_loader.py` → `core/transform_loader.py`
- `ast_transforms.2.py` → `core/transforms.py`
- `primitives.py` → `core/primitives.py`（如果被引用）

#### 2. 参数生成（core/）
- `AdversarialDatasetGenerator.py` → `core/param_generator.py`

#### 3. 模型交互（core/）
- `taget_model.py` → `core/target_model.py`
- `Testbench_valid.py` → `core/testbench.py`

#### 4. 数据集生成（pipeline/）
- `scripts/dataset/gen_rule_attacks_from_qualified.py` → `pipeline/1_generate_attacks.py`
- `build_sft_from_attack_success.py` → `pipeline/2_build_sft_dataset.py`

#### 5. 模型训练（pipeline/）
- 训练配置 `llamafactory_configs/*.yaml` → `configs/training/`
- 新建 `pipeline/3_train_model.py` - 封装训练流程

#### 6. 模型评估（pipeline/）
- `scripts/eval/eval_attack_success.py` → `pipeline/5_evaluate_model.py`

### ⚠️ 可选保留（分析工具）

#### 分析脚本（scripts/analysis/）
- `analyze_attack_success_rate.py`
- `scripts/analysis/*.py`

### ❌ 可以删除（临时/调试文件）

#### 重复/过时的文件
- `ast_transforms.py`（旧版本）
- `AttackConfigGenerator.py`（被新版本替代）
- `AttackConfigGenerator_LLM.py`（被新版本替代）

#### 临时分析脚本
- `analyze_t48_*.py`
- `check_*.py`
- `test_*.py`
- `deep_analyze_*.py`
- `extract_*.py`
- `view_*.py`

#### 过时的构建脚本
- `build_sft_dataset.py`（旧版本）
- `build_obfuscation_sft_dataset.py`
- `balanced_dedup_sft_dataset.py`
- `deduplicate_sft_dataset.py`
- `collect_successful_attacks.py`

#### 一次性转换脚本
- `convert_to_llamafactory.py`
- `register_datasets_to_llamafactory.py`
- `filter_qualified.py`

#### 旧的评估脚本
- `evaluate.py`
- `asr_with_default_assumption.py`
- `correct_asr_calculation.py`
- `accurate_metrics_analysis.py`

---

## 🚀 统一入口设计

### main.py - 命令行界面

```python
#!/usr/bin/env python3
"""
Verilog混淆攻击框架 - 统一入口
"""
import argparse
from pipeline import (
    generate_attacks,
    build_sft_dataset,
    train_model,
    merge_lora,
    evaluate_model
)

def main():
    parser = argparse.ArgumentParser(
        description="Verilog Obfuscation Attack Framework"
    )
    subparsers = parser.add_subparsers(dest='command', help='Pipeline steps')
    
    # Step 1: 生成对抗样本
    parser_attack = subparsers.add_parser('attack', help='Generate adversarial samples')
    parser_attack.add_argument('--input', required=True, help='Input dataset')
    parser_attack.add_argument('--output', required=True, help='Output directory')
    parser_attack.add_argument('--rules', nargs='+', help='Rule IDs to use')
    
    # Step 2: 构建SFT数据集
    parser_sft = subparsers.add_parser('build-sft', help='Build SFT dataset')
    parser_sft.add_argument('--attacks', required=True, help='Attacks directory')
    parser_sft.add_argument('--output', required=True, help='Output SFT dataset')
    
    # Step 3: 训练模型
    parser_train = subparsers.add_parser('train', help='Train model with LoRA')
    parser_train.add_argument('--dataset', required=True, help='SFT dataset')
    parser_train.add_argument('--base-model', required=True, help='Base model path')
    parser_train.add_argument('--gpus', default='0,1,2,3', help='GPU IDs')
    parser_train.add_argument('--config', help='Training config YAML')
    
    # Step 4: 合并LoRA
    parser_merge = subparsers.add_parser('merge', help='Merge LoRA weights')
    parser_merge.add_argument('--lora', required=True, help='LoRA checkpoint')
    parser_merge.add_argument('--base-model', required=True, help='Base model')
    parser_merge.add_argument('--output', required=True, help='Output directory')
    
    # Step 5: 评估模型
    parser_eval = subparsers.add_parser('eval', help='Evaluate attack model')
    parser_eval.add_argument('--model', required=True, help='Attack model path')
    parser_eval.add_argument('--eval-data', required=True, help='Evaluation dataset')
    parser_eval.add_argument('--attack-gpus', default='0', help='GPUs for attack model')
    parser_eval.add_argument('--judge-gpus', default='1', help='GPUs for judge model')
    parser_eval.add_argument('--use-cot', action='store_true', help='Use CoT for judge')
    parser_eval.add_argument('--output', required=True, help='Results output path')
    
    # 完整流程
    parser_full = subparsers.add_parser('full', help='Run full pipeline')
    parser_full.add_argument('--config', required=True, help='Pipeline config YAML')
    
    args = parser.parse_args()
    
    if args.command == 'attack':
        generate_attacks.run(args)
    elif args.command == 'build-sft':
        build_sft_dataset.run(args)
    elif args.command == 'train':
        train_model.run(args)
    elif args.command == 'merge':
        merge_lora.run(args)
    elif args.command == 'eval':
        evaluate_model.run(args)
    elif args.command == 'full':
        run_full_pipeline(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
```

---

## 📝 使用示例

### 完整流程
```bash
# 一键运行完整pipeline
python main.py full --config configs/pipeline.yaml
```

### 单步运行
```bash
# Step 1: 生成对抗样本
python main.py attack \
    --input data/raw/verilog_eval.json \
    --output data/attacks/ \
    --rules T07 T19 T20 T34

# Step 2: 构建SFT数据集
python main.py build-sft \
    --attacks data/attacks/ \
    --output data/sft/obfuscation.jsonl

# Step 3: 训练模型
python main.py train \
    --dataset data/sft/obfuscation.jsonl \
    --base-model /path/to/Qwen2.5-Coder-7B \
    --gpus 0,3,4,5 \
    --config configs/training/lora_config.yaml

# Step 4: 合并LoRA
python main.py merge \
    --lora models/checkpoints/obfuscation_lora \
    --base-model /path/to/Qwen2.5-Coder-7B \
    --output models/merged/obfuscation_model

# Step 5: 评估模型
python main.py eval \
    --model models/merged/obfuscation_model \
    --eval-data data/eval/verilog_eval.json \
    --attack-gpus 0,1 \
    --judge-gpus 2,3 \
    --use-cot \
    --output results/evaluation/eval_results.json
```

---

## 🔧 配置文件示例

### configs/pipeline.yaml
```yaml
# 完整pipeline配置
data:
  raw_dataset: data/raw/verilog_eval.json
  attacks_dir: data/attacks
  sft_dataset: data/sft/obfuscation.jsonl
  eval_dataset: data/eval/verilog_eval.json

models:
  base_model: /data3/pengqingsong/Model/Qwen2.5-Coder-7B/
  lora_checkpoint: models/checkpoints/obfuscation_lora
  merged_model: models/merged/obfuscation_model

training:
  gpus: [0, 3, 4, 5]
  config: configs/training/lora_config.yaml
  epochs: 5
  batch_size: 4

evaluation:
  attack_gpus: [0, 1]
  judge_gpus: [2, 3]
  judge_use_cot: true
  max_samples: 100
  n_per_task: 5

rules:
  enabled:
    - T07  # assign_reorder
    - T19  # dead_code_injection
    - T20  # misleading_comment
    - T34  # semantic_inversion_rename
```

---

## ✅ 重组执行计划

### Phase 1: 创建新结构
1. 创建新目录结构
2. 移动核心文件到对应位置
3. 重命名和整理文件

### Phase 2: 实现统一入口
1. 实现 `main.py`
2. 创建 `pipeline/*` 模块
3. 创建 `utils/*` 工具

### Phase 3: 清理旧文件
1. 备份当前项目
2. 删除临时/调试文件
3. 更新文档

### Phase 4: 测试验证
1. 测试每个pipeline步骤
2. 测试完整流程
3. 更新README

---

## 📊 预期效果

### 重组前
- 根目录：40+ Python文件
- scripts/：30+ 文件
- 结构混乱，难以维护

### 重组后
- 清晰的模块化结构
- 统一的命令行入口
- 核心代码 <15 个文件
- 易于理解和扩展

---

## 🎯 下一步

是否开始执行重组？我可以：

1. **自动重组**：创建新结构并移动文件
2. **手动指导**：给出详细的移动命令
3. **分步执行**：一步步完成重组

请告诉我您的选择！
