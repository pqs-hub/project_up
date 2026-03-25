# 数据集与评估指标说明

本文档记录 **LLM_attack** 仓库中主要 **数据集的生成方式**、**文件格式** 以及 **规则评估 / 并集统计** 等指标含义，便于日后复现与写论文时查阅。

> **更新建议**：若你改了筛选条件、换模型重跑评估或新增数据文件，请在对应小节补一行「日期 + 变更说明」。

---

## 1. 总览：数据从哪来到哪去

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 原始 Verilog 题库（JSON 列表，字段因来源而异）                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
                    python filter_qualified.py  （config.yaml: data.input_path）
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ data/qualified_samples.json — 经目标模型判定「理解正确」的样本 + verdict   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
              scripts/dataset/convert_qualified_to_dataset.py
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ data/qualified_dataset.json — evaluate / 规则评估使用的标准 dataset 格式   │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
              scripts/dataset/normalize_module_names.py（可选但评估前推荐）
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│ data/qualified_dataset.normalized.json — RTL 模块名与 TB 中 dut 实例一致   │
└─────────────────────────────────────────────────────────────────────────┘
         │                                    │
         │                                    │
         ▼                                    ▼
  scripts/eval/evaluate_rules.py          generate_dataset.py
  + evaluate.py                      + AdversarialDatasetGenerator
         │                                    │
         ▼                                    ▼
  rule_eval/results*/ & metrics*/     data/adversarial_dataset*.jsonl
                                    data/filtered_* → SFT jsonl
