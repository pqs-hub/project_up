# 代码库结构说明与常用命令

本文说明仓库目录职责、`rule_eval/` 下各数据集的重要性，以及日常会用到的命令。更细的指标与数据集定义见 [DATASETS_AND_METRICS.md](./DATASETS_AND_METRICS.md)。

---

## 1. 项目在做什么（一条线）

1. **合格题目与 RTL**：`data/qualified_dataset.normalized.json`（`task_id`、`prompt`、`canonical_solution`）。
2. **变换引擎**：`ast_transforms.2.py`（经 `ast_transforms_loader.py` 加载）对 RTL 施加规则 `Txx`，得到对抗代码。
3. **判题**：`evaluate.py` 调用本地/云端 LLM 判断「代码是否符合规格」，配合 `simulator.py` 等；规则级批跑见 `scripts/eval/evaluate_rules.py`。
4. **产物**：变换结果在 `rule_eval/results*`；判题结果在 `rule_eval/metrics*` 与缓存 JSON；高质量 SFT 由 `scripts/sft/build_sft_from_rule_eval.py` 从上述产物离线拼接。

---

## 2. 目录结构（心智模型）

```
LLM_attack/
├── ast_transforms.2.py      # 核心：各 T 规则实现 + VerilogObfuscationEngine
├── ast_transforms_loader.py # 加载 ast_transforms.2（文件名含点无法直接 import）
├── evaluate.py              # 单次/批量判题（OpenAI/Anthropic/本地 vLLM 等）
├── primitives.py            # P1–P6 高层原语（当前主流程较少直接 import，偏扩展/实验）
├── simulator.py             # evaluate 侧仿真接口
├── Testbench_valid.py       # testbench 跑通验证（生成/补缺样本等脚本会用）
├── AttackConfigGenerator.py # 攻击配置（与 generate_missing_rules_verified 等配合）
├── taget_model.py           # 目标模型客户端（拼写历史原因）
├── filter_qualified.py      # 筛合格样本 → 可接 qualified 数据集流水线
├── generate_dataset.py      # 旧版数据集生成入口（若已全面用 qualified + rule_eval，可视为备用）
├── generate_missing_rules_verified.py / replace_targeted_rules_verified.py
│                            # 按规则补缺、替换验证
├── data/
│   ├── qualified_dataset.normalized.json   # 主数据集（训练/SFT/评估入口）
│   ├── filter_and_convert_sft.py           # SFT 格式：INSTRUCTION、build_sft_sample、SEMANTIC_NAMES
│   └── …                                   # 其它 jsonl、子集目录
├── scripts/                 # 工具脚本按用途分子目录（见 scripts/README.md）
│   ├── sft/               # SFT 生成、归一化、统计、均衡
│   ├── eval/              # evaluate_rules、ASR 计算、判题一致性检查
│   ├── analysis/          # 覆盖并集、难度、绘图、导出子集
│   ├── dataset/           # qualified→dataset、模块名归一、批量套规则
│   ├── dev/               # 报告合并备份、等价性检查等
│   └── ops/               # shell：vLLM、LoRA 合并、归档、训练入口
├── rule_eval/               # 评估产物根目录（体积大，见下一节）
└── docs/
    ├── CODEBASE_AND_USAGE.md # 本文件
    └── DATASETS_AND_METRICS.md
```

**原则**：核心引擎与 `evaluate.py` 在根目录是历史布局；**新脚本按类别放入 `scripts/<sft|eval|analysis|dataset|dev|ops>/`**。

---

## 3. `rule_eval/` 里都是什么？重要吗？

| 路径 / 文件 | 作用 | 建议 |
|-------------|------|------|
| **`metrics_conf_v2_on_fullall_adv/`** | 各规则 `Txx/adv_eval/*_rep0.json`：对抗码判题结果（`adversarial_passed`、置信等）；**SFT 与 ASR 报告依赖** | **必须保留**（与当前论文/主实验一致时） |
| **`results_full_all_rules/`** | 各规则 `Txx/adv/*.json`：`final`、`params_used`（文本类规则的大模型参数）等 | **做带参 SFT 时保留**；与 metrics 需同源判题才严谨 |
| **`results/`** | 另一套变换落盘结果（常与早期或不同批评估对应） | 若已只用 `results_full_all_rules` 且磁盘紧，可 **`--aggressive` 归档后删除**（先打 tar） |
| **`metrics/`、`metrics_conf_v2/`、`metrics_full_all_rules/`** | 旧版或并行实验 metrics | 一般 **不如 `metrics_conf_v2_on_fullall_adv` 关键**；确认不用后可归档删除 |
| **`orig_verdict_cache_conf_v2.json`** | 原始 RTL 判题缓存（`original_passed` 等） | **与 SFT join 必须一致**；`union_asr_report.json` 里 `cache_key_used` 应对齐 |
| **`orig_verdict_cache.json`** | 旧缓存 | 仅当无脚本引用时可删 |
| **`plots_metrics_conf_v2_fullall/`** | 图表输出 | 可再生成则非必须长期保留 |
| **`plots_attack_difficulty/`**、`**attack_difficulty_report*.json** | 难度/分析报告 | 论文要用的图/表则保留 |
| **`_archives/`** | 你已打包的实验目录 | **备份**，勿删除非确认无需恢复 |
| **`unflipped_orig_pass_tasks.txt`** | 任务列表辅助分析 | 按需 |

**结论**：对你当前「高质量 SFT + conf_v2 全量 ASR」主线，**最重要的是**  
`metrics_conf_v2_on_fullall_adv` + **`orig_verdict_cache_conf_v2.json`（正确 cache_key）** + 与判题**同源**的 **`results` 或 `results_full_all_rules` 二选一（不要混用口径）**。其余多为历史或重复实验，可归档。

---

## 4. 常用命令（在仓库根目录执行）

### 4.1 环境与路径

```bash
cd /data3/pengqingsong/LLM_attack
# Python 环境里需已安装：pyslang、evaluate 所用 API 客户端等（见 CLAUDE.md）
```

### 4.2 从全量评估产物生成 SFT（当前推荐）

```bash
# 与 ASR 一致 + 带参 results；默认均衡（uniform cap + equalize-to-min）+ 补全 target（慢）
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

