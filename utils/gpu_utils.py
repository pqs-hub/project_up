#!/usr/bin/env python3
"""
GPU工具函数
"""
import subprocess
import re

def get_gpu_info():
    """
    获取GPU信息
    
    Returns:
        List of dict with keys: id, name, memory_used, memory_total, utilization
    """
    try:
        result = subprocess.run(
            ['nvidia-smi', '--query-gpu=index,name,memory.used,memory.total,utilization.gpu',
             '--format=csv,noheader,nounits'],
            capture_output=True,
            text=True,
            check=True
        )
        
        gpus = []
        for line in result.stdout.strip().split('\n'):
            parts = [p.strip() for p in line.split(',')]
            if len(parts) >= 5:
                gpus.append({
                    'id': int(parts[0]),
                    'name': parts[1],
                    'memory_used': int(parts[2]),
                    'memory_total': int(parts[3]),
                    'utilization': int(parts[4])
                })
        return gpus
    except:
        return []

def find_free_gpus(min_free_memory=10000, max_utilization=20):
    """
    找到空闲的GPU
    
    Args:
        min_free_memory: 最小空闲显存（MB）
        max_utilization: 最大利用率（%）
        
    Returns:
        List of GPU IDs
    """
    gpus = get_gpu_info()
    free_gpus = []
    
    for gpu in gpus:
        free_memory = gpu['memory_total'] - gpu['memory_used']
        if free_memory >= min_free_memory and gpu['utilization'] <= max_utilization:
            free_gpus.append(gpu['id'])
    
    return free_gpus

def format_gpu_list(gpu_ids):
    """
    将GPU ID列表格式化为字符串
    
    Args:
        gpu_ids: List of int or str like "0,1,2"
        
    Returns:
        str like "0,1,2"
    """
    if isinstance(gpu_ids, str):
        return gpu_ids
    return ','.join(map(str, gpu_ids))

def print_gpu_status():
    """打印GPU状态"""
    gpus = get_gpu_info()
    if not gpus:
        print("未找到GPU")
        return
    
    print("\n" + "="*70)
    print("GPU状态:")
    print("="*70)
    print(f"{'ID':<4} {'显存使用':<20} {'利用率':<10} {'名称':<30}")
    print("-"*70)
    
    for gpu in gpus:
        used = gpu['memory_used']
        total = gpu['memory_total']
        util = gpu['utilization']
        free = total - used
        
        mem_str = f"{used:>5}MB / {total:>5}MB (空闲: {free:>5}MB)"
        util_str = f"{util:>3}%"
        
        status = "✓ 空闲" if free > 10000 and util < 20 else "✗ 占用"
        print(f"{gpu['id']:<4} {mem_str:<20} {util_str:<10} {gpu['name']:<30} {status}")
    
    print("="*70)
    print()
