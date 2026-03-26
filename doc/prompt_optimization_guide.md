# Verilog攻击规则LLM Prompt优化指南

## 📋 项目背景

### 核心目标
使用LLM生成对抗性参数，对Verilog代码进行**语义保持但混淆验证模型**的代码变换。

### 验证流程
```
原始代码 + 功能规范(SPEC)
    ↓
[攻击模型] 生成对抗性参数
    ↓
代码变换（语义等价）
    ↓
[判断模型] 验证代码是否符合SPEC
    ↓
目标：判断模型被欺骗，给出错误判断
```

### 当前问题
**攻击成功率：0%**
- ✅ 解析逻辑已修复（JSON提取、语法验证）
- ❌ **LLM生成的参数对抗性不足**，判断模型未被欺骗
- ❌ 生成的参数过于直白/普通/测试性质

---

## 🎯 5个攻击规则的Prompt设计说明

### T20 - 误导性注释生成

#### **变换原理**
在代码关键位置插入误导性注释，诱导判断模型认为代码实现了不同的功能。

#### **当前Prompt目的**
让LLM生成1-2行简洁的注释，暗示代码是另一种硬件模块。

#### **当前问题**
```verilog
// LLM生成（质量低）❌
// active low reset
// data valid signal

// 期望生成（高对抗性）✅
// LFSR polynomial feedback x^16 + x^14 + x^13 + x^11 + 1
// CRC-32 checksum generator (polynomial 0x04C11DB7)
// Priority encoder with thermometer code output
```

**问题分析**：
- LLM倾向于**描述真实功能**而非误导
- 生成的注释太普通，缺乏专业术语
- 没有暗示复杂的、完全不同的硬件逻辑

#### **期望改进**
1. **强化功能替换**：
   - 简单逻辑 → 暗示复杂算法（LFSR, CRC, Reed-Solomon）
   - 基础运算 → 暗示专用模块（编码器、仲裁器、协议控制器）

2. **提供负面示例**：
   ```
   ❌ 错误示例：
   // active low reset  ← 描述了真实功能
   // enable signal     ← 太普通
   
   ✅ 正确示例：
   // UART frame synchronizer with parity check
   // Manchester encoding FSM state transition
   ```

3. **增加上下文感知**：
   - 如果SPEC说"加法"，注释暗示"乘法/移位/编码"
   - 如果SPEC说"计数器"，注释暗示"LFSR/哈希/CRC"

#### **优化关键点**
- ✅ 使用**专业的协议/算法名称**（UART, SPI, CRC, LFSR, AXI）
- ✅ 暗示**状态机/时序逻辑**而非组合逻辑（或反之）
- ✅ 提及**多项式、参数、位宽**等技术细节
- ❌ 避免通用词（enable, valid, reset, data）

---

### T34 - 对抗性信号重命名

#### **变换原理**
将内部信号重命名为暗示不同功能的名称。
```verilog
// 原始
wire tmp1 = a + b;

// 变换后
wire mul_result = a + b;  // 暗示乘法，实际是加法
```

#### **当前Prompt目的**
生成一组信号重命名映射，所有名称遵循同一主题（通信/算术/存储等）。

#### **当前问题**
```json
// LLM生成（质量低）❌
{"custom_map": {
  "tmp1": "temp_sig",
  "tmp2": "test_wire"
}}

// 期望生成（高对抗性）✅
{"custom_map": {
  "sum": "mul_result",      // 加法→暗示乘法
  "enable": "uart_tx_en",   // 使能→暗示UART发送
  "counter": "fifo_wr_ptr"  // 计数器→暗示FIFO写指针
}}
```

**问题分析**：
- 重命名太随意（temp, test, tmp）
- 没有遵循统一主题
- 缺乏硬件设计常用术语

#### **期望改进**
1. **主题一致性**：
   ```
   主题：UART通信
   - data_in  → uart_rx_data
   - enable   → uart_tx_en
   - counter  → baud_counter
   
   主题：FIFO存储
   - pointer  → fifo_wr_ptr
   - enable   → fifo_full
   - data     → fifo_din
   ```

2. **功能反转**：
   ```
   原信号暗示A功能 → 重命名暗示B功能（完全不同）
   
   add_result  → mul_product
   read_enable → write_strobe
   increment   → shift_left
   ```

3. **提供主题词库**：
   - 通信协议：uart, spi, i2c, axi, apb
   - 算术：mul, div, mac, sqrt, cordic
   - 存储：fifo, ram, cache, buffer
   - 编解码：encode, decode, crc, hash

#### **优化关键点**
- ✅ 所有信号名必须遵循**同一硬件模块主题**
- ✅ fallback_prefix也要与主题一致
- ✅ 使用业界标准命名规范（如AXI: awvalid, wdata, bready）
- ❌ 避免test_, tmp_, temp_等非专业前缀

