#!/bin/bash
# 对单规则攻击失败的样本进行多规则束搜索攻击

set -e

echo "======================================================================="
echo "多规则束搜索攻击 - 针对单规则失败样本"
echo "======================================================================="
echo ""

# 配置参数
FAILED_SAMPLES="data/single_rule_failed_samples.json"
OUTPUT="data/multi_rule_beam_search_attacks.json"
BEAM_WIDTH=3
MAX_DEPTH=3
LIMIT=100  # 先测试 100 个样本
MODEL_PORT=8001

echo "[1/4] 检查失败样本数据集..."
if [ ! -f "$FAILED_SAMPLES" ]; then
    echo "错误: 未找到失败样本文件: $FAILED_SAMPLES"
    echo "请先运行: python scripts/sft/extract_failed_samples.py"
    exit 1
fi

TOTAL_SAMPLES=$(python -c "import json; print(len(json.load(open('$FAILED_SAMPLES'))))")
echo "  失败样本总数: $TOTAL_SAMPLES"
echo "  本次处理: $LIMIT 个"
echo ""

echo "[2/4] 检查模型服务..."
if curl -s "http://localhost:$MODEL_PORT/v1/models" > /dev/null 2>&1; then
    echo "  ✓ 模型服务运行正常 (端口 $MODEL_PORT)"
else
    echo "  ✗ 模型服务未运行"
    echo ""
    echo "  请先启动模型服务:"
    echo "  CUDA_VISIBLE_DEVICES=1 python -m vllm.entrypoints.openai.api_server \\"
    echo "    --model /mnt/public/pqs/Model/Qwen2.5-Coder-7B/ \\"
    echo "    --port $MODEL_PORT \\"
    echo "    --served-model-name Qwen/Qwen2.5-Coder-7B-Instruct"
    exit 1
fi
echo ""

echo "[3/4] 运行束搜索攻击..."
echo "  配置:"
echo "    束宽度: $BEAM_WIDTH"
echo "    最大深度: $MAX_DEPTH"
echo "    样本数: $LIMIT"
echo ""

python scripts/sft/run_beam_search_attack.py \
    --dataset "$FAILED_SAMPLES" \
    --output "$OUTPUT" \
    --beam-width $BEAM_WIDTH \
    --max-depth $MAX_DEPTH \
    --limit $LIMIT \
    --base-url "http://localhost:$MODEL_PORT/v1" \
    --model "Qwen/Qwen2.5-Coder-7B-Instruct"

echo ""
echo "[4/4] 统计结果..."

if [ -f "$OUTPUT" ]; then
    python -c "
import json
with open('$OUTPUT') as f:
    data = json.load(f)

print(f'\n束搜索攻击统计:')
print(f'  处理样本数: $LIMIT')
print(f'  成功攻击数: {len(data)}')
if $LIMIT > 0:
    print(f'  成功率: {len(data) / $LIMIT * 100:.2f}%')

if data:
    depths = [d.get('search_depth', 0) for d in data]
    print(f'  平均深度: {sum(depths) / len(depths):.2f}')
    
    from collections import Counter
    depth_counts = Counter(depths)
    print(f'\n深度分布:')
    for depth in sorted(depth_counts.keys()):
        print(f'    深度 {depth}: {depth_counts[depth]} 个')
    
    all_rules = []
    for d in data:
        for step in d.get('attack_chain', []):
            all_rules.append(step.get('rule'))
    rule_counts = Counter(all_rules)
    print(f'\n最常用规则 (Top 5):')
    for rule, count in rule_counts.most_common(5):
        print(f'    {rule}: {count} 次')
"
else
    echo "警告: 输出文件不存在"
fi

echo ""
echo "======================================================================="
echo "完成！"
echo "======================================================================="
echo ""
echo "结果文件: $OUTPUT"
echo ""
echo "继续处理更多样本:"
echo "  # 处理 500 个"
echo "  LIMIT=500 bash $0"
echo ""
echo "  # 处理全部"
echo "  python scripts/sft/run_beam_search_attack.py \\"
echo "    --dataset $FAILED_SAMPLES \\"
echo "    --output data/multi_rule_attacks_full.json \\"
echo "    --beam-width 3 --max-depth 3"
echo ""
