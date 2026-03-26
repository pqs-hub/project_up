#!/usr/bin/env python3
"""
从评估数据集中筛选出原始代码被判断模型认为正确的样本。
只有原始代码被判为正确的样本才值得进行攻击评估。
"""
import argparse
import json
import sys
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from core.target_model import TargetModelClient
import yaml


def load_config(config_path: str = "config.yaml"):
    """加载配置文件"""
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def filter_correct_samples(
    input_file: str,
    output_file: str,
    config_path: str = "config.yaml",
    max_samples: int = None,
    verbose: bool = False
):
    """筛选原始代码被判为正确的样本"""
    
    # 加载配置
    config = load_config(config_path)
    target_cfg = config.get("target_model", {})
    
    # 初始化判断模型
    judge_client = TargetModelClient(
        base_url=target_cfg.get("base_url", "http://localhost:8001/v1"),
        api_key=target_cfg.get("api_key", "EMPTY"),
        model=target_cfg.get("model", "qwen25_coder"),
        timeout=target_cfg.get("timeout", 60),
        max_retries=target_cfg.get("max_retries", 3),
        use_local_transformers=target_cfg.get("use_local_transformers", False),
        max_new_tokens=target_cfg.get("max_new_tokens", 512),
    )
    
    # 读取输入数据
    print(f"📖 读取数据集: {input_file}")
    with open(input_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    total = len(data)
    if max_samples:
        data = data[:max_samples]
        print(f"📊 限制处理前 {max_samples} 个样本（共 {total} 个）")
    
    # 筛选过程
    correct_samples = []
    incorrect_samples = []
    failed_samples = []
    
    print(f"\n🔍 开始判断原始代码...")
    for idx, item in enumerate(data, 1):
        task_id = item.get("task_id", f"unknown_{idx}")
        spec = item.get("prompt", "")
        rtl = item.get("canonical_solution", "")
        
        if not spec or not rtl:
            print(f"⚠️  [{idx}/{len(data)}] {task_id}: 缺少规范或RTL代码，跳过")
            failed_samples.append(item)
            continue
        
        # 判断原始代码
        result = judge_client.judge(spec, rtl, use_cot=False)
        
        if result is None:
            print(f"❌ [{idx}/{len(data)}] {task_id}: 判断失败（API错误）")
            failed_samples.append(item)
        elif result.get("is_correct", False):
            if verbose:
                confidence = result.get("confidence", 0.0)
                print(f"✅ [{idx}/{len(data)}] {task_id}: 正确 (置信度: {confidence:.2f})")
            else:
                print(f"✅ [{idx}/{len(data)}] {task_id}: 正确")
            correct_samples.append(item)
        else:
            confidence = result.get("confidence", 0.0)
            print(f"❌ [{idx}/{len(data)}] {task_id}: 错误 (置信度: {confidence:.2f})")
            incorrect_samples.append(item)
    
    # 保存结果
    print(f"\n💾 保存筛选结果到: {output_file}")
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(correct_samples, f, indent=2, ensure_ascii=False)
    
    # 统计信息
    print("\n" + "="*60)
    print("📊 筛选统计:")
    print(f"  总样本数: {len(data)}")
    print(f"  ✅ 原始代码正确: {len(correct_samples)} ({len(correct_samples)/len(data)*100:.1f}%)")
    print(f"  ❌ 原始代码错误: {len(incorrect_samples)} ({len(incorrect_samples)/len(data)*100:.1f}%)")
    print(f"  ⚠️  判断失败: {len(failed_samples)} ({len(failed_samples)/len(data)*100:.1f}%)")
    print("="*60)
    
    # 可选：保存被过滤掉的样本
    if incorrect_samples or failed_samples:
        filtered_file = output_file.replace(".json", "_filtered_out.json")
        with open(filtered_file, "w", encoding="utf-8") as f:
            json.dump({
                "incorrect": incorrect_samples,
                "failed": failed_samples
            }, f, indent=2, ensure_ascii=False)
        print(f"\n📝 被过滤样本已保存到: {filtered_file}")
    
    return len(correct_samples)


def main():
    parser = argparse.ArgumentParser(description="筛选原始代码被判为正确的样本")
    parser.add_argument(
        "--input",
        type=str,
        default="data/verilog_eval.json",
        help="输入数据集路径"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/verilog_eval_correct_only.json",
        help="输出数据集路径（只包含原始代码正确的样本）"
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config.yaml",
        help="配置文件路径"
    )
    parser.add_argument(
        "--max-samples",
        type=int,
        default=None,
        help="最多处理多少个样本（用于测试）"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="显示详细信息"
    )
    
    args = parser.parse_args()
    
    # 执行筛选
    n_correct = filter_correct_samples(
        input_file=args.input,
        output_file=args.output,
        config_path=args.config,
        max_samples=args.max_samples,
        verbose=args.verbose
    )
    
    print(f"\n✅ 完成！共筛选出 {n_correct} 个原始代码正确的样本")
    print(f"💡 后续评估可使用: --eval-file {args.output}")


if __name__ == "__main__":
    main()