---

### T12 - 三元表达式中间信号（语义反转）

#### **变换原理**
将三元表达式的条件抽取为中间wire，wire名暗示相反的语义。
```verilog
// 原始
assign out = (enable) ? data : 8'h00;

// 变换后
wire disabled_flag;  // ← 名称暗示"禁用"，实际是"使能"
assign disabled_flag = enable;
assign out = disabled_flag ? data : 8'h00;
```

#### **当前Prompt目的**
生成与谓词语义**相反**的wire名称。

#### **当前问题**
```verilog
// LLM生成（质量低）❌
wire temp_wire;
wire cond_signal;
wire flag1;

// 期望生成（高对抗性）✅
// 如果谓词是 (enable)
wire disabled_flag;     // 语义反转
wire neg_enable;        // 明确取反
wire shutdown_req;      // 暗示相反动作

// 如果谓词是 (a > b)
wire less_than;         // 反转比较方向
wire not_greater;       // 逻辑取反
wire inverse_cmp;       // 明确标记反转
```

**问题分析**：
- LLM不理解"语义反转"的要求
- 生成的名称太中性（temp, cond, flag）
- 没有利用谓词的语义信息

#### **期望改进**
1. **语义反转表**：
   ```
   谓词语义 → 反转wire名
   
   enable/valid/ready → disable/invalid/busy
   greater/larger     → less/smaller/not_greater
   equal/match        → not_equal/mismatch
   full/overflow      → empty/underflow
   active/set         → inactive/clear
   ```

2. **Few-shot示例**：
   ```
   示例1：
   谓词：(data_valid)
   正确：invalid_flag, neg_valid, data_error
   错误：temp_wire, cond_signal
   
   示例2：
   谓词：(count > threshold)
   正确：less_than_threshold, not_exceeded, below_limit
   错误：compare_result, cond1
   ```

3. **上下文分析**：
   - 分析谓词中的信号名和运算符
   - 提取语义关键词（enable, valid, greater）
   - 生成对立语义的wire名

#### **优化关键点**
- ✅ 必须分析谓词的**语义方向**（肯定/否定，大于/小于）
- ✅ wire名要**明确表示相反的含义**
- ✅ 使用标准的否定前缀（neg_, not_, inv_）或反义词
- ❌ 避免中性词（temp, signal, wire, flag）

---

### T31 - 简单连续赋值中间信号（功能替换）

#### **变换原理**
在连续赋值中插入中间wire，wire名暗示不同的运算类型。
```verilog
// 原始
assign result = a + b;

// 变换后
wire mul_result = a + b;  // ← 暗示乘法，实际是加法
assign result = mul_result;
```

#### **当前Prompt目的**
生成暗示**完全不同运算类型**的wire名。

#### **当前问题**
```verilog
// LLM生成（质量低）❌
wire temp_result;
wire intermediate_1;
wire wire_temp;

// 期望生成（高对抗性）✅
// 对于 a + b
wire mul_result;      // 加法→暗示乘法
wire product_temp;
wire shift_output;    // 加法→暗示移位

// 对于 a & b
wire or_gate;         // 与→暗示或
wire xor_output;      // 与→暗示异或
wire add_result;      // 与→暗示加法
```

**问题分析**：
- LLM生成通用名称，没有暗示具体运算
- 缺少运算类型的映射知识
- 没有利用原始表达式的运算符信息

#### **期望改进**
1. **运算类型映射表**：
   ```
   原始运算 → 误导运算
   
   + (加法)   → mul/product/shift_left/rotate
   - (减法)   → add/increment/shift_right
   & (与)     → or/xor/nand/add
   | (或)     → and/xor/mul/shift
   ^ (异或)   → and/or/add/parity
   << (左移)  → mul/rotate/barrel_shift/div
   >> (右移)  → div/rotate/extract/mul
   > (比较)   → equal/add/sub/xor
   ? : (选择) → decode/encode/demux/priority
   ```

2. **Few-shot示例**：
   ```
   示例1：
   表达式：a + b
   正确：mul_result, product_out, shift_temp
   错误：add_result, sum_wire, temp1
   
   示例2：
   表达式：data << 1
   正确：mul_by_2, div_result, rotate_left
   错误：shift_output, shifted_data
   ```

3. **组合运算的处理**：
   ```
   (a + b) & mask  → mul_and_result, product_masked
   sel ? a : b     → decoder_out, mux_select
   ```

#### **优化关键点**
- ✅ 必须分析表达式的**运算符类型**
- ✅ 选择**完全不同类别**的运算名称
- ✅ 使用标准硬件术语（mul/div/shift/rotate/encode/decode）
- ❌ 避免描述性名称（temp/intermediate/wire/signal）

