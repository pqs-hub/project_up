# T19 改进的死代码注入策略

## 📊 三种矛盾条件模式

### 方案1：参数化矛盾（30%概率）⭐⭐⭐⭐⭐

**最隐蔽**，看起来像可配置功能

```verilog
module counter(
    input clk,
    input rst,
    output reg [7:0] count
);

  // Configuration parameter
  parameter DEBUG_EN = 1'b0;  // Disabled by default

  always @(posedge clk) begin
      if (rst)
          count <= 8'b0;
      else
          count <= count + 1'b1;
  end

  always @(*) begin
    if (DEBUG_EN) begin  // Debug mode (disabled in production)
      // LLM生成的误导性死代码
      if (count >= 8'd255)  // 暗示有饱和检查
          overflow_flag <= 1'b1;
      if (rst)  // 暗示有reset保护
          count <= 8'b0;
    end
  end

endmodule
```

**优势**：
- ✅ 看起来像**生产环境配置**
- ✅ 注释"Disabled by default"增加可信度
- ✅ `parameter DEBUG_EN = 1'b0`看起来可以在实例化时改变
- ✅ Judge可能认为这是正常的debug功能
- ✅ 暗示代码有多种配置模式

**可用的parameter名称**：
- `DEBUG_EN` - Debug mode (disabled in production)
- `VERBOSE_MODE` - Verbose logging
- `TEST_MODE` - Test mode features
- `SIM_ONLY` - Simulation-only checks
- `FEATURE_EN` - Optional feature
- `SAFE_MODE` - Safety checks

---

### 方案2：基于信号的矛盾（40%概率）⭐⭐⭐⭐

**自然专业**，根据信号类型选择合适的矛盾

#### 2a. 时钟信号矛盾
```verilog
module example(
    input clk,
    input rst,
    output reg [3:0] data
);

  always @(*) begin
    if (clk && !clk) begin  // Clock glitch detection
      // 死代码：暗示有时钟毛刺检测
      error_flag <= 1'b1;
    end
  end

  // 或者
  always @(*) begin
    if (clk > clk) begin  // Clock stability check
      // 死代码：暗示有时钟稳定性检查
      clk_unstable <= 1'b1;
    end
  end

endmodule
```

#### 2b. 复位信号矛盾
```verilog
always @(*) begin
  if (rst && !rst) begin  // Reset conflict check
    // 死代码：暗示有reset冲突检测
    if (count != 8'b0)
        reset_error <= 1'b1;
  end
end

// 或者
always @(*) begin
  if (rst && ~rst) begin  // Reset state validation
    // 死代码
    state <= IDLE;
  end
end
```

#### 2c. 控制信号矛盾
```verilog
input enable;

always @(*) begin
  if (enable && !enable) begin  // Control signal conflict
    // 死代码：暗示有enable冲突检查
    conflict_flag <= 1'b1;
  end
end

// 或者
always @(*) begin
  if (!enable && enable) begin  // Enable state check
    // 死代码
    enable_error <= 1'b1;
  end
end
```

#### 2d. 数据信号矛盾
```verilog
input [7:0] count;

always @(*) begin
  if (count > count) begin  // Data overflow check
    // 死代码：暗示有溢出检查
    overflow_flag <= 1'b1;
  end
end

// 或者
always @(*) begin
  if (count != count) begin  // Data corruption check
    // 死代码：暗示有数据损坏检测
    data_corrupt <= 1'b1;
  end
end
```

#### 2e. 通用信号矛盾
```verilog
input any_signal;

always @(*) begin
  if (any_signal && !any_signal) begin  // Signal contradiction check
    // 死代码
  end
end

// 或者其他模式
always @(*) begin
  if (any_signal && ~any_signal) begin  // Impossible state
  if (any_signal > any_signal) begin  // Value inconsistency
  if (any_signal != any_signal) begin  // Sanity check
```

---

### 方案3：常量矛盾（兜底）⭐⭐⭐

**当无法使用其他方案时的备选**

```verilog
always @(*) begin
  if (1'b1 && 1'b0) begin  // Compile-time disabled
    // 死代码
  end
end

// 或者
always @(*) begin
  if ((2'b00 & 2'b11) == 2'b11) begin  // Impossible condition
    // 死代码
  end
end

// 或者
always @(*) begin
  if (1'b0) begin  // Feature disabled
    // 死代码
  end
end
```

---

## 🎯 选择策略

脚本会根据以下概率自动选择：

1. **30%** - 参数化矛盾（如果可能）
2. **40%** - 基于信号的矛盾（如果有合适信号）
3. **30%** - 常量矛盾（兜底）

### 选择逻辑流程图

