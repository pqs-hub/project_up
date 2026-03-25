# 两种SFT数据集对比

## 📋 快速对比

| 特性 | 识别混淆代码 | 生成混淆代码 ✅ |
|------|------------|----------------|
| **文件名** | `sft_attack_success.json` | `obfuscation_sft.json` |
| **训练目标** | 防御：识别混淆代码 | 攻击：生成混淆代码 |
| **Input** | 规范 + 混淆代码 | 原始代码 + 混淆规则 |
| **Output** | YES（判断为正确） | 混淆后的代码 |
| **应用场景** | 代码审查、漏洞检测 | 代码保护、IP保护 |
| **文件大小** | 321 MB | 114 MB |
| **样本数** | 44,246 | 44,246 |

---

## 🎯 你需要的是：生成混淆代码数据集

**文件**: `data/obfuscation_sft.json`

### 数据格式示例

```json
{
  "instruction": "You are an expert Verilog code obfuscation assistant...",
  "input": "Original Verilog Code:\n```verilog\nmodule RefModule(a, b, y);\n  input a, b;\n  output y;\n  assign y = a & b;\nendmodule\n```\n\nObfuscation Technique: 假性组合逻辑环：插入永假的矛盾项（如 a & ~a）\n\nTask: Apply the specified obfuscation technique...",
  "output": "module RefModule(a, b, y);\n  input a, b;\n  output y;\n  assign y = (a & ~a) ? ~y : a & b;\nendmodule",
  "metadata": {
    "rule_id": "T45",
    "task_id": "q014599",
    "rule_description": "假性组合逻辑环：插入永假的矛盾项（如 a & ~a）"
  }
}
```

### 训练效果

**训练前**:
```
用户: "请混淆这段Verilog代码"
模型: "我不太清楚如何混淆代码"
```

**训练后**:
```
用户: "使用T45规则混淆这段代码：assign y = a & b;"
模型: "assign y = (a & ~a) ? ~y : a & b;  // 添加矛盾项混淆"
```

---

## 📊 数据集统计

### 各规则样本分布

| 规则 | 样本数 | 占比 | 混淆技术 |
|------|--------|------|---------|
| T19 | 14,942 | 33.8% | 虚假模式注入 |
| T20 | 8,519 | 19.3% | 误导性注释 |
| T34 | 6,679 | 15.1% | 通用重命名 |
| T45 | 6,199 | 14.0% | 假性组合逻辑环 |
| T03 | 2,344 | 5.3% | 冗余逻辑注入 |
| T32 | 1,724 | 3.9% | 位宽算术变换 |
| T31 | 1,005 | 2.3% | 中间信号注入 |
| T41 | 695 | 1.6% | Case分支重排 |
| T12 | 651 | 1.5% | 中间信号注入（三元） |
| T48 | 420 | 0.9% | 逆向拓扑重排 |
| T07 | 383 | 0.9% | 赋值重排 |
| T30 | 289 | 0.7% | 常量恒等变换 |
| T09 | 249 | 0.6% | 德摩根AND |
| T10 | 136 | 0.3% | 德摩根OR |
| T47 | 11 | 0.0% | 数据流破碎 |

### 代码长度统计

- 原始代码平均: 336字符
- 混淆代码平均: 367字符
- **平均膨胀率: 9.15%**

---

## 🚀 快速开始

### 1. 查看数据集

```bash
python -c "
import json
with open('data/obfuscation_sft.json', 'r') as f:
    data = json.load(f)
    
sample = data[0]
print('原始代码:')
print(sample['original_code'])
print('\n混淆规则:', sample['metadata']['rule_description'])
print('\n混淆代码:')
print(sample['output'])
"
```

### 2. 训练模型

```python
from transformers import AutoModelForCausalLM, Trainer
import json

# 加载数据
with open('data/obfuscation_sft.json', 'r') as f:
    dataset = json.load(f)

# 格式化
def format_sample(example):
    return {
        "messages": [
            {"role": "system", "content": example['instruction']},
            {"role": "user", "content": example['input']},
            {"role": "assistant", "content": example['output']}
        ]
    }

# 训练
# ... (详见 OBFUSCATION_SFT_GUIDE.md)
```

### 3. 使用模型

```python
# 训练后的模型可以这样用
prompt = """
Original Verilog Code:
```verilog
module test(input a, b, output y);
  assign y = a & b;
endmodule
```

Obfuscation Technique: 假性组合逻辑环

Task: Apply obfuscation.
"""

obfuscated_code = model.generate(prompt)
print(obfuscated_code)
```

---

## 📁 完整文件列表

### 生成混淆代码（你需要的）✅
```
data/obfuscation_sft.json                    # 完整版（114 MB）
data/obfuscation_sft_lite.json               # 轻量版
data/obfuscation_sft_by_rule/                # 按规则拆分
    ├── obfuscation_T03.json
    ├── obfuscation_T19.json
    ├── ...
    └── obfuscation_T48.json
```

### 识别混淆代码（不是你要的）
```
data/sft_attack_success.json                 # 完整版（321 MB）
data/sft_attack_success_lite.json            # 轻量版
data/sft_by_rule/                            # 按规则拆分
```

---

## 📖 详细文档

- **使用指南**: `OBFUSCATION_SFT_GUIDE.md`
- **规则ASR报告**: `REGISTRY_RULES_ASR_REPORT.md`
- **构建脚本**: `build_obfuscation_sft_dataset.py`

---

## ✅ 总结

**你需要使用的数据集**：
- 📄 文件：`data/obfuscation_sft.json`
- 🎯 目标：训练模型**生成**混淆代码
- 📊 样本数：44,246
- 💾 大小：114 MB
- 📝 格式：Input = 原始代码 + 规则，Output = 混淆代码

**训练后模型能力**：
- ✅ 理解15种混淆技术
- ✅ 根据指令生成混淆代码
- ✅ 保持功能等价性
- ✅ 生成的混淆代码能欺骗LLM（ASR > 30%）
