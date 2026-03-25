#!/bin/bash
# 修复依赖冲突 - 正确版本

echo "=========================================="
echo "  修复 LLaMA-Factory 依赖冲突 (v2)"
echo "=========================================="
echo

# 激活环境
source /data3/pengqingsong/software/miniconda3/etc/profile.d/conda.sh
conda activate hw_attack

echo "当前版本:"
pip show transformers huggingface-hub vllm 2>/dev/null | grep -E "^Name:|^Version:"
echo

echo "问题分析:"
echo "  - vllm 0.17.0 需要: transformers<5,>=4.56.0"
echo "  - transformers 5.x 太新，与 vllm 不兼容"
echo "  - 需要安装 transformers 4.x 的最新版本"
echo

echo "🔧 修复步骤:"
echo "  1. 卸载 transformers 5.3.0"
echo "  2. 安装 transformers 4.47.1 (4.x 最新稳定版)"
echo "  3. 升级 huggingface-hub"
echo

# 安装兼容版本
echo "执行修复..."
pip install --upgrade \
    'transformers>=4.56.0,<5.0.0' \
    'huggingface-hub>=0.26.0' \
    --force-reinstall

echo
echo "✅ 修复完成！"
echo
echo "验证版本:"
pip show transformers huggingface-hub | grep -E "^Name:|^Version:"

echo
echo "=========================================="
echo "  现在可以开始训练了！"
echo "=========================================="
echo
