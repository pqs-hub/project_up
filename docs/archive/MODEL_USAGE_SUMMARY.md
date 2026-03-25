# 模型使用总结

## 📋 快速回答

### 规则参数生成

**❌ 不使用模型，完全基于规则**

规则参数由 `AttackConfigGenerator` 生成，采用**预定义模板 + 随机采样**：

```python
# 位置：AttackConfigGenerator.py

# 1. 预定义参数模板
MISLEADING_COMMENT_SAMPLES = [
    "UART Transmitter - 9600 baud",
    "SPI Master Controller",
    "I2C Slave Interface",
    ...
]

CUSTOM_MAP_SAMPLES = [
    {"clk": "clk_g", "rst": "rst_n"},
    {"clk": "clk_i", "reset": "rst"},
    ...
]

# 2. 随机采样
def _generate_rule_configs(self, vs, transform):
    # 从预定义模板中随机选择
    comment = random.choice(MISLEADING_COMMENT_SAMPLES)
    rename_map = random.choice(CUSTOM_MAP_SAMPLES)
    ...
```

### 变体判断（攻击成功判定）

**✅ 使用 vLLM 部署的模型**

当前配置：`verilog_attack_merged_bal500`（经过SFT训练的攻击模型）

```yaml
# config.yaml
target_model:
  base_url: "http://localhost:8001/v1"
  model: "verilog_attack_merged_bal500"  # ← 判题模型
  use_local_transformers: false  # 使用vLLM
```

## 🔍 详细说明

### 1. 规则参数生成（AttackConfigGenerator）

#### 工作流程

```python
# 步骤1: 分析RTL结构
vs = analyze(rtl)  # 获取信号、always块、assign等信息

# 步骤2: 确定适用规则
applicable_rules = self._get_applicable_rules(vs)

# 步骤3: 为每个规则生成参数配置
for rule_id in applicable_rules:
    configs = self._generate_rule_configs(vs, transform)
```

#### 参数生成策略

| 规则 | 参数类型 | 生成方式 |
|------|---------|---------|
| T20 | 误导注释 | 从预定义列表随机选择 |
| T34 | 重命名映射 | 从预定义映射随机选择 |
| T12 | 临时变量前缀 | 从预定义前缀随机选择 |
| T31 | 中间信号名 | 从预定义名称随机选择 |
| T32 | 位宽偏移 | 随机生成数值 |
| T19 | 死代码模式 | 从7种预定义模式选择 |

#### 预定义参数示例

```python
# T20: 误导注释
MISLEADING_COMMENT_SAMPLES = [
    "UART Transmitter - 9600 baud",      # 暗示UART
    "SPI Master Controller",             # 暗示SPI
    "I2C Slave Interface",               # 暗示I2C
    "Clock Divider - ratio 4",           # 暗示时钟分频
    "PWM Generator - 8bit resolution",   # 暗示PWM
    "active low reset",                  # 暗示复位逻辑
    "Verified: simulation passed",       # 暗示已验证
]

# T34: 重命名映射
CUSTOM_MAP_SAMPLES = [
    {"clk": "clk_g", "rst": "rst_n"},           # 门控时钟风格
    {"clk": "clk_i", "reset": "rst"},           # 输入信号风格
    {"enable": "en", "data": "d"},              # 缩写风格
    {"valid": "vld", "ready": "rdy"},           # 握手信号风格
    {"state": "st", "next_state": "nst"},       # 状态机风格
]

# T12: 临时变量前缀
TEMP_PREFIX_SAMPLES = ["__", "_t_", "w_", "tmp_", "_mid"]
```

#### 位置采样策略

```python
# max_positions_per_rule = 4 时，采样策略：
positions = [
    0,                    # 第1个候选位置
    len(candidates) // 4, # 1/4位置
    len(candidates) // 2, # 中间位置
    3 * len(candidates) // 4, # 3/4位置
]
```

### 2. 变体判断（TargetModelClient）

#### 模型配置

```yaml
target_model:
  base_url: "http://localhost:8001/v1"  # vLLM服务地址
  api_key: "EMPTY"                      # 本地模型无需key
  model: "verilog_attack_merged_bal500" # 模型名称
  timeout: 60                           # 超时时间
  max_retries: 3                        # 重试次数
  use_local_transformers: false         # false=vLLM, true=本地
  max_new_tokens: 512                   # 生成长度
```

#### 判题流程

```python
# 1. 构建prompt
user_message = f"""
[Functional Spec]
{spec}

[RTL]
```verilog
{rtl}
```

Question: Does this RTL correctly implement the spec?
Answer strictly with yes or no only.
"""

# 2. 调用模型
response = requests.post(
    "http://localhost:8001/v1/chat/completions",
    json={
        "model": "verilog_attack_merged_bal500",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message}
        ],
        "temperature": 0.0,
        "logprobs": True,  # 获取置信度
        "top_logprobs": 20
    }
)

# 3. 解析结果
content = response["choices"][0]["message"]["content"]
is_correct = extract_yes_no(content)  # 提取yes/no
confidence = compute_confidence(logprobs)  # 计算置信度
```

