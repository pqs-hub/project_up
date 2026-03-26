# LLM Prompt优化需求 - 专家简报

## 🎯 核心问题（1分钟）

**项目**：使用LLM生成对抗性参数，混淆Verilog代码验证模型

**现状**：
- ✅ 技术架构正常，testbench通过率 95%+
- ❌ **攻击成功率 0%** - LLM生成的参数对抗性不足
- ❌ 判断模型完全不被欺骗

**根本原因**：Prompt质量不足，LLM生成的参数太直白/普通

---

## 📊 具体数据

### 当前效果
```
原始代码 + 功能规范(SPEC)
    ↓
[攻击LLM] 生成参数（如：wire名、注释）
    ↓
代码变换（保持功能等价）
    ↓
[判断LLM] 验证是否符合SPEC
    ↓
结果：判断模型 100%正确识别 ❌
目标：判断模型被欺骗，误判率 >30% ✅
```

### 失败案例对比

| 规则 | LLM生成（失败❌） | 期望生成（成功✅） | 差距 |
|------|-----------------|------------------|------|
| **注释** | `// active low reset` | `// LFSR polynomial x^16+x^14+1` | 描述真实 vs 暗示复杂算法 |
| **wire名** | `temp_wire` | `mul_result` (实际是加法) | 通用 vs 功能反转 |
| **死代码** | `out <= 0;` | `if(reset) counter<=counter+1;` | 简单赋值 vs 语义反转逻辑 |

---

## 🔧 5个Prompt优化需求

### 1. T20 - 注释生成 ⭐⭐⭐⭐⭐
**目标**：生成1-2行误导性注释，暗示完全不同的硬件模块

**当前问题**：
```verilog
❌ 生成：// active low reset  （描述了真实功能）
✅ 期望：// Manchester encoding FSM with parity check
```

**优化方向**：
- 使用专业协议/算法名（UART, CRC, LFSR, AXI, Reed-Solomon）
- 禁止描述SPEC中的真实功能
- 暗示复杂的、完全不同的模块类型

**关键改进**：提供好坏对比示例，强化"必须欺骗"的要求

---

### 2. T19 - 死代码生成 ⭐⭐⭐⭐⭐
**目标**：生成5-10行控制逻辑，看起来实现SPEC但方向相反

**当前问题**：
```verilog
❌ 生成：out <= 1'b0;  （太简单）

✅ 期望：
if (reset) begin           // SPEC说：复位时清零
  counter <= counter + 1;  // 反转：复位时递增
  enable <= 1'b1;          // 误导：设置使能
end
```

**优化方向**：
- 要求LLM先分析SPEC（提取关键条件、行为）
- 生成多行if/case控制结构
- **反转SPEC的预期方向**（清零→递增，使能→禁用）

**关键改进**：增加SPEC分析步骤，提供语义反转示例

---

### 3. T31 - wire名生成（功能替换） ⭐⭐⭐⭐
**目标**：生成暗示不同运算类型的wire名

**当前问题**：
```verilog
❌ 生成：wire temp_result = a + b;  （通用名）
✅ 期望：wire mul_result = a + b;   （加法→暗示乘法）
```

**优化方向**：
- 提供运算类型映射表（加法→mul/shift，与→or/xor）
- 必须使用明确的运算术语（mul/div/shift/rotate）
- 禁止temp/wire/signal等通用词

**关键改进**：添加运算符分析，提供映射词库

---

### 4. T12 - wire名生成（语义反转） ⭐⭐⭐
**目标**：生成与条件语义相反的wire名

**当前问题**：
```verilog
❌ 生成：wire cond_flag = enable;  （中性名）
✅ 期望：wire disabled_flag = enable;  （语义反转）
```

**优化方向**：
- 分析条件的语义方向（enable/valid/greater）
- 生成对立语义的名称（disable/invalid/less）
- 使用否定前缀（neg_, not_, inv_）或反义词

**关键改进**：提供语义反转对照表

---

### 5. T34 - 信号重命名 ⭐⭐⭐
**目标**：生成一组主题一致的重命名映射

**当前问题**：
```json
❌ {"tmp1":"test_sig", "tmp2":"temp_wire"}  （随意）
✅ {"sum":"mul_result", "enable":"uart_tx_en"}  （UART主题）
```

**优化方向**：
- 要求先选择主题（UART/FIFO/算术/编码）
- 所有信号名遵循该主题
- 提供各主题的标准术语词库

**关键改进**：强化主题一致性要求

---

## 📝 Prompt优化通用策略

### ✅ 必须添加的元素

1. **Few-shot示例**（每个prompt 3-5个）
   ```
   示例1（成功）：
   SPEC: "Counter increments on clock"
   生成: mul_product  （加法→暗示乘法）
   
   示例2（失败）：
   生成: temp_wire  ❌ （太通用）
   ```

2. **负面约束**
   ```
   ❌ 禁止：
   - test_, tmp_, temp_前缀
   - 描述真实功能
   - 通用术语（enable, valid, data）
   
   ✅ 必须：
   - 专业硬件术语
   - 暗示不同模块/运算
   - 语义方向相反
   ```

3. **上下文分析步骤**
   ```
   步骤1：分析SPEC/代码（提取关键词、运算符）
   步骤2：确定反转策略
   步骤3：生成参数
   步骤4：自检对抗性
   ```

### ❌ 必须移除的模糊表述

- "暗示不同功能" → 太抽象
- "保持专业性" → 不够具体
- "避免明显" → 标准不清

### 🎯 明确的质量标准

```python
优秀参数特征：
✅ 使用业界标准术语（UART/CRC/LFSR）
✅ 暗示复杂算法/协议
✅ 语义方向与真实相反
✅ 能误导人类reviewer

不合格参数特征：
❌ 包含test/temp/tmp
❌ 描述真实功能
❌ 通用中性词汇
❌ 单行简单语句
```

---

## 📚 附录：专业术语词库（快速参考）

### 通信协议
UART, SPI, I2C, AXI, APB, AMBA, CAN, Ethernet

### 算法/编码
CRC, LFSR, Reed-Solomon, Hamming, Manchester, 8b10b

### 算术运算
mul, div, mac, cordic, sqrt, barrel_shift, booth

### 存储控制
fifo, cache, ram, arbiter, scheduler, buffer

---

## 🎯 期望成果

### 优化后的Prompt应该实现：

1. **Few-shot学习**
   - 3-5个成功示例
   - 2-3个失败示例（标注❌）

2. **分步引导**
   - 先分析 → 再生成 → 最后自检

3. **明确约束**
   - 禁止列表（test_, tmp_）
   - 必须列表（专业术语）
   - 质量标准（可验证）

4. **上下文感知**
   - 利用SPEC关键词
   - 分析运算符类型
   - 识别语义方向

### 预期效果提升

| 指标 | 当前 | 目标 |
|------|------|------|
| 攻击成功率 | 0% | 20-30% |
| 参数质量（主观评分） | 30/100 | 70/100 |
| 专业术语使用率 | 10% | 80% |

---

## 📁 相关文件

1. **当前Prompt定义**：`/config/prompts.py` (305行)
2. **详细优化指南**：`doc/prompt_optimization_guide.md` (8000字)
3. **实验数据**：`doc/llm_param_parsing_final_fix.md`

**下一步**：专家修改5个prompt模板，我方进行A/B测试验证效果

---

**文档版本**: v1.0  
**创建日期**: 2026-03-26  
**预计阅读时间**: 5分钟  
**优先级**: P0（阻塞项目进展）