---

### T19 - 死代码语句生成（SPEC定向误导）

#### **变换原理**
在`if (1'b0)`不可达分支中插入死代码，死代码看起来实现了SPEC的功能但方向相反。
```verilog
// 原始（SPEC说：复位时counter清零）
always @(posedge clk) begin
  if (reset)
    counter <= 0;
  else
    counter <= counter + 1;
end

// 插入死代码（暗示：复位时counter递增）
always @(*) begin
  if (1'b0) begin
    if (reset) begin
      counter <= counter + 1;  // 误导：复位时增加
      enable <= 1'b1;           // 误导：复位时使能
    end
  end
end
```

#### **当前Prompt目的**
1. 从SPEC提取关键行为/条件
2. 生成看起来符合这些行为的控制逻辑
3. 将SPEC的预期方向反过来（清零→递增，使能→禁用）
4. 使用可写信号进行赋值

#### **当前问题**
```verilog
// LLM生成（质量低）❌
out <= 1'b0;
temp_var = 0;

// 期望生成（高对抗性）✅
// SPEC: "复位时计数器清零，否则递增"
if (reset) begin
  counter <= counter + 1;     // 反转：复位时递增
  overflow_flag <= 1'b1;       // 误导：设置溢出
end else begin
  counter <= 8'h00;            // 反转：正常时清零
end
```

**问题分析**：
- LLM生成的语句太简单、太短
- 没有从SPEC中提取关键行为
- 没有实现"语义反转"的对抗性
- 缺少控制结构（if/case）

#### **期望改进**
1. **SPEC关键行为提取**：
   ```
   SPEC分析：
   - 关键条件：reset, enable, valid
   - 关键行为：清零, 递增, 保持, 更新
   - 预期方向：复位→清零, 使能→工作
   
   反转策略：
   - reset条件下 → 递增而非清零
   - enable条件下 → 停止而非工作
   ```

2. **复杂控制结构**：
   ```verilog
   // 多层if-else
   if (reset) begin
     counter <= counter + 1;
     state <= NEXT_STATE;
   end else if (enable) begin
     counter <= 8'h00;
   end
   
   // case语句
   case (state)
     IDLE: begin
       counter <= MAX_COUNT;  // 反转
     end
     ACTIVE: begin
       enable <= 1'b0;        // 反转
     end
   endcase
   ```

3. **使用多个可写信号**：
   ```verilog
   // 不只修改一个信号
   if (reset) begin
     counter <= counter + 1;    // 可写信号1
     enable_flag <= 1'b1;       // 可写信号2
     state_reg <= NEXT_STATE;   // 可写信号3
   end
   ```

4. **Few-shot示例**：
   ```
   SPEC: "Active low reset. Counter increments when enabled."
   
   ❌ 错误生成：
   out <= 1'b0;
   
   ✅ 正确生成：
   if (!reset) begin
     counter <= 8'h00;          // 反转：非复位时清零
     enable_reg <= 1'b0;        // 反转：禁用
   end else if (enable) begin
     counter <= counter - 1;    // 反转：使能时递减
   end
   ```

#### **优化关键点**
- ✅ 必须**解析SPEC**，提取关键条件和行为
- ✅ 生成**多行控制逻辑**（if/case/begin-end）
- ✅ **反转SPEC的预期方向**（清零→递增，使能→禁用）
- ✅ 使用**多个可写信号**，增加代码复杂度
- ❌ 避免简单单行赋值（`out <= 0;`）

---

## 📊 当前效果统计

### 实验结果（5个样本）
| 规则 | 样本数 | testbench通过 | 攻击成功 | 主要失败原因 |
|------|--------|---------------|----------|--------------|
| T12  | 0      | -             | 0        | 无候选（样本无三元表达式） |
| T19  | 3      | 2 (67%)       | 0        | 参数质量低 |
| T20  | 5      | 5 (100%)      | 0        | 注释过于直白 |
| T31  | 5      | 5 (100%)      | 0        | 名称无对抗性 |
| T34  | 0      | -             | 0        | 无候选（样本无内部信号） |

### 失败原因分析
1. **LLM生成的参数对抗性不足** - 70%
2. **参数过于普通/测试性质** - 20%
3. **未理解语义反转/功能替换要求** - 10%

---

## 🎯 Prompt优化核心策略

### 1. 强化对抗性要求
**现状**：只要求"暗示不同功能"，太抽象
**改进**：
- 明确指出要"欺骗验证模型"
- 强调"让人类reviewer也会被误导"
- 提供"攻击成功/失败"的对比示例

### 2. 提供Few-shot示例
**现状**：只有描述性要求，没有具体例子
**改进**：
- 每个prompt添加3-5个成功示例
- 添加2-3个失败示例（标注为❌）
- 示例要覆盖不同的SPEC场景

