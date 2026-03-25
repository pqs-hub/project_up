#!/bin/bash
# vLLM部署环境安装脚本

set -e

echo "=== 激活vllm_deploy环境 ==="
source /data3/pengqingsong/software/miniconda3/etc/profile.d/conda.sh
conda activate vllm_deploy

echo "=== 安装PyTorch (CUDA 12.1) ==="
pip install torch==2.4.0 torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

echo "=== 安装vLLM ==="
pip install vllm -i https://mirrors.aliyun.com/pypi/simple/

echo "=== 安装额外依赖 ==="
pip install transformers accelerate -i https://mirrors.aliyun.com/pypi/simple/

echo "=== 测试vLLM安装 ==="
python -c "import vllm; print(f'✓ vLLM version: {vllm.__version__}')"

echo ""
echo "=== ✅ vLLM环境安装完成！==="
echo ""
echo "使用方法:"
echo "  conda activate vllm_deploy"
echo "  python -m vllm.entrypoints.openai.api_server --model <模型路径> --port 8000"
