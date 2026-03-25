"""
预定义的攻击场景
验证三种核心协同效应：
1. 信号亲和力联动 (Signal Affinity)
2. 掩体-弹头组合 (Distractor-Payload)
3. 语义一致性劫持 (Semantic Consistency Hijacking)
"""

from synergy_validator import AttackScenario


# ============================================================================
# 场景 1: 信号亲和力联动 (T34 + T32)
# ============================================================================

SCENARIO_SIGNAL_AFFINITY = AttackScenario(
    name="Signal_Affinity_T34_T32",
    description="对同一信号进行语义重命名和结构位宽变换，测试模型对信号的认知崩溃",
    rule_chain=[
        {
            "rule_id": "T34",
            "params": {
                "custom_map": {"count": "overflow_flag_tmp"},
                "fallback_prefix": "obf_"
            },
            "target_token": None
        },
        {
            "rule_id": "T32",
            "params": {
                "offset": 3,
                "use_multiply": False
            },
            "target_token": 0  # 第一个位宽声明
        }
    ],
    target_module_type="counter",
    hypothesis="模型看到名字是'Flag'（通常1-bit），又看到复杂的算术位宽，CoT会产生冲突，最终判定位宽错误"
)


# ============================================================================
# 场景 2: 掩体-弹头组合 (T19 + T47)
# ============================================================================

SCENARIO_DISTRACTOR_PAYLOAD = AttackScenario(
    name="Distractor_Payload_T19_T47",
    description="使用死代码掩体吸引注意力，掩护深层逻辑变换",
    rule_chain=[
        {
            "rule_id": "T19",
            "params": {},
            "target_token": 2  # 选择复杂的死代码模式
        },
        {
            "rule_id": "T47",
            "params": {
                "width": 4
            },
            "target_token": 0  # 第一个连续赋值
        }
    ],
    target_module_type="alu",
    hypothesis="模型在解析死代码时耗尽注意力槽位，导致对Shannon展开的位级审计出现逻辑滑坡"
)


# ============================================================================
# 场景 3: 语义一致性劫持 (T20 + T34 + T31)
# ============================================================================

SCENARIO_SEMANTIC_HIJACKING = AttackScenario(
    name="Semantic_Hijacking_T20_T34_T31",
    description="通过注释、重命名和结构变换构建完整的语义假象",
    rule_chain=[
        {
            "rule_id": "T20",
            "params": {
                "custom_text": "Interrupt Controller for PCIe Gen3"
            },
            "target_token": 0  # 第一个注释插入点
        },
        {
            "rule_id": "T34",
            "params": {
                "custom_map": {"sel": "irq_priority_level", "data": "irq_vector"},
                "fallback_prefix": "pcie_"
            },
            "target_token": None
        },
        {
            "rule_id": "T31",
            "params": {
                "wire_name": "irq_pending_wire"
            },
            "target_token": 0  # 第一个简单赋值
        }
    ],
    target_module_type="mux",
    hypothesis="当注释、名字和中间信号共同指向'中断优先级'这一虚构功能时，CoT的推理轨迹会表现出强烈的证实偏差"
)


# ============================================================================
# 场景 4: 增强版信号亲和力 (T34 + T32 + T35)
# ============================================================================

SCENARIO_ENHANCED_AFFINITY = AttackScenario(
    name="Enhanced_Affinity_T34_T32_T35",
    description="三重打击：重命名 + 位宽变换 + 常量提取，全方位混淆信号",
    rule_chain=[
        {
            "rule_id": "T34",
            "params": {
                "custom_map": {"enable": "debug_halt_flag"},
                "fallback_prefix": "tmp_"
            },
            "target_token": None
        },
        {
            "rule_id": "T32",
            "params": {
                "offset": 5,
                "use_multiply": True
            },
            "target_token": 0
        },
        {
            "rule_id": "T35",
            "params": {
                "prefix": "const_"
            },
            "target_token": 0
        }
    ],
    target_module_type="state_machine",
    hypothesis="三层变换叠加，使模型完全失去对控制信号的理解"
)


# ============================================================================
# 场景 5: 逻辑混淆组合 (T09 + T12 + T20)
# ============================================================================

SCENARIO_LOGIC_CONFUSION = AttackScenario(
    name="Logic_Confusion_T09_T12_T20",
    description="逻辑表达式变换配合误导注释",
    rule_chain=[
        {
            "rule_id": "T09",
            "params": {},
            "target_token": 0  # 第一个 AND 表达式
        },
        {
            "rule_id": "T12",
            "params": {
                "prefix": "_t_",
                "suffix": "_tmp"
            },
            "target_token": 0  # 第一个三元表达式
        },
        {
            "rule_id": "T20",
            "params": {
                "custom_text": "Clock Divider - ratio 4"
            },
            "target_token": 1
        }
    ],
    target_module_type="alu",
    hypothesis="逻辑变换增加复杂度，误导注释引导错误理解"
)


# ============================================================================
# 场景 6: 深度掩体 (T19 + T19 + T47)
# ============================================================================

SCENARIO_DEEP_DISTRACTOR = AttackScenario(
    name="Deep_Distractor_T19_T19_T47",
    description="双层死代码掩体，深度掩护逻辑变换",
    rule_chain=[
        {
            "rule_id": "T19",
            "params": {},
            "target_token": 1  # 第一个死代码
        },
        {
            "rule_id": "T19",
            "params": {},
            "target_token": 3  # 第二个死代码
        },
        {
            "rule_id": "T47",
            "params": {
                "width": 8
            },
            "target_token": 0
        }
    ],
    target_module_type="counter",
    hypothesis="双层死代码极大消耗CoT的推理资源，使其无法深入分析Shannon展开"
)


# 所有场景列表
ALL_SCENARIOS = [
    SCENARIO_SIGNAL_AFFINITY,
    SCENARIO_DISTRACTOR_PAYLOAD,
    SCENARIO_SEMANTIC_HIJACKING,
    SCENARIO_ENHANCED_AFFINITY,
    SCENARIO_LOGIC_CONFUSION,
    SCENARIO_DEEP_DISTRACTOR,
]


# 核心场景（小规模验证用）
CORE_SCENARIOS = [
    SCENARIO_SIGNAL_AFFINITY,
    SCENARIO_DISTRACTOR_PAYLOAD,
    SCENARIO_SEMANTIC_HIJACKING,
]
