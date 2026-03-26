#!/bin/bash
# 双模型评估脚本
# 攻击模型：训练后的LoRA合并模型
# 判断模型：原始基础模型

set -e

echo "========================================"
echo "  双模型评估启动脚本"
echo "========================================"

# 配置路径
ATTACK_MODEL_PATH="/mnt/public/pqs/Veri_atack/project_up/models"
JUDGE_MODEL_PATH="/mnt/public/pqs/Model/Qwen2.5-Coder-7B"
EVAL_DATA_PATH="/mnt/public/pqs/Veri_atack/project_up/data/verilog_eval.json"
RESULTS_DIR="/mnt/public/pqs/Veri_atack/project_up/results"

# 创建结果目录
mkdir -p "$RESULTS_DIR"

# 检查模型路径
if [ ! -d "$ATTACK_MODEL_PATH" ]; then
    echo "❌ 攻击模型不存在: $ATTACK_MODEL_PATH"
    exit 1
fi

if [ ! -d "$JUDGE_MODEL_PATH" ]; then
    echo "❌ 判断模型不存在: $JUDGE_MODEL_PATH"
    exit 1
fi

if [ ! -f "$EVAL_DATA_PATH" ]; then
    echo "❌ 评估数据不存在: $EVAL_DATA_PATH"
    exit 1
fi

echo "✅ 攻击模型: $ATTACK_MODEL_PATH"
echo "✅ 判断模型: $JUDGE_MODEL_PATH"
echo "✅ 评估数据: $EVAL_DATA_PATH"
echo ""

# 启动判断模型（基础模型）
echo "🚀 启动判断模型（基础模型，端口8001）..."
CUDA_VISIBLE_DEVICES=2,3 nohup python -m vllm.entrypoints.openai.api_server \
    --model "$JUDGE_MODEL_PATH" \
    --host 0.0.0.0 \
    --port 8001 \
    --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.9 \
    --max-model-len 4096 \
    --served-model-name "Qwen2.5-Coder-7B" \
    > "$RESULTS_DIR/judge_model.log" 2>&1 &
JUDGE_PID=$!
echo "判断模型PID: $JUDGE_PID"

# 等待判断模型启动
echo "⏳ 等待判断模型启动..."
sleep 30

# 测试判断模型连接
echo "🔍 测试判断模型连接..."
for i in {1..10}; do
    if curl -s http://localhost:8001/v1/models > /dev/null 2>&1; then
        echo "✅ 判断模型就绪"
        break
    else
        echo "⏳ 等待判断模型... ($i/10)"
        sleep 10
    fi
done

# 启动攻击模型（LoRA合并模型）
echo "🚀 启动攻击模型（LoRA合并模型，端口8002）..."
CUDA_VISIBLE_DEVICES=0,1 nohup python -m vllm.entrypoints.openai.api_server \
    --model "$ATTACK_MODEL_PATH" \
    --host 0.0.0.0 \
    --port 8002 \
    --tensor-parallel-size 2 \
    --gpu-memory-utilization 0.9 \
    --max-model-len 4096 \
    --served-model-name "obfuscation_merged" \
    > "$RESULTS_DIR/attack_model.log" 2>&1 &
ATTACK_PID=$!
echo "攻击模型PID: $ATTACK_PID"

# 等待攻击模型启动
echo "⏳ 等待攻击模型启动..."
sleep 30

# 测试攻击模型连接
echo "🔍 测试攻击模型连接..."
for i in {1..10}; do
    if curl -s http://localhost:8002/v1/models > /dev/null 2>&1; then
        echo "✅ 攻击模型就绪"
        break
    else
        echo "⏳ 等待攻击模型... ($i/10)"
        sleep 10
    fi
done

echo ""
echo "🎯 两个模型都已就绪，开始评估..."
echo ""

# 运行评估
timestamp=$(date +%Y%m%d_%H%M)
eval_output="$RESULTS_DIR/eval_${timestamp}.json"
success_examples="$RESULTS_DIR/success_examples_${timestamp}.txt"

python pipeline/5_evaluate_model.py \
    --eval-file "$EVAL_DATA_PATH" \
    --attack-base-url "http://localhost:8002/v1" \
    --attack-model "obfuscation_merged" \
    --max-samples 100 \
    --n-per-task 5 \
    --temperature 0.7 \
    --output "$eval_output" \
    --save-success-examples "$success_examples" \
    --verbose

echo ""
echo "🎉 评估完成！"
echo "📊 结果文件: $eval_output"
echo "📝 成功样例: $success_examples"
echo ""

# 清理选项
echo "是否停止vLLM服务？(y/n)"
read -r response
if [ "$response" = "y" ]; then
    echo "🛑 停止服务..."
    kill $JUDGE_PID $ATTACK_PID 2>/dev/null || true
    echo "✅ 服务已停止"
else
    echo "ℹ️  服务继续运行："
    echo "   判断模型: http://localhost:8001/v1 (PID: $JUDGE_PID)"
    echo "   攻击模型: http://localhost:8002/v1 (PID: $ATTACK_PID)"
    echo ""
    echo "停止命令："
    echo "   kill $JUDGE_PID $ATTACK_PID"
fi
