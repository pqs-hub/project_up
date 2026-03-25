#!/usr/bin/env python3
"""
vLLM部署工具

支持指定GPU、端口、模型参数等
"""
import subprocess
import time
import requests
from pathlib import Path

def deploy_vllm(
    model_path: str,
    port: int = 8000,
    gpus: str = "0",
    tensor_parallel_size: int = 1,
    gpu_memory_utilization: float = 0.9,
    max_model_len: int = 4096,
    host: str = "0.0.0.0",
    log_file: str = None
):
    """
    部署vLLM API服务
    
    Args:
        model_path: 模型路径
        port: API端口
        gpus: 使用的GPU（如 "0,1"）
        tensor_parallel_size: 张量并行大小
        gpu_memory_utilization: GPU内存利用率
        max_model_len: 最大模型长度
        host: 绑定地址
        log_file: 日志文件路径
        
    Returns:
        subprocess.Popen对象
    """
    import os
    
    # 设置环境变量
    env = os.environ.copy()
    env['CUDA_VISIBLE_DEVICES'] = gpus
    
    # 构建命令
    cmd = [
        "python", "-m", "vllm.entrypoints.openai.api_server",
        "--model", model_path,
        "--host", host,
        "--port", str(port),
        "--tensor-parallel-size", str(tensor_parallel_size),
        "--gpu-memory-utilization", str(gpu_memory_utilization),
        "--max-model-len", str(max_model_len),
    ]
    
    # 启动服务
    if log_file:
        log_file = Path(log_file)
        log_file.parent.mkdir(parents=True, exist_ok=True)
        f = open(log_file, 'w')
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=f,
            stderr=subprocess.STDOUT
        )
    else:
        process = subprocess.Popen(
            cmd,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )
    
    print(f"vLLM服务已启动 (PID: {process.pid})")
    print(f"  模型: {model_path}")
    print(f"  端口: {port}")
    print(f"  GPU: {gpus}")
    if log_file:
        print(f"  日志: {log_file}")
    
    return process

def wait_for_api(base_url: str, timeout: int = 120):
    """
    等待API服务就绪
    
    Args:
        base_url: API基础URL（如 http://localhost:8000/v1）
        timeout: 超时时间（秒）
        
    Returns:
        True if ready, False if timeout
    """
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            response = requests.get(f"{base_url.rstrip('/')}/models", timeout=5)
            if response.status_code == 200:
                print(f"✓ API服务已就绪: {base_url}")
                return True
        except:
            pass
        time.sleep(2)
    
    print(f"✗ API服务启动超时: {base_url}")
    return False

def stop_vllm(process):
    """停止vLLM服务"""
    if process:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
        print(f"✓ vLLM服务已停止 (PID: {process.pid})")
