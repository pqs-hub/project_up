#!/usr/bin/env bash
# LLaMAFactory SFT：使用 data/sft_dataset_final.jsonl 微调 Verilog 攻击决策模型
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
# LLaMAFactory 安装目录（请按本机路径修改）
LLAMAFACTORY_DIR="${LLAMAFACTORY_DIR:-/data3/pengqingsong/finetune/LLaMA-Factory}"
CONFIG_YAML="${LLAMAFACTORY_DIR}/examples/train_lora/verilog_attack_sft.yaml"

cd "$LLAMAFACTORY_DIR"
export dataset_dir="$PROJECT_DIR/data"

# 若 dataset_info.json 在项目 data 目录，确保存在
if [[ ! -f "$PROJECT_DIR/data/dataset_info.json" ]]; then
  echo "请先在 $PROJECT_DIR/data 下创建 dataset_info.json（见上方说明）"
  exit 1
fi

# 单卡
# llamafactory-cli train "$CONFIG_YAML" dataset_dir="$dataset_dir"

# 多卡示例（4 卡）：
CUDA_VISIBLE_DEVICES=0,1,2,3 llamafactory-cli train "$CONFIG_YAML" dataset_dir="$dataset_dir"