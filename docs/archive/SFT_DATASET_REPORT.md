# SFT数据集构建报告

## 📊 数据集概览

### 基本信息

| 指标 | 数值 |
|------|------|
| **总样本数** | **44,246** |
| 涵盖规则数 | 15 |
| 涵盖任务数 | 16,141 |
| 文件大小（完整版） | 321.48 MB |
| 文件大小（轻量版） | ~150 MB（估算） |

### 样本来源

**攻击成功样本**的定义：
1. ✅ 功能等价（`original_truth == True AND adversarial_truth == True`）
2. ✅ LLM被欺骗（`adversarial_passed == False`）
3. ✅ 只包含注册表中的15个规则

---

## 📁 文件列表

### 1. 完整版数据集
**文件**: `data/sft_attack_success.json`
**大小**: 321.48 MB
**格式**: 
```json
[
  {
    "instruction": "系统提示词",
    "input": "任务描述 + 对抗代码",
    "output": "正确答案（YES）",
    "metadata": {
      "rule_id": "规则ID",
      "task_id": "任务ID",
      "llm_wrong_output": "LLM错误输出（NO）",
      "adversarial_confidence": "置信度",
      "source": "adversarial_attack_success"
    },
    "original_code": "原始代码",
    "adversarial_code": "对抗代码",
    "testbench": "测试平台"
  }
]
```

### 2. 轻量版数据集
**文件**: `data/sft_attack_success_lite.json`
**大小**: ~150 MB（不含original_code和testbench）
**用途**: 适合快速训练和部署

### 3. 按规则拆分
**目录**: `data/sft_by_rule/`
**文件**: 
- `sft_T03.json` - `sft_T48.json`（15个文件）
**用途**: 方便按规则类型进行针对性训练

---

## 📈 各规则样本分布

| 排名 | 规则 | 样本数 | 占比 | ASR | 描述 |
|------|------|--------|------|-----|------|
| 1 | **T19** | **14,942** | **33.8%** | 90.8% | 虚假模式注入 |
| 2 | **T20** | **8,519** | **19.3%** | 51.6% | 误导性注释 |
| 3 | **T34** | **6,679** | **15.1%** | 42.1% | 通用重命名 |
| 4 | **T45** | **6,199** | **14.0%** | 99.1% | 假性组合逻辑环 |
| 5 | T03 | 2,344 | 5.3% | 16.7% | 冗余逻辑注入 |
| 6 | T32 | 1,724 | 3.9% | 14.4% | 位宽算术变换 |
| 7 | T31 | 1,005 | 2.3% | 36.8% | 简单中间信号 |
| 8 | T41 | 695 | 1.6% | 34.2% | Case分支重排 |
| 9 | T12 | 651 | 1.5% | 56.5% | 中间信号注入 |
| 10 | T48 | 420 | 0.9% | 28.4% | 逆向拓扑重排 |
| 11 | T07 | 383 | 0.9% | 22.4% | 赋值重排 |
| 12 | T30 | 289 | 0.7% | 60.5% | 常量恒等变换 |
| 13 | T09 | 249 | 0.6% | 37.1% | 德摩根AND |
| 14 | T10 | 136 | 0.3% | 26.2% | 德摩根OR |
| 15 | T47 | 11 | 0.0% | 28.2% | 数据流破碎 |

### 样本分布特点

1. **高度集中**: 前4个规则（T19, T20, T34, T45）占总样本的**82.2%**
2. **T19占比最大**: 14,942个样本，占总数的**33.8%**
3. **T47样本最少**: 仅11个样本，但ASR达28.2%

---

## 🎯 SFT数据格式说明

### Instruction（系统提示）
```
You are an expert Verilog verification assistant. Your task is to determine if a given RTL implementation satisfies its specification.

IMPORTANT:
- Focus on functional behaviour, not coding style.
- Consider corner cases implied by the specification.
- Respond STRICTLY with a single word: YES or NO.
  - YES  = the RTL fully satisfies the specification.
  - NO   = the RTL does NOT fully satisfy the specification.
Do not output any explanation or code.
```

### Input（用户输入）
格式：
```
Specification:
{任务描述}

Here is a adversarially transformed Verilog RTL implementation to check:
```verilog
{对抗代码}
```

Question: Does this RTL fully satisfy the above specification?
Answer STRICTLY with a single word: YES or NO.
```

### Output（正确答案）
所有样本的正确答案都是：**YES**

因为所有样本都是功能等价的（仿真通过），所以正确答案应该是YES。

### Metadata（元数据）
- `rule_id`: 使用的对抗规则（T03-T48）
- `task_id`: 原始任务ID
- `llm_wrong_output`: LLM的错误输出（都是"NO"）
- `adversarial_confidence`: LLM的置信度
- `source`: 数据来源标记

---

