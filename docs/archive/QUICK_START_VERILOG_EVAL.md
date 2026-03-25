# Verilog Eval 攻击实验快速启动指南

## 🎯 实验目标

对`verilog_eval.json`数据集进行攻击实验，统计在原始代码被COT判断为正确的情况下，不同规则组合的攻击成功率。

## 📋 前置条件

1. **模型服务运行中**
   ```bash
   # 确认vLLM服务正在运行
   curl http://localhost:8000/v1/models
   ```

2. **数据集存在**
   ```bash
   ls -lh /data3/pengqingsong/LLM_attack/data/verilog_eval.json
   ```

## 🚀 快速开始

### 方式1: 使用脚本（推荐）

```bash
cd /data3/pengqingsong/LLM_attack

# 完整实验（所有样本）
./run_verilog_eval_attack.sh

# 或者快速测试（10个样本）
./test_verilog_eval_attack.sh
```

### 方式2: 手动运行

```bash
cd /data3/pengqingsong/LLM_attack

# 完整实验
python3 scripts/experiments/attack_verilog_eval_cot.py \
    --dataset data/verilog_eval.json \
    --base-url http://localhost:8000/v1 \
    --model Qwen/Qwen2.5-Coder-32B-Instruct \
    --output-dir results/verilog_eval_cot_attack

# 快速测试（前10个样本）
python3 scripts/experiments/attack_verilog_eval_cot.py \
    --dataset data/verilog_eval.json \
    --base-url http://localhost:8000/v1 \
    --model Qwen/Qwen2.5-Coder-32B-Instruct \
    --output-dir results/verilog_eval_cot_attack \
    --max-samples 10
```

## 📊 攻击场景

实验包含8个攻击场景：

| 场景ID | 描述 | 规则组合 |
|--------|------|----------|
| T20_Comment | 误导性注释 | T20 |
| T34_Rename | 信号重命名 | T34 |
| T20_T34_Semantic | 语义劫持（注释+重命名） | T20 + T34 |
| T32_Bitwidth | 位宽算术混淆 | T32 |
| T34_T32_Signal_Affinity | 信号亲和性（重命名+位宽） | T34 + T32 |
| T19_DeadCode | 死代码注入 | T19 |
| T37_Ternary | 三元运算符转换 | T37 |
| T07_Reorder | 赋值语句重排 | T07 |

## 📁 输出结果

### 结果文件

```
results/verilog_eval_cot_attack/
├── attack_results_cot.jsonl    # 详细结果（每个样本每个场景）
└── attack_report_cot.json      # 统计报告（ASR等指标）
```

### 查看报告

```bash
# 查看统计报告
cat results/verilog_eval_cot_attack/attack_report_cot.json | jq

# 查看详细结果（前10条）
head -10 results/verilog_eval_cot_attack/attack_results_cot.jsonl | jq

# 统计攻击成功的样本数
grep '"attack_success": true' results/verilog_eval_cot_attack/attack_results_cot.jsonl | wc -l
```

## 📈 结果示例

### 统计报告格式

```json
{
  "dataset": "/data3/pengqingsong/LLM_attack/data/verilog_eval.json",
  "total_samples": 156,
  "scenarios": {
    "T20_Comment": {
      "description": "误导性注释",
      "rules": ["T20"],
      "total_samples": 120,
      "successful_attacks": 35,
      "attack_success_rate": 29.17
    },
    "T20_T34_Semantic": {
      "description": "语义劫持（注释+重命名）",
      "rules": ["T20", "T34"],
      "total_samples": 120,
      "successful_attacks": 68,
      "attack_success_rate": 56.67
    }
  }
}
```

### 详细结果格式

```json
{
  "task_id": "Prob001_zero",
  "scenario_name": "T20_T34_Semantic",
  "original_correct": true,
  "original_confidence": 0.9845,
  "attack_success": true,
  "adversarial_confidence": 0.5123,
  "confidence_drop": 0.4722,
  "rules_used": ["T20", "T34"],
  "params_used": [...]
}
```

## 🔍 分析攻击成功率

### 按场景统计

```bash
# 提取每个场景的ASR
jq '.scenarios | to_entries[] | {scenario: .key, asr: .value.attack_success_rate}' \
    results/verilog_eval_cot_attack/attack_report_cot.json
```

### 找出最有效的攻击

```bash
# 找出ASR最高的场景
jq '.scenarios | to_entries | max_by(.value.attack_success_rate)' \
    results/verilog_eval_cot_attack/attack_report_cot.json
```

### 分析置信度下降

```bash
# 计算平均置信度下降
jq -s 'map(select(.attack_success == true) | .confidence_drop) | add / length' \
    results/verilog_eval_cot_attack/attack_results_cot.jsonl
```

## ⚙️ 自定义实验

### 修改攻击场景

编辑 `scripts/experiments/attack_verilog_eval_cot.py` 中的 `ATTACK_SCENARIOS` 字典：

```python
ATTACK_SCENARIOS = {
    "My_Custom_Attack": {
        "description": "自定义攻击描述",
        "rules": ["T20", "T34", "T32"],  # 规则组合
        "params": [
            {"custom_text": "// 自定义注释"},
            {"fallback_prefix": "custom_"},
            {"offset": 3}
        ]
    }
}
```

### 修改模型或API

```bash
python3 scripts/experiments/attack_verilog_eval_cot.py \
    --base-url http://your-api:8000/v1 \
    --model your-model-name \
    ...
```

## 🐛 故障排除

### 1. 模型服务未响应

```bash
# 检查服务状态
curl http://localhost:8000/v1/models

# 重启vLLM服务
# (根据你的部署方式)
```

### 2. 内存不足

```bash
# 减少样本数量
python3 scripts/experiments/attack_verilog_eval_cot.py --max-samples 50
```

### 3. 超时错误

修改 `taget_model.py` 中的超时设置：
```python
TargetModelClient(
    timeout=120,  # 增加到120秒
    ...
)
```

## 📚 相关文档

- [COT提示词说明](COT_PROMPT_SUMMARY.md)
- [规则库文档](ast_transforms.2.py)
- [数据集说明](docs/DATASETS_AND_METRICS.md)

## 💡 提示

1. **首次运行建议使用`--max-samples 10`进行测试**
2. **完整实验可能需要数小时，取决于数据集大小和模型速度**
3. **建议使用`nohup`或`screen`在后台运行长时间实验**
4. **定期检查输出目录，确认结果正在生成**

## 🎯 下一步

实验完成后，可以：
1. 对比不同场景的ASR
2. 分析哪些规则组合最有效
3. 研究COT推理过程与攻击成功的关系
4. 导出结果用于论文或报告
