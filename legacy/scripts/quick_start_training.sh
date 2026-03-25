#!/bin/bash
# LLaMA-Factory 快速启动训练脚本

set -e

echo "=========================================="
echo "  Verilog代码混淆模型训练 - Quick Start"
echo "=========================================="
echo

# 激活 hw_attack 环境
echo "🔧 激活 hw_attack 环境..."
source /data3/pengqingsong/software/miniconda3/etc/profile.d/conda.sh
conda activate hw_attack

# 验证环境
if ! command -v llamafactory-cli &> /dev/null; then
    echo "❌ 错误: llamafactory-cli 未找到"
    echo "   请确保已安装 LLaMA-Factory: pip install llamafactory"
    exit 1
fi

echo "✓ llamafactory-cli: $(which llamafactory-cli)"
echo

# 检查LLaMA-Factory是否存在
LLAMAFACTORY_DIR="/data3/pengqingsong/finetune/LLaMA-Factory"
if [ ! -d "$LLAMAFACTORY_DIR" ]; then
    echo "❌ 错误: LLaMA-Factory目录不存在"
    echo "   路径: $LLAMAFACTORY_DIR"
    exit 1
fi

echo "✓ LLaMA-Factory目录: $LLAMAFACTORY_DIR"
echo

# 显示训练选项
echo "请选择训练配置:"
echo "  1) 快速测试 (1000样本, 1 epoch, ~15分钟) [推荐首次使用]"
echo "  2) LoRA训练 (37K样本, 5 epochs, ~3-5小时) [推荐显存<40GB]"
echo "  3) 全参数训练 (37K样本, 3 epochs, ~4-6小时) [推荐显存≥40GB]"
echo

read -p "请输入选项 (1/2/3): " choice

case $choice in
    1)
        CONFIG_FILE="sft_obfuscation_test.yaml"
        echo "✓ 选择: 快速测试"
        ;;
    2)
        CONFIG_FILE="sft_obfuscation_lora.yaml"
        echo "✓ 选择: LoRA训练"
        ;;
    3)
        CONFIG_FILE="sft_obfuscation_balanced.yaml"
        echo "✓ 选择: 全参数训练"
        ;;
    *)
        echo "❌ 无效选项"
        exit 1
        ;;
esac

CONFIG_PATH="/data3/pengqingsong/LLM_attack/llamafactory_configs/$CONFIG_FILE"

# 检查配置文件
if [ ! -f "$CONFIG_PATH" ]; then
    echo "❌ 配置文件不存在: $CONFIG_PATH"
    exit 1
fi

echo "✓ 配置文件: $CONFIG_PATH"
echo

# 显示配置详情
echo "=========================================="
echo "训练配置详情:"
echo "=========================================="
cat "$CONFIG_PATH" | grep -E "^(dataset|model_name_or_path|num_train_epochs|per_device_train_batch_size|learning_rate|output_dir|finetuning_type):" | sed 's/^/  /'
echo

# 确认开始训练
read -p "是否开始训练? (y/n): " confirm
if [ "$confirm" != "y" ]; then
    echo "❌ 训练已取消"
    exit 0
fi

echo
echo "=========================================="
echo "  开始训练..."
echo "=========================================="
echo

# 切换到LLaMA-Factory目录
cd "$LLAMAFACTORY_DIR"

# 运行训练
llamafactory-cli train "$CONFIG_PATH"

echo
echo "=========================================="
echo "  ✅ 训练完成！"
echo "=========================================="
echo
echo "下一步:"
echo "  1. 查看训练日志和loss曲线"
echo "  2. 测试模型效果"
echo "  3. 评估ASR提升"
echo
