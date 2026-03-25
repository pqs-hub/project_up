#!/bin/bash
# 最终修复方案：安装 LLaMA-Factory 兼容版本

echo "=========================================="
echo "  LLaMA-Factory 依赖最终修复"
echo "=========================================="
echo

# 激活环境
source /data3/pengqingsong/software/miniconda3/etc/profile.d/conda.sh
conda activate hw_attack

echo "问题分析:"
echo "  - vllm 0.17.0 要求: transformers>=4.56.0"
echo "  - llamafactory 0.9.3 要求: transformers<=4.52.4"
echo "  - 两者冲突，无法同时满足"
echo
echo "解决方案:"
echo "  - 训练不需要 vllm（vllm 只用于推理）"
echo "  - 安装 llamafactory 要求的版本"
echo "  - transformers 4.52.4"
echo "  - numpy < 2.0.0"
echo

echo "🔧 执行修复..."

# 安装 llamafactory 要求的版本
pip install --force-reinstall \
    'transformers==4.52.4' \
    'numpy<2.0.0' \
    'tokenizers==0.21.1' \
    'fsspec<=2025.3.0'

echo
echo "✅ 安装完成！"
echo
echo "当前版本:"
pip show transformers numpy tokenizers | grep -E "^Name:|^Version:"

echo
echo "=========================================="
echo "  现在可以开始训练了！"
echo "=========================================="
echo
echo "注意:"
echo "  - vllm 的警告可以忽略（训练不需要 vllm）"
echo "  - 如果遇到 vllm 相关错误，可以考虑卸载 vllm"
echo
