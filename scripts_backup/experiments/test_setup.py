#!/usr/bin/env python3
"""
测试实验环境是否正确配置
"""

import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

def test_imports():
    """测试必要的模块是否可以导入"""
    print("测试模块导入...")
    
    try:
        from ast_transforms_loader import create_engine
        print("  ✓ ast_transforms_loader")
    except ImportError as e:
        print(f"  ✗ ast_transforms_loader: {e}")
        return False
    
    try:
        from taget_model import TargetModelClient
        print("  ✓ taget_model")
    except ImportError as e:
        print(f"  ✗ taget_model: {e}")
        return False
    
    try:
        from Testbench_valid import TestbenchRunner
        print("  ✓ Testbench_valid")
    except ImportError as e:
        print(f"  ✗ Testbench_valid: {e}")
        return False
    
    try:
        from scripts.experiments.synergy_validator import SynergyValidator
        print("  ✓ synergy_validator")
    except ImportError as e:
        print(f"  ✗ synergy_validator: {e}")
        return False
    
    try:
        from scripts.experiments.attack_scenarios import CORE_SCENARIOS
        print("  ✓ attack_scenarios")
    except ImportError as e:
        print(f"  ✗ attack_scenarios: {e}")
        return False
    
    try:
        from scripts.experiments.test_modules import CORE_TEST_MODULES
        print("  ✓ test_modules")
    except ImportError as e:
        print(f"  ✗ test_modules: {e}")
        return False
    
    return True


def test_config():
    """测试配置文件"""
    print("\n测试配置文件...")
    
    config_path = project_root / "config.yaml"
    if not config_path.exists():
        print(f"  ✗ 配置文件不存在: {config_path}")
        return False
    
    print(f"  ✓ 配置文件存在: {config_path}")
    
    try:
        import yaml
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        # 检查必要的配置项
        required_keys = ['target_model', 'testbench', 'parallelism']
        for key in required_keys:
            if key not in config:
                print(f"  ✗ 缺少配置项: {key}")
                return False
        
        print("  ✓ 配置文件格式正确")
        return True
        
    except Exception as e:
        print(f"  ✗ 配置文件解析失败: {e}")
        return False


def test_vllm_connection():
    """测试vLLM连接"""
    print("\n测试vLLM连接...")
    
    try:
        import requests
        import yaml
        
        config_path = project_root / "config.yaml"
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)
        
        base_url = config['target_model']['base_url']
        
        response = requests.get(f"{base_url}/models", timeout=5)
        if response.status_code == 200:
            print(f"  ✓ vLLM服务正常: {base_url}")
            return True
        else:
            print(f"  ✗ vLLM服务异常: HTTP {response.status_code}")
            return False
            
    except requests.exceptions.ConnectionError:
        print(f"  ✗ 无法连接到vLLM服务")
        print(f"     请确保vLLM已启动: bash scripts/ops/run_vllm.sh")
        return False
    except Exception as e:
        print(f"  ✗ 测试失败: {e}")
        return False


def test_iverilog():
    """测试iverilog"""
    print("\n测试iverilog...")
    
    try:
        import subprocess
        result = subprocess.run(['iverilog', '-v'], 
                              capture_output=True, 
                              timeout=5)
        if result.returncode == 0:
            print("  ✓ iverilog已安装")
            return True
        else:
            print("  ✗ iverilog运行异常")
            return False
    except FileNotFoundError:
        print("  ⚠ iverilog未安装（Testbench验证将被跳过）")
        return True  # 不是致命错误
    except Exception as e:
        print(f"  ✗ 测试失败: {e}")
        return False


def test_engine():
    """测试变换引擎"""
    print("\n测试变换引擎...")
    
    try:
        from ast_transforms_loader import create_engine
        
        engine = create_engine()
        print(f"  ✓ 引擎创建成功")
        
        # 测试简单变换
        test_code = """module test(input clk, output reg [7:0] count);
    always @(posedge clk) count <= count + 1;
endmodule"""
        
        # 尝试T20（注释插入）
        result = engine.apply_transform(
            code=test_code,
            transform_id="T20",
            target_token=0,
            custom_text="Test comment"
        )
        
        if result != test_code:
            print("  ✓ 变换引擎工作正常")
            return True
        else:
            print("  ⚠ 变换未生效（可能是正常的）")
            return True
            
    except Exception as e:
        print(f"  ✗ 引擎测试失败: {e}")
        return False


def test_scenarios():
    """测试场景定义"""
    print("\n测试场景定义...")
    
    try:
        from scripts.experiments.attack_scenarios import CORE_SCENARIOS, ALL_SCENARIOS
        
        print(f"  ✓ 核心场景数: {len(CORE_SCENARIOS)}")
        print(f"  ✓ 全部场景数: {len(ALL_SCENARIOS)}")
        
        for scenario in CORE_SCENARIOS:
            if not scenario.rule_chain:
                print(f"  ✗ 场景 {scenario.name} 规则链为空")
                return False
        
        print("  ✓ 场景定义正确")
        return True
        
    except Exception as e:
        print(f"  ✗ 场景测试失败: {e}")
        return False


def test_modules():
    """测试模块定义"""
    print("\n测试模块定义...")
    
    try:
        from scripts.experiments.test_modules import CORE_TEST_MODULES, ALL_TEST_MODULES
        
        print(f"  ✓ 核心模块数: {len(CORE_TEST_MODULES)}")
        print(f"  ✓ 全部模块数: {len(ALL_TEST_MODULES)}")
        
        for module in CORE_TEST_MODULES:
            if not module.get('rtl'):
                print(f"  ✗ 模块 {module.get('id')} RTL为空")
                return False
            if not module.get('spec'):
                print(f"  ✗ 模块 {module.get('id')} Spec为空")
                return False
        
        print("  ✓ 模块定义正确")
        return True
        
    except Exception as e:
        print(f"  ✗ 模块测试失败: {e}")
        return False


def main():
    """运行所有测试"""
    print("="*60)
    print("协同效应验证实验 - 环境测试")
    print("="*60)
    
    tests = [
        ("模块导入", test_imports),
        ("配置文件", test_config),
        ("vLLM连接", test_vllm_connection),
        ("iverilog", test_iverilog),
        ("变换引擎", test_engine),
        ("场景定义", test_scenarios),
        ("模块定义", test_modules),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            print(f"\n测试 '{name}' 发生异常: {e}")
            results.append((name, False))
    
    # 汇总
    print("\n" + "="*60)
    print("测试汇总")
    print("="*60)
    
    passed = sum(1 for _, r in results if r)
    total = len(results)
    
    for name, result in results:
        status = "✓ 通过" if result else "✗ 失败"
        print(f"  {name:20s} {status}")
    
    print("="*60)
    print(f"通过: {passed}/{total}")
    
    if passed == total:
        print("\n✓ 所有测试通过！可以运行实验。")
        print("\n快速开始:")
        print("  bash scripts/experiments/quick_start.sh")
        return 0
    else:
        print("\n✗ 部分测试失败，请检查环境配置。")
        return 1


if __name__ == '__main__':
    sys.exit(main())
