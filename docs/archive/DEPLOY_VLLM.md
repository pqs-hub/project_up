# 使用 vLLM 部署模型加速推理

在 `hw_attack` 环境中用 vLLM 部署本地模型，`filter_qualified.py` 和 `evaluate.py` 通过 HTTP 调用可显著加快运行速度（尤其批量请求时）。

## 1. 安装 vLLM（在 hw_attack 环境中）

```bash
conda activate hw_attack
pip install vllm -i https://mirrors.aliyun.com/pypi/simple/
```

若已配置默认 pip 源为国内镜像，直接执行 `pip install vllm` 即可。

## 2. 启动 vLLM 服务

**方式一：用项目脚本（推荐）**

```bash
cd /data3/pengqingsong/LLM_attack
chmod +x scripts/ops/run_vllm.sh
./scripts/ops/run_vllm.sh
```

脚本会自动激活 `hw_attack`，并从 `config.yaml` 读取 `target_model.model` 作为模型路径。也可手动指定：

```bash
./scripts/ops/run_vllm.sh /data3/pengqingsong/Model/Qwen2.5-Coder-7B
```

**方式二：手动命令**

```bash
conda activate hw_attack
vllm serve /data3/pengqingsong/Model/Qwen2.5-Coder-7B \
  --served-model-name "/data3/pengqingsong/Model/Qwen2.5-Coder-7B" \
  --host 0.0.0.0 --port 8000
```

服务就绪后终端会提示 `Uvicorn running on http://0.0.0.0:8000`，保持该终端运行。

## 3. 使用 vLLM 跑筛选 / 评估

- **filter_qualified.py**：在 `config.yaml` 中将 `use_local_transformers` 改为 `false`，然后照常运行：

  ```bash
  conda activate hw_attack
  python filter_qualified.py
  ```

  此时会请求 `http://localhost:8000/v1`，并启用 `parallelism.num_workers` 并发，加快筛选。

- **evaluate.py**：无需改 config，直接指定本地服务：

  ```bash
  python evaluate.py --results <results_dir> --dataset <dataset.json> \
    --provider local --model "/data3/pengqingsong/Model/Qwen2.5-Coder-7B" \
    --base-url http://localhost:8000/v1 --output eval_results/
  ```

  `--model` 需与 vLLM 的 `--served-model-name` 一致（脚本中已与 config 的 `model` 一致）。

## 4. 注意

- 先启动 vLLM，再运行 filter/evaluate，否则会连不上 8000 端口。
- 不用 vLLM 时，将 `use_local_transformers` 改回 `true` 即可继续用本地 transformers 推理。
- 若本机有多张 GPU，vLLM 会自动用多卡；可通过 `CUDA_VISIBLE_DEVICES` 指定使用的 GPU。
