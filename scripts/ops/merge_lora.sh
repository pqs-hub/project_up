#!/usr/bin/env bash
# 将 SFT 的 LoRA 与 base 模型合并为完整模型，便于 vLLM 直接加载（无需 --enable-lora）。
# 合并只需做一次，之后 run_vllm.sh 指向合并后的目录即可。
#
# 用法：
#   ./scripts/ops/merge_lora.sh [输出目录]
#   默认输出目录：项目下 models/verilog_attack_merged（可传参覆盖）
#
# 依赖：conda 环境 hw_attack，且已安装 LLaMA-Factory（用于 llamafactory-cli export）

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

# base 模型（与 verilog_attack_sft.yaml 中 model_name_or_path 一致）
BASE_MODEL="${BASE_MODEL:-/data3/pengqingsong/Model/Qwen2.5-Coder-7B}"
# LoRA 适配器目录（LLaMA-Factory 的 saves 下）
LORA_PATH="${LORA_PATH:-/data3/pengqingsong/finetune/LLaMA-Factory/saves/qwen25coder_verilog_attack_lora_sft_bal500}"
# 合并后输出目录
OUTPUT_DIR="${1:-$PROJECT_DIR/models/verilog_attack_merged_bal500}"

LLAMA_FACTORY_DIR="${LLAMA_FACTORY_DIR:-/data3/pengqingsong/finetune/LLaMA-Factory}"

if [[ ! -d "$LLAMA_FACTORY_DIR" ]]; then
    echo "错误: 未找到 LLaMA-Factory 目录: $LLAMA_FACTORY_DIR"
    echo "请设置环境变量 LLAMA_FACTORY_DIR 或 BASE_MODEL / LORA_PATH"
    exit 1
fi
# 若 LORA_PATH 根目录无 adapter_config.json，尝试使用最新 checkpoint-* 子目录
if [[ ! -f "$LORA_PATH/adapter_config.json" ]]; then
    latest_ckpt=""
    while IFS= read -r -d '' ckpt; do
        [[ -f "$ckpt/adapter_config.json" ]] || continue
        [[ -z "$latest_ckpt" || "$ckpt" -nt "$latest_ckpt" ]] && latest_ckpt="$ckpt"
    done < <(find "$LORA_PATH" -maxdepth 1 -type d -name 'checkpoint-[0-9]*' -print0 2>/dev/null)
    if [[ -n "$latest_ckpt" ]]; then
        echo "[INFO] 使用最新 checkpoint: $latest_ckpt"
        LORA_PATH="$latest_ckpt"
    else
        echo "错误: 未找到 LoRA 适配器: $LORA_PATH (缺少 adapter_config.json 或 checkpoint-*/adapter_config.json)"
        exit 1
    fi
fi

echo "合并 LoRA 到 base 模型"
echo "  base:   $BASE_MODEL"
echo "  lora:   $LORA_PATH"
echo "  输出:   $OUTPUT_DIR"
echo ""

# 使用 LLaMA-Factory 的 export（会加载 base + adapter，merge_and_unload 后保存）
mkdir -p "$(dirname "$OUTPUT_DIR")"
export_dir_abs="$(cd "$(dirname "$OUTPUT_DIR")" && pwd)/$(basename "$OUTPUT_DIR")"

TMP_YAML=$(mktemp --suffix=.yaml)
trap 'rm -f "$TMP_YAML"' EXIT
cat > "$TMP_YAML" << EOF
# merge_lora: Verilog attack SFT LoRA -> 完整模型
model_name_or_path: $BASE_MODEL
adapter_name_or_path: $LORA_PATH
template: qwen
trust_remote_code: true

export_dir: $export_dir_abs
export_size: 5
export_device: auto
export_legacy_format: false
EOF

echo "激活 conda 环境: hw_attack"
eval "$(conda shell.bash hook)"
conda activate hw_attack

cd "$LLAMA_FACTORY_DIR"
echo "执行: llamafactory-cli export $TMP_YAML"
llamafactory-cli export "$TMP_YAML"

echo ""
echo "合并完成。启动 vLLM 请使用合并后的路径："
echo "  ./scripts/ops/run_vllm.sh $export_dir_abs"
echo "或在 config.yaml 中设置 target_model.model: $export_dir_abs"
echo "然后直接运行: ./scripts/ops/run_vllm.sh"
echo ""
