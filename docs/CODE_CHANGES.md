# 代码改动记录

## 2026-03-25: 优化结果文件存储方式

### 问题
之前的代码会为每个评估任务生成一个单独的 JSON 文件，导致产生海量零散文件（数十万个），影响文件系统性能和代码库管理。

### 解决方案
修改 `legacy/evaluate.py`，将所有评估结果统一保存到 `summary.json` 文件中，而不是每个任务一个文件。

### 修改文件
- `legacy/evaluate.py` (第 564-566 行)
  - 注释掉单个文件保存逻辑
  - 所有结果通过 `summary.json` 的 `results` 字段统一保存

### 影响
- ✅ 减少文件数量：从 N 个文件减少到 1 个 `summary.json`
- ✅ 提升文件系统性能
- ✅ 便于版本控制和代码库管理
- ✅ 保持数据完整性：所有结果仍然完整保存在 `summary.json` 中

### 使用方式
评估脚本的使用方式不变：

```bash
python legacy/evaluate.py \
    --results results/final_v3 \
    --dataset dataset.json \
    --provider local \
    --model Qwen2.5-Coder-7B \
    --base-url http://localhost:8000/v1 \
    --output eval_results/
```

结果将保存在 `eval_results/summary.json` 中，包含：
- 总体统计信息
- 每个任务的详细结果（`results` 数组）

### 数据访问
从 `summary.json` 读取结果：

```python
import json

with open("eval_results/summary.json") as f:
    data = json.load(f)
    
# 总体统计
print(f"Total: {data['total']}")
print(f"Passed: {data['original_passed']}")

# 单个任务结果
for result in data['results']:
    print(f"{result['task_id']}: {result['original_passed']}")
```

### 历史数据迁移
已有的零散 JSON 文件已通过 `scripts/ops/consolidate_json_files.py` 合并为单个文件。

---

## 其他改动

### 文件整理工具
新增工具脚本用于合并零散 JSON 文件：

- `scripts/ops/consolidate_json_files.py` - 通用 JSON 文件合并工具
- `scripts/ops/batch_consolidate.sh` - 批量处理脚本

使用方式：
```bash
# 合并单个目录
python scripts/ops/consolidate_json_files.py <source_dir> -o <output.json> -d

# 递归合并所有子目录
python scripts/ops/consolidate_json_files.py <base_dir> -r -d
```
