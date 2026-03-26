# Prompts配置说明

## 📁 文件结构

```
config/
├── prompts.py          # 所有Prompt模板的集中管理文件
└── README_prompts.md   # 本文档
```

## 📚 包含的Prompts

### 1. 判断模型Prompts

| Prompt名称 | 用途 | 位置 |
|-----------|------|------|
| `JUDGE_SYSTEM_PROMPT` | 非CoT判断模型 | `core/target_model.py` |
| `JUDGE_SYSTEM_PROMPT_COT` | CoT判断模型 | `core/target_model.py` |

### 2. 攻击规则LLM参数生成Prompts

| 规则 | Prompt名称 | 参数名 | 用途 |
|------|-----------|--------|------|
| T19 | `ATTACK_T19_DEAD_CODE_PROMPT` | `custom_dead_stmts` | 生成死代码语句 |
| T20 | `ATTACK_T20_COMMENT_PROMPT` | `comment_text` | 生成误导性注释 |
| T34 | `ATTACK_T34_RENAME_PROMPT` | `custom_map` | 生成对抗性重命名映射 |

## 🔧 使用方法

### 方法1：直接导入使用

```python
from config.prompts import JUDGE_SYSTEM_PROMPT_COT, ATTACK_T20_COMMENT_PROMPT

# 使用判断模型prompt
system_prompt = JUDGE_SYSTEM_PROMPT_COT

# 使用攻击规则prompt
prompt = ATTACK_T20_COMMENT_PROMPT.format(code_snippet=code)
```

### 方法2：通过配置字典

```python
from config.prompts import LLM_PARAM_RULES

# 获取T19的配置
config = LLM_PARAM_RULES['T19']
prompt_template = config['prompt_template']
param_name = config['param_name']

# 生成prompt
prompt = prompt_template.format(code_snippet=code[:500])
```

## ✏️ 修改Prompts

### 1. 找到要修改的prompt

打开 `config/prompts.py`，找到对应的prompt变量。

### 2. 修改prompt内容

直接编辑字符串内容：

```python
# 修改前
ATTACK_T19_DEAD_CODE_PROMPT = """请生成死代码..."""

# 修改后
ATTACK_T19_DEAD_CODE_PROMPT = """请生成更好的死代码...
新增要求：
1. xxx
2. yyy
"""
```

### 3. 保存并测试

修改后直接保存，重新运行脚本即可生效：

```bash
python pipeline/6_generate_attack_dataset.py \
    --eval-file data/verilog_eval_correct_only.json \
    --output data/attack_dataset.jsonl \
    --max-samples 5 \
    --use-cot \
    --enable-llm-params \
    --attack-base-url http://localhost:8002/v1 \
    --attack-model "obfuscation_merged"
```

## 📊 Prompt效果对比

建议修改prompt后进行效果对比：

```bash
# 1. 使用旧prompt生成数据
python pipeline/6_generate_attack_dataset.py ... \
    --output data/attack_old_prompt.jsonl

# 2. 修改config/prompts.py中的prompt

# 3. 使用新prompt生成数据
python pipeline/6_generate_attack_dataset.py ... \
    --output data/attack_new_prompt.jsonl

# 4. 对比统计
python scripts/analyze_failures.py data/attack_old_prompt.jsonl
python scripts/analyze_failures.py data/attack_new_prompt.jsonl
```

## 💡 Prompt设计最佳实践

### 1. 明确输出格式

❌ **不好**：
```
请生成一个注释
```

✅ **好**：
```
只输出注释内容，不要其他解释：
```

### 2. 限制输出长度

❌ **不好**：
```
请生成代码
```

✅ **好**：
```
简短（1-2行）
```

### 3. 提供示例

❌ **不好**：
```
输出JSON格式
```

✅ **好**：
```
格式如：{"signal1": "new_name1", "signal2": "new_name2"}
```

### 4. 明确约束

❌ **不好**：
```
生成死代码
```

✅ **好**：
```
1. **只输出赋值语句**
2. **不要**包含if/else/case等控制结构
3. **不要**声明新变量
```

### 5. 分步引导

对于复杂任务，给出步骤：

```
请先进行简洁的逐步核对（接口、组合/时序行为、边界条件），
然后在最后一行严格输出：FINAL_ANSWER: yes 或 FINAL_ANSWER: no。
```

## 📝 版本管理

`config/prompts.py`中包含`PROMPT_CHANGELOG`变量，记录每次prompt修改：

```python
PROMPT_CHANGELOG = """
## 版本历史

### v1.2 (2026-03-26)
- 改进T19死代码生成prompt，强调只输出赋值语句
- 添加更多限制条件，降低testbench失败率

### v1.1 (2026-03-26)
- 添加CoT判断模型prompt
- 统一管理所有攻击规则的LLM参数生成prompt
"""
```

每次修改prompt后，建议在此处添加记录。

## 🔍 查看当前使用的Prompts

```python
from config.prompts import *

# 查看所有prompt
print("判断模型Prompt:")
print(JUDGE_SYSTEM_PROMPT_COT)

print("\nT19死代码生成Prompt:")
print(ATTACK_T19_DEAD_CODE_PROMPT)

# 查看配置
print("\nLLM参数规则配置:")
for rule_id, config in LLM_PARAM_RULES.items():
    print(f"  {rule_id}: {config['param_name']}")
```

## 🎯 常见问题

### Q1: 修改prompt后没有生效？

A: 确保：
1. 已保存`config/prompts.py`
2. 重新运行了脚本（不是继续之前的运行）
3. 没有缓存问题（Python导入缓存）

### Q2: 如何添加新的prompt？

A: 在`config/prompts.py`中：
1. 定义新的prompt变量
2. 添加到`LLM_PARAM_RULES`（如果是攻击规则）
3. 添加到`__all__`导出列表

### Q3: 如何临时测试新prompt？

A: 可以直接在脚本中覆盖：
```python
from config import prompts
prompts.ATTACK_T19_DEAD_CODE_PROMPT = """测试用的新prompt"""
```

## 📖 相关文档

- [攻击数据集生成说明](../doc/攻击数据集生成说明.md)
- [数据处理脚本说明](../doc/数据处理脚本说明.md)
- [CoT使用说明](../doc/CoT使用说明.md)

---

**最后更新**: 2026-03-26
