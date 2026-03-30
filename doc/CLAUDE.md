# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

This is a **Verilog obfuscation attack research framework** that trains LLMs to apply semantics-preserving code transformations to Verilog RTL in order to fool LLM-based hardware design verification models. The pipeline: generate adversarial Verilog samples → build SFT dataset → fine-tune (LoRA) a base model → evaluate attack success rate (ASR).

## Environment Setup

```bash
conda create -n hw_attack python=3.10
conda activate hw_attack
pip install -r requirements.txt
# GPU (CUDA): install PyTorch first:
# pip install torch --index-url https://download.pytorch.org/whl/cu118
```

External dependencies (not in requirements.txt):
- **iverilog / vvp** — Verilog simulation for testbench validation
- **LLaMA-Factory** — SFT training framework (installed separately)
- **vLLM** — for fast inference serving

## Key Commands

### Pipeline Entry Point

```bash
python main.py gpu                        # Check GPU status
python main.py attack --input <dataset> --output <dir>   # Step 1: Generate adversarial samples
python main.py build-sft --attacks <dir> --output <file> # Step 2: Build SFT dataset
python main.py train --dataset <file> --base-model <path> --gpus 0,1,2,3  # Step 3: Train
python main.py merge --lora <path> --base-model <path> --output <path>    # Step 4: Merge LoRA
python main.py eval --model <path> --eval-data <file> --output <file>     # Step 5: Evaluate
```

### vLLM Deployment

```bash
# Deploy model (reads model path from config.yaml by default)
./scripts/ops/run_vllm.sh [/path/to/merged/model]

# Manual: attack model on port 8002
CUDA_VISIBLE_DEVICES=0,1 python -m vllm.entrypoints.openai.api_server \
    --model <model_path> --port 8002 --tensor-parallel-size 2

# Manual: judge model on port 8001
CUDA_VISIBLE_DEVICES=2,3 python -m vllm.entrypoints.openai.api_server \
    --model <model_path> --port 8001 --tensor-parallel-size 2

# Test connectivity
curl http://localhost:8001/v1/models
curl http://localhost:8002/v1/models
```

### Training (LLaMA-Factory)

```bash
# SFT training via script (multi-GPU)
CUDA_VISIBLE_DEVICES=0,1,2,3 llamafactory-cli train configs/training/sft_obfuscation_lora.yaml

# Merge LoRA into base model (required before vLLM deployment)
./scripts/ops/merge_lora.sh [output_dir]
```

### Evaluation

```bash
# Full dual-model evaluation (starts both vLLM services automatically)
./scripts/eval/run_dual_model_eval.sh

# Evaluate trained attack model (vLLM services must be running first)
python pipeline/5_evaluate_model.py \
    --eval-file data/verilog_eval.json \
    --attack-base-url http://localhost:8002/v1 \
    --attack-model <served_model_name> \
    --max-samples 100 --n-per-task 5 --temperature 0.7 \
    --output results/eval.json --verbose

# Evaluate individual transformation rules
python scripts/eval/evaluate_rules.py \
    --rules T09 T10 T12 \
    --dataset data/qualified_dataset.json \
    --results-root rule_eval/results \
    --eval-output rule_eval/metrics \
    --provider local --model <model_name> --base-url http://localhost:8000/v1
```

### Per-step Pipeline Scripts

```bash
python pipeline/0_filter_correct_samples.py   # Pre-filter samples the judge model gets right
python pipeline/1_generate_attacks.py --input <dataset> --output <dir> [--rules T09 T10] [--max-samples N]
python pipeline/2_build_sft_dataset.py --attacks <dir> --output <file> [--balance]
python pipeline/4_merge_lora.py --lora <path> --base-model <path> --output <path>
python pipeline/5_evaluate_model.py ...       # See above
python pipeline/6_generate_attack_dataset_parallel.py  # Parallel version
python pipeline/7_analyze_attack_dataset.py   # Analysis of generated attacks
```

## Architecture

### Core Attack Framework (`core/`)

