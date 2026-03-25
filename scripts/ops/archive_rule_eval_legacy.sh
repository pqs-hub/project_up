#!/usr/bin/env bash
# 将 rule_eval 下「非主用」子目录打成 tar.gz，便于腾出空间；默认不删除源目录。
#
# 主用（默认不打包）：
#   - metrics_conf_v2_on_fullall_adv/
#   - results_full_all_rules/   （你当前 SFT 用的带 params 的结果）
#   - orig_verdict_cache_conf_v2.json
#   - plots_metrics_conf_v2_fullall/
#   - union_asr 相关、orig 缓存、顶层 json/txt 报告
#
# 用法：
#   bash scripts/ops/archive_rule_eval_legacy.sh              # 仅小包：small / smoke / T19 迭代
#   bash scripts/ops/archive_rule_eval_legacy.sh --aggressive # 额外打包 results/、metrics/、metrics_conf_v2、metrics_full_all_rules 等
#   bash scripts/ops/archive_rule_eval_legacy.sh --dry-run    # 只打印将打包的路径
#   bash scripts/ops/archive_rule_eval_legacy.sh --quiet      # 不显示 pv/打点进度
#
# 进度：若已安装 pv，显示百分比与 ETA；否则 GNU tar 定期打印「.」；再否则静默 tar。
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
REV="${ROOT}/rule_eval"
ARCH="${REV}/_archives"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ARCH}/rule_eval_legacy_${TS}.tar.gz"

DRY=0
AGGRESSIVE=0
QUIET=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --aggressive) AGGRESSIVE=1 ;;
    --quiet) QUIET=1 ;;
    -h|--help)
      sed -n '1,30p' "$0"
      exit 0
      ;;
  esac
done

# 默认：实验/冒烟目录（体量相对小）
DEFAULT_DIRS=(
  metrics_small
  metrics_small2
  metrics_rerun_all_smoke
  results_rerun_all_smoke
  metrics_small_T19
  metrics_small_T19_v2
  metrics_small_T19_v3
  metrics_small_T19_v4
  metrics_small_T19_v5
  results_small
  results_small2
  results_small_T19
  results_small_T19_v2
  results_small_T19_v3
  results_small_T19_v4
  results_small_T19_v5
  plots_full_all_rules
)

# 激进：旧版全量 metrics / 与 results_full_all_rules 并存的另一套 results（体积大，确认后再用）
AGGRESSIVE_DIRS=(
  metrics
  metrics_conf_v2
  metrics_full_all_rules
  results
  plots_attack_difficulty
)

DIRS=("${DEFAULT_DIRS[@]}")
if [[ "$AGGRESSIVE" -eq 1 ]]; then
  DIRS+=("${AGGRESSIVE_DIRS[@]}")
fi

EXIST=()
for d in "${DIRS[@]}"; do
  p="${REV}/${d}"
  if [[ -e "$p" ]]; then
    EXIST+=("$d")
  fi
done

if [[ ${#EXIST[@]} -eq 0 ]]; then
  echo "未找到任何待归档路径（已清理过？）。rev=${REV}"
  exit 0
fi

echo "将打包下列目录/文件（相对于 rule_eval/）："
printf '  %s\n' "${EXIST[@]}"
echo "输出: ${OUT}"

if [[ "$DRY" -eq 1 ]]; then
  echo "[dry-run] 未创建压缩包。"
  exit 0
fi

mkdir -p "$ARCH"
cd "$REV"
# 使用相对路径打包，解压时在 rule_eval 同级或内部均可按说明展开
TOTAL=$(du -sb "${EXIST[@]}" | awk '{s+=$1} END {print s+0}')
if command -v numfmt >/dev/null 2>&1; then
  echo "待打包未压缩合计约: $(numfmt --to=iec-i --suffix=B "$TOTAL" 2>/dev/null || echo "${TOTAL} B")"
else
  echo "待打包未压缩合计约: ${TOTAL} 字节"
fi

if [[ "$QUIET" -eq 1 ]]; then
  tar -czf "$OUT" "${EXIST[@]}"
elif command -v pv >/dev/null 2>&1 && [[ "$TOTAL" -gt 1048576 ]]; then
  echo "使用 pv 显示进度（已读字节按未压缩 tarball 估算）…"
  tar -cf - "${EXIST[@]}" | pv -f -s "$TOTAL" -N 'pack' | gzip -1 > "$OUT"
elif tar --version 2>/dev/null | head -1 | grep -qi gnu; then
  echo "打包中（每约 5MB 数据打一个点）…"
  tar --checkpoint=10000 --checkpoint-action=ttyout='.' -czf "$OUT" "${EXIST[@]}"
  echo
else
  echo "打包中…"
  tar -czf "$OUT" "${EXIST[@]}"
fi

echo "完成: $(du -h "$OUT" | cut -f1)  $OUT"
echo ""
echo "请手动校验压缩包后，再删除原目录，例如："
echo "  tar -tzf \"$OUT\" | head"
echo "  # 确认无误后："
for d in "${EXIST[@]}"; do
  echo "  rm -rf \"${REV}/${d}\""
done
