#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从qualified_dataset_correct.json中提取置信度<0.5的样本
"""

import json

def extract_low_confidence():
    input_file = "/mnt/public/pqs/Veri_atack/project_up/data/qualified_newcot_correct.json"
    output_file = "/mnt/public/pqs/Veri_atack/project_up/data/qualified_newcot_noconfidence.json"
    
    print(f"📖 读取文件: {input_file}")
    with open(input_file, 'r') as f:
        data = json.load(f)
    
    print(f"✅ 总样本数: {len(data)}")
    
    # 给每个样本添加confidence用于排序
    samples_with_conf = []
    for sample in data:
        judge_verdict = sample.get('judge_verdict', {})
        confidence = judge_verdict.get('confidence', 1.0)
        samples_with_conf.append((confidence, sample))
    
    # 按置信度从小到大排序
    samples_with_conf.sort(key=lambda x: x[0])
    
    # 提取置信度最小的10000个样本
    max_samples = 10000
    low_confidence_samples = [s[1] for s in samples_with_conf[:max_samples]]
    
    print(f"🔍 提取置信度最小的 {len(low_confidence_samples)} 个样本")
    
    # 保存到新文件
    with open(output_file, 'w') as f:
        json.dump(low_confidence_samples, f, indent=2, ensure_ascii=False)
    
    print(f"💾 已保存到: {output_file}")
    
    # 显示统计信息
    if low_confidence_samples:
        confidences = [s.get('judge_verdict', {}).get('confidence', 1.0) for s in low_confidence_samples]
        print(f"\n📊 置信度统计:")
        print(f"  最小值: {min(confidences):.4f}")
        print(f"  最大值: {max(confidences):.4f}")
        print(f"  平均值: {sum(confidences)/len(confidences):.4f}")
        
        # 显示前5个样本的task_id
        print(f"\n📝 前5个低置信度样本:")
        for i, sample in enumerate(low_confidence_samples[:5]):
            task_id = sample.get('task_id', 'unknown')
            conf = sample.get('judge_verdict', {}).get('confidence', 1.0)
            print(f"  {i+1}. {task_id} - 置信度: {conf:.4f}")

if __name__ == "__main__":
    extract_low_confidence()