- **默认**：每条规则先随机保留至多 `--uniform-max-per-rule`，再 **equalize-to-min**（各规则条数拉齐到当前池中的最小值，使 `attack_name` 均匀）。仅保留 uniform、不要截齐时加 `--no-equalize-to-min`。
- **旧行为**（Head 规则高 cap、Tail 低 cap，分布易偏）：加 `--legacy-head-tail-caps`；若仍想最后拉齐，可再加 `--equalize-to-min`。
- 若 **metrics 与 `results/` 同源**而非 `results_full_all_rules`，把 `--results-root` 改成 `rule_eval/results`。
- 不想枚举 `target_token`（快）：去掉 `--resolve-target-token`；或重跑 `evaluate_rules` 写盘 `target_line`/`target_token`。

### 4.3 SFT 后处理与统计

```bash
python scripts/sft/normalize_sft_json_format.py data/sft_from_eval_highquality.jsonl --no-backup
python scripts/sft/stats_sft_distribution.py --input data/sft_from_eval_highquality.jsonl
# 可选：再均衡（默认构建已 equalize-to-min 时通常可省略）
python scripts/sft/sample_sft_balanced.py --input data/sft_from_eval_highquality.jsonl \
  --output data/sft_balanced.jsonl --max-per-rule 500 --seed 42
```

### 4.4 规则级评估（生成 `results/` + `metrics/`）

```bash
python scripts/eval/evaluate_rules.py  # 按脚本内 argparse 传 dataset、规则列表、API 等
```

写盘字段包含：`final`、`params_used`、`target_token`、`target_line`、`target_signal`（以当前脚本版本为准）。

### 4.5 单次判题（`evaluate.py`）

```bash
python evaluate.py --dataset data/qualified_dataset.normalized.json \
  --provider local --model <模型名> --base-url http://localhost:8001/v1 \
  --output <输出目录> ...
# 具体参数见 evaluate.py --help
```

### 4.6 分析与 ASR / 覆盖

```bash
python scripts/analysis/union_attack_coverage.py        # 视脚本内说明传参
python scripts/eval/compute_asr_from_evals.py
python scripts/analysis/analyze_attack_success_difficulty.py
```

### 4.7 归档旧实验数据（带进度）

```bash
bash scripts/ops/archive_rule_eval_legacy.sh --dry-run
bash scripts/ops/archive_rule_eval_legacy.sh
# 大块旧 results/metrics：确认后再
bash scripts/ops/archive_rule_eval_legacy.sh --aggressive --dry-run
bash scripts/ops/archive_rule_eval_legacy.sh --aggressive

bash scripts/ops/archive_data_sft_legacy.sh --dry-run
bash scripts/ops/archive_data_sft_legacy.sh
```

（安装 `pv` 后大包可见进度条：`sudo apt install pv`。）

### 4.8 合格集与转换

```bash
python scripts/dataset/convert_qualified_to_dataset.py   # 按需
python filter_qualified.py                       # 见脚本说明
```

---

## 5. 给后续自己的备忘

- **改规则**：主要改 `ast_transforms.2.py`，用 `transform_validator.py`（若存在）或单测思路做语法/仿真验证。
- **改 SFT 格式**：改 `data/filter_and_convert_sft.py` 中 `INSTRUCTION`、`build_sft_sample`、`SEMANTIC_NAMES`。
- **AI 助手上下文**：根目录 `CLAUDE.md` 面向 Cursor/Claude Code；人类完整指标说明在 `docs/DATASETS_AND_METRICS.md`。

---

*文档版本：与仓库当前布局一致；若你移动或删除 `rule_eval` 子目录，请同步更新本节路径说明。*