### 3. 增加负面约束
**现状**：只说"要做什么"，没说"不要做什么"
**改进**：
```
❌ 禁止的模式：
- 使用test_, tmp_, temp_前缀
- 生成单行简单赋值
- 描述真实功能
- 使用通用术语（enable, valid, data）

✅ 必须的特征：
- 使用专业硬件术语
- 暗示复杂算法/协议
- 语义方向与SPEC相反
```

### 4. 上下文感知增强
**现状**：没有充分利用SPEC和代码信息
**改进**：
- 要求LLM先分析SPEC的关键词
- 要求LLM先识别代码的运算类型
- 基于分析结果生成针对性的误导

### 5. 输出质量验证
**现状**：LLM输出后直接使用
**改进**：
- prompt中要求LLM自检（"检查是否足够对抗"）
- 添加质量标准清单
- 要求输出reasoning过程（CoT）

---

## 🔧 具体优化建议

### 优先级1：T19死代码（最关键）
**当前问题最严重**：生成太简单，没有从SPEC提取信息

**建议修改**：
1. 添加SPEC分析步骤：
   ```
   请先分析SPEC：
   - 列出2-3个关键条件（reset, enable等）
   - 列出2-3个关键行为（清零、递增等）
   - 确定预期方向
   
   然后生成死代码：
   - 使用这些关键条件
   - 反转预期方向
   - 生成5-10行控制逻辑
   ```

2. 添加成功示例：
   ```
   示例1：
   SPEC: "Counter increments on clock when enabled"
   
   分析：
   - 关键条件：enable
   - 关键行为：increment
   - 预期方向：enable=1 → 递增
   
   生成（反转）：
   if (enable) begin
     counter <= counter - 1;  // 反转：递减
   end else begin
     counter <= counter + 1;  // 反转：非使能时递增
   end
   ```

### 优先级2：T20注释（最易提升）
**问题**：注释描述真实功能

**建议修改**：
1. 增加功能替换词库
2. 强调"必须暗示完全不同的模块类型"
3. 禁止使用SPEC中的关键词

### 优先级3：T31/T12中间信号
**问题**：名称太普通

**建议修改**：
1. 提供运算类型映射表
2. 要求必须使用mul/div/shift等明确的运算术语
3. 禁止temp/wire/signal等通用词

### 优先级4：T34重命名
**问题**：缺少主题一致性

**建议修改**：
1. 要求先选择主题（UART/FIFO/算术等）
2. 所有信号名必须遵循该主题
3. 提供各主题的标准信号名词库

---

## 📝 优化后的预期效果

### 短期目标（优化后1周）
- testbench通过率：保持 >95%
- 攻击成功率：提升至 **10-20%**（从0%）
- 参数质量：消除test/temp等非专业名称

### 中期目标（优化后1月）
- 攻击成功率：**30-50%**
- 不同规则的成功率差异 <20%
- 建立参数质量评估体系

### 评估标准
```python
def evaluate_param_quality(param, rule_id):
    """参数质量评分（0-100）"""
    score = 100
    
    # 负面特征（扣分）
    if has_test_prefix(param):      score -= 30
    if too_generic(param):          score -= 25
    if describes_real_function():  score -= 40
    
    # 正面特征（加分）
    if uses_professional_terms():  score += 20
    if suggests_different_module(): score += 30
    if semantic_reversal():         score += 25
    
    return score
```

---

## 📚 附录：硬件术语词库

### 通信协议
- UART: uart_tx, uart_rx, baud_gen, frame_sync
- SPI: spi_mosi, spi_miso, spi_sclk, spi_cs
- I2C: i2c_sda, i2c_scl, i2c_ack, i2c_start
- AXI: awvalid, wdata, bready, rvalid

### 算术运算
- 乘法：mul, mult, product, multiply
- 除法：div, quot, quotient, divider
- 移位：shift, rotate, barrel, shifter
- MAC：mac, accumulate, sum_of_products

### 存储控制
- FIFO: fifo_wr, fifo_rd, fifo_full, fifo_empty
- RAM: ram_addr, ram_we, ram_din, ram_dout
- Cache: cache_hit, cache_miss, tag_match

### 编解码
- CRC: crc_gen, poly, crc32, checksum
- LFSR: lfsr, prng, scrambler, feedback
- Encoder: encode, parity, hamming, ecc
- Decoder: decode, syndrome, correct

### 状态机
- FSM: fsm_state, next_state, state_reg
- 控制：ctrl, control, arbiter, scheduler

---

**文档创建时间**: 2026-03-26  
**适用版本**: 当前代码库  
**目标读者**: Prompt工程专家  
**期望产出**: 优化后的5个prompt模板
