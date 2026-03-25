# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`LLM_attack` is a Verilog adversarial-transformation and evaluation pipeline:

1. Start from qualified Verilog tasks (`data/qualified_dataset*.json`).
2. Apply semantic-preserving rule transforms (`Txx`) to generate adversarial RTL.
3. Evaluate model judgment on original vs adversarial code (`evaluate.py`, `scripts/eval/evaluate_rules.py`).
4. Build SFT data from `rule_eval` artifacts (`scripts/sft/build_sft_from_rule_eval.py`).

This repo is script- and artifact-driven (JSON inputs/outputs), not a package with a standard build/lint/test stack.

## Environment setup

Use one of:

```bash
conda env create -f environment.yml
conda activate hw_attack
```

or

```bash
pip install -r requirements.txt
```

Important deps: `pyslang`, `torch`, `transformers`, `openai`, `anthropic`, `PyYAML`, `tqdm`.

## Common commands

Run from repo root.

### 1) Evaluate existing attack results (`evaluate.py`)

```bash
python evaluate.py \
 --results <results_dir> \
 --dataset data/qualified_dataset.normalized.json \
 --output <output_dir> \
 --provider local \
 --model <model_name> \
 --base-url http://localhost:8001/v1 \
 --modes original adversarial \
 --repeat 1 \
 --progress
```

Quick subset run:

```bash
python evaluate.py ... --start 0 --end 100
```

### 2) Rule-wise batch evaluation (`scripts/eval/evaluate_rules.py`)

```bash
python scripts/eval/evaluate_rules.py \
 --rules T09 T10 T12 \
 --dataset data/qualified_dataset.json \
 --results-root rule_eval/results \
 --eval-output rule_eval/metrics \
 --provider local \
 --model Qwen2.5-Coder-7B \
 --base-url http://localhost:8000/v1 \
 --sample-limit 500 \
 --progress
```

Reuse existing adversarial files:

```bash
python scripts/eval/evaluate_rules.py ... --reuse-existing-adv --skip-clean-adv
```

### 3) Build high-quality SFT from rule-eval artifacts

```bash
python scripts/sft/build_sft_from_rule_eval.py \
 --metrics-root rule_eval/metrics_conf_v2_on_fullall_adv \
 --results-root rule_eval/results_full_all_rules \
 --orig-cache rule_eval/orig_verdict_cache_conf_v2.json \
 --union-report rule_eval/metrics_conf_v2_on_fullall_adv/union_asr_report.json \
 --uniform-max-per-rule 500 \
 --resolve-target-token \
 --output data/sft_from_eval_highquality.jsonl \
 --manifest data/sft_from_eval_build_manifest.json \
 --seed 42
```

### 4) SFT post-processing and stats

```bash
python scripts/sft/normalize_sft_json_format.py data/sft_from_eval_highquality.jsonl --no-backup
python scripts/sft/stats_sft_distribution.py --input data/sft_from_eval_highquality.jsonl
```

### 5) Analysis utilities

```bash
python scripts/analysis/union_attack_coverage.py <args>
python scripts/eval/compute_asr_from_evals.py <args>
python scripts/analysis/analyze_attack_success_difficulty.py <args>
```

### 6) Export a task subset for focused inspection

```bash
python scripts/analysis/export_task_subset.py \
 --task-list <task_ids.txt> \
 --dataset data/qualified_dataset.normalized.json \
 --out-dir data/unflipped_orig_pass_subset
```

### 7) Archive legacy large artifacts

```bash
bash scripts/ops/archive_rule_eval_legacy.sh --dry-run
bash scripts/ops/archive_rule_eval_legacy.sh
```

## “Run a single test” equivalent

There is no configured `pytest`/`unittest` suite in this repository.

Closest equivalents:
- small-slice `evaluate.py` using `--start/--end`
- small-slice `evaluate_rules.py` using `--sample-limit`

## High-level architecture

### Core runtime modules (root)

- `ast_transforms.2.py`: main transform engine and T-rule implementations (candidate finding, target resolution, code rewrite).
- `ast_transforms_loader.py`: loader wrapper for `ast_transforms.2.py`.
- `evaluate.py`: model-side evaluation (`clean` / `original` / `adversarial`) and per-task metric JSON writing.
- `simulator.py`: simulation interface used during evaluation.
- `primitives.py`: higher-level primitives (P1–P6) built on T-rules for experimental control spaces.

### Script layers (`scripts/`)

- `scripts/eval/`: batch rule evaluation + ASR helpers (`evaluate_rules.py` is primary entry).
- `scripts/sft/`: build/rebalance/normalize SFT data from rule-eval artifacts.
- `scripts/analysis/`: union coverage, attack difficulty, plotting, subset export.
- `scripts/dataset/`: qualified dataset conversion and module-name normalization.
- `scripts/ops/`: ops shell scripts (archive, vLLM helpers, training launch scripts).

### Data/artifact flow

1. qualified tasks -> `data/qualified_dataset(.normalized).json`
2. transformed code artifacts -> `rule_eval/results*/<rule>/adv/*.json`
3. evaluation artifacts -> `rule_eval/metrics*/<rule>/adv_eval/*.json`
4. original verdict cache -> `rule_eval/orig_verdict_cache*.json`
5. aggregate reports -> `*_report.json`, `union_asr_report.json`
6. SFT output -> `data/sft_*.jsonl`

### Critical coupling

- Keep `metrics-root`, `results-root`, and `orig-cache` from the same experiment family; mixing families breaks label consistency.
- Current mainline experiments are centered on `rule_eval/metrics_conf_v2_on_fullall_adv` + `rule_eval/orig_verdict_cache_conf_v2.json`.
- `target_line` / `target_signal` and `nth_occurrence` are equivalent candidate-index views in the engine, except ambiguous same-line/same-signal collisions (first match wins).

## Reference docs

- `README.md`
- `docs/CODEBASE_AND_USAGE.md`
- `docs/DATASETS_AND_METRICS.md`
- `scripts/README.md`

## Repository instruction files scan

No Cursor rules (`.cursor/rules/`, `.cursorrules`) and no Copilot instructions file (`.github/copilot-instructions.md`) were found.
