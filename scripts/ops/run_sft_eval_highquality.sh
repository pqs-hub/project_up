#!/usr/bin/env bash
# 使用 data/sft_from_eval_highquality.jsonl 对 Qwen2.5-Coder 做 LoRA SFT（复用 LLaMA-Factory 配置）。
#
# 前置：
#   - 已安装 LLaMA-Factory（默认 LLAMAFACTORY_DIR）
#   - 训练 yaml 中 model_name_or_path 指向你的 Qwen2.5-Coder 基座（如 verilog_attack_sft.yaml）
#
# 用法（在仓库根目录）：
#   bash scripts/ops/run_sft_eval_highquality.sh
#   CONDA_ENV=hw_attack CUDA_VISIBLE_DEVICES=0,1 bash scripts/ops/run_sft_eval_highquality.sh
#   OUTPUT_DIR=/path/to/save bash scripts/ops/run_sft_eval_highquality.sh
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 委托给通用启动脚本（会写 dataset_info 并 llamafactory-cli train）
export DATASET_NAME="${DATASET_NAME:-verilog_attack_sft_eval_hq}"
export DATASET_FILE="${DATASET_FILE:-sft_from_eval_highquality.jsonl}"

LLAMAFACTORY_DIR="${LLAMAFACTORY_DIR:-/data3/pengqingsong/finetune/LLaMA-Factory}"
export OUTPUT_DIR="${OUTPUT_DIR:-$LLAMAFACTORY_DIR/saves/qwen25coder_verilog_attack_lora_eval_hq}"

exec bash "$SCRIPT_DIR/run_sft_balanced500.sh"
