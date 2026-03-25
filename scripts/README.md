# `scripts/` 目录说明

所有命令均在**仓库根目录** `LLM_attack/` 下执行（`python scripts/...`）。

| 子目录 | 用途 | 典型入口 |
|--------|------|----------|
| **`sft/`** | 从 rule_eval 生成/整理 SFT | `sft/build_sft_from_rule_eval.py`、`normalize_sft_json_format.py`、`stats_sft_distribution.py`、`sample_sft_balanced.py` |
| **`eval/`** | 规则级批评估、ASR、判题校验 | `eval/evaluate_rules.py`、`eval_attack_success.py`、`compute_asr_from_evals.py`、`verify_adv_conf_vs_verdict.py`、`rule_applicator.py`、`textual_param_generator.py` |
| **`analysis/`** | 覆盖并集、难度分析、绘图、导出子集 | `union_attack_coverage.py`、`analyze_attack_success_difficulty.py`、`plot_rule_metrics_full_all.py`、`export_task_subset.py` |
| **`dataset/`** | 合格集转换、批量套规则、模块名归一 | `convert_qualified_to_dataset.py`、`apply_rule_on_dataset.py`、`normalize_module_names.py` |
| **`dev/`** | 维护/排障用小程序 | `merge_rules_report_with_backup.py`、`remove_invalid_attack_records.py`、`verify_line_signal_equiv.py` |
| **`ops/`** | Shell：归档、vLLM、LoRA 合并、训练启动 | `archive_rule_eval_legacy.sh`、`run_vllm.sh`、`merge_lora.sh`、`run_eval_attack_success.sh`、`run_sft_balanced500.sh`、`run_sft_eval_highquality.sh`（`sft_from_eval_highquality.jsonl`）、`run_sft.sh` |

更完整的命令与 `rule_eval` 数据说明见 [docs/CODEBASE_AND_USAGE.md](../docs/CODEBASE_AND_USAGE.md)。
