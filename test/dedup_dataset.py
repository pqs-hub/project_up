#!/usr/bin/env python3
"""对合并后的数据集进行去重处理"""

import json
import hashlib
from pathlib import Path

def compute_code_fingerprint(code: str) -> str:
    """计算代码的指纹用于去重"""
    if not code:
        return ""
    # 归一化代码：去除空格和换行
    normalized = ''.join(code.split())
    return hashlib.md5(normalized.encode('utf-8')).hexdigest()

def compute_sample_fingerprint(sample: dict) -> str:
    """计算样本的综合指纹"""
    # 使用多个字段组合生成指纹
    key_fields = [
        sample.get('rule_id', ''),
        sample.get('input', ''),
        sample.get('transformed_rtl', '')
    ]
    combined = '|'.join(key_fields)
    return hashlib.md5(combined.encode('utf-8')).hexdigest()

def main():
    input_file = "/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/attack_success_samples.jsonl"
    output_file = "/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/attack_success_samples_dedup.jsonl"
    report_file = "/mnt/public/pqs/Veri_atack/project_up/doc/rule15_verified_dataset/dedup_report.txt"
    
    print("开始去重处理...")
    
    # 读取所有样本
    samples = []
    duplicates_count = 0
    rule_stats = {}
    
    with open(input_file, "r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            if not line.strip():
                continue
                
            try:
                sample = json.loads(line)
                samples.append(sample)
                
                # 统计各规则原始数量
                rule_id = sample.get('rule_id', 'unknown')
                if rule_id not in rule_stats:
                    rule_stats[rule_id] = {'original': 0, 'deduped': 0}
                rule_stats[rule_id]['original'] += 1
                
                if line_num % 10000 == 0:
                    print(f"已读取 {line_num} 行")
                    
            except Exception as e:
                print(f"解析第 {line_num} 行时出错: {e}")
                continue
    
    print(f"总共读取 {len(samples)} 个样本")
    
    # 去重处理 - 只基于transformed_rtl去重
    seen_code_fingerprints = set()
    deduped_samples = []
    
    for i, sample in enumerate(samples):
        # 只计算变换后代码的指纹
        code_fp = compute_code_fingerprint(sample.get('transformed_rtl', ''))
        
        # 检查是否重复
        if code_fp in seen_code_fingerprints:
            duplicates_count += 1
        else:
            deduped_samples.append(sample)
            seen_code_fingerprints.add(code_fp)
            
            # 更新去重后统计
            rule_id = sample.get('rule_id', 'unknown')
            if rule_id in rule_stats:
                rule_stats[rule_id]['deduped'] += 1
        
        if (i + 1) % 10000 == 0:
            print(f"已处理 {i + 1}/{len(samples)} 个样本，去重 {duplicates_count} 个")
    
    # 写入去重后的文件
    with open(output_file, "w", encoding="utf-8") as f:
        for sample in deduped_samples:
            f.write(json.dumps(sample, ensure_ascii=False) + "\n")
    
    # 生成去重报告
    with open(report_file, "w", encoding="utf-8") as f:
        f.write("数据集去重报告（仅基于transformed_rtl）\n")
        f.write("=" * 50 + "\n")
        f.write(f"原始样本数: {len(samples)}\n")
        f.write(f"去重样本数: {duplicates_count}\n")
        f.write(f"保留样本数: {len(deduped_samples)}\n")
        f.write(f"去重率: {duplicates_count/len(samples)*100:.2f}%\n\n")
        
        f.write("各规则去重统计:\n")
        f.write("-" * 30 + "\n")
        for rule_id, stats in sorted(rule_stats.items()):
            original = stats['original']
            deduped = stats['deduped']
            dup_count = original - deduped
            dup_rate = dup_count / original * 100 if original > 0 else 0
            f.write(f"{rule_id}: {deduped}/{original} (去重 {dup_count}, {dup_rate:.1f}%)\n")
    
    print(f"\n去重完成!")
    print(f"  原始样本: {len(samples)}")
    print(f"  去重样本: {duplicates_count}")
    print(f"  保留样本: {len(deduped_samples)}")
    print(f"  去重率: {duplicates_count/len(samples)*100:.2f}%")
    print(f"  输出文件: {output_file}")
    print(f"  报告文件: {report_file}")

if __name__ == "__main__":
    main()
