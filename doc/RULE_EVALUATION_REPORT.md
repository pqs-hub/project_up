# 15个规则攻击成功率评估报告

## 评估配置
- **数据集**: `data/verilog_eval.json`
- **总样本数**: 156个
- **每规则测试**: 30个样本
- **评估时间**: 2026-03-28
- **Testbench验证**: 未启用（仅测试代码变换成功率）

## 整体统计

- **总测试**: 450次（15个规则 × 30个样本）
- **变换成功**: 167次
- **变换失败**: 283次
- **平均成功率**: **37.1%**

## 规则成功率排名

### 🟢 高成功率规则（≥80%）

| 规则 | 名称 | 成功率 | 成功/总数 | 说明 |
|------|------|--------|-----------|------|
| **T03** | 冗余逻辑 | **100.0%** | 30/30 | 在信号上添加冗余操作（如 `& 1'b1`） |
| **T19** | 死代码注入 | **100.0%** | 30/30 | 插入永远不会执行的代码块 |
| **T20** | 误导性注释 | **100.0%** | 30/30 | 添加误导性注释 |
| **T31** | 简单中间信号 | **90.0%** | 27/30 | 在assign中插入中间wire信号 |
| **T45** | 伪组合循环 | **80.0%** | 24/30 | 创建看似循环但实际无害的逻辑 |

**分析**: 这5个规则是**最可靠的攻击规则**，适合大规模使用。T03/T19/T20几乎可以应用到任何代码上。

### 🟡 中等成功率规则（10-50%）

| 规则 | 名称 | 成功率 | 成功/总数 | 说明 |
|------|------|--------|-----------|------|
| **T32** | 位宽算术 | **40.0%** | 12/30 | 将位宽数字转换为算术表达式 |
| **T47** | Shannon展开 | **16.7%** | 5/30 | 使用Shannon定理展开逻辑 |
| **T09** | DeMorgan AND | **13.3%** | 4/30 | AND转换为OR+NOT |
| **T30** | 常量恒等 | **10.0%** | 3/30 | 常量替换为等价表达式 |
| **T12** | 谓词提取 | **6.7%** | 2/30 | 从三元表达式中提取谓词 |

**分析**: 这些规则依赖特定代码模式：
- **T32**: 需要位宽声明（如`[7:0]`）
- **T09**: 需要AND表达式（`&`）
- **T47**: 需要复杂逻辑表达式
- **T30**: 需要位常量（`1'b0`, `1'b1`）
- **T12**: 需要三元表达式（`? :`）

### 🔴 零成功率规则（0%）

| 规则 | 名称 | 成功率 | 成功/总数 | 可能原因 |
|------|------|--------|-----------|----------|
| **T07** | assign重排序 | **0.0%** | 0/30 | 需要多条assign语句 |
| **T10** | DeMorgan OR | **0.0%** | 0/30 | 需要OR表达式（`\|`） |
| **T34** | 语义反转重命名 | **0.0%** | 0/30 | 需要特定信号名模式 |
| **T41** | Case分支重排 | **0.0%** | 0/30 | 需要case语句 |
| **T48** | 反拓扑排序 | **0.0%** | 0/30 | 需要多条assign语句 |

**分析**: 这些规则失败的主要原因：

1. **代码结构不匹配**: 
   - T07/T48需要多条assign（测试集样本可能较简单）
   - T41需要case语句（测试集可能主要是assign/always）

2. **信号名模式不匹配**:
   - T34需要特定命名模式（如`out`, `enable`, `valid`等）

3. **表达式类型不匹配**:
   - T10需要OR表达式

## 建议

### 1. 提高失败规则成功率

#### 针对T07/T48（需要多条assign）
```python
# 增加多位置尝试
for target_token in range(5):  # 尝试多个位置
    transformed = engine.apply_transform(code, 'T07', target_token=target_token)
    if transformed != code:
        break
```

