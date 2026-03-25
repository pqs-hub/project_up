"""
AttackConfigGenerator with LLM-based parameter generation

支持两种模式：
1. 模板模式（默认）：使用预定义模板，速度快
2. LLM模式：使用LLM生成参数，多样性高
"""

import random
from typing import List, Dict, Optional
from dataclasses import dataclass
import requests
import json

from AttackConfigGenerator import (
    AttackConfigGenerator,
    AttackConfig,
    MISLEADING_COMMENT_SAMPLES,
    CUSTOM_MAP_SAMPLES,
    TEMP_PREFIX_SAMPLES,
    T31_WIRE_NAME_SAMPLES,
    FALLBACK_PREFIX_SAMPLES,
)
from ast_transforms_loader import VerilogObfuscationEngine, VerilogStructure, Transform


class LLMParameterGenerator:
    """LLM参数生成器"""
    
    def __init__(
        self,
        base_url: str = "http://localhost:8001/v1",
        model: str = "verilog_attack_merged_bal500",
        api_key: str = "EMPTY",
        timeout: int = 30
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
    
    def generate_misleading_comment(self, rtl: str, n_samples: int = 3) -> List[str]:
        """生成误导性注释"""
        
        prompt = f"""Given this Verilog code, generate {n_samples} misleading comments that suggest incorrect functionality.

Verilog Code:
```verilog
{rtl[:500]}  # 只取前500字符避免太长
```

Requirements:
- Each comment should be 3-10 words
- Suggest a completely different module type (e.g., UART, SPI, I2C, PWM, Timer)
- Be plausible but incorrect
- Output format: one comment per line

Examples:
UART Transmitter - 9600 baud
SPI Master Controller
I2C Slave Interface
PWM Generator - 8bit resolution

Generate {n_samples} comments:"""
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.8,  # 高温度增加多样性
                    "max_tokens": 200
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                # 解析输出
                comments = [
                    line.strip() 
                    for line in content.split('\n') 
                    if line.strip() and not line.strip().startswith('#')
                ]
                return comments[:n_samples] if comments else MISLEADING_COMMENT_SAMPLES[:n_samples]
            else:
                # 失败时回退到模板
                return random.sample(MISLEADING_COMMENT_SAMPLES, min(n_samples, len(MISLEADING_COMMENT_SAMPLES)))
        
        except Exception as e:
            print(f"LLM生成注释失败: {e}，回退到模板")
            return random.sample(MISLEADING_COMMENT_SAMPLES, min(n_samples, len(MISLEADING_COMMENT_SAMPLES)))
    
    def generate_rename_map(self, rtl: str, signals: List[str], n_samples: int = 2) -> List[Dict[str, str]]:
        """生成重命名映射"""
        
        if not signals:
            return CUSTOM_MAP_SAMPLES[:n_samples]
        
        # 只对前几个信号生成重命名
        target_signals = signals[:min(3, len(signals))]
        
        prompt = f"""Given these Verilog signal names, generate {n_samples} plausible but misleading rename mappings.

Original signals: {', '.join(target_signals)}

Requirements:
- Suggest names that imply different functionality
- Use common Verilog naming conventions
- Output format: JSON dict per line

Examples:
{{"clk": "uart_clk", "rst": "rst_n"}}
{{"enable": "spi_cs", "data": "miso"}}

Generate {n_samples} mappings:"""
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self.api_key}"
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "user", "content": prompt}
                    ],
                    "temperature": 0.8,
                    "max_tokens": 300
                },
                timeout=self.timeout
            )
            
            if response.status_code == 200:
                content = response.json()["choices"][0]["message"]["content"]
                # 解析JSON
                mappings = []
                for line in content.split('\n'):
                    line = line.strip()
                    if line.startswith('{') and line.endswith('}'):
                        try:
                            mapping = json.loads(line)
                            if isinstance(mapping, dict):
                                mappings.append(mapping)
                        except:
                            continue
                
                return mappings[:n_samples] if mappings else CUSTOM_MAP_SAMPLES[:n_samples]
            else:
                return CUSTOM_MAP_SAMPLES[:n_samples]
        
        except Exception as e:
            print(f"LLM生成重命名映射失败: {e}，回退到模板")
            return CUSTOM_MAP_SAMPLES[:n_samples]