```

---

## 2. 各数据集文件说明

### 2.1 `data/qualified_samples.json`

| 项目 | 说明 |
|------|------|
| **生成** | `filter_qualified.py` |
| **输入** | `config.yaml` → `data.input_path` 指向的 JSON 样本列表 |
| **逻辑** | 用目标模型（本地 transformers 或 API）对每条样本做「是否理解规格/代码」类判定；输出中需包含明确 **yes** 且不能主导为 **no** 的才保留；可选从 `logprobs` 解析置信度写入 `original_verdict` |
| **断点** | `data/qualified_filter_checkpoint.json`，跑完后会删除 |
| **用途** | 中间产物，再转为标准 dataset |

### 2.2 `data/qualified_dataset.json`

| 项目 | 说明 |
|------|------|
| **生成** | `scripts/dataset/convert_qualified_to_dataset.py` |
| **输入** | `qualified_samples.json`（或同类结构：含 `spec`, `rtl`, `testbench`） |
| **逻辑** | 将 `spec`→`prompt`，`rtl`→`canonical_solution`（并把首个 `module` 改名为 `RefModule` 以配合评估流水线），`testbench`→`test`；`task_id` 格式 `q000000` 起递增 |
| **用途** | `evaluate.py`、`scripts/eval/evaluate_rules.py` 的 `--dataset` |

### 2.3 `data/qualified_dataset.normalized.json`

| 项目 | 说明 |
|------|------|
| **生成** | `scripts/dataset/normalize_module_names.py` |
| **输入** | `qualified_dataset.json` |
| **逻辑** | 若 `canonical_solution` 中模块名与 testbench 里 `... dut (...)` 的模块名不一致，则在 RTL 内做整词替换，使二者一致，减少仿真/评估时实例化名不匹配 |
| **用途** | **推荐**作为规则评估主数据集（与 `qualified_dataset.json` 条目一一对应，仅部分 RTL 被改写） |

### 2.4 对抗生成线：`data/adversarial_dataset.jsonl` / `metadata`

| 项目 | 说明 |
|------|------|
| **生成** | `generate_dataset.py` → `AdversarialDatasetGenerator`（`config.yaml`） |
| **逻辑** | 对样本按配置采样规则与位置，做 AST 变换；可选跑 testbench 过滤；可调用目标模型；输出 jsonl + 同行对齐的 metadata |
| **用途** | 大规模对抗样本构造、后续筛选与 SFT 数据制作 |

### 2.5 SFT 相关：`data/sft_dataset_*.jsonl`

| 文件示例 | 说明 |
|----------|------|
| `sft_dataset_final.jsonl` | `data/filter_and_convert_sft.py`：对 `adversarial_dataset` + metadata **筛选**（testbench 通过、按规则去重、每样本条数上限、规则占比均衡等）再 **格式转换**（语义化规则名、行号、短 CoT 等） |
| `sft_dataset_balanced*.jsonl` / `uniform300` / `uniform500` | 在最终或平衡流程上再采样子集，用于训练规模控制 |
| **格式** | Alpaca 风格：`instruction` / `input` / `output`（见 `data/dataset_info.json` 映射） |

### 2.6 `data/unflipped_orig_pass_subset/`（可选子集导出）

| 项目 | 说明 |
|------|------|
| **生成** | `python scripts/analysis/export_task_subset.py --task-list <ids.txt> --dataset data/qualified_dataset.normalized.json --out-dir data/unflipped_orig_pass_subset` |
| **内容** | `dataset.json`（标准四字段）+ `spec/*.txt`、`rtl/*.v`、`testbench/*.v` 与 `task_id` 同名，便于单独查阅或再做实验 |

### 2.7 其它

| 路径 | 说明 |
|------|------|
| `data/filtered_adversarial_dataset.jsonl` | 筛选后的对抗数据，与 `filtered_metadata.jsonl` 行对齐 |
| `rule_eval/results/<规则>/orig|adv/*.json` | `evaluate_rules.py` 写的单题攻击结果（`final` 为 RTL 文本等） |
| `rule_eval/metrics*/<规则>/adv_eval/*.json` | `evaluate.py` 对对抗 RTL 的逐题评估结果 |
| `rule_eval/*_verdict_cache*.json` | 全局 **original** 模式 LLM 判决缓存（含 `original_passed`、`original_confidence`），按 provider/model/url 分区 |

---

## 3. `evaluate.py` 里「判决」与真值

对每条 task：

| 字段 | 含义 |
|------|------|
| `original_truth` / `adversarial_truth` | 用 **testbench 仿真** 判断 RTL 是否功能正确（与 LLM 无关） |
| `original_passed` / `adversarial_passed` | LLM 对「该 RTL 是否满足规格」的预测 **是否与上述 truth 一致**（预测对了为 `true`） |
| `*_confidence` | 在 OpenAI 兼容 API 开启 logprobs 时，由 yes/no 概率导出的标量（具体实现见 `evaluate.py` / 客户端） |
| `*_error` | 仿真失败、请求失败、无法解析判决等 |

**ASR（攻击成功率）常用操作定义**（在 `evaluate.py` summary 与 `evaluate_rules.py` 中一致思路）：

- 仅关心 **原始 RTL 被模型判对** 的子集：`original_passed == True`
- 若对抗 RTL 上 **模型判错**：`adversarial_passed == False`
- 即「从判对 → 判错」的 flip，用于衡量攻击是否让验证模型失手

---

## 4. `scripts/eval/evaluate_rules.py`：单规则指标（`*_report.json`）

对每条规则、在 **整个 dataset** 上先统计 **变换能否应用**，再对 **变换成功** 的 task 子集跑 LLM 评估。

### 4.1 规则层「覆盖率」相关（与 LLM 无关）

| 指标 | 定义 |
|------|------|
| `num_samples` | 本规则评估时遍历的数据集样本数（或受 `--sample-limit` 截断） |
| `applicable_samples` | `num_candidates > 0` 的样本数（引擎认为至少有一个变换候选位置） |
| `success_samples` | `num_success > 0` 的样本数（至少成功做了一次语义保持变换） |
| `total_candidates` | 所有样本的候选数之和 |
| `total_success` | 所有样本上「成功变换次数」之和（通常每样本最多计 1） |
| `coverage` | `success_samples / num_samples` — **多大比例的题能被这条规则成功改写** |
| `success_rate` | `total_success / total_candidates` — 在 **有候选** 的位置上，变换成功率 |

### 4.2 LLM 评估子集

只对 **`success_samples` 对应 task**（即生成了 adv json 并成功评估 pipeline 的集合）统计下列量；`original_passed` 等来自 **全局 `orig_verdict_cache`**，与规则无关。

| 指标 | 定义 |
|------|------|
| `acc_orig` | 上述子集中 `original_passed == True` 的比例（模型对 **原始** RTL 判对的比率） |
| `acc_adv` | 子集中 `adversarial_passed == True` 的比例（模型对 **对抗** RTL 仍判对的比率） |
| `conf_orig` / `conf_adv` | 子集上 `original_confidence` / `adversarial_confidence` 的 **样本平均**（缺失则不计入分子，分母仍为子集大小，见脚本实现） |
| `gain` | `conf_adv - conf_orig` — 置信度层面「更倾向 NO」的差（与 `evaluate_rules` 中注释一致：攻击希望 adv 侧分数更高） |
| `asr` | 条件于 **`original_passed == True`** 的样本：其中 `adversarial_passed == False` 的比例（经典 **flip 率**） |
| `strength` | `coverage * gain`（gain 缺失时退化为 `coverage`）— 同时考虑 **能打上多少题** 与 **置信度位移** |

### 4.3 常用命令参数（备忘）

- `--results-root`：每规则 `orig/`、`adv/` 攻击结果根目录  
- `--eval-output`：每规则 `orig_eval/`、`adv_eval/` 及 `Txx_report.json`  
- `--orig-verdict-cache`：跨规则复用 original 评估，避免重复请求  
- `--reuse-existing-adv` / `--skip-clean-adv`：复用已有对抗代码  
- `--progress`：终端 tqdm + 子进程不吞输出  

---

## 5. `scripts/analysis/union_attack_coverage.py`：多规则并集与「冗余规则」

基于 **已跑完** 的 `metrics-root` 下各规则的 `adv_eval/*_rep0.json` + **`orig_verdict_cache`**（需与当时评估同一 cache 分区）。

### 5.1 ASR flip（单规则、单样本）

- `original_passed == True`（来自 cache）  
- `adversarial_passed == False`（来自该规则 `adv_eval`）  

### 5.2 并集

- **`num_union_asr_flip`**：至少被 **一条** 规则 flip 的样本数  
- **`rate_union_asr_flip_vs_all_dataset`**：相对全数据集  
- **`rate_union_asr_flip_vs_original_passed`**：相对 cache 中 original 判对样本  

### 5.3 「冗余规则」

对规则 R，记 Flip(R) 为 R 下 ASR flip 样本集合。

若 **Flip(R) 非空** 且 **Flip(R) ⊆ ⋃_{R'≠R} Flip(R')**，则 R 的每个成功攻击样本都可被其它规则再攻击成功；脚本输出：

- `exists_rule_whose_all_asr_flips_are_also_asr_flips_of_other_rules`  
- `rules_nonempty_all_flips_covered_by_other_rules`  
- `per_rule_redundancy_vs_others`（含 `num_exclusive_flip_not_by_other_rules`）  

### 5.4 辅助输出

- `--list-unflipped-orig-pass`：`original` 判对但并集上 **从未** flip 的 `task_id` 列表  

---

## 6. 绘图脚本（`scripts/analysis/plot_rule_metrics_full_all.py`）

从各规则 `Txx_report.json` 汇总画图（强度排序、coverage vs ASR、热力图等）；热力图可能对 **列** 做 min-max 归一化，读图时注意图注 **「normalized per column」**，与第 4 节原始指标数值不是同一缩放。

---

## 7. 配置文件与日志

| 文件 | 作用 |
|------|------|
| `config.yaml` | `filter_qualified`、`AdversarialDatasetGenerator`、参数生成模型等共用：路径、模型 URL、并行度、仿真器等 |
| `logs/filter_qualified.log` | 筛选详细日志 |
| `logs/generation.log` | 对抗数据集生成日志 |

---

## 8. 快速对照表（该用哪个 dataset）

| 目的 | 推荐数据文件 |
|------|----------------|
| 规则覆盖 / ASR / strength 评估 | `data/qualified_dataset.normalized.json` |
| 与旧实验严格对齐（未做模块名对齐） | `data/qualified_dataset.json` |
| SFT / RL 选规则监督信号 | `data/sft_dataset_final.jsonl` 或 balanced 子集 |
| 复盘「哪些题永远打不动」 | `union_attack_coverage.py` + `--list-unflipped-orig-pass` |

---

## 9. 修订历史

| 日期 | 说明 |
|------|------|
| 2026-03-17 | 初版：汇总 qualified 流水线、SFT 线、evaluate_rules / union 指标与字段含义 |
