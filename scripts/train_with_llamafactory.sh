#!/bin/bash
# Verilog攻击模型训练脚本 - LlamaFactory版本

set -e  # 出错时退出

# 颜色输出
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo "======================================================================"
echo "Verilog代码混淆攻击模型训练 - LlamaFactory"
echo "======================================================================"

# 配置
PROJECT_ROOT="/mnt/public/pqs/Veri_atack/project_up"
LLAMAFACTORY_PATH="${LLAMAFACTORY_PATH:-$HOME/LLaMA-Factory}"
CONFIG_TYPE="${1:-test}"  # test, lora, full
GPU_DEVICES="${2:-0,1,2,3}"  # 默认使用0,1,2,3四张卡

# 检查LlamaFactory
if [ ! -d "$LLAMAFACTORY_PATH" ]; then
    echo -e "${RED}❌ LlamaFactory未找到: $LLAMAFACTORY_PATH${NC}"
    echo "请设置环境变量: export LLAMAFACTORY_PATH=/path/to/LLaMA-Factory"
    echo "或安装LlamaFactory: git clone https://github.com/hiyouga/LLaMA-Factory.git"
    exit 1
fi

echo -e "${GREEN}✓${NC} LlamaFactory路径: $LLAMAFACTORY_PATH"

# 检查数据集
DATASET_FILE="$PROJECT_ROOT/data/llamafactory_attack_strategy.json"
if [ ! -f "$DATASET_FILE" ]; then
    echo -e "${YELLOW}⚠${NC}  数据集文件不存在，正在转换..."
    python3 "$PROJECT_ROOT/scripts/convert_to_llamafactory.py" \
        "$PROJECT_ROOT/data/sft_attack_strategy_cleaned.jsonl" \
        "$DATASET_FILE"
fi

echo -e "${GREEN}✓${NC} 数据集文件: $DATASET_FILE"

# 复制数据集到LlamaFactory
TARGET_FILE="$LLAMAFACTORY_PATH/data/verilog_attack_strategy.json"
if [ ! -f "$TARGET_FILE" ] || [ "$DATASET_FILE" -nt "$TARGET_FILE" ]; then
    echo -e "${YELLOW}⚠${NC}  复制数据集到LlamaFactory..."
    cp "$DATASET_FILE" "$TARGET_FILE"
    echo -e "${GREEN}✓${NC} 数据集已更新"
fi

# 注册数据集
echo -e "${YELLOW}⚠${NC}  检查数据集注册..."
DATASET_INFO="$LLAMAFACTORY_PATH/data/dataset_info.json"

# 检查是否已注册
if ! grep -q "verilog_attack_strategy" "$DATASET_INFO" 2>/dev/null; then
    echo -e "${YELLOW}⚠${NC}  注册数据集到dataset_info.json..."
    
    # 备份原文件
    cp "$DATASET_INFO" "${DATASET_INFO}.bak" 2>/dev/null || true
    
    # 使用Python添加配置
    python3 -c "
import json
dataset_info_path = '$DATASET_INFO'
try:
    with open(dataset_info_path, 'r') as f:
        data = json.load(f)
except:
    data = {}

data['verilog_attack_strategy'] = {
    'file_name': 'verilog_attack_strategy.json',
    'formatting': 'sharegpt',
    'columns': {'messages': 'messages'},
    'tags': {
        'role_tag': 'role',
        'content_tag': 'content',
        'user_tag': 'user',
        'assistant_tag': 'assistant',
        'system_tag': 'system'
    }
}

with open(dataset_info_path, 'w') as f:
    json.dump(data, f, indent=2, ensure_ascii=False)

print('✓ 数据集已注册')
"
fi

echo -e "${GREEN}✓${NC} 数据集注册完成"

# 选择配置文件
case "$CONFIG_TYPE" in
    test)
        CONFIG_FILE="$PROJECT_ROOT/configs/llamafactory/sft_attack_test.yaml"
        DESCRIPTION="快速测试 (1000样本, 1 epoch, ~15分钟)"
        ;;
    lora)
        CONFIG_FILE="$PROJECT_ROOT/configs/llamafactory/sft_attack_lora.yaml"
        DESCRIPTION="LoRA训练 (7598样本, 5 epochs, ~3-5小时)"
        ;;
    full)
        CONFIG_FILE="$PROJECT_ROOT/configs/llamafactory/sft_attack_full.yaml"
        DESCRIPTION="全参数训练 (7598样本, 3 epochs, ~4-6小时)"
        ;;
    *)
        echo -e "${RED}❌ 未知配置类型: $CONFIG_TYPE${NC}"
        echo "用法: $0 [test|lora|full] [GPU设备]"
        echo ""
        echo "示例:"
        echo "  $0 lora              # 使用默认GPU: 0,1,2,3"
        echo "  $0 lora 0,1          # 使用GPU 0,1"
        echo "  $0 lora 4,5,6,7      # 使用GPU 4,5,6,7"
        exit 1
        ;;
esac

echo ""
echo "======================================================================"
echo "训练配置"
echo "======================================================================"
echo "类型: $CONFIG_TYPE"
echo "描述: $DESCRIPTION"
echo "配置文件: $CONFIG_FILE"
echo "数据集: verilog_attack_strategy (7598 样本)"
echo "基础模型: /mnt/public/pqs/Model/Qwen2.5-Coder-7B/"
echo "GPU设备: $GPU_DEVICES"
echo "======================================================================"
echo ""

read -p "确认开始训练？[y/N] " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "训练已取消"
    exit 0
fi

# 切换到LlamaFactory目录
cd "$LLAMAFACTORY_PATH"

# 开始训练
echo ""
echo -e "${GREEN}🚀 开始训练...${NC}"
echo ""

# 设置GPU设备并训练
export CUDA_VISIBLE_DEVICES=$GPU_DEVICES
echo "使用GPU: $CUDA_VISIBLE_DEVICES"
echo ""

# 使用llamafactory-cli训练
llamafactory-cli train "$CONFIG_FILE"

echo ""
echo "======================================================================"
echo -e "${GREEN}✅ 训练完成！${NC}"
echo "======================================================================"
echo ""

# 显示保存路径
case "$CONFIG_TYPE" in
    test)
        SAVE_DIR="$PROJECT_ROOT/saves/attack_test"
        ;;
    lora)
        SAVE_DIR="$PROJECT_ROOT/saves/attack_lora_v1"
        echo "💡 LoRA模型已保存，需要合并权重:"
        echo "   llamafactory-cli export $PROJECT_ROOT/configs/llamafactory/sft_attack_lora_export.yaml"
        ;;
    full)
        SAVE_DIR="$PROJECT_ROOT/saves/attack_full_v1"
        ;;
esac

echo "模型保存路径: $SAVE_DIR"
echo ""
echo "下一步:"
if [ "$CONFIG_TYPE" = "lora" ]; then
    echo "  1. 合并LoRA权重（见上方命令）"
    echo "  2. 启动vLLM服务进行评估"
else
    echo "  1. 启动vLLM服务进行评估"
fi
