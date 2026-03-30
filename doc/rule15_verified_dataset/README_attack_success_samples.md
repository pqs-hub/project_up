# 攻击成功样本数据集说明

## 概述

本文件包含从 `rule15_verified_dataset.jsonl` 中提取的攻击成功样本，基于 `eval_results/attack_success_eval.json` 的评估结果。

## 文件信息

- **文件名**: `attack_success_samples.jsonl`
- **大小**: 154MB
- **样本数量**: 59,289 个
- **生成时间**: 2026-03-29

## 数据结构

每个样本包含以下字段：

```json
{
  "record_type": "structured",
  "source_file": "原始数据集文件路径",
  "source_loc": "源文件行号",
  "rule_id": "攻击规则ID (如 T32, T45, T03 等)",
  "attack_success": null,  // 原始字段，评估后填充
  "target_token": null,
  "target_line": null,
  "target_signal": null,
  "instruction": "攻击指令",
  "input": "功能规范和原始代码",
  "output": "攻击策略和参数",
  "raw_excerpt": null,
  "transformed_rtl": "变换后的RTL代码",
  "estimated_attack_success": true  // 标记为基于统计估算的攻击成功样本
}
```

## 规则分布

| 规则ID | 样本数量 | 成功率 |
|--------|----------|--------|
| T32    | 19,354   | 42.26% |
| T45    | 15,544   | 98.72% |
| T03    | 11,719   | 15.10% |
| T20    | 1,961    | 4.94%  |
| T19    | 2,404    | 10.91% |
| T48    | 1,762    | 40.77% |
| T41    | 1,510    | 48.37% |
| T07    | 1,128    | 49.00% |
| T30    | 1,161    | 57.91% |
| T09    | 940      | 57.28% |
| T10    | 611      | 54.55% |
| T34    | 632      | 23.69% |
| T31    | 455      | 10.38% |
| T12    | 90       | 5.22%  |
| T47    | 18       | 27.27% |

## 使用方法

### 1. 读取特定规则的样本

```bash
# 提取T32规则的样本
grep '"rule_id": "T32"' attack_success_samples.jsonl > t32_samples.jsonl

# 统计T32样本数量
grep '"rule_id": "T32"' attack_success_samples.jsonl | wc -l
```

### 2. 读取指定数量的样本

```bash
# 读取前100个样本
head -100 attack_success_samples.jsonl > first_100_samples.jsonl
```

### 3. Python处理示例

```python
import json

# 读取攻击成功样本
with open('attack_success_samples.jsonl', 'r', encoding='utf-8') as f:
    for line in f:
        sample = json.loads(line.strip())
        rule_id = sample['rule_id']
        transformed_code = sample['transformed_rtl']
        # 处理样本...
```

## 注意事项

1. **估算样本**: 这些样本是基于评估统计信息估算的攻击成功样本，不是实际运行评估的结果
2. **标记字段**: 每个样本都包含 `estimated_attack_success: true` 字段来标识这是估算的结果
3. **文件大小**: 文件较大（154MB），建议使用流式处理
4. **编码格式**: 文件使用UTF-8编码

## 相关文件

- `attack_success_samples.jsonl.stats.json`: 详细统计报告
- `eval_results/attack_success_eval.json`: 原始评估结果
- `rule15_verified_dataset.jsonl`: 原始完整数据集
- `extract_attack_success_samples.py`: 提取脚本

## 生成脚本

使用以下命令重新生成：

```bash
python extract_attack_success_samples.py --method estimate
```

参数说明：
- `--method estimate`: 基于统计信息估算（默认）
- `--method direct`: 直接从attack_success字段提取（需要先运行评估）
- `--limit N`: 限制提取的样本数量
