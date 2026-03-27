#!/bin/bash
# T19修复验证测试脚本

echo "================================"
echo "T19 修复效果测试"
echo "================================"
echo ""
echo "开始时间: $(date)"
echo ""

# 运行测试（10个样本，快速验证，4线程并行）
python pipeline/6_generate_attack_dataset.py \
  --eval-file data/qualified_dataset.json \
  --output data/test_t19_fixed.jsonl \
  --max-samples 10 \
  --rules T19 \
  --enable-llm-params \
  --attack-base-url http://localhost:8001/v1 \
  --attack-model Qwen2.5-Coder-7B \
  --workers 4 \
  --verbose

echo ""
echo "完成时间: $(date)"
echo ""

# 分析结果
if [ -f data/test_t19_fixed.jsonl ]; then
    echo "================================"
    echo "测试结果统计"
    echo "================================"
    
    total=$(wc -l < data/test_t19_fixed.jsonl)
    echo "总样本数: $total"
    
    # 统计有custom_dead_stmts的样本
    with_custom=$(grep -c '"custom_dead_stmts"' data/test_t19_fixed.jsonl || echo 0)
    echo "有custom_dead_stmts: $with_custom"
    
    if [ $total -gt 0 ]; then
        success_rate=$(python3 -c "print(f'{$with_custom/$total*100:.1f}%')")
        echo "LLM生成成功率: $success_rate"
        
        if [ $with_custom -gt 0 ]; then
            echo ""
            echo "LLM生成的内容示例:"
            grep '"custom_dead_stmts"' data/test_t19_fixed.jsonl | head -3 | \
              python3 -c "
import sys, json
for line in sys.stdin:
    data = json.loads(line)
    stmt = data['attack_params'].get('custom_dead_stmts', '')
    print(f'  - {stmt[:80]}')
"
        fi
    fi
    
    echo ""
    echo "✅ 测试完成！详细结果保存在: data/test_t19_fixed.jsonl"
else
    echo "❌ 测试失败，未生成输出文件"
fi
