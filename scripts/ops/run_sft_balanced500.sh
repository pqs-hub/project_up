#!/usr/bin/env bash
# 使用均衡数据集（每类最多 500）训练 Qwen2.5-Coder-7B 的 LoRA
# 默认数据集: data/sft_dataset_balanced_uniform500.jsonl
#
# 用法:
#   bash scripts/ops/run_sft_balanced500.sh
# 或覆盖参数:
#   DATASET_NAME=verilog_attack_sft_balanced500 \
#   DATASET_FILE=sft_dataset_balanced_uniform500.jsonl \
#   OUTPUT_DIR=/path/to/save \
#   bash scripts/ops/run_sft_balanced500.sh
#
# 若 OUTPUT_DIR 下已有 checkpoint，会从该 checkpoint 恢复；要从头训请换新目录，例如:
#   OUTPUT_DIR=$LLAMAFACTORY_DIR/saves/qwen25coder_verilog_attack_lora_sft_bal500_new bash scripts/ops/run_sft_balanced500.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"

LLAMAFACTORY_DIR="${LLAMAFACTORY_DIR:-/data3/pengqingsong/finetune/LLaMA-Factory}"
CONFIG_YAML="${CONFIG_YAML:-$LLAMAFACTORY_DIR/examples/train_lora/verilog_attack_sft.yaml}"
CONDA_SH="${CONDA_SH:-/data3/pengqingsong/software/miniconda3/etc/profile.d/conda.sh}"
# 默认使用 codev-r1 环境；可覆盖: CONDA_ENV=hw_attack bash scripts/ops/run_sft_balanced500.sh
CONDA_ENV="${CONDA_ENV:-codev-r1}"

DATA_DIR="${DATA_DIR:-$PROJECT_DIR/data}"
DATASET_INFO="${DATASET_INFO:-$DATA_DIR/dataset_info.json}"
DATASET_NAME="${DATASET_NAME:-verilog_attack_sft_balanced500}"
DATASET_FILE="${DATASET_FILE:-sft_dataset_balanced_uniform500.jsonl}"
OUTPUT_DIR="${OUTPUT_DIR:-$LLAMAFACTORY_DIR/saves/qwen25coder_verilog_attack_lora_sft_bal500}"
CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-0,1,2,3}"

if [[ ! -d "$LLAMAFACTORY_DIR" ]]; then
  echo "错误: 未找到 LLaMA-Factory 目录: $LLAMAFACTORY_DIR"
  exit 1
fi

if [[ ! -f "$CONFIG_YAML" ]]; then
  echo "错误: 未找到训练配置: $CONFIG_YAML"
  exit 1
fi

if [[ ! -f "$DATA_DIR/$DATASET_FILE" ]]; then
  echo "错误: 未找到数据集文件: $DATA_DIR/$DATASET_FILE"
  exit 1
fi

if [[ ! -f "$DATASET_INFO" ]]; then
  echo "错误: 未找到 dataset_info.json: $DATASET_INFO"
  exit 1
fi

# 确保 dataset_info.json 中存在目标数据集条目
python - "$DATASET_INFO" "$DATASET_NAME" "$DATASET_FILE" <<'PY'
import json
import sys
from pathlib import Path

dataset_info = Path(sys.argv[1])
dataset_name = sys.argv[2]
dataset_file = sys.argv[3]

obj = {}
if dataset_info.exists():
    try:
        obj = json.loads(dataset_info.read_text(encoding="utf-8"))
    except Exception:
        pass

entry = {
    "file_name": dataset_file,
    "formatting": "alpaca",
    "columns": {
        "prompt": "instruction",
        "query": "input",
        "response": "output",
        "history": "history"
    }
}

changed = dataset_name not in obj or obj.get(dataset_name) != entry
obj[dataset_name] = entry

if changed:
    dataset_info.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[INFO] 已更新 dataset_info: {dataset_name} -> {dataset_file}")
else:
    print(f"[INFO] dataset_info 已包含 {dataset_name}")
PY

if [[ ! -f "$CONDA_SH" ]]; then
  echo "错误: 未找到 conda 初始化脚本: $CONDA_SH"
  exit 1
fi

source "$CONDA_SH"
# conda activate/deactivate 过程中部分 hook 脚本会访问未定义变量；
# 临时关闭 nounset，避免在非目标环境切换时报错（例如 CONDA_BACKUP_CXX）。
set +u
conda activate "$CONDA_ENV"
set -u

# 先检查核心依赖，避免跑到一半才报错
python - <<'PY'
mods = ["torch", "transformers", "peft", "datasets", "accelerate"]
missing = []
for m in mods:
    try:
        __import__(m)
    except Exception:
        missing.append(m)
if missing:
    print("缺少依赖模块:", ", ".join(missing))
    print("请先安装，例如: pip install " + " ".join(missing))
    raise SystemExit(1)
PY

cd "$LLAMAFACTORY_DIR"
mkdir -p "$OUTPUT_DIR"

echo "============================================================"
echo "LLaMA-Factory SFT 启动参数"
echo "  config      : $CONFIG_YAML"
echo "  dataset_dir : $DATA_DIR"
echo "  dataset     : $DATASET_NAME"
echo "  output_dir  : $OUTPUT_DIR"
echo "  gpus        : $CUDA_VISIBLE_DEVICES"
echo "============================================================"

# 优先使用命令行入口，找不到时回退到 python -m（配 PYTHONPATH）
if command -v llamafactory-cli >/dev/null 2>&1; then
  CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES" \
  llamafactory-cli train "$CONFIG_YAML" \
    dataset_dir="$DATA_DIR" \
    dataset="$DATASET_NAME" \
    output_dir="$OUTPUT_DIR"
else
  echo "[WARN] llamafactory-cli 不存在，回退到 python -m llamafactory.cli"
  CUDA_VISIBLE_DEVICES="$CUDA_VISIBLE_DEVICES" \
  PYTHONPATH="$LLAMAFACTORY_DIR/src" \
  python -m llamafactory.cli train "$CONFIG_YAML" \
    dataset_dir="$DATA_DIR" \
    dataset="$DATASET_NAME" \
    output_dir="$OUTPUT_DIR"
fi

