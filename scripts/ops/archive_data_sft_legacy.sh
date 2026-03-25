#!/usr/bin/env bash
# 将 data/ 下「旧版 SFT / 中间 jsonl」打成 tar.gz（不删源文件）。
# 默认不打包 sft_from_eval_highquality.jsonl 与当前 manifest / distribution。
#
# 用法：
#   bash scripts/ops/archive_data_sft_legacy.sh
#   bash scripts/ops/archive_data_sft_legacy.sh --dry-run
#   bash scripts/ops/archive_data_sft_legacy.sh --quiet
#
# 进度：与 archive_rule_eval_legacy.sh 相同（pv / GNU tar 打点 / 静默）。
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DATA="${ROOT}/data"
ARCH="${DATA}/_archives"
TS="$(date +%Y%m%d_%H%M%S)"
OUT="${ARCH}/data_sft_legacy_${TS}.tar.gz"

DRY=0
QUIET=0
for a in "$@"; do
  case "$a" in
    --dry-run) DRY=1 ;;
    --quiet) QUIET=1 ;;
  esac
done

FILES=(
  sft_dataset_final.jsonl
  sft_dataset_balanced.jsonl
  sft_dataset_balanced_500.jsonl
  sft_dataset_balanced_uniform300.jsonl
  sft_dataset_balanced_uniform500.jsonl
  sft_dataset_supplemented.jsonl
  sft_from_eval_highquality_balanced.jsonl
  sft_from_eval_highquality_balanced_build.jsonl
  sft_from_eval_build_manifest_balanced.json
)

EXIST=()
for f in "${FILES[@]}"; do
  p="${DATA}/${f}"
  [[ -f "$p" ]] && EXIST+=("$f")
done

if [[ ${#EXIST[@]} -eq 0 ]]; then
  echo "未找到待归档的 data 文件。"
  exit 0
fi

echo "将打包（相对于 data/）："
printf '  %s\n' "${EXIST[@]}"
echo "输出: ${OUT}"
echo "未包含: sft_from_eval_highquality.jsonl、sft_from_eval_build_manifest.json、*_distribution.*（请自行决定是否再归档）"

if [[ "$DRY" -eq 1 ]]; then
  echo "[dry-run]"
  exit 0
fi

mkdir -p "$ARCH"
cd "$DATA"
TOTAL=0
for f in "${EXIST[@]}"; do
  [[ -f "$f" ]] && TOTAL=$((TOTAL + $(stat -c%s "$f" 2>/dev/null || echo 0)))
done
echo "待打包文件合计约: ${TOTAL} 字节"

if [[ "$QUIET" -eq 1 ]]; then
  tar -czf "$OUT" "${EXIST[@]}"
elif command -v pv >/dev/null 2>&1 && [[ "$TOTAL" -gt 1048576 ]]; then
  echo "使用 pv 显示进度…"
  tar -cf - "${EXIST[@]}" | pv -f -s "$TOTAL" -N 'pack' | gzip -1 > "$OUT"
elif tar --version 2>/dev/null | head -1 | grep -qi gnu; then
  echo "打包中…"
  tar --checkpoint=5000 --checkpoint-action=ttyout='.' -czf "$OUT" "${EXIST[@]}"
  echo
else
  tar -czf "$OUT" "${EXIST[@]}"
fi

echo "完成: $(du -h "$OUT" | cut -f1)  $OUT"
echo "校验: tar -tzf \"$OUT\" | head"
echo "确认无误后可删除原文件："
for f in "${EXIST[@]}"; do
  echo "  rm -f \"${DATA}/${f}\""
done