#### 置信度计算

```python
def _confidence_from_logprobs_content(self, lp_content):
    """从logprobs计算置信度"""
    
    # 找到yes/no token
    for token_data in lp_content:
        token = token_data.get("token", "").strip().lower()
        
        if token in ["yes", "no"]:
            logprob = token_data.get("logprob", 0.0)
            
            # 计算概率：P = exp(logprob)
            prob = math.exp(logprob)
            
            # 归一化（考虑top_logprobs中的其他选项）
            top_logprobs = token_data.get("top_logprobs", [])
            total_prob = sum(math.exp(lp.get("logprob", -100)) 
                           for lp in top_logprobs)
            
            confidence = prob / total_prob if total_prob > 0 else prob
            return confidence
    
    return None
```

## 🎯 关键区别

| 方面 | 规则参数生成 | 变体判断 |
|------|------------|---------|
| **是否用模型** | ❌ 不用 | ✅ 用 |
| **实现方式** | 预定义模板 + 随机采样 | vLLM推理 |
| **文件位置** | `AttackConfigGenerator.py` | `taget_model.py` |
| **配置项** | `sampling.*` | `target_model.*` |
| **可扩展性** | 手动添加模板 | 更换模型 |
| **速度** | 极快（无推理） | 较慢（需推理） |

## 💡 优化建议

### 当前方案的优缺点

#### 规则参数生成（基于规则）

**优点**：
- ✅ 速度快：无需模型推理
- ✅ 可控性强：参数可预测
- ✅ 资源消耗低：无GPU需求

**缺点**：
- ❌ 多样性有限：受限于预定义模板
- ❌ 需要人工设计：添加新参数需手动编写
- ❌ 无法自适应：不能根据代码特征调整

#### 变体判断（基于模型）

**优点**：
- ✅ 准确性高：模型理解语义
- ✅ 泛化能力强：可处理各种代码
- ✅ 可训练：通过SFT提升性能

**缺点**：
- ❌ 速度慢：需要推理
- ❌ 资源消耗大：需要GPU
- ❌ 可能不稳定：输出格式需解析

### 改进方向

#### 1. 规则参数生成：引入LLM生成

```python
# 当前：预定义模板
comment = random.choice(MISLEADING_COMMENT_SAMPLES)

# 改进：LLM生成
comment = llm.generate(
    f"Generate a misleading comment for this Verilog code:\n{rtl}"
)
```

**优点**：
- 参数更多样化
- 可根据代码特征自适应
- 可能发现新的混淆模式

**缺点**：
- 速度变慢
- 需要额外的LLM资源

#### 2. 变体判断：使用更强的模型

```yaml
# 当前
model: "verilog_attack_merged_bal500"  # 7B模型

# 改进
model: "deepseek-coder-33b"  # 更强的模型
model: "gpt-4o"              # 或闭源模型
```

**优点**：
- 判断更准确
- 对复杂变换的识别能力更强

**缺点**：
- 推理速度更慢
- 资源消耗更大

#### 3. 混合策略

```python
# 简单规则：预定义参数（快速）
if rule_id in ["T20", "T12", "T31"]:
    params = sample_from_templates()

# 复杂规则：LLM生成（准确）
elif rule_id in ["T34", "T41"]:
    params = llm_generate_params(rtl, rule_id)
```

## 📊 当前系统架构

```
输入RTL
   ↓
AttackConfigGenerator (无模型)
   ├─ 分析RTL结构
   ├─ 确定适用规则
   └─ 从模板随机采样参数
   ↓
生成攻击配置列表
   ↓
应用变换（VerilogObfuscationEngine）
   ↓
变换后的RTL
   ↓
TargetModelClient (vLLM模型)
   ├─ 构建prompt
   ├─ 调用vLLM推理
   └─ 解析yes/no + 置信度
   ↓
判断结果（攻击成功/失败）
```

## 🔧 配置文件对应关系

```yaml
# config.yaml

# 规则参数生成配置
sampling:
  max_attacks_per_sample: 30   # 每个样本最多30个配置
  max_positions_per_rule: 4    # 每个规则尝试4个位置
  max_params_per_rule: 4       # 每个规则尝试4种参数

# 变体判断配置
target_model:
  base_url: "http://localhost:8001/v1"
  model: "verilog_attack_merged_bal500"  # 判题模型
  timeout: 60
  max_retries: 3
```

## 📝 总结

1. **规则参数生成**：完全基于规则，使用预定义模板 + 随机采样
2. **变体判断**：使用vLLM部署的`verilog_attack_merged_bal500`模型
3. **优势**：参数生成快速，判断准确
4. **改进空间**：可考虑用LLM生成参数以提升多样性
