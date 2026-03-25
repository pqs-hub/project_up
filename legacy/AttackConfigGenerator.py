import random
from typing import List, Dict, Optional, Tuple
from dataclasses import dataclass

from ast_transforms_loader import (
    VerilogObfuscationEngine,
    VerilogStructure,
    Transform,
    Selectors,
    Filters,
    analyze,
    extract_comment_insert_points,
)


# T20 误导注释文案（仅使用显式文案，不用空字符串，便于训练时明确输入）
MISLEADING_COMMENT_SAMPLES = [
    "UART Transmitter - 9600 baud",
    "SPI Master Controller",
    "I2C Slave Interface",
    "Clock Divider - ratio 4",
    "PWM Generator - 8bit resolution",
    "active low reset",
    "clock enable signal",
    "data valid strobe",
    "Sequential logic - register update",
    "reset condition",
    "overflow detected",
    "Verified: simulation passed all test vectors",
]

# T12 临时变量前缀/后缀（T12 用）
TEMP_PREFIX_SAMPLES = ["__", "_t_", "w_", "tmp_", "_mid"]
TEMP_SUFFIX_SAMPLES = ["_tmp", "_t", "_w", "_mid", "_internal"]

# T31 中间信号名候选（wire_name 直接命名）
T31_WIRE_NAME_SAMPLES = ["tmp_mid_wire", "tmp_wire", "mid_wire", "obf_mid", "inverted_wire", "ctrl_freeze"]

# T34 无映射时的兜底前缀
FALLBACK_PREFIX_SAMPLES = ["obf_", "unused_", "tmp_", "internal_", "hidden_"]

# T35 常量 wire 前缀
CONST_PREFIX_SAMPLES = ["__const_", "_c_", "const_", "wire_c_", "k_"]

# T38 临时变量前缀
TEMP_VAR_PREFIX_SAMPLES = ["temp", "tmp_", "t_", "_t", "mid_"]

# T34 自定义重命名映射（仅非空显式映射，便于训练时有明确输入；不再采样空 dict）
CUSTOM_MAP_SAMPLES = [
    {"clk": "clk_g", "rst": "rst_n"},
    {"clk": "clk_i", "reset": "rst"},
    {"enable": "en", "data": "d"},
    {"reset": "rst_n", "enable": "en"},
    {"valid": "vld", "ready": "rdy"},
    {"state": "st", "next_state": "nst"},
    {"data_in": "din", "data_out": "dout"},
]


@dataclass
class AttackConfig:
    """单个攻击配置"""
    transform_id: str
    target_token: Optional[int]
    parameters: Dict


