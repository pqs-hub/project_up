#!/bin/bash
# 评估训练后的混淆模型

set -e

echo "=========================================="
echo "  评估训练后的Verilog混淆模型"
echo "=========================================="
echo

# 激活环境
source /data3/pengqingsong/software/miniconda3/etc/profile.d/conda.sh
conda activate hw_attack

MODEL_PATH="/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged"
API_PORT=8002
API_LOG="$HOME/api_obfuscation_eval.log"
API_PID_FILE="/tmp/obfuscation_api.pid"

echo "Step 1: 启动API服务..."
echo "  模型路径: $MODEL_PATH"
echo "  API端口: $API_PORT"
echo

# 检查端口是否被占用
if lsof -Pi :$API_PORT -sTCP:LISTEN -t >/dev/null 2>&1; then
    echo "⚠️  端口 $API_PORT 已被占用"
    read -p "是否杀掉现有进程? (y/n): " confirm
    if [ "$confirm" = "y" ]; then
        lsof -ti:$API_PORT | xargs kill -9
        sleep 2
    else
        echo "❌ 评估已取消"
        exit 1
    fi
fi

# 使用vLLM启动API服务（更快）
echo "启动vLLM API服务..."
cd /data3/pengqingsong/LLM_attack

nohup python -m vllm.entrypoints.openai.api_server \
    --model $MODEL_PATH \
    --host 0.0.0.0 \
    --port $API_PORT \
    --tensor-parallel-size 1 \
    --gpu-memory-utilization 0.9 \
    --max-model-len 4096 \
    > $API_LOG 2>&1 &

API_PID=$!
echo $API_PID > $API_PID_FILE
echo "✓ API服务已启动 (PID: $API_PID)"
echo "  日志: $API_LOG"
echo

# 等待API服务就绪
echo "Step 2: 等待API服务启动..."
for i in {1..60}; do
    if curl -s http://localhost:$API_PORT/v1/models >/dev/null 2>&1; then
        echo "✓ API服务已就绪！"
        break
    fi
    if [ $i -eq 60 ]; then
        echo "❌ API服务启动超时"
        echo "查看日志: tail -100 $API_LOG"
        exit 1
    fi
    echo -n "."
    sleep 2
done
echo

# 显示可用模型
echo "可用模型:"
curl -s http://localhost:$API_PORT/v1/models | jq -r '.data[].id' || echo "  (请手动检查)"
echo

# 运行评估
echo "Step 3: 运行评估..."
echo "  评估文件: data/verilog_eval.json"
echo "  样本数: 100"
echo "  每个任务采样数: 5 (用于计算pass@1/3/5)"
echo

cd /data3/pengqingsong/LLM_attack

python scripts/eval/eval_attack_success.py \
    --eval-file data/verilog_eval.json \
    --attack-base-url http://localhost:$API_PORT/v1 \
    --attack-model $MODEL_PATH \
    --max-samples 100 \
    --n-per-task 5 \
    --temperature 0.7 \
    --output results/eval_finetuned_lora_$(date +%Y%m%d_%H%M%S).json \
    --save-success-examples results/eval_success_examples_$(date +%Y%m%d_%H%M%S).txt \
    --save-all-responses results/eval_all_responses_$(date +%Y%m%d_%H%M%S).jsonl \
    --verbose

echo
echo "=========================================="
echo "  ✅ 评估完成！"
echo "=========================================="
echo
echo "下一步:"
echo "  1. 查看评估结果: ls -lh results/eval_finetuned_lora_*.json"
echo "  2. 关闭API服务: kill $(cat $API_PID_FILE)"
echo "  3. 查看成功样例: cat results/eval_success_examples_*.txt | less"
echo
