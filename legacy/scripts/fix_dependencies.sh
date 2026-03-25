#!/bin/bash
# 修复依赖冲突

echo "=========================================="
echo "  修复 LLaMA-Factory 依赖冲突"
echo "=========================================="
echo

# 激活环境
source /data3/pengqingsong/software/miniconda3/etc/profile.d/conda.sh
conda activate hw_attack

echo "当前版本:"
echo "  transformers: $(pip show transformers | grep Version | awk '{print $2}')"
echo "  vllm: $(pip show vllm | grep Version | awk '{print $2}')"
echo

echo "🔧 升级 transformers..."
pip install --upgrade 'transformers>=4.56.0' --no-deps

echo
echo "✅ 升级完成！新版本:"
pip show transformers | grep Version

echo
echo "=========================================="
echo "  现在可以开始训练了！"
echo "=========================================="
echo
echo "运行命令:"
echo "  conda activate hw_attack"
echo "  cd /data3/pengqingsong/finetune/LLaMA-Factory"
echo "  llamafactory-cli train \\"
echo "      /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_test.yaml"
echo
