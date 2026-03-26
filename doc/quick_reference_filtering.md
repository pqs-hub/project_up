# 数据集过滤 - 快速参考

## 🚀 一句话总结

使用 `--only-valid-samples` 只保留**功能正确**的样本，过滤掉变换失败和testbench错误的数据。

---

## 📋 常用命令

### 调试分析（保留所有样本）
```bash
python pipeline/6_generate_attack_dataset.py \
  --eval-file data/verilog_eval_correct_only.json \
  --output data/debug_all.jsonl \
  --max-samples 5 \
  --enable-llm-params \
  --verbose
```

### 生成训练集（只保留有效样本）⭐
```bash
python pipeline/6_generate_attack_dataset.py \
  --eval-file data/verilog_eval_correct_only.json \
  --output data/train_valid.jsonl \
  --max-samples 100 \
  --enable-llm-params \
  --only-valid-samples
```

---

## 🎯 过滤规则

| 样本状态 | testbench | 默认 | --only-valid-samples |
|---------|-----------|------|----------------------|
| success | ✅ 通过 | 保留 | ✅ **保留** |
| attack_failed | ✅ 通过 | 保留 | ✅ **保留** |
| judge_error | ✅ 通过 | 保留 | ✅ **保留** |
| no_change | ❌ 未通过 | 保留 | ❌ **过滤** |
| testbench_failed | ❌ 失败 | 保留 | ❌ **过滤** |
| testbench_error | ❌ 错误 | 保留 | ❌ **过滤** |
| exception | ❌ 异常 | 保留 | ❌ **过滤** |

---

## 📊 效果示例

### 实际数据（5个样本，10个规则）

**不加过滤**：
```
总样本数: 58
  no_change: 36       ← 会被保存
  attack_failed: 18   
  judge_error: 3
  testbench_failed: 1 ← 会被保存
```

**加 --only-valid-samples**：
```
总样本数: 58
已保存: 21 (只包含testbench通过的)
  attack_failed: 18   ← 保留
  judge_error: 3      ← 保留
  (no_change: 36)     ← 过滤
  (testbench_failed: 1) ← 过滤

保留率: 36.2%
```

---

## ✅ 验证过滤结果

```bash
# 方法1：快速统计
python -c "
import json
with open('data/train_valid.jsonl') as f:
    samples = [json.loads(line) for line in f]
    
print(f'样本数: {len(samples)}')
all_passed = all(s.get('testbench_passed', False) for s in samples)
print(f'全部testbench通过: {all_passed}')
"

# 方法2：详细分析
python -c "
import json
from collections import Counter

with open('data/train_valid.jsonl') as f:
    samples = [json.loads(line) for line in f]

print('状态分布:', dict(Counter(s['status'] for s in samples)))
print('规则分布:', dict(Counter(s['attack_rule'] for s in samples)))
"
```

---

## 💡 何时使用

| 场景 | 是否使用 | 原因 |
|------|----------|------|
| **调试prompt** | ❌ 不用 | 需要看失败案例分析问题 |
| **分析失败原因** | ❌ 不用 | 需要完整数据 |
| **生成训练数据** | ✅ **使用** | 只要高质量样本 |
| **测试代码变换** | ❌ 不用 | 需要看各种情况 |
| **CI/CD流水线** | ✅ **使用** | 自动化生成训练集 |

---

**创建时间**: 2026-03-26  
**相关文档**: `dataset_filtering_guide.md` (详细版)
