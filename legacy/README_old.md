# LLM_attack

对 Verilog 做语义保持的结构变换，评测 LLM 在对抗代码上的稳健性；支持规则级批评估、ASR 统计与 **从 `rule_eval` 产物离线生成 SFT**。

## 文档

- **[代码结构、`rule_eval` 数据说明与常用命令](docs/CODEBASE_AND_USAGE.md)** ← 日常从这里开始  
- [按用途分类的 `scripts/` 索引](scripts/README.md)  
- [数据集与指标（人类可读）](docs/DATASETS_AND_METRICS.md)  
- [面向 AI 助手的开发说明](CLAUDE.md)

## 最短路径：生成当前主用 SFT

```bash
cd /data3/pengqingsong/LLM_attack
python scripts/sft/build_sft_from_rule_eval.py \
  --metrics-root rule_eval/metrics_conf_v2_on_fullall_adv \
  --results-root rule_eval/results_full_all_rules \
  --uniform-max-per-rule 500 \
  --output data/sft_from_eval_highquality.jsonl
```

默认已做 **每规则 uniform cap + equalize-to-min**（各规则条数拉齐）。若要旧版 Head/Tail 不同上限（易不均匀），加 `--legacy-head-tail-caps`。是否与 `metrics` 同源、是否加 `--resolve-target-token` 等见 `docs/CODEBASE_AND_USAGE.md`。

## 依赖与评测

核心依赖含 **pyslang**、`evaluate.py` 所选 provider 的 SDK。判题与仿真细节见 `CLAUDE.md` 与 `evaluate.py --help`。
