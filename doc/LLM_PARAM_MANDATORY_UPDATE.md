# LLM参数强制使用更新

## 修改日期
2026-03-28

## 修改说明

### 背景
原代码中，对于支持LLM生成参数的规则（T03, T12, T19, T20, T31, T34），如果LLM参数生成失败，会自动回退到使用`DEFAULT_PARAM_SETS`中定义的默认参数。

### 修改内容
修改`/pipeline/6_generate_attack_dataset.py`中的`get_param_sets`方法，删除了LLM生成失败时的默认参数回退逻辑。

#### 修改前行为
```python
if llm_param:
    # 使用LLM生成的参数
    return [llm_param_set]
else:
    # LLM生成失败，回退到默认参数
    logger.debug(f"{rule_id}: LLM参数生成失败，使用默认参数")
    return DEFAULT_PARAM_SETS.get(rule_id, [{}])
```

#### 修改后行为
```python
if llm_param:
    # 使用LLM生成的参数
    return [llm_param_set]
else:
    # LLM生成失败，返回空列表（强制要求使用LLM生成的参数）
    logger.warning(f"{rule_id}: LLM参数生成失败，跳过此规则（不使用默认参数）")
    return []
```

### 影响范围

#### 支持LLM生成参数的规则（必须使用LLM参数）
- **T03**: 冗余逻辑 - 参数：`redundant_name`
- **T12**: 中间信号抽取 - 参数：`wire_name`
- **T19**: 虚假模式注入 - 参数：`custom_dead_stmts`
- **T20**: 灵活误导性注释 - 参数：`custom_text`
- **T31**: 简单中间信号 - 参数：`wire_name`
- **T34**: 通用对抗性重命名 - 参数：`custom_map`

对于这些规则：
- ✅ LLM生成成功：使用LLM生成的参数
- ❌ LLM生成失败：跳过该规则（返回空列表），**不再使用默认参数**

#### 不支持LLM生成的规则（继续使用默认参数）
- **T07**: assign重排序
- **T09**: DeMorgan AND变换
- **T10**: DeMorgan OR变换
- **T30**: 常量恒等变换
- **T32**: 位宽算术变换
- **T41**: Case分支重排
- **T45**: 伪组合循环
- **T47**: 数据流分解
- **T48**: 反拓扑排序

这些规则继续使用`DEFAULT_PARAM_SETS`中定义的默认参数。

### 行为变化
1. **更严格的质量控制**：强制要求支持LLM生成参数的规则必须使用LLM生成的参数
2. **日志级别变化**：LLM生成失败时，日志级别从`debug`提升到`warning`
3. **数据集生成影响**：当LLM参数生成失败时，该规则将不会产生任何攻击样本

### 配置说明
需要确保在配置文件中启用LLM参数生成：
```yaml
llm_params:
  enabled: true
  base_url: "http://..."
  model: "..."
```

### 注意事项
- 如果LLM服务不可用或频繁失败，可能导致支持LLM参数的6个规则无法生成攻击样本
- 建议监控LLM参数生成成功率，确保数据集质量
- 如需临时回退到默认参数，可以在配置中设置`llm_params.enabled: false`
