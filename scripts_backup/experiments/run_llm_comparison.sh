#!/bin/bash
# 运行LLM参数生成对比实验

set -e

CONDA_ENV="/data3/pengqingsong/software/miniconda3/envs/hw_attack"
PROJECT_ROOT="/data3/pengqingsong/LLM_attack"

cd $PROJECT_ROOT

echo "============================================================"
echo "LLM参数生成方法对比实验"
echo "============================================================"
echo ""
echo "对比两种方法:"
echo "1. 历史感知LLM参数生成（已完成）"
echo "2. 独立LLM参数生成（即将运行）"
echo ""

# 检查历史感知实验结果是否存在
if [ ! -f "results/linked_llm_experiment/linked_results.jsonl" ]; then
    echo "❌ 错误: 未找到历史感知实验结果"
    echo "请先运行: python scripts/experiments/linked_combination_experiment.py"
    exit 1
fi

echo "✅ 历史感知实验结果已存在"
echo ""

# 运行独立LLM实验
echo "============================================================"
echo "步骤1: 运行独立LLM参数生成实验"
echo "============================================================"
echo ""

conda run -p $CONDA_ENV python scripts/experiments/independent_llm_experiment.py \
    --config config.yaml \
    --n-samples 50 \
    --output-dir results/independent_llm_experiment

echo ""
echo "✅ 独立LLM实验完成"
echo ""

# 对比分析
echo "============================================================"
echo "步骤2: 对比分析两种方法"
echo "============================================================"
echo ""

conda run -p $CONDA_ENV python scripts/experiments/compare_llm_methods.py \
    --linked results/linked_llm_experiment/linked_results.jsonl \
    --independent results/independent_llm_experiment/independent_results.jsonl \
    --output-dir results/llm_comparison

echo ""
echo "✅ 对比分析完成"
echo ""

# 显示结果
echo "============================================================"
echo "实验完成！"
echo "============================================================"
echo ""
echo "结果文件:"
echo "  - 历史感知: results/linked_llm_experiment/"
echo "  - 独立生成: results/independent_llm_experiment/"
echo "  - 对比分析: results/llm_comparison/"
echo ""
echo "可视化图表:"
echo "  - results/llm_comparison/llm_method_comparison.png"
echo ""
echo "详细报告:"
echo "  - results/llm_comparison/comparison_stats.json"
echo "  - results/llm_comparison/case_comparison.json"
echo ""
