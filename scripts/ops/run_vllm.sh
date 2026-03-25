#!/usr/bin/env bash
# 在 hw_attack 环境中用 vLLM 部署本地模型，供 filter_qualified / evaluate 通过 HTTP 调用以加速推理。
#
# 推荐：先把 SFT 的 LoRA 与 base 合并为完整模型，再启动 vLLM（无需 LoRA 参数，部署简单）。
#   先执行一次: ./scripts/ops/merge_lora.sh
#   合并完成后: 在 config.yaml 中 target_model.model 填合并目录，或: ./scripts/ops/run_vllm.sh /path/to/merged
#
# 用法：
#   ./scripts/ops/run_vllm.sh                    # 使用 config 或默认路径（见下）
#   ./scripts/ops/run_vllm.sh /path/to/model    # 指定完整模型路径（合并后的目录或纯 base）
#
# 未合并时：若当前默认路径是 LoRA 目录（含 adapter_config.json），会自动以 base+LoRA 方式启动；
#   也可显式指定: VLLM_USE_LORA=1 BASE_MODEL=... LORA_PATH=... ./scripts/ops/run_vllm.sh
#
# 依赖：conda 环境 hw_attack 中已安装 vllm

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

# 模型路径：优先命令行参数，否则从 config.yaml 的 target_model.model 读取
if [[ -n "$1" ]]; then
    MODEL_PATH="$1"
else
    if command -v python3 &>/dev/null; then
        MODEL_PATH=$(python3 -c "
import yaml
with open('config.yaml') as f:
    print(yaml.safe_load(f)['target_model']['model'].strip())
" 2>/dev/null || true)
    fi
    if [[ -z "$MODEL_PATH" ]]; then
        # 优先使用合并后的模型目录（若存在），否则回退到 LoRA 目录（将自动 base+LoRA 启动）
        MERGED_DEFAULT="$PROJECT_DIR/models/verilog_attack_merged_bal500"
        if [[ -d "$MERGED_DEFAULT" ]] && [[ -f "$MERGED_DEFAULT/config.json" ]]; then
            MODEL_PATH="$MERGED_DEFAULT"
            echo "未指定模型路径且未从 config 读取到，使用已合并模型: $MODEL_PATH"
        else
            MODEL_PATH="/data3/pengqingsong/finetune/LLaMA-Factory/saves/qwen25coder_verilog_attack_lora_sft"
            echo "未指定模型路径且未从 config 读取到，使用默认（LoRA 目录，将 base+LoRA 启动）: $MODEL_PATH"
            echo "若希望直接加载完整模型，请先执行: ./scripts/ops/merge_lora.sh"
        fi
    fi
fi

# 若 MODEL_PATH 目录下有 adapter_config.json，视为 LoRA 目录，自动用 base+LoRA 方式启动
if [[ -f "${MODEL_PATH}/adapter_config.json" ]]; then
    AUTO_LORA=1
else
    AUTO_LORA=0
fi
USE_LORA="${VLLM_USE_LORA:-$AUTO_LORA}"
# base 模型路径（仅 USE_LORA=1 时需要）
BASE_MODEL="${BASE_MODEL:-/data3/pengqingsong/Model/Qwen2.5-Coder-7B}"
# LoRA 适配器目录（仅 USE_LORA=1 时需要；默认用上面的 MODEL_PATH 当作 LoRA 目录）
LORA_PATH="${LORA_PATH:-$MODEL_PATH}"
# LoRA 在 API 中的模型名，请求时 model 填此名
LORA_SERVED_NAME="${LORA_SERVED_NAME:-verilog_attack}"

# 完整模型在 API 中的模型名（请求时 model 填此名）。用短名避免与 vLLM 默认注册名不一致导致 404
VLLM_SERVED_MODEL_NAME="${VLLM_SERVED_MODEL_NAME:-verilog_attack_merged_bal500}"
SERVED_NAME="$VLLM_SERVED_MODEL_NAME"

# 使用 GPU 卡 0,1,2,3；可通过 CUDA_VISIBLE_DEVICES 覆盖
export CUDA_VISIBLE_DEVICES="${CUDA_VISIBLE_DEVICES:-2,3,4,5}"

PORT="${VLLM_PORT:-8001}"
TP_SIZE="${VLLM_TP_SIZE:-4}"
# LoRA rank（与训练时一致，如 verilog_attack_sft.yaml 里 lora_rank: 64）
MAX_LORA_RANK="${VLLM_MAX_LORA_RANK:-64}"

echo "激活 conda 环境: hw_attack"
eval "$(conda shell.bash hook)"
conda activate hw_attack

if [[ "$USE_LORA" == "1" ]]; then
    echo "启动 vLLM 服务（base + LoRA）"
    echo "  base: $BASE_MODEL"
    echo "  lora:  $LORA_PATH"
    echo "  API 模型名: $LORA_SERVED_NAME（请在 config.yaml 中 target_model.model 填此名）"
    echo "  GPU: $CUDA_VISIBLE_DEVICES, 端口: $PORT, 张量并行: $TP_SIZE"
    echo ""
    exec vllm serve "$BASE_MODEL" \
        --enable-lora \
        --lora-modules "${LORA_SERVED_NAME}=${LORA_PATH}" \
        --max-lora-rank "$MAX_LORA_RANK" \
        --host 0.0.0.0 \
        --port "$PORT" \
        --tensor-parallel-size "$TP_SIZE"
fi

echo "启动 vLLM 服务（完整模型）"
echo "  模型路径: $MODEL_PATH"
echo "  API 模型名: $SERVED_NAME（config.yaml / --attack-model 请填此名）"
echo "  GPU: $CUDA_VISIBLE_DEVICES, 端口: $PORT, 张量并行: $TP_SIZE"
echo "若此为 LoRA 目录而非合并后的模型，请使用: VLLM_USE_LORA=1 ./scripts/ops/run_vllm.sh"
echo ""
exec vllm serve "$MODEL_PATH" \
    --served-model-name "$SERVED_NAME" \
    --host 0.0.0.0 \
    --port "$PORT" \
    --tensor-parallel-size "$TP_SIZE"
