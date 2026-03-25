#!/usr/bin/env python3
"""
运行规则组合协同效应验证实验

使用方法:
    # 小规模验证（核心场景 + 核心模块）
    python run_synergy_experiment.py --mode core
    
    # 完整实验（所有场景 + 所有模块）
    python run_synergy_experiment.py --mode full
    
    # 自定义实验
    python run_synergy_experiment.py --scenarios scenario1,scenario2 --modules counter,alu
"""

import argparse
import logging
import sys
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

from scripts.experiments.synergy_validator import SynergyValidator
from scripts.experiments.attack_scenarios import (
    ALL_SCENARIOS, CORE_SCENARIOS,
    SCENARIO_SIGNAL_AFFINITY,
    SCENARIO_DISTRACTOR_PAYLOAD,
    SCENARIO_SEMANTIC_HIJACKING,
    SCENARIO_ENHANCED_AFFINITY,
    SCENARIO_LOGIC_CONFUSION,
    SCENARIO_DEEP_DISTRACTOR,
)
from scripts.experiments.test_modules import (
    ALL_TEST_MODULES, CORE_TEST_MODULES,
    COUNTER_MODULES, STATE_MACHINE_MODULES, ALU_MODULES, MUX_MODULES
)


def setup_logging(level=logging.INFO):
    """配置日志"""
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler('logs/synergy_experiment.log'),
            logging.StreamHandler()
        ]
    )


def parse_args():
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description='运行规则组合协同效应验证实验',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
    # 快速验证（推荐首次运行）
    python run_synergy_experiment.py --mode core
    
    # 完整实验
    python run_synergy_experiment.py --mode full
    
    # 仅测试信号亲和力场景
    python run_synergy_experiment.py --scenarios signal_affinity
    
    # 测试计数器和ALU模块
    python run_synergy_experiment.py --module-types counter,alu
        """
    )
    
    parser.add_argument(
        '--mode',
        choices=['core', 'full', 'custom'],
        default='core',
        help='实验模式：core=核心验证（3场景×4模块），full=完整实验（6场景×20模块），custom=自定义'
    )
    
    parser.add_argument(
        '--scenarios',
        type=str,
        help='逗号分隔的场景名称（custom模式）：signal_affinity,distractor_payload,semantic_hijacking,enhanced_affinity,logic_confusion,deep_distractor'
    )
    
    parser.add_argument(
        '--module-types',
        type=str,
        help='逗号分隔的模块类型（custom模式）：counter,state_machine,alu,mux'
    )
    
    parser.add_argument(
        '--config',
        type=str,
        default='config.yaml',
        help='配置文件路径'
    )
    
    parser.add_argument(
        '--output-dir',
        type=str,
        default='results/synergy_experiments',
        help='输出目录'
    )
    
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='详细日志输出'
    )
    
    return parser.parse_args()


def select_scenarios(args):
    """根据参数选择场景"""
    if args.mode == 'core':
        return CORE_SCENARIOS
    elif args.mode == 'full':
        return ALL_SCENARIOS
    else:  # custom
        if not args.scenarios:
            print("错误：custom模式需要指定 --scenarios")
            sys.exit(1)
        
        scenario_map = {
            'signal_affinity': SCENARIO_SIGNAL_AFFINITY,
            'distractor_payload': SCENARIO_DISTRACTOR_PAYLOAD,
            'semantic_hijacking': SCENARIO_SEMANTIC_HIJACKING,
            'enhanced_affinity': SCENARIO_ENHANCED_AFFINITY,
            'logic_confusion': SCENARIO_LOGIC_CONFUSION,
            'deep_distractor': SCENARIO_DEEP_DISTRACTOR,
        }
        
        selected = []
        for name in args.scenarios.split(','):
            name = name.strip()
            if name in scenario_map:
                selected.append(scenario_map[name])
            else:
                print(f"警告：未知场景 '{name}'，跳过")
        
        return selected


def select_modules(args):
    """根据参数选择测试模块"""
    if args.mode == 'core':
        return CORE_TEST_MODULES
    elif args.mode == 'full':
        return ALL_TEST_MODULES
    else:  # custom
        if not args.module_types:
            print("错误：custom模式需要指定 --module-types")
            sys.exit(1)
        
        type_map = {
            'counter': COUNTER_MODULES,
            'state_machine': STATE_MACHINE_MODULES,
            'alu': ALU_MODULES,
            'mux': MUX_MODULES,
        }
        
        selected = []
        for mtype in args.module_types.split(','):
            mtype = mtype.strip()
            if mtype in type_map:
                selected.extend(type_map[mtype])
            else:
                print(f"警告：未知模块类型 '{mtype}'，跳过")
        
        return selected


def main():
    """主函数"""
    args = parse_args()
    
    # 设置日志
    log_level = logging.DEBUG if args.verbose else logging.INFO
    setup_logging(log_level)
    logger = logging.getLogger(__name__)
    
    # 创建输出目录
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # 选择场景和模块
    scenarios = select_scenarios(args)
    modules = select_modules(args)
    
    logger.info(f"实验模式: {args.mode}")
    logger.info(f"场景数量: {len(scenarios)}")
    logger.info(f"模块数量: {len(modules)}")
    logger.info(f"总测试数: {len(scenarios) * len(modules)}")
    
    # 打印场景列表
    print("\n" + "="*60)
    print("实验配置")
    print("="*60)
    print(f"模式: {args.mode}")
    print(f"\n场景列表 ({len(scenarios)}):")
    for i, s in enumerate(scenarios, 1):
        print(f"  {i}. {s.name}")
        print(f"     {s.description}")
    
    print(f"\n模块列表 ({len(modules)}):")
    module_types = {}
    for m in modules:
        mtype = m['type']
        module_types[mtype] = module_types.get(mtype, 0) + 1
    for mtype, count in module_types.items():
        print(f"  - {mtype}: {count} 个")
    print("="*60)
    
    # 确认继续
    if args.mode == 'full':
        response = input("\n这将运行大量测试，可能需要较长时间。是否继续？(y/n): ")
        if response.lower() != 'y':
            print("实验已取消")
            return
    
    # 创建验证器
    logger.info("初始化验证器...")
    validator = SynergyValidator(args.config)
    
    # 运行实验
    logger.info("开始运行实验...")
    try:
        results = validator.run_experiment(scenarios, modules)
        
        # 保存结果
        results_file = output_dir / 'experiment_results.jsonl'
        validator.save_results(str(results_file))
        
        # 生成报告
        report_file = output_dir / 'experiment_report.json'
        validator.generate_report(str(report_file))
        
        logger.info(f"\n实验完成！")
        logger.info(f"结果已保存到: {results_file}")
        logger.info(f"报告已保存到: {report_file}")
        
    except KeyboardInterrupt:
        logger.warning("\n实验被用户中断")
        # 保存已有结果
        if validator.results:
            results_file = output_dir / 'experiment_results_partial.jsonl'
            validator.save_results(str(results_file))
            logger.info(f"部分结果已保存到: {results_file}")
    
    except Exception as e:
        logger.error(f"实验执行出错: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