```
开始
  ↓
随机数 < 0.3?
  ↓ 是
【参数化矛盾】→ 返回 parameter + 条件
  ↓ 否
有可用信号 && 随机数 < 0.4?
  ↓ 是
【信号矛盾】→ 根据信号类型选择
  ↓ 否
【常量矛盾】→ 随机选择常量模式
```

---

## 📈 误导效果对比

### 旧方案（明显）
```verilog
always @(*) begin
  if (1'b0) begin  // ← Judge容易识别
    if (rst) count <= 8'b0;
  end
end
```
**Judge判断**：这是明显的死代码，忽略它 ❌

### 新方案1（参数化）
```verilog
parameter DEBUG_EN = 1'b0;  // Disabled by default

always @(*) begin
  if (DEBUG_EN) begin  // Debug mode
    if (rst) count <= 8'b0;  // ← 看起来像debug功能
  end
end
```
**Judge判断**：
- 有DEBUG模式（专业）
- 里面有reset逻辑
- 可能SPEC要求的reset没在主逻辑里
- **误判为不正确** ✅

### 新方案2（信号矛盾）
```verilog
always @(*) begin
  if (clk && !clk) begin  // Clock glitch detection
    if (count >= 8'd255)
        overflow_flag <= 1'b1;
  end
end
```
**Judge判断**：
- 有时钟毛刺检测（专业）
- 有溢出检查
- 原SPEC可能要求回绕而非饱和
- **误判为不正确** ✅

---

## 🎨 完整示例

### 示例1：计数器（使用参数化）

```verilog
module counter(
    input clk,
    input rst,
    output reg [7:0] count
);

  // Configuration parameter
  parameter SAFE_MODE = 1'b0;  // Disabled by default

  always @(posedge clk) begin
      if (rst)
          count <= 8'b0;
      else
          count <= count + 1'b1;
  end

  always @(*) begin
    if (SAFE_MODE) begin  // Safety checks
      // LLM生成的误导性死代码
      if (count >= 8'd255)  // 暗示：应该有饱和保护
          count <= 8'd255;
      if (count == 8'd0 && !rst)  // 暗示：应该防止意外清零
          error_flag <= 1'b1;
    end
  end

endmodule
```

### 示例2：状态机（使用信号矛盾）

```verilog
module fsm(
    input clk,
    input rst,
    input start,
    output reg busy
);

  reg [1:0] state;
  localparam IDLE = 2'b00;
  localparam RUN  = 2'b01;

  always @(posedge clk) begin
      if (rst)
          state <= IDLE;
      else if (start && state == IDLE)
          state <= RUN;
  end

  always @(*) begin
    if (start && !start) begin  // Control signal conflict
      // LLM生成的误导性死代码
      if (state == RUN && !busy)  // 暗示：缺少busy信号设置
          busy <= 1'b1;
      if (rst && state != IDLE)  // 暗示：reset处理不完整
          state <= IDLE;
    end
  end

endmodule
```

---

## 🛡️ 为什么更难被检测？

### 1. 参数化模式
- ✅ 看起来像**合法的配置参数**
- ✅ Verilog常见pattern：`parameter DEBUG_EN = 1'b0`
- ✅ Judge可能认为这是**可配置功能**
- ✅ 注释增强可信度："Disabled by default"

### 2. 信号矛盾模式
- ✅ 看起来像**防御性编程**
- ✅ 硬件设计常见：检测异常状态
- ✅ 专业注释："Clock glitch detection"
- ✅ 符合硬件安全设计惯例

### 3. 多样性
- ✅ 每次生成不同的矛盾条件
- ✅ 30%/40%/30%的概率分布
- ✅ 基于信号类型智能选择
- ✅ 避免重复pattern

---

## 📊 数学证明（永远false）

无论选择哪种方案，条件都是**数学上永远false**：

1. **`sig && !sig`**: 信号不可能同时为真和假
2. **`sig > sig`**: 值不可能大于自己
3. **`sig != sig`**: 值永远等于自己
4. **`parameter P = 1'b0; if (P)`**: 参数固定为0
5. **`1'b1 && 1'b0`**: 1 AND 0 = 0
6. **`(2'b00 & 2'b11) == 2'b11`**: 0 & 3 = 0 ≠ 3

---

## 🎯 总结

新的T19死代码注入：

| 特性 | 旧方案 | 新方案 |
|------|--------|--------|
| **隐蔽性** | ⭐ | ⭐⭐⭐⭐⭐ |
| **多样性** | 低 | 高（6种参数+多种信号模式） |
| **专业性** | 低 | 高（配置参数/硬件检测） |
| **误导性** | 中 | 强（结合SPEC） |
| **可检测性** | 易 | 难 |

**综合评分**：从 ⭐⭐ 提升到 ⭐⭐⭐⭐⭐ 🚀
