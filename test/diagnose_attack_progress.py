#!/usr/bin/env python3
"""诊断攻击数据集生成进度"""

import json
import time
from pathlib import Path

def diagnose():
    """诊断当前进度"""
    
    # 1. 检查输出文件
    data_dir = Path("data")
    jsonl_files = sorted(data_dir.glob("attack_dataset_*.jsonl"), key=lambda p: p.stat().st_mtime, reverse=True)
    
    print("=" * 60)
    print("📁 输出文件检查")
    print("=" * 60)
    
    if jsonl_files:
        latest = jsonl_files[0]
        stat = latest.stat()
        print(f"最新文件: {latest.name}")
        print(f"大小: {stat.st_size} bytes")
        print(f"修改时间: {time.ctime(stat.st_mtime)}")
        
        # 读取行数
        try:
            with open(latest) as f:
                lines = f.readlines()
            print(f"成功样本数: {len(lines)}")
            
            if len(lines) > 0:
                print("\n最后一个样本:")
                last_sample = json.loads(lines[-1])
                print(f"  task_id: {last_sample.get('task_id')}")
                print(f"  attack_rule: {last_sample.get('attack_rule')}")
                print(f"  judge_transformed_answer: {last_sample.get('judge_transformed_answer')}")
        except Exception as e:
            print(f"读取文件错误: {e}")
    else:
        print("❌ 没有找到输出文件！")
        print("   可能文件还未创建，或路径不对")
    
    print("\n" + "=" * 60)
    print("🔍 可能的问题")
    print("=" * 60)
    
    if not jsonl_files or jsonl_files[0].stat().st_size == 0:
        print("""
可能原因：
1. ❌ Testbench运行失败
   - 所有变换后的代码都没通过testbench
   - 检查testbench运行器状态
   
2. ❌ Judge判断很慢
   - 每个job需要2次judge调用（original + transformed）
   - 37000个job已处理 = 74000次judge调用
   - 如果judge每次2秒，需要41小时
   
3. ❌ Judge认为所有代码都正确
   - 攻击全部被识破
   - 需要检查攻击规则是否有效

建议检查：
1. 查看终端是否有大量WARNING
2. 检查judge模型响应速度：
   curl http://localhost:8001/v1/models
3. 检查testbench运行器日志
4. 降低workers数量（当前32可能太多）
""")
    
    print("\n" + "=" * 60)
    print("⚡ 性能估算")
    print("=" * 60)
    
    total_jobs = 187830
    completed = 37212  # 从你的进度条
    rate = 60.79  # job/s
    
    print(f"总任务数: {total_jobs:,}")
    print(f"已完成: {completed:,} ({completed/total_jobs*100:.1f}%)")
    print(f"当前速度: {rate:.1f} job/s")
    
    remaining = total_jobs - completed
    eta_seconds = remaining / rate
    eta_minutes = eta_seconds / 60
    
    print(f"\n预计剩余时间: {eta_minutes:.1f} 分钟 ({eta_seconds/3600:.1f} 小时)")
    
    # 计算每个job的平均时间
    avg_time_per_job = 1 / rate
    print(f"每个job平均耗时: {avg_time_per_job:.2f} 秒")
    
    # 如果有testbench + 2次judge
    print(f"\n如果每个job包含:")
    print(f"  - Testbench运行: ~1秒")
    print(f"  - Judge判断×2: ~2秒")
    print(f"  - 代码变换: ~0.5秒")
    print(f"  理论耗时: ~3.5秒/job")
    print(f"  但实际: {avg_time_per_job:.2f}秒/job")
    
    if avg_time_per_job > 3:
        print(f"\n⚠️  实际耗时({avg_time_per_job:.2f}s) > 理论耗时(3.5s)")
        print(f"   可能瓶颈: Judge响应慢或Testbench慢")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    diagnose()