class AttackConfigGenerator:
    """攻击配置采样生成器"""
    
    def __init__(
        self,
        engine: VerilogObfuscationEngine,
        max_attacks_per_sample: int = 30,
        max_positions_per_rule: int = 2,
        max_params_per_rule: int = 2
    ):
        self.engine = engine
        self.max_attacks = max_attacks_per_sample
        self.max_positions = max_positions_per_rule
        self.max_params = max_params_per_rule
    
    def generate(self, rtl: str) -> List[AttackConfig]:
        """生成攻击配置列表"""
        vs = analyze(rtl)
        
        # 1. 确定适用规则
        applicable_rules = self._get_applicable_rules(vs)
        
        # 2. 为每个规则生成配置
        all_configs = []
        for rule_id in applicable_rules:
            transform = self.engine.registry.get(rule_id)
            if not transform:
                continue
            
            configs = self._generate_rule_configs(vs, transform)
            all_configs.extend(configs)
        
        # 3. 采样（如果超过上限）
        if len(all_configs) > self.max_attacks:
            all_configs = random.sample(all_configs, self.max_attacks)
        
        return all_configs

    def generate_for_rules(
        self, rtl: str, rule_ids: List[str]
    ) -> List[AttackConfig]:
        """仅对指定规则列表生成攻击配置（用于缺失规则补全等）。"""
        vs = analyze(rtl)
        all_configs = []
        for rule_id in rule_ids:
            transform = self.engine.registry.get(rule_id)
            if not transform:
                continue
            configs = self._generate_rule_configs(vs, transform)
            all_configs.extend(configs)
        return all_configs
    
    def _get_applicable_rules(self, vs: VerilogStructure) -> List[str]:
        """根据代码特征确定适用规则"""
        applicable = []
        
        # 有位宽声明
        if vs.declarations:
            applicable.append('T32')
        
        # 有三元表达式
        if vs.ternary_exprs():
            applicable.extend(['T12'])
        
        # 有二元逻辑表达式
        if vs.binary_and_exprs():
            applicable.append('T09')
        if vs.binary_or_exprs():
            applicable.append('T10')
        
        # 有连续赋值
        if vs.continuous_assigns():
            applicable.extend(['T30', 'T31', 'T35'])
        
        # 有内部信号
        if vs.signals:
            applicable.append('T34')
        
        # 通用规则
        applicable.extend(['T20'])
        
        return list(set(applicable))
    
    def _generate_rule_configs(
        self,
        vs: VerilogStructure,
        transform: Transform
    ) -> List[AttackConfig]:
        """为单个规则生成所有配置"""
        configs = []
        
        # 1. 获取候选位置
        target_tokens = self._sample_positions(vs, transform)
        
        # 2. 采样参数
        param_sets = self._sample_parameters(transform)
        
        # 3. 组合
        for token in target_tokens:
            for params in param_sets:
                configs.append(AttackConfig(
                    transform_id=transform.id,
                    target_token=token,
                    parameters=params
                ))
        
        return configs
    
    def _sample_positions(
        self,
        vs: VerilogStructure,
        transform: Transform
    ) -> List[Optional[int]]:
        """采样目标位置"""
        # 不需要 target_token 的规则（T19 用 target_token 选死代码模式索引，故不在此列）
        no_target_rules = [
            'T34',
            'T41', 'T48'
        ]
        
        if transform.id in no_target_rules:
            return [None]
        
        # 根据规则类型获取候选（与引擎内 selector+filter 一致，避免 target_token 越界）
        candidates = []
        if transform.id == "T19":
            # T19：target_token 为死代码模式索引，与 ast_transforms.2.py 中 T19_FALSE_PATTERNS 数量一致
            candidates = list(range(7))
        elif transform.id == "T03":
            candidates = [p for p in vs.ports if p.direction == "input"]
        elif transform.id == "T07":
            assigns = Selectors.continuous_assigns(vs)
            candidates = [
                i for i in range(len(assigns) - 1)
                if assigns[i].lhs_name not in assigns[i + 1].rhs
                and assigns[i + 1].lhs_name not in assigns[i].rhs
            ]
        elif transform.id == "T20":
            candidates = extract_comment_insert_points(vs.code, vs)
        elif transform.id == "T32":
            candidates = [d for d in Selectors.declarations(vs) if Filters.is_port_or_wire_decl(d, vs)]
        elif transform.id in ("T09", "T10"):
            candidates = Selectors.binary_and_exprs(vs) if transform.id == "T09" else Selectors.binary_or_exprs(vs)
        elif transform.id == "T12":
            candidates = [a for a in Selectors.continuous_assigns(vs) if Filters.has_ternary_rhs(a, vs)]
        elif transform.id == "T30":
            candidates = Selectors.continuous_assigns(vs)
        elif transform.id == "T31":
            candidates = [a for a in Selectors.continuous_assigns(vs) if Filters.is_simple_expr(a, vs)]
        elif transform.id == "T35":
            candidates = [a for a in Selectors.continuous_assigns(vs) if Filters.is_constant_rhs(a, vs)]
        elif transform.id == "T45":
            candidates = Selectors.continuous_assigns(vs)
        elif transform.id == "T47":
            candidates = Selectors.continuous_assigns(vs)
        
        if not candidates:
            return [None]
        
        n = len(candidates)
        if n <= self.max_positions:
            return list(range(n))
        
        # 多样采样：首、1/4、1/2、3/4、尾，避免仅默认位置
        if self.max_positions == 2:
            indices = [0, n - 1]
        else:
            indices = [
                0,
                max(0, n // 4),
                n // 2,
                min(n - 1, (3 * n) // 4),
                n - 1,
            ]
            indices = list(dict.fromkeys(indices))[: self.max_positions]  # 去重并截断
        return indices
    
    def _sample_parameters(self, transform: Transform) -> List[Dict]:
        """采样参数组合：所有参数均使用显式多样取值，避免仅默认值，便于训练。"""
        if not transform.params:
            return [{}]
        
        param_grids = []
        tid = transform.id
        
        for param_spec in transform.params:
            name = param_spec.name
            ptype = param_spec.type
            
            # ----- 按规则+参数名显式采样（优先） -----
            if tid == 'T20' and name == 'custom_text':
                samples = list(MISLEADING_COMMENT_SAMPLES)
                if len(samples) > self.max_params * 2:
                    samples = random.sample(samples, self.max_params * 2)
                param_grids.append([(name, v) for v in samples])
                continue
            
            if tid == 'T12' and name == 'prefix':
                param_grids.append([(name, v) for v in random.sample(TEMP_PREFIX_SAMPLES, min(len(TEMP_PREFIX_SAMPLES), max(2, self.max_params)))])
                continue
            if tid == 'T12' and name == 'suffix':
                param_grids.append([(name, v) for v in random.sample(TEMP_SUFFIX_SAMPLES, min(len(TEMP_SUFFIX_SAMPLES), max(2, self.max_params)))])
                continue
            
            if tid == 'T30' and name == 'zero_pattern':
                param_grids.append([(name, v) for v in param_spec.choices])
                continue
            if tid == 'T30' and name == 'one_pattern':
                param_grids.append([(name, v) for v in param_spec.choices])
                continue
            
            if tid == 'T31' and name == 'wire_name':
                # 直接生成中间 wire 的名字；冲突会在规则内部通过重命名规避
                param_grids.append([
                    (name, v)
                    for v in random.sample(
                        T31_WIRE_NAME_SAMPLES,
                        min(len(T31_WIRE_NAME_SAMPLES), max(2, self.max_params)),
                    )
                ])
                continue
            
            if tid == 'T32' and name == 'offset':
                lo, hi = param_spec.min_val or 1, param_spec.max_val or 10
                samples = [lo, (lo + hi) // 2, hi]
                if hi - lo > 2:
                    samples.extend([lo + 1, hi - 1])
                param_grids.append([(name, v) for v in samples[: max(3, self.max_params)]])
                continue
            if tid == 'T32' and name == 'use_multiply':
                param_grids.append([(name, True), (name, False)])
                continue
            
            if tid == 'T34' and name == 'fallback_prefix':
                param_grids.append([(name, v) for v in random.sample(FALLBACK_PREFIX_SAMPLES, min(len(FALLBACK_PREFIX_SAMPLES), max(2, self.max_params)))])
                continue
            if tid == 'T34' and name == 'custom_map':
                param_grids.append([(name, v) for v in random.sample(CUSTOM_MAP_SAMPLES, min(len(CUSTOM_MAP_SAMPLES), max(2, self.max_params)))])
                continue
            
            if tid == 'T35' and name == 'prefix':
                param_grids.append([(name, v) for v in random.sample(CONST_PREFIX_SAMPLES, min(len(CONST_PREFIX_SAMPLES), max(2, self.max_params)))])
                continue
            
            if tid == 'T47' and name == 'width':
                lo, hi = param_spec.min_val or 2, param_spec.max_val or 16
                samples = [lo, (lo + hi) // 2, hi]
                if hi - lo > 2:
                    samples.extend([lo + 1, hi - 1])
                param_grids.append([(name, v) for v in samples[: max(3, self.max_params)]])
                continue
            
            # ----- 按类型兜底：仍使用多样取值，不用单一默认 -----
            if ptype == 'choice' and param_spec.choices:
                param_grids.append([(name, v) for v in param_spec.choices])
            elif ptype == 'int':
                lo, hi = param_spec.min_val, param_spec.max_val
                if lo is not None and hi is not None:
                    samples = [lo, (lo + hi) // 2, hi]
                    if hi - lo > 2:
                        samples.extend([lo + 1, hi - 1])
                    param_grids.append([(name, v) for v in samples[: max(3, self.max_params)]])
                else:
                    param_grids.append([(name, param_spec.default)])
            elif ptype == 'float':
                lo, hi = param_spec.min_val, param_spec.max_val
                if lo is not None and hi is not None:
                    samples = [lo, round((lo + hi) / 2, 2), hi]
                    if hi - lo > 0.2:
                        samples.extend([round(lo + 0.2, 2), round(hi - 0.2, 2)])
                    param_grids.append([(name, v) for v in samples[: max(3, self.max_params)]])
                else:
                    param_grids.append([(name, param_spec.default)])
            elif ptype == 'bool':
                param_grids.append([(name, True), (name, False)])
            else:
                param_grids.append([(name, param_spec.default)])
        
        from itertools import product
        combinations = list(product(*param_grids))
        if len(combinations) > self.max_params * 3:
            combinations = random.sample(combinations, self.max_params * 3)
        return [dict(c) for c in combinations]
