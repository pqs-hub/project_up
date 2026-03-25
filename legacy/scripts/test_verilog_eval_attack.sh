#!/bin/bash
# 测试verilog_eval攻击脚本（使用少量样本）

echo "测试verilog_eval攻击脚本..."

python3 scripts/experiments/attack_verilog_eval_cot.py \
    --dataset /data3/pengqingsong/LLM_attack/data/verilog_eval.json \
    --base-url http://localhost:8001/v1 \
    --model verilog_attack_merged_bal500 \
    --output-dir results/verilog_eval_cot_attack \
    --max-samples 10

echo "测试完成！查看结果："
echo "  详细结果: results/verilog_eval_cot_attack/attack_results_cot.jsonl"
echo "  统计报告: results/verilog_eval_cot_attack/attack_report_cot.json"