- **`core/transforms.py`** (loaded via `core/transform_loader.py`) — The central `VerilogObfuscationEngine` with `AST_TRANSFORM_REGISTRY` containing 15 active T-rules (T03, T07, T09, T10, T12, T19, T20, T30, T31, T32, T34, T41, T45, T47, T48). Each rule is a `Transform` object with `apply()` method. Uses `pyslang` for AST-based transformations, falls back to regex.
- **`core/primitives.py`** — Higher-level abstraction: 6 attack primitives (P1–P6) that each wrap multiple T-rules into a single parameterized interface. Used for RL/search-based attack strategies.
- **`core/param_generator.py`** — `AdversarialDatasetGenerator`: the main orchestrator class. Loads config, runs transform + testbench validation + LLM judge in parallel threads, produces JSONL training samples in Alpaca format.
- **`core/testbench.py`** — `TestbenchRunner`: wraps `iverilog`/`vvp` simulation. Compiles RTL + testbench, runs simulation, classifies as pass/fail based on FAIL/ERROR keywords in output.
- **`core/transform_loader.py`** — Dynamic loader that imports `core/transforms.py` and re-exports key symbols (`create_engine`, `VerilogObfuscationEngine`, `AST_TRANSFORM_REGISTRY`, etc.)

### Pipeline Steps (`pipeline/`)

Numbered scripts representing the full research pipeline:
1. `0_filter_correct_samples.py` — Filter dataset to samples the judge model answers correctly (these are "qualified" for attack)
2. `1_generate_attacks.py` — Apply T-rules to qualified samples, produce per-task attack result JSONs
3. `2_build_sft_dataset.py` — Collect attack-success records and format as Alpaca-style JSONL for SFT
4. `3_train_model.py` — Wrap LLaMA-Factory `llamafactory-cli train` (single or multi-GPU via torchrun)
5. `4_merge_lora.py` — Merge LoRA adapter into base model using LLaMA-Factory export
6. `5_evaluate_model.py` — Evaluate trained model ASR: generates obfuscated code via attack model, validates with testbench, judges with judge model; computes pass@1/3/5
7. `6_generate_attack_dataset_*.py` — Variants for parallel/exhaustive dataset generation

### Two-Model Evaluation Architecture

Evaluation requires two independently running vLLM services:
- **Attack model** (port 8002): The fine-tuned model that proposes obfuscation rules given a Verilog spec+RTL
- **Judge model** (port 8001): A base model (e.g., Qwen2.5-Coder-7B) that determines whether submitted RTL is functionally correct

Attack success = original RTL judged correct AND obfuscated RTL judged incorrect AND obfuscated RTL passes testbench.

### Configuration (`configs/config.yaml`)

Central config controls:
- `target_model`: base_url, model name (must match `--served-model-name` in vLLM), `use_local_transformers` toggle
- `sampling`: max attacks per sample, max positions/params per rule
- `testbench`: simulator (`iverilog` or `verilator`), timeout, filter_mode
- `parallelism.num_workers`: concurrent API request threads
- `data`: input/output paths, checkpoint path

### Data Flow

```
data/qualified_dataset.json (or qualified_samples.json)
  → pipeline/1 → per-task attack JSONs (RTL + transform metadata)
  → pipeline/2 → data/sft_attack_success_balanced.jsonl (Alpaca format)
  → LLaMA-Factory SFT → LoRA checkpoint
  → merge_lora → models/verilog_attack_merged_*
  → pipeline/5 (+ vLLM serving) → results/eval_*.json (ASR metrics)
```

### T-Rule Naming Conventions

Rules are referenced as `T<NN>` (e.g., T09, T34). The `TRANSFORM_REGISTRY` in `core/transforms.py` and `ATTACK_NAME_TO_TID` in `pipeline/5_evaluate_model.py` map between semantic names and T-IDs. The SFT training data uses semantic names (e.g., `misleading_comment`, `semantic_inversion_rename`); the evaluation script normalizes these back to T-IDs.

### Legacy & Scripts

- `legacy/` — Earlier experimental scripts, kept for reference but not part of the active pipeline
- `scripts/analysis/` — Post-hoc analysis of rule metrics, ASR, attack difficulty
- `scripts/sft/` — Dataset manipulation utilities (balance, normalize, sample)
- `scripts/ops/` — Operational scripts: deploy vLLM, run SFT, merge LoRA, consolidate outputs
- `scripts_backup/` — Older experiment scripts
