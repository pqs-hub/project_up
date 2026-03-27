#!/bin/bash
# 完整的束搜索攻击工作流示例脚本
# 
# 用法:
#   bash scripts/sft/complete_beam_search_workflow.sh
#
# 前置条件:
#   1. 已安装所有依赖 (pip install -r requirements.txt)
#   2. 已安装 iverilog
#   3. 有可用的 GPU

set -e  # 遇到错误立即退出

# 配置参数
DATASET="data/qualified_dataset.json"
OUTPUT="data/beam_search_attacks.json"
SFT_OUTPUT="data/sft_beam_search.jsonl"
BEAM_WIDTH=3
MAX_DEPTH=3
LIMIT=100
MODEL_NAME="Qwen/Qwen2.5-Coder-7B-Instruct"
MODEL_PORT=8001

echo "======================================================================="
echo "束搜索攻击完整工作流"
echo "======================================================================="
echo ""

# 检查前置条件
echo "[1/6] 检查前置条件..."
echo ""

# 检查 Python
if ! command -v python &> /dev/null; then
    echo "错误: 未找到 Python"
    exit 1
fi
echo "✓ Python: $(python --version)"

# 检查 iverilog
if ! command -v iverilog &> /dev/null; then
    echo "错误: 未找到 iverilog，请安装:"
    echo "  Ubuntu/Debian: sudo apt-get install iverilog"
    echo "  macOS: brew install icarus-verilog"
    exit 1
fi
echo "✓ iverilog: $(iverilog -V | head -1)"

# 检查数据集
if [ ! -f "$DATASET" ]; then
    echo "警告: 数据集文件不存在: $DATASET"
    echo "请先准备数据集或修改脚本中的 DATASET 变量"
    exit 1
fi
echo "✓ 数据集: $DATASET"

echo ""
echo "======================================================================="
echo "[2/6] 启动目标模型服务..."
echo "======================================================================="
echo ""

# 检查模型服务是否已运行
if curl -s "http://localhost:$MODEL_PORT/v1/models" > /dev/null 2>&1; then
    echo "✓ 模型服务已在运行 (端口 $MODEL_PORT)"
else
    echo "启动 vLLM 服务..."
    echo "模型: $MODEL_NAME"
    echo "端口: $MODEL_PORT"
    echo ""
    
    # 在后台启动模型服务
    nohup python -m vllm.entrypoints.openai.api_server \
        --model "$MODEL_NAME" \
        --port $MODEL_PORT \
        --served-model-name "$MODEL_NAME" \
        > logs/vllm_server.log 2>&1 &
    
    VLLM_PID=$!
    echo "vLLM PID: $VLLM_PID"
    
    # 等待服务启动
    echo "等待服务启动..."
    MAX_WAIT=120
    WAIT_TIME=0
    while ! curl -s "http://localhost:$MODEL_PORT/v1/models" > /dev/null 2>&1; do
        sleep 5
        WAIT_TIME=$((WAIT_TIME + 5))
        if [ $WAIT_TIME -ge $MAX_WAIT ]; then
            echo "错误: 服务启动超时"
            kill $VLLM_PID 2>/dev/null || true
            exit 1
        fi
        echo "  等待中... ($WAIT_TIME/$MAX_WAIT 秒)"
    done
    
    echo "✓ 模型服务启动成功"
fi

echo ""
echo "======================================================================="
echo "[3/6] 运行束搜索攻击..."
echo "======================================================================="
echo ""
echo "配置:"
echo "  数据集: $DATASET"
echo "  输出: $OUTPUT"
echo "  束宽度: $BEAM_WIDTH"
echo "  最大深度: $MAX_DEPTH"
echo "  样本限制: $LIMIT"
echo ""

python scripts/sft/run_beam_search_attack.py \
    --dataset "$DATASET" \
    --output "$OUTPUT" \
    --beam-width $BEAM_WIDTH \
    --max-depth $MAX_DEPTH \
    --limit $LIMIT \
    --base-url "http://localhost:$MODEL_PORT/v1" \
    --model "$MODEL_NAME"

if [ $? -ne 0 ]; then
    echo "错误: 束搜索攻击失败"
    exit 1
fi

echo ""
echo "✓ 束搜索攻击完成"

echo ""
echo "======================================================================="
echo "[4/6] 统计结果..."
echo "======================================================================="
echo ""

if [ -f "$OUTPUT" ]; then
    python - <<EOF
import json
with open('$OUTPUT', 'r') as f:
    data = json.load(f)

print(f"总攻击数: {len(data)}")
if data:
    depths = [d['search_depth'] for d in data]
    print(f"平均深度: {sum(depths)/len(depths):.2f}")
    print(f"成功翻转: {sum(1 for d in data if d.get('verdict_flip', False))}")
    
    # 统计每个深度的数量
    from collections import Counter
    depth_counts = Counter(depths)
    print("\n深度分布:")
    for depth in sorted(depth_counts.keys()):
        print(f"  深度 {depth}: {depth_counts[depth]} 个")
    
    # 统计使用的规则
    all_rules = []
    for d in data:
        for step in d.get('attack_chain', []):
            all_rules.append(step.get('rule'))
    rule_counts = Counter(all_rules)
    print("\n最常用规则 (Top 5):")
    for rule, count in rule_counts.most_common(5):
        print(f"  {rule}: {count} 次")
EOF
else
    echo "警告: 输出文件不存在"
fi

echo ""
echo "======================================================================="
echo "[5/6] 转换为 SFT 格式（可选）..."
echo "======================================================================="
echo ""

if [ -f "pipeline/2_build_sft_dataset.py" ]; then
    echo "转换 $OUTPUT -> $SFT_OUTPUT"
    python pipeline/2_build_sft_dataset.py \
        --input "$OUTPUT" \
        --output "$SFT_OUTPUT" || {
        echo "警告: SFT 转换失败，跳过此步骤"
    }
    
    if [ -f "$SFT_OUTPUT" ]; then
        echo "✓ SFT 数据集已生成: $SFT_OUTPUT"
        echo "样本数: $(wc -l < $SFT_OUTPUT)"
    fi
else
    echo "跳过 SFT 转换（未找到转换脚本）"
fi

echo ""
echo "======================================================================="
echo "[6/6] 清理与总结"
echo "======================================================================="
echo ""

# 询问是否停止模型服务
if [ ! -z "$VLLM_PID" ]; then
    echo "模型服务 PID: $VLLM_PID"
    echo "是否停止模型服务? (y/N)"
    read -t 10 -r STOP_SERVICE || STOP_SERVICE="N"
    
    if [[ $STOP_SERVICE =~ ^[Yy]$ ]]; then
        echo "停止模型服务..."
        kill $VLLM_PID 2>/dev/null || true
        echo "✓ 服务已停止"
    else
        echo "保持模型服务运行"
    fi
fi

echo ""
echo "======================================================================="
echo "工作流完成！"
echo "======================================================================="
echo ""
echo "生成的文件:"
echo "  - 攻击数据: $OUTPUT"
if [ -f "$SFT_OUTPUT" ]; then
    echo "  - SFT 数据: $SFT_OUTPUT"
fi
echo ""
echo "下一步:"
echo "  1. 查看攻击结果:"
echo "     python -m json.tool $OUTPUT | less"
echo ""
echo "  2. 分析攻击模式:"
echo "     python scripts/analysis/analyze_attack_patterns.py --input $OUTPUT"
echo ""
echo "  3. 训练模型 (如果已生成 SFT 数据):"
echo "     llamafactory-cli train configs/llamafactory/sft_attack_lora.yaml"
echo ""
echo "======================================================================="
