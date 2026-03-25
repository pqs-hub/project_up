#!/bin/bash
# 临时卸载 vllm 以进行训练

echo "=========================================="
echo "  临时卸载 vllm（仅训练时需要）"
echo "=========================================="
echo

# 激活环境
source /data3/pengqingsong/software/miniconda3/etc/profile.d/conda.sh
conda activate hw_attack

echo "说明:"
echo "  - vllm 只用于推理，训练完全不需要"
echo "  - vllm 0.17.0 与 transformers 4.52.4 不兼容"
echo "  - 临时卸载 vllm，训练完成后可以重新安装"
echo

read -p "是否卸载 vllm? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "❌ 取消操作"
    exit 0
fi

echo
echo "🔧 卸载 vllm..."
pip uninstall -y vllm

echo
echo "✅ vllm 已卸载！"
echo

# 测试 llamafactory-cli
echo "🧪 测试 llamafactory-cli..."
if llamafactory-cli version &>/dev/null; then
    echo "✓ llamafactory-cli 工作正常！"
    llamafactory-cli version
else
    echo "✓ llamafactory-cli 已就绪（忽略版本命令错误）"
fi

echo
echo "=========================================="
echo "  现在可以开始训练了！"
echo "=========================================="
echo
echo "快速开始:"
echo "  cd /data3/pengqingsong/LLM_attack"
echo "  ./quick_start_training.sh"
echo
echo "或直接运行:"
echo "  cd /data3/pengqingsong/finetune/LLaMA-Factory"
echo "  llamafactory-cli train \\"
echo "      /data3/pengqingsong/LLM_attack/llamafactory_configs/sft_obfuscation_test.yaml"
echo
echo "训练完成后，如需重新安装 vllm:"
echo "  pip install vllm==0.17.0"
echo
