# 规则组合协同效应验证实验 - 实现总结

## 已实现功能

### 1. 核心框架

✅ **SynergyValidator** (`synergy_validator.py`)
- 完整的实验执行引擎
- 单规则 vs 组合规则对比评估
- 协同效应自动检测
- 多线程并行处理
- 详细的结果记录和统计

✅ **攻击场景定义** (`attack_scenarios.py`)
- 6个预定义场景，涵盖3种核心协同模式：
  1. **信号亲和力联动** (T34+T32)
  2. **掩体-弹头组合** (T19+T47)
  3. **语义一致性劫持** (T20+T34+T31)
  4. 增强版信号亲和力 (T34+T32+T35)
  5. 逻辑混淆组合 (T09+T12+T20)
  6. 深度掩体 (T19+T19+T47)

✅ **测试模块集** (`test_modules.py`)
- 20个精心设计的Verilog模块
- 4类典型硬件：计数器、状态机、ALU、多路复用器
- 每类5个样本，覆盖不同复杂度
- 核心子集（4个）用于快速验证

### 2. 实验执行

✅ **主执行脚本** (`run_synergy_experiment.py`)
- 3种运行模式：core（快速）、full（完整）、custom（自定义）
- 灵活的场景和模块选择
- 进度跟踪和中断恢复
- 详细的日志记录

✅ **快速启动脚本** (`quick_start.sh`)
- 一键式环境检查
- 交互式模式选择
- 自动化执行和分析
- 友好的用户界面

✅ **环境测试** (`test_setup.py`)
- 全面的环境检查
- 模块导入验证
- vLLM连接测试
- 变换引擎测试

### 3. 结果分析

✅ **分析工具** (`analyze_synergy_results.py`)
- LaTeX表格生成（论文级）
- Markdown表格生成（可读性）
- 可视化图表（ASR对比、置信度下降）
- 统计摘要（JSON格式）

✅ **输出格式**
- 详细结果（JSONL）
- 汇总报告（JSON）
- 学术表格（LaTeX）
- 可读表格（Markdown）
- 高质量图表（PNG）

### 4. 文档

✅ **完整文档**
- README.md：使用指南
- IMPLEMENTATION_SUMMARY.md：实现总结（本文档）
- experiment_config_example.yaml：配置示例
- 代码内注释：详细的实现说明

## 技术特点

### 协同效应检测算法

```python
# 非线性增益判断
is_synergistic = (
    (combined_asr - max_single_asr > 0.2) or  # ASR提升>20%
    (combined_conf_drop - max_single_conf_drop > 0.15)  # 置信度提升>0.15
)
```

### 实验设计亮点

1. **对照实验**：每个组合规则都与其单个规则进行对比
2. **多维评估**：ASR、置信度、推理轨迹多角度分析
3. **统计严谨**：平均值、标准差、协同率等指标
4. **可重现**：固定随机种子、详细记录参数

### 性能优化

- 并行处理：ThreadPoolExecutor并发执行
- 结果缓存：避免重复计算
- 增量保存：实时写入结果，防止数据丢失
- 中断恢复：支持从检查点继续

## 使用流程

### 最小化验证（推荐首次运行）

```bash
# 1. 测试环境
python scripts/experiments/test_setup.py

# 2. 运行核心验证（3场景 × 4模块 = 12测试）
bash scripts/experiments/quick_start.sh
# 选择选项 1

# 3. 查看结果
cat results/synergy_experiments/analysis/results_table.md
```

预计耗时：10-20分钟

### 完整实验

```bash
# 运行所有场景（6场景 × 20模块 = 120测试）
bash scripts/experiments/quick_start.sh
# 选择选项 2
```

预计耗时：1-2小时

### 自定义实验

```bash
# 仅测试特定场景和模块
python scripts/experiments/run_synergy_experiment.py \
    --mode custom \
    --scenarios signal_affinity,distractor_payload \
    --module-types counter,alu
```

## 预期结果

### 成功标准

如果实验成功，你应该看到：

1. **协同率 > 50%**
   - 超过一半的测试显示协同效应
   
2. **平均ASR提升 > 20%**
   - 组合规则显著优于单规则
   
3. **置信度提升 > 0.15**
   - 模型置信度显著下降

### 典型输出

```
实验报告摘要
================================================================
总场景数: 3
总测试数: 12
协同案例数: 9
协同率: 75.00%

各场景表现:

  Signal_Affinity_T34_T32:
    平均 ASR 提升: 35.00%
    平均置信度提升: 0.7500
    协同率: 75.00%
```

