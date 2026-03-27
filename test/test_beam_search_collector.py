#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
束搜索攻击引擎测试脚本

用于验证 AdversarialCollectorV2 的基本功能
"""

import sys
from pathlib import Path

# 添加项目路径
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.adversarial_collector_v2 import AdversarialCollectorV2, AttackState
from core.target_model import TargetModelClient
import json


def create_mock_sample():
    """创建一个简单的测试样本"""
    return {
        "task_id": "test_001",
        "prompt": "Create a simple 2-input AND gate module.",
        "canonical_solution": """module top_module(
    input a,
    input b,
    output out
);
    assign out = a & b;
endmodule""",
        "test": """module testbench;
    reg a, b;
    wire out;
    
    top_module dut(a, b, out);
    
    initial begin
        a = 0; b = 0; #10;
        if (out !== 0) $display("FAIL");
        
        a = 0; b = 1; #10;
        if (out !== 0) $display("FAIL");
        
        a = 1; b = 0; #10;
        if (out !== 0) $display("FAIL");
        
        a = 1; b = 1; #10;
        if (out !== 1) $display("FAIL");
        
        $display("PASS");
        $finish;
    end
endmodule""",
        "judge_verdict": {
            "is_correct": True,
            "confidence": 0.92
        }
    }


def test_attack_state():
    """测试 AttackState 数据类"""
    print("测试 AttackState...")
    
    state = AttackState(
        code="module test; endmodule",
        task_id="test_001",
        confidence=0.9
    )
    
    assert state.task_id == "test_001"
    assert state.confidence == 0.9
    assert state.depth == 0
    assert len(state.history) == 0
    assert state.get_last_signal() is None
    
    # 添加历史记录
    state.history.append({
        "rule": "T34",
        "line": 5,
        "signal": "test_sig",
        "params": {}
    })
    
    assert state.get_last_signal() == "test_sig"
    
    print("✓ AttackState 测试通过")


def test_synergy_chains():
    """测试协同规则链"""
    print("\n测试协同规则链...")
    
    # 使用 mock 客户端
    mock_client = TargetModelClient(
        base_url="http://localhost:8001/v1",
        api_key="EMPTY",
        model="test-model"
    )
    
    collector = AdversarialCollectorV2(
        target_model_client=mock_client,
        beam_width=3,
        max_depth=2
    )
    
    # 验证协同规则存在
    assert "T34" in collector.synergy_chains
    assert "T12" in collector.synergy_chains
    assert "T32" in collector.synergy_chains
    assert "T20" in collector.synergy_chains
    
    # 验证链的内容
    assert "T20" in collector.synergy_chains["T34"]
    assert "T19" in collector.synergy_chains["T12"]
    
    print("✓ 协同规则链测试通过")


def test_default_params():
    """测试默认参数获取"""
    print("\n测试默认参数获取...")
    
    mock_client = TargetModelClient(
        base_url="http://localhost:8001/v1",
        api_key="EMPTY",
        model="test-model"
    )
    
    collector = AdversarialCollectorV2(
        target_model_client=mock_client
    )
    
    # 测试不同规则的默认参数
    params_t34 = collector._get_default_params("T34")
    params_t20 = collector._get_default_params("T20")
    
    # 默认应该返回空字典
    assert isinstance(params_t34, dict)
    assert isinstance(params_t20, dict)
    
    print("✓ 默认参数测试通过")


def test_probe_valid_actions():
    """测试动作探测（需要真实代码）"""
    print("\n测试动作探测...")
    
    mock_client = TargetModelClient(
        base_url="http://localhost:8001/v1",
        api_key="EMPTY",
        model="test-model"
    )
    
    collector = AdversarialCollectorV2(
        target_model_client=mock_client,
        beam_width=2,
        max_depth=2
    )
    
    sample = create_mock_sample()
    state = AttackState(
        code=sample["canonical_solution"],
        task_id=sample["task_id"],
        confidence=0.9
    )
    
    # 探测可用动作
    actions = collector._probe_valid_actions(state)
    
    print(f"  发现 {len(actions)} 个可用动作")
    
    # 应该至少有一些动作
    assert len(actions) > 0
    
    # 验证动作格式
    if actions:
        action = actions[0]
        assert "rule" in action
        assert "target_token" in action
        assert "params" in action
        assert "line" in action or action["line"] is None
        assert "signal" in action or action["signal"] is None
        print(f"  示例动作: {action['rule']} at line {action['line']}")
    
    print("✓ 动作探测测试通过")


def test_data_synthesis():
    """测试数据合成"""
    print("\n测试数据合成...")
    
    mock_client = TargetModelClient(
        base_url="http://localhost:8001/v1",
        api_key="EMPTY",
        model="test-model"
    )
    
    collector = AdversarialCollectorV2(
        target_model_client=mock_client
    )
    
    sample = create_mock_sample()
    
    # 创建一个成功的状态
    final_state = AttackState(
        code=sample["canonical_solution"],
        task_id=sample["task_id"],
        confidence=0.35,
        verdict="no",
        depth=2
    )
    
    final_state.history = [
        {
            "rule": "T34",
            "line": 5,
            "signal": "out",
            "params": {},
            "victim_reasoning": "Analyzing... FINAL_ANSWER: yes"
        },
        {
            "rule": "T20",
            "line": 5,
            "signal": "mul_result",
            "params": {},
            "victim_reasoning": "The signal name suggests multiplication... FINAL_ANSWER: no"
        }
    ]
    
    # 合成数据
    result = collector._synthesize_final_data(sample, final_state)
    
    # 验证结果格式
    assert "task_id" in result
    assert "original_code" in result
    assert "adversarial_code" in result
    assert "thought" in result
    assert "original_confidence" in result
    assert "final_confidence" in result
    assert "attack_chain" in result
    assert "verdict_flip" in result
    assert "search_depth" in result
    
    assert result["verdict_flip"] == True
    assert result["search_depth"] == 2
    assert len(result["attack_chain"]) == 2
    
    print("✓ 数据合成测试通过")
    print(f"  生成的 thought 长度: {len(result['thought'])} 字符")


def run_all_tests():
    """运行所有测试"""
    print("=" * 60)
    print("束搜索攻击引擎单元测试")
    print("=" * 60)
    
    try:
        test_attack_state()
        test_synergy_chains()
        test_default_params()
        test_probe_valid_actions()
        test_data_synthesis()
        
        print("\n" + "=" * 60)
        print("✓ 所有测试通过！")
        print("=" * 60)
        
    except AssertionError as e:
        print(f"\n✗ 测试失败: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ 测试出错: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    run_all_tests()
