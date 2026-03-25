# 为什么某些规则无法保持功能等价

## 问题总结

19个规则中：
- **10个规则**能保持功能等价（<5%改变率）
- **7个规则**有中等改变率（10%-40%）
- **2个规则**有高改变率（>40%）：T31（57.3%）、T47（95.0%）

## 规则分析

### ✅ 能保持功能等价的规则（<5%）

#### T30 - 常量等价变换（0.0%）
```verilog
// 原始: assign x = 1'b0;
// 变换: assign x = (1'b1 & 1'b0);  // 等价表达式
```
**为什么等价**：纯粹的逻辑等价替换，不涉及结构改变

---

#### T32 - 位宽算术混淆（0.0%）
```verilog
// 原始: wire [7:0] data;
// 变换: wire [8-1:1-1] data;  // 8-1=7, 1-1=0
```
**为什么等价**：纯粹的算术等价，位宽完全相同

---

#### T19 - 死代码注入（0.3%）
```verilog
// 原始: always @(posedge clk) out <= in;
// 变换: always @(posedge clk) begin
//         out <= in;
//         if (1'b0) out <= ~in;  // 永远不执行
//       end
```
**为什么等价**：死代码永远不会执行，不影响功能

**0.3%改变的原因**：可能是边界情况，如：
- 死代码中引用了不存在的信号
- 语法错误

---

#### T20 - 误导性注释（0.6%）
```verilog
// 原始: assign out = a + b;
// 变换: // This is a multiplier
//       assign out = a + b;
```
**为什么等价**：注释不影响功能

**0.6%改变的原因**：可能是注释插入位置不当，破坏了语法

---

#### T34 - 信号重命名（1.6%）
```verilog
// 原始: wire enable; assign out = enable;
// 变换: wire unused_enable; assign out = unused_enable;
```
**为什么等价**：只是改名，逻辑不变

**1.6%改变的原因**：
- 重命名时可能遗漏某些引用
- 端口重命名可能导致接口不匹配

---

### ⚠️ 中等改变率的规则（10%-40%）

#### T03 - Case重排序（15.6%）
```verilog
// 原始: case(sel) 0: out=a; 1: out=b; endcase
// 变换: case(sel) 1: out=b; 0: out=a; endcase
```
**为什么会改变**：
- 如果有`default`分支，重排序可能改变优先级
- 如果case不是完全并行的，顺序可能影响结果

---

#### T09/T10 - DeMorgan变换（20.4%/36.6%）
```verilog
// 原始: assign out = a & b;
// 变换: assign out = ~(~a | ~b);
```
**为什么会改变**：
- 位宽不匹配：如果`a`和`b`位宽不同
- 未定义值（X/Z）的处理不同
- 可能引入额外的信号声明问题

---

#### T12 - 中间信号注入（20.9%）
```verilog
// 原始: assign out = cond ? a : b;
// 变换: wire tmp = cond ? a : b; assign out = tmp;
```
**为什么会改变**：
- 与T31类似的问题（见下文）
- 但改变率较低，说明实现相对更好

---

### ❌ 高改变率的规则（>40%）

#### T31 - 中间信号注入（57.3%）⚠️

**实现**：
```python
def ast_simple_assign_intermediate(code, vs, target, wire_name=''):
    # 生成中间信号名
    tmp_name = f'__{target.lhs_name}_tmp'
    
    # 插入wire声明和新的assign
    wire_decl = f'{indent}wire {tmp_name} = {target.rhs};\n'
    new_assign = f'{indent}assign {target.lhs} = {tmp_name};'
    
    return code[:line_start] + wire_decl + new_assign + code[target.end:]
```

**为什么会改变功能（57.3%）**：

##### 问题1：wire声明位置不当
```verilog
// 原始代码
module test(input a, output b);
  assign b = a;
endmodule

// 变换后（可能错误）
module test(input a, output b);
  wire __b_tmp = a;  // ❌ wire声明在module内但在assign之前
  assign b = __b_tmp;
endmodule
```
**问题**：在某些Verilog版本中，`wire`的连续赋值声明（`wire x = expr;`）可能不被支持，或者与`assign`语句的语义不同。

##### 问题2：时序问题
```verilog
// 原始代码（组合逻辑）
assign out = a & b;

// 变换后
wire __out_tmp = a & b;  // 这是连续赋值
assign out = __out_tmp;  // 这也是连续赋值
```
**问题**：虽然理论上等价，但在某些综合工具中，两次连续赋值可能引入微小的时序差异。

##### 问题3：作用域问题
```verilog
// 原始代码
always @(*) begin
  assign out = a;  // ❌ 这本身就是错误的
end

// 如果T31应用在这里
wire __out_tmp = a;  // wire声明在哪里？
```

##### 问题4：位宽推断问题
```verilog
// 原始代码
assign out = a + b;  // out的位宽由a+b推断

// 变换后
wire __out_tmp = a + b;  // __out_tmp的位宽是多少？
assign out = __out_tmp;
```
**问题**：如果没有显式声明`__out_tmp`的位宽，可能导致位宽不匹配。

**修复建议**：
```python
def ast_simple_assign_intermediate(code, vs, target, wire_name=''):
    # 1. 获取目标信号的位宽
    lhs_width = get_signal_width(vs, target.lhs_name)
    
    # 2. 显式声明wire的位宽
    if lhs_width > 1:
        wire_decl = f'{indent}wire [{lhs_width-1}:0] {tmp_name};\n'
    else:
        wire_decl = f'{indent}wire {tmp_name};\n'
    
    # 3. 使用标准的assign语句，而非wire的连续赋值
    wire_assign = f'{indent}assign {tmp_name} = {target.rhs};\n'
    new_assign = f'{indent}assign {target.lhs} = {tmp_name};'
    
    return code[:line_start] + wire_decl + wire_assign + new_assign + code[target.end:]
```