#### 针对T34（信号名不匹配）
```python
# 启用LLM生成custom_map
transformed = engine.apply_transform(
    code, 
    'T34', 
    custom_map={'internal_sig': 'misleading_name'}  # LLM生成
)
```

#### 针对T41（需要case语句）
- 过滤数据集，只对包含case的样本应用此规则
- 或增加数据集中case语句的样本

### 2. 优化评估策略

当前评估只尝试`target_token=0`（第一个候选位置），建议：

```python
# 尝试多个位置
for target_token in [0, 1, 2, 3, None]:  # None=随机位置
    transformed = engine.apply_transform(code, rule_id, target_token=target_token)
    if transformed != code:
        success = True
        break
```

### 3. 组合使用规则

**推荐组合**（基于成功率）：
- **核心组合**: T03 + T19 + T20（三个100%规则）
- **扩展组合**: 核心 + T31 + T45（5个高成功率规则）
- **全面组合**: 扩展 + T32 + T09 + T47（覆盖更多代码模式）

### 4. 数据集特性分析

建议分析数据集以了解：
```bash
# 统计代码特征
python -c "
import json
data = json.load(open('data/verilog_eval.json'))
rtl_codes = [d['canonical_solution'] for d in data]

# 统计特征
print('包含assign:', sum('assign' in c for c in rtl_codes))
print('包含case:', sum('case' in c for c in rtl_codes))
print('包含always:', sum('always' in c for c in rtl_codes))
print('包含三元:', sum('?' in c and ':' in c for c in rtl_codes))
print('包含OR:', sum('|' in c for c in rtl_codes))
print('包含AND:', sum('&' in c for c in rtl_codes))
"
```

## 下一步行动

### 短期（提高当前规则效果）
1. ✅ **多位置尝试**: 修改评估脚本，对每个规则尝试多个`target_token`
2. ✅ **启用LLM参数**: 对T03/T12/T19/T20/T31/T34启用LLM生成参数
3. ✅ **Testbench验证**: 加上`--enable-testbench`确认变换不破坏功能

### 中期（优化规则实现）
1. 🔧 **改进T07/T48**: 增强对少量assign的处理
2. 🔧 **改进T34**: 优化默认重命名映射，增加更多常见信号名
3. 🔧 **改进T41**: 降低对case语句的依赖，或标记为"高级规则"

### 长期（扩展攻击策略）
1. 📊 **数据集分析**: 基于代码特征自动选择适用规则
2. 🤖 **智能规则选择**: 训练模型预测哪些规则适用于给定代码
3. 🔀 **规则链接**: 研究多规则组合的协同效果

## 运行更详细的评估

### 启用Testbench验证
```bash
python test/quick_rule_evaluation.py \
    --dataset data/verilog_eval.json \
    --max-samples 30 \
    --enable-testbench \
    --output test/rule_eval_with_tb.json
```

### 测试全部数据集
```bash
python test/quick_rule_evaluation.py \
    --dataset data/verilog_eval.json \
    --max-samples 156 \
    --output test/rule_eval_full.json
```

### 只测试高成功率规则
```bash
python test/quick_rule_evaluation.py \
    --dataset data/verilog_eval.json \
    --rules T03,T19,T20,T31,T45 \
    --max-samples 50 \
    --enable-testbench \
    --output test/rule_eval_high_success.json
```

## 总结

### ✅ 可靠规则（推荐优先使用）
- **T03, T19, T20, T31, T45** - 成功率80-100%

### ⚠️ 条件规则（需特定代码模式）
- **T32, T47, T09, T30, T12** - 成功率6.7-40%

### ❌ 待优化规则（当前不推荐）
- **T07, T10, T34, T41, T48** - 成功率0%

**整体评估**: 15个规则中有**5个高成功率规则**可以覆盖大部分攻击场景，**5个中等规则**可以针对特定代码模式，**5个规则**需要优化或限定使用场景。
