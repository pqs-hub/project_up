#!/bin/bash
# 快速启动协同效应验证实验

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 项目根目录
PROJECT_ROOT="/data3/pengqingsong/LLM_attack"
cd "$PROJECT_ROOT"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}规则组合协同效应验证实验 - 快速启动${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 检查环境
echo -e "${YELLOW}[1/5] 检查环境...${NC}"

# 检查Python
if ! command -v python &> /dev/null; then
    echo -e "${RED}错误: Python未安装${NC}"
    exit 1
fi
echo -e "${GREEN}✓ Python已安装${NC}"

# 检查iverilog
if ! command -v iverilog &> /dev/null; then
    echo -e "${YELLOW}警告: iverilog未安装，Testbench验证将被跳过${NC}"
else
    echo -e "${GREEN}✓ iverilog已安装${NC}"
fi

# 检查vLLM
echo -e "${YELLOW}[2/5] 检查vLLM服务...${NC}"
if curl -s http://localhost:8001/v1/models > /dev/null 2>&1; then
    echo -e "${GREEN}✓ vLLM服务正常运行${NC}"
else
    echo -e "${RED}错误: vLLM服务未运行${NC}"
    echo -e "${YELLOW}请先启动vLLM: bash scripts/ops/run_vllm.sh${NC}"
    exit 1
fi

# 创建必要目录
echo -e "${YELLOW}[3/5] 创建输出目录...${NC}"
mkdir -p logs
mkdir -p results/synergy_experiments
mkdir -p results/synergy_experiments/analysis
echo -e "${GREEN}✓ 目录已创建${NC}"

# 选择实验模式
echo ""
echo -e "${BLUE}请选择实验模式:${NC}"
echo "  1) 核心验证 (3场景 × 4模块 = 12测试, 约10-20分钟)"
echo "  2) 完整实验 (6场景 × 20模块 = 120测试, 约1-2小时)"
echo "  3) 自定义实验"
echo ""
read -p "请输入选项 [1-3]: " mode_choice

case $mode_choice in
    1)
        MODE="core"
        echo -e "${GREEN}已选择: 核心验证模式${NC}"
        ;;
    2)
        MODE="full"
        echo -e "${YELLOW}警告: 完整实验将耗时较长${NC}"
        read -p "确认继续? (y/n): " confirm
        if [ "$confirm" != "y" ]; then
            echo "已取消"
            exit 0
        fi
        ;;
    3)
        MODE="custom"
        echo -e "${BLUE}自定义模式${NC}"
        echo "可用场景: signal_affinity, distractor_payload, semantic_hijacking,"
        echo "          enhanced_affinity, logic_confusion, deep_distractor"
        read -p "请输入场景（逗号分隔）: " scenarios
        
        echo "可用模块类型: counter, state_machine, alu, mux"
        read -p "请输入模块类型（逗号分隔）: " modules
        
        CUSTOM_ARGS="--scenarios $scenarios --module-types $modules"
        ;;
    *)
        echo -e "${RED}无效选项${NC}"
        exit 1
        ;;
esac

# 运行实验
echo ""
echo -e "${YELLOW}[4/5] 运行实验...${NC}"
echo -e "${BLUE}========================================${NC}"

if [ "$MODE" = "custom" ]; then
    python scripts/experiments/run_synergy_experiment.py \
        --mode custom \
        $CUSTOM_ARGS \
        --config config.yaml \
        --output-dir results/synergy_experiments \
        --verbose
else
    python scripts/experiments/run_synergy_experiment.py \
        --mode $MODE \
        --config config.yaml \
        --output-dir results/synergy_experiments \
        --verbose
fi

EXPERIMENT_STATUS=$?

if [ $EXPERIMENT_STATUS -ne 0 ]; then
    echo -e "${RED}实验执行失败${NC}"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}✓ 实验完成${NC}"

# 分析结果
echo ""
echo -e "${YELLOW}[5/5] 分析结果...${NC}"

RESULTS_FILE="results/synergy_experiments/experiment_results.jsonl"

if [ ! -f "$RESULTS_FILE" ]; then
    echo -e "${RED}错误: 结果文件不存在${NC}"
    exit 1
fi

# 生成所有分析输出
python scripts/experiments/analyze_synergy_results.py \
    "$RESULTS_FILE" \
    --output-dir results/synergy_experiments/analysis \
    --all

echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}实验完成！${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${GREEN}输出文件:${NC}"
echo "  - 详细结果: $RESULTS_FILE"
echo "  - 汇总报告: results/synergy_experiments/experiment_report.json"
echo "  - LaTeX表格: results/synergy_experiments/analysis/results_table.tex"
echo "  - Markdown表格: results/synergy_experiments/analysis/results_table.md"
echo "  - ASR对比图: results/synergy_experiments/analysis/synergy_comparison.png"
echo "  - 置信度图: results/synergy_experiments/analysis/confidence_drop.png"
echo "  - 统计摘要: results/synergy_experiments/analysis/statistical_summary.json"
echo ""
echo -e "${BLUE}查看详细结果:${NC}"
echo "  cat results/synergy_experiments/analysis/results_table.md"
echo ""
echo -e "${BLUE}查看统计摘要:${NC}"
echo "  cat results/synergy_experiments/analysis/statistical_summary.json"
echo ""