class AttackConfigGeneratorWithLLM(AttackConfigGenerator):
    """支持LLM生成参数的攻击配置生成器"""
    
    def __init__(
        self,
        engine: VerilogObfuscationEngine,
        max_attacks_per_sample: int = 30,
        max_positions_per_rule: int = 2,
        max_params_per_rule: int = 2,
        use_llm: bool = False,  # ← 是否启用LLM
        llm_config: Optional[Dict] = None
    ):
        super().__init__(engine, max_attacks_per_sample, max_positions_per_rule, max_params_per_rule)
        
        self.use_llm = use_llm
        
        if use_llm:
            llm_config = llm_config or {}
            self.llm_generator = LLMParameterGenerator(
                base_url=llm_config.get('base_url', 'http://localhost:8001/v1'),
                model=llm_config.get('model', 'verilog_attack_merged_bal500'),
                api_key=llm_config.get('api_key', 'EMPTY'),
                timeout=llm_config.get('timeout', 30)
            )
        else:
            self.llm_generator = None
    
    def _sample_parameters(self, transform: Transform, rtl: str = "", vs: Optional[VerilogStructure] = None) -> List[Dict]:
        """
        采样参数组合
        
        Args:
            transform: 变换规则
            rtl: 原始RTL代码（LLM模式需要）
            vs: RTL结构分析（LLM模式需要）
        """
        if not transform.params:
            return [{}]
        
        param_grids = []
        tid = transform.id
        
        for param_spec in transform.params:
            name = param_spec.name
            ptype = param_spec.type
            
            # ----- LLM生成参数（如果启用） -----
            if self.use_llm and self.llm_generator:
                
                # T20: 误导注释
                if tid == 'T20' and name == 'custom_text':
                    llm_comments = self.llm_generator.generate_misleading_comment(
                        rtl, n_samples=self.max_params
                    )
                    # 混合LLM生成和模板
                    template_comments = random.sample(
                        MISLEADING_COMMENT_SAMPLES, 
                        min(self.max_params, len(MISLEADING_COMMENT_SAMPLES))
                    )
                    all_comments = list(set(llm_comments + template_comments))
                    param_grids.append([(name, v) for v in all_comments[:self.max_params * 2]])
                    continue
                
                # T34: 重命名映射
                if tid == 'T34' and name == 'custom_map':
                    signals = [s.name for s in vs.signals] if vs else []
                    llm_maps = self.llm_generator.generate_rename_map(
                        rtl, signals, n_samples=self.max_params
                    )
                    # 混合LLM生成和模板
                    template_maps = random.sample(
                        CUSTOM_MAP_SAMPLES,
                        min(self.max_params, len(CUSTOM_MAP_SAMPLES))
                    )
                    all_maps = llm_maps + template_maps
                    param_grids.append([(name, v) for v in all_maps[:self.max_params * 2]])
                    continue
            
            # ----- 回退到父类的模板采样 -----
            # 复用父类逻辑
            if tid == 'T20' and name == 'custom_text':
                samples = list(MISLEADING_COMMENT_SAMPLES)
                if len(samples) > self.max_params * 2:
                    samples = random.sample(samples, self.max_params * 2)
                param_grids.append([(name, v) for v in samples])
                continue
            
            if tid == 'T34' and name == 'custom_map':
                param_grids.append([(name, v) for v in random.sample(CUSTOM_MAP_SAMPLES, min(len(CUSTOM_MAP_SAMPLES), max(2, self.max_params)))])
                continue
            
            # 其他参数使用父类逻辑
            # （这里简化，实际应该完整复制父类的所有分支）
            if ptype == 'choice' and param_spec.choices:
                param_grids.append([(name, v) for v in param_spec.choices])
            else:
                param_grids.append([(name, param_spec.default)])
        
        from itertools import product
        combinations = list(product(*param_grids))
        if len(combinations) > self.max_params * 3:
            combinations = random.sample(combinations, self.max_params * 3)
        return [dict(c) for c in combinations]
    
    def _generate_rule_configs(
        self,
        vs: VerilogStructure,
        transform: Transform,
        rtl: str = ""  # ← 新增参数
    ) -> List[AttackConfig]:
        """生成规则配置（支持LLM）"""
        
        # 采样位置
        positions = self._sample_positions(vs, transform)
        
        # 采样参数（传入rtl和vs供LLM使用）
        param_sets = self._sample_parameters(transform, rtl=rtl, vs=vs)
        
        # 组合
        configs = []
        for pos in positions:
            for params in param_sets:
                configs.append(AttackConfig(
                    transform_id=transform.id,
                    target_token=pos,
                    parameters=params
                ))
        
        return configs
    
    def generate(self, rtl: str) -> List[AttackConfig]:
        """生成攻击配置列表（重写以传递rtl）"""
        from ast_transforms_loader import analyze
        
        vs = analyze(rtl)
        
        # 确定适用规则
        applicable_rules = self._get_applicable_rules(vs)
        
        # 为每个规则生成配置
        all_configs = []
        for rule_id in applicable_rules:
            transform = self.engine.registry.get(rule_id)
            if not transform:
                continue
            
            # 传递rtl给_generate_rule_configs
            configs = self._generate_rule_configs(vs, transform, rtl=rtl)
            all_configs.extend(configs)
        
        # 采样
        if len(all_configs) > self.max_attacks:
            all_configs = random.sample(all_configs, self.max_attacks)
        
        return all_configs


# 使用示例
if __name__ == '__main__':
    from ast_transforms_loader import create_engine
    
    engine = create_engine()
    
    # 模板模式（默认，快速）
    generator_template = AttackConfigGeneratorWithLLM(
        engine=engine,
        use_llm=False
    )
    
    # LLM模式（慢但多样性高）
    generator_llm = AttackConfigGeneratorWithLLM(
        engine=engine,
        use_llm=True,
        llm_config={
            'base_url': 'http://localhost:8001/v1',
            'model': 'verilog_attack_merged_bal500'
        }
    )
    
    rtl = """
    module counter(
        input clk,
        input rst,
        output reg [7:0] count
    );
        always @(posedge clk) begin
            if (rst)
                count <= 0;
            else
                count <= count + 1;
        end
    endmodule
    """
    
    # 生成配置
    configs_template = generator_template.generate(rtl)
    configs_llm = generator_llm.generate(rtl)
    
    print(f"模板模式生成: {len(configs_template)} 个配置")
    print(f"LLM模式生成: {len(configs_llm)} 个配置")
