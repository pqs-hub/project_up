#\!/bin/bash
python3 scripts/experiments/attack_verilog_eval_cot.py \
    --dataset data/verilog_eval.json \
    --output-dir results/verilog_eval_cot_attack_v2 \
    --base-url http://localhost:8001/v1 \
    --model verilog_attack_merged_bal500 \
    --max-samples 10
