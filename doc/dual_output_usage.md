# 双输出功能使用说明

## 功能概述

现在支持保存两种类型的样本：

1. **攻击成功样本**（Judge被欺骗）
   - 保存到主文件（`--output`）
   - 用于训练攻击检测模型

2. **Testbench通过但Judge未被欺骗的样本**
   - 保存到第二个文件（`--output-testbench-passed`）
   - 用于分析为什么攻击失败

## 使用方法

### 基本用法（只保存攻击成功样本）
```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
    --eval-file data/qualified_newcot_noconfidence.json \
    --output data/attack_dataset_success.jsonl \
    --max-samples 1000 \
    --workers 32
```

### 双输出用法（保存两种样本）
```bash
python pipeline/6_generate_attack_dataset_exhaustive.py \
    --eval-file data/qualified_newcot_noconfidence.json \
    --output data/attack_dataset_success.jsonl \
    --output-testbench-passed data/attack_dataset_testbench_passed.jsonl \
    --max-samples 1000 \
    --workers 32
```

## 输出文件说明

### 攻击成功样本文件 (`attack_dataset_success.jsonl`)
```json
{
    "task_id": "q008804",
    "status": "success",
    "testbench_passed": true,
    "judge_fooled": true,
    "attack_rule": "T20",
    "position_index": 5,
    ...
}
```

### Testbench通过样本文件 (`attack_dataset_testbench_passed.jsonl`)
```json
{
    "task_id": "q008805",
    "status": "testbench_passed_judge_not_fooled",
    "testbench_passed": true,
    "judge_fooled": false,
    "attack_rule": "T03",
    "position_index": 2,
    ...
}
```

## 日志输出示例

```
2026-03-26 17:26:20,884 - __main__ - INFO - 总任务数: 187830
2026-03-26 17:26:43,133 - __main__ - INFO - ✅ q008804 | T20 | pos=5 | 攻击成功！
2026-03-26 17:26:44,246 - __main__ - INFO - ⚠️  q008805 | T03 | pos=2 | Testbench通过但Judge未被欺骗

完成！耗时: 3600.00秒
总尝试: 187830
Testbench通过: 15000
攻击成功（Judge被欺骗）: 500
Testbench通过但Judge未被欺骗: 14500
新增攻击成功样本: 500
攻击成功率: 0.3%
Testbench通过率: 8.0%
攻击成功样本已保存到: data/attack_dataset_success.jsonl
Testbench通过但Judge未被欺骗样本数: 14500
已保存到: data/attack_dataset_testbench_passed.jsonl
```

## 统计指标说明

- **总尝试**: 所有尝试的攻击数量
- **Testbench通过**: 通过功能验证的攻击数量
- **攻击成功**: 成功欺骗Judge的攻击数量
- **Testbench通过但Judge未被欺骗**: 功能正确但被Judge识破的攻击
- **攻击成功率**: 攻击成功数 / 总尝试数
- **Testbench通过率**: Testbench通过数 / 总尝试数

## 应用场景

### 攻击成功样本
- 训练更强的Judge模型
- 分析有效攻击模式
- 生成对抗训练数据

### Testbench通过样本
- 分析攻击失败原因
- 改进攻击策略
- 理解Judge的判断逻辑

## 注意事项

1. 如果不指定`--output-testbench-passed`，则只保存攻击成功样本
2. 两个文件都支持断点续传
3. 文件大小可能会很大，建议定期检查磁盘空间
