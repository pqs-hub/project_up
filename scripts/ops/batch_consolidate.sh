#!/bin/bash
# 批量合并 legacy/rule_eval 目录中的零散 JSON 文件

set -e

BASE_DIR="legacy/rule_eval"
SCRIPT="scripts/ops/consolidate_json_files.py"

echo "========================================="
echo "批量合并 JSON 文件"
echo "========================================="
echo ""

# 统计需要处理的目录
total_dirs=$(find "$BASE_DIR" -type d -name "adv" -o -name "orig" -o -name "adv_eval" | wc -l)
echo "📂 找到 $total_dirs 个需要处理的目录"
echo ""

current=0

# 处理所有 adv 目录
for dir in $(find "$BASE_DIR" -type d \( -name "adv" -o -name "orig" -o -name "adv_eval" \)); do
    current=$((current + 1))
    
    # 检查是否有 JSON 文件
    json_count=$(find "$dir" -maxdepth 1 -name "*.json" | wc -l)
    
    if [ $json_count -le 1 ]; then
        echo "[$current/$total_dirs] ⏭️  跳过 $dir (只有 $json_count 个文件)"
        continue
    fi
    
    echo "[$current/$total_dirs] 🔄 处理 $dir ($json_count 个文件)"
    
    # 生成输出文件名
    parent_dir=$(dirname "$dir")
    dir_name=$(basename "$dir")
    output_file="$parent_dir/${dir_name}_consolidated.json"
    
    # 运行合并脚本
    python "$SCRIPT" "$dir" -o "$output_file" -d
    
    echo ""
done

echo "========================================="
echo "✅ 批量合并完成！"
echo "========================================="

# 统计结果
echo ""
echo "📊 统计信息："
echo "  - 合并前文件数: $(git diff --stat | grep 'delete mode' | wc -l)"
echo "  - 新增合并文件: $(git diff --stat | grep 'create mode' | wc -l)"