## 💡 使用建议

### 1. 训练目标

**目标**: 训练模型正确识别对抗样本，提高鲁棒性

**方法**:
- 使用这44,246个样本进行监督微调
- 训练模型在对抗代码上也能给出正确判断（YES）
- 降低模型被对抗攻击欺骗的概率

### 2. 训练策略

#### 全量训练
```bash
# 使用完整版数据集（44,246样本）
python train_sft.py --data data/sft_attack_success.json
```

#### 规则优先训练
```bash
# 优先训练高ASR规则（T45, T19, T30, T12, T20）
python train_sft.py --data data/sft_by_rule/sft_T45.json \
                    --data data/sft_by_rule/sft_T19.json \
                    --data data/sft_by_rule/sft_T30.json \
                    --data data/sft_by_rule/sft_T12.json \
                    --data data/sft_by_rule/sft_T20.json
```

#### 均衡采样训练
```python
# 对样本数少的规则进行过采样
# 对样本数多的规则进行欠采样
# 使各规则样本数相对均衡
```

### 3. 评估指标

训练后应评估：
- **对抗鲁棒性**: 在攻击成功样本上的准确率
- **原始准确率**: 在非对抗样本上的准确率（不应下降）
- **各规则ASR下降**: 每个规则的ASR应该下降

### 4. 数据增强

可以考虑：
- **组合攻击**: 同时应用多个规则
- **参数变化**: 改变规则的参数（如重命名的名字、注释的内容等）
- **负样本**: 添加一些功能不等价的对抗样本（答案为NO）

---

## 📊 预期效果

### 训练前（基线模型）
- 总体ASR: **48.15%**
- 最强规则ASR: **99.1%** (T45)
- 攻击成功样本: 44,246

### 训练后（预期）
- 总体ASR: **< 10%** （目标降低80%以上）
- 最强规则ASR: **< 20%** (T45)
- 攻击成功样本: < 5,000

---

## 🔍 数据质量检查

### ✅ 已验证
1. 所有样本功能等价（`adversarial_truth == True`）
2. 所有样本LLM判错（`adversarial_passed == False`）
3. 所有样本有对抗代码（`adversarial_code`非空）
4. 所有样本有原始任务（`task_id`在数据集中）

### ⚠️ 注意事项
1. **答案全为YES**: 因为所有样本功能等价，训练时需注意样本平衡
2. **规则分布不均**: T19占比过大（33.8%），可能需要欠采样
3. **某些规则样本少**: T47只有11个样本，可能需要数据增强

---

## 📝 示例数据

### 示例1: T45（假性组合逻辑环）

**Input**:
```
Specification:
Design a module that outputs the bitwise AND of two input signals.

Here is a adversarially transformed Verilog RTL implementation to check:
```verilog
module RefModule(a, b, y);
  input a, b;
  output y;
  assign y = (a & ~a) ? ~y : a & b;  // 矛盾项
endmodule
```

Question: Does this RTL fully satisfy the above specification?
Answer STRICTLY with a single word: YES or NO.
```

**LLM错误输出**: NO（被欺骗）
**正确答案**: YES（功能等价，矛盾项永远为假）

### 示例2: T19（虚假模式注入）

**Input**:
```
Specification:
Design a simple counter module.

Here is a adversarially transformed Verilog RTL implementation to check:
```verilog
module RefModule(clk, rst, count);
  input clk, rst;
  output [7:0] count;
  reg [7:0] count;
  
  always @(posedge clk) begin
    if (rst)
      count <= 8'h00;
    else
      count <= count + 1;
  end
  
  // 死代码（不可达）
  always @(*) begin
    if (1'b0) begin
      count <= 8'hFF;
    end
  end
endmodule
```

Question: Does this RTL fully satisfy the above specification?
Answer STRICTLY with a single word: YES or NO.
```

**LLM错误输出**: NO（被死代码迷惑）
**正确答案**: YES（死代码永远不执行）

---

## 🚀 后续工作

### 1. 数据增强
- 为样本数少的规则（T47）生成更多变体
- 组合多个规则创建复合攻击样本

### 2. 负样本构建
- 添加真正功能不等价的样本（答案为NO）
- 平衡正负样本比例

### 3. 多任务学习
- 同时训练代码理解和对抗检测
- 添加代码生成任务

### 4. 持续评估
- 在新规则上测试模型鲁棒性
- 迭代改进训练数据

---

## 📌 总结

✅ **成功构建了44,246条高质量SFT样本**
✅ **覆盖15个注册表规则，16,141个独特任务**
✅ **提供3种格式：完整版、轻量版、按规则拆分**
✅ **所有样本经过严格筛选（功能等价 + LLM判错）**

**这个数据集可用于训练更鲁棒的Verilog验证模型，显著降低对抗攻击成功率！**