## 论文写作支持

### 生成的材料

1. **LaTeX表格** (`results_table.tex`)
   - 直接插入论文
   - 格式符合学术标准
   
2. **高质量图表** (PNG, 300 DPI)
   - ASR对比图
   - 置信度下降图
   
3. **统计数据** (JSON)
   - 所有数值指标
   - 便于引用

### 建议的论文结构

**Methodology章节**：
- 描述三种协同模式（信号亲和力、掩体-弹头、语义劫持）
- 引用实验设计（对照组、评估指标）

**Results章节**：
- 插入LaTeX表格
- 引用图表
- 讨论协同效应的统计显著性

**Discussion章节**：
- 非线性增益的理论解释
- 认知资源饱和假说
- 跨层一致性需求

## 扩展方向

### 1. 添加新场景

编辑 `attack_scenarios.py`：

```python
SCENARIO_NEW = AttackScenario(
    name="Your_Scenario_Name",
    description="场景描述",
    rule_chain=[
        {"rule_id": "Txx", "params": {...}, "target_token": 0},
        {"rule_id": "Tyy", "params": {...}, "target_token": 1},
    ],
    target_module_type="counter",
    hypothesis="你的假设"
)

# 添加到列表
ALL_SCENARIOS.append(SCENARIO_NEW)
```

### 2. 添加新模块

编辑 `test_modules.py`：

```python
NEW_MODULE = {
    "id": "your_module_id",
    "type": "counter",
    "spec": "功能规范",
    "rtl": "Verilog代码",
    "testbench": "测试代码（可选）"
}

COUNTER_MODULES.append(NEW_MODULE)
```

### 3. 自定义协同判断

编辑 `synergy_validator.py` 中的 `_compute_synergy` 方法：

```python
# 修改阈值
is_synergistic = (
    (asr_boost > YOUR_THRESHOLD) or
    (conf_boost > YOUR_THRESHOLD)
)
```

### 4. 集成MCTS

未来可以将本实验框架与MCTS搜索结合：

```python
# 伪代码
class MCTSGuidedSynergy:
    def search(self, rtl, spec):
        # 使用MCTS搜索最优规则组合
        best_chain = mcts.search(rtl, spec)
        
        # 使用SynergyValidator验证
        result = validator.evaluate_scenario(
            scenario=create_scenario_from_chain(best_chain),
            module={"rtl": rtl, "spec": spec}
        )
        
        return result
```

## 故障排查

### 常见问题

1. **ImportError: No module named 'xxx'**
   - 解决：`pip install -r requirements.txt`

2. **vLLM连接失败**
   - 检查：`curl http://localhost:8001/v1/models`
   - 启动：`bash scripts/ops/run_vllm.sh`

3. **Testbench验证失败**
   - 检查：`iverilog -v`
   - 安装：`sudo apt-get install iverilog`

4. **内存不足**
   - 减少并发：修改 `config.yaml` 中的 `num_workers`
   - 使用核心模式：`--mode core`

5. **结果为空**
   - 检查原始RTL是否通过判题
   - 增加日志级别：`--verbose`

## 文件清单

```
scripts/experiments/
├── README.md                      # 使用指南
├── IMPLEMENTATION_SUMMARY.md      # 实现总结（本文档）
├── synergy_validator.py           # 核心验证器
├── attack_scenarios.py            # 场景定义
├── test_modules.py                # 测试模块
├── run_synergy_experiment.py      # 主执行脚本
├── analyze_synergy_results.py     # 结果分析
├── quick_start.sh                 # 快速启动
├── test_setup.py                  # 环境测试
└── experiment_config_example.yaml # 配置示例
```

## 依赖项

- Python 3.8+
- PyYAML
- requests
- matplotlib (可选，用于图表)
- iverilog (可选，用于Testbench)
- vLLM (必需，用于模型推理)

## 许可证

与主项目保持一致。

## 致谢

本实验框架基于以下理论和技术：
- MCTS for Adversarial Search
- Chain-of-Thought Reasoning
- Hardware Verification with LLMs
- Synergistic Attack Composition

## 联系方式

如有问题或建议，请：
1. 查看 README.md
2. 运行 test_setup.py 诊断
3. 查看日志文件 logs/synergy_experiment.log
4. 提交Issue到主项目

---

**最后更新**: 2026-03-24
**版本**: 1.0
**状态**: 生产就绪 ✅
