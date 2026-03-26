# 缓存任务构建器集成指南

## 当前问题

攻击任务列表每次都要重新构建，耗时较长：
- 需要为每个RTL-规则组合计算候选位置
- 10000个任务 × 15个规则 = 150,000次计算
- 每次计算约0.0001秒，总计15-30秒

## 解决方案

使用`CachedTaskBuilder`缓存候选位置数量：

### 性能提升
```
第一次运行: 4.0秒
第二次运行: 0.0秒  
提升: 262倍
```

### 集成方法

#### 1. 修改主脚本

在`6_generate_attack_dataset_exhaustive.py`中替换任务构建逻辑：

```python
# 在文件顶部添加导入
from pipeline.cached_task_builder import CachedTaskBuilder

# 在generate_dataset_exhaustive方法中替换构建逻辑
def generate_dataset_exhaustive(self, ...):
    # ... 验证阶段代码 ...
    
    # 使用缓存构建器
    builder = CachedTaskBuilder()
    jobs = builder.build_job_list(
        valid_tasks, 
        rules_to_test, 
        max_positions_per_rule, 
        random_seed
    )
    
    # ... 执行阶段代码 ...
```

#### 2. 缓存文件位置

```
data/cache/
├── candidates_cache.pkl  # 候选位置数量缓存
└── ...                   # 其他缓存文件
```

#### 3. 缓存策略

- **缓存内容**: 只缓存候选位置数量，不缓存具体对象
- **缓存键**: RTL的MD5哈希值 + 规则ID
- **缓存格式**: pickle文件
- **自动更新**: 如果RTL或规则变化，自动重新计算

## 使用建议

### 开发阶段
```bash
# 第一次运行会创建缓存
python pipeline/6_generate_attack_dataset_exhaustive.py \
    --eval-file data/test.json \
    --output data/test_output.jsonl \
    --max-samples 100

# 后续运行瞬间完成任务构建
python pipeline/6_generate_attack_dataset_exhaustive.py \
    --eval-file data/test.json \
    --output data/test_output2.jsonl \
    --max-samples 200
```

### 生产阶段
```bash
# 缓存可以复用，大幅提升启动速度
python pipeline/6_generate_attack_dataset_exhaustive.py \
    --eval-file data/qualified_newcot_noconfidence.json \
    --output data/attack_dataset_production.jsonl \
    --output-testbench-passed data/testbench_passed.jsonl
```

## 注意事项

1. **缓存文件大小**: 约1-10MB，取决于数据集大小
2. **缓存失效**: 如果修改了攻击规则或RTL格式，需要删除缓存
3. **并发安全**: 当前不支持多进程同时写入缓存

## 清理缓存

如果需要重新计算所有候选位置：

```bash
rm -rf data/cache/candidates_cache.pkl
```

## 预期效果

集成后，程序启动时间从30秒减少到不到1秒，大幅提升开发效率。