---

#### T47 - Shannon展开（95.0%）⚠️⚠️⚠️

**实现**：
```python
def ast_dataflow_shattering(code, vs, target, width=4):
    # 对于 a == b，展开为位级比较
    if op == '==':
        for i in range(width):
            wires.append(f'wire _n{i+1:02d} = {a}[{i}] ^ {b}[{i}];')
        final_expr = ' & '.join([f'~_n{i+1:02d}' for i in range(width)])
        wires.append(f'assign {out_var} = {final_expr};')
    
    # 对于 a + b，展开为全加器链
    else:  # op == '+'
        wires.append(f'wire _n01 = {a}[0] ^ {b}[0];')
        wires.append(f'wire _c01 = {a}[0] & {b}[0];')
        for i in range(1, width):
            wires.append(f'wire _n{i+1:02d} = {a}[{i}] ^ {b}[{i}] ^ _c{i:02d};')
            wires.append(f'wire _c{i+1:02d} = ({a}[{i}] & {b}[{i}]) | ...')
        sum_bits = ', '.join([f'_n{i+1:02d}' for i in range(width)])
        wires.append(f'assign {out_var} = {{{sum_bits}}};')
```

**为什么会改变功能（95.0%）**：

##### 问题1：位宽假设错误（最严重）
```verilog
// 原始代码
wire [7:0] a, b;
assign eq = (a == b);  // eq是1位

// T47变换（假设width=4）
wire _n01 = a[0] ^ b[0];
wire _n02 = a[1] ^ b[1];
wire _n03 = a[2] ^ b[2];
wire _n04 = a[3] ^ b[3];
assign eq = ~_n01 & ~_n02 & ~_n03 & ~_n04;
```
**问题**：
- 原始代码比较8位，但T47只展开了4位！
- 结果：`a[7:4]`的比较被忽略了，功能完全错误

##### 问题2：加法器进位链错误
```verilog
// 原始代码
wire [7:0] sum = a + b;  // 8位加法

// T47变换（width=4）
wire _n01 = a[0] ^ b[0];
wire _c01 = a[0] & b[0];
wire _n02 = a[1] ^ b[1] ^ _c01;
wire _c02 = (a[1] & b[1]) | (a[1] & _c01) | (b[1] & _c01);
// ... 只到第4位
assign sum = {_n04, _n03, _n02, _n01};  // ❌ 只有4位！
```
**问题**：
- 原始是8位加法，但只生成了4位结果
- 高位全部丢失

##### 问题3：默认width参数
```python
def ast_dataflow_shattering(code, vs, target, width=4):
```
**问题**：默认`width=4`，但实际信号可能是任意位宽！

##### 问题4：未检查实际位宽
```python
# 代码中没有检查a和b的实际位宽
a = expr.left_text.strip()
b = expr.right_text.strip()
# 直接使用参数width，而不是从信号声明中获取
```

**修复建议**：
```python
def ast_dataflow_shattering(code, vs, target, width=None):
    # 1. 自动检测信号位宽
    if width is None:
        a_width = get_signal_width(vs, a)
        b_width = get_signal_width(vs, b)
        width = max(a_width, b_width)
    
    # 2. 验证位宽匹配
    actual_a_width = get_signal_width(vs, a)
    actual_b_width = get_signal_width(vs, b)
    if actual_a_width != width or actual_b_width != width:
        # 位宽不匹配，不应用此变换
        return code
    
    # 3. 对于加法，确保输出位宽正确
    if op == '+':
        out_width = get_signal_width(vs, out_var)
        if out_width != width:
            # 需要处理进位或截断
            pass
    
    # ... 其余逻辑
```

---

### 其他中等改变率规则的问题

#### T18, T48 - 语句重排序（26.7%, 25.1%）
```verilog
// 原始: assign a = x; assign b = y;
// 变换: assign b = y; assign a = x;
```
**为什么会改变**：
- 如果存在数据依赖（虽然连续赋值应该是并发的）
- 某些综合工具可能对顺序敏感
- 如果涉及到`initial`块或时序逻辑，顺序可能影响初始化

---

## 总结

### 功能等价的关键要素

✅ **能保持等价的变换**：
1. **纯逻辑等价**：T30（常量）、T32（位宽）
2. **不影响执行的添加**：T19（死代码）、T20（注释）
3. **纯重命名**：T34（信号名）
4. **简单重排序**：T41（case分支）、T07（独立assign）

❌ **容易破坏等价的变换**：
1. **位宽处理**：T47（Shannon展开）- 必须正确处理位宽
2. **信号声明**：T31（中间信号）- 必须正确声明和赋值
3. **数据依赖**：T48（语句重排）- 必须检查依赖关系
4. **逻辑变换**：T09/T10（DeMorgan）- 必须处理边界情况

### 修复优先级

**高优先级**（影响大）：
1. **T47** - 95%改变率，必须修复位宽检测
2. **T31** - 57.3%改变率，必须修复wire声明方式

**中优先级**（可接受）：
3. **T10** - 36.6%改变率，改进DeMorgan实现
4. **T18, T48** - 25%改变率，添加依赖检查

**低优先级**（已经很好）：
5. **T03, T09, T12** - 15-20%改变率，可以进一步优化

### 建议

**短期**：
- 使用10个功能等价规则（<5%改变率）
- 排除T31和T47

**中期**：
- 修复T47的位宽检测
- 修复T31的wire声明方式
- 添加自动化测试验证功能等价性

**长期**：
- 为每个规则添加前置条件检查
- 实现位宽推断系统
- 建立规则质量评估框架
