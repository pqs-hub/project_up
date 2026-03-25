#!/usr/bin/env bash
# 使用 eval_attack_success.py 评估训练好的攻击模型（合并后的 verilog_attack_merged_bal500）
#
# 前置条件：
#   1. 已合并 LoRA：models/verilog_attack_merged_bal500（或先执行 ./scripts/ops/merge_lora.sh）
#   2. 已启动 vLLM 服务该模型：./scripts/ops/run_vllm.sh /path/to/verilog_attack_merged_bal500
#   3. config.yaml 中 target_model 指向该 vLLM（base_url + model 与 vLLM 一致）
#
# 用法：
#   ./scripts/ops/run_eval_attack_success.sh                    # 全量评估，结果写 results/eval_attack_success.json
#   ./scripts/ops/run_eval_attack_success.sh --max-samples 10    # 仅评估前 10 条（快速验证）
#   SAVE_ALL_RESPONSES=1 ./scripts/ops/run_eval_attack_success.sh  # 同时把每条模型输出记录到 data/eval_all_responses.jsonl
#   ./scripts/ops/run_eval_attack_success.sh --save-all-responses data/my_responses.jsonl  # 指定记录文件

set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/../.." && pwd)"
cd "$PROJECT_DIR"

# 第一个参数若以 -- 开头则全部当作传给 python 的额外参数，否则视为可选模型路径
if [[ -n "$1" && "$1" != --* ]]; then
    MERGED_MODEL="$1"
    shift || true
fi
MERGED_MODEL="${MERGED_MODEL:-/data3/pengqingsong/LLM_attack/models/verilog_attack_merged_bal500}"
EXTRA_ARGS=("$@")

# 与 run_vllm.sh 中 VLLM_SERVED_MODEL_NAME 一致，请求时 model 参数用此短名（避免 404）
ATTACK_MODEL="${ATTACK_MODEL_NAME:-verilog_attack_merged_bal500}"
ATTACK_BASE_URL="${ATTACK_BASE_URL:-http://localhost:8001/v1}"
EVAL_FILE="${EVAL_FILE:-$PROJECT_DIR/data/verilog_eval.json}"
OUTPUT="${OUTPUT:-$PROJECT_DIR/results/eval_attack_success.json}"

echo "评估脚本: scripts/eval/eval_attack_success.py"
echo "攻击模型: $ATTACK_MODEL"
echo "API 地址: $ATTACK_BASE_URL"
echo "评估数据: $EVAL_FILE"
echo "结果输出: $OUTPUT"
echo "请确认已启动 vLLM 且 API 模型名为 $ATTACK_MODEL: ./scripts/ops/run_vllm.sh $MERGED_MODEL"
echo ""

mkdir -p "$(dirname "$OUTPUT")"
SAVE_ALL_ARGS=()
if [[ -n "${SAVE_ALL_RESPONSES:-}" ]]; then
  SAVE_ALL_ARGS=(--save-all-responses "${SAVE_ALL_RESPONSES_PATH:-$PROJECT_DIR/data/eval_all_responses.jsonl}")
  echo "将记录所有模型输出到: ${SAVE_ALL_ARGS[1]}"
fi
python scripts/eval/eval_attack_success.py \
    --eval-file "$EVAL_FILE" \
    --attack-base-url "$ATTACK_BASE_URL" \
    --attack-model "$ATTACK_MODEL" \
    --output "$OUTPUT" \
    --n-per-task 10 \
    --temperature 0.7 \
    --save-success-examples "$PROJECT_DIR/data/eval_success_examples.txt" \
    --max-success-examples 30 \
    "${SAVE_ALL_ARGS[@]}" \
    "${EXTRA_ARGS[@]}"
