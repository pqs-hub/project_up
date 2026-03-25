# vLLM 联动说明（run_vllm.sh + evaluate.py）

本文档解释如何在本地用 vLLM 部署 Qwen2.5-Coder-7B，并保证 `evaluate.py` 能正确找到模型（避免 404 Not Found）。

## 1) 启动 vLLM

推荐方式（你当前正在用的方式，明确 served model name）：

```bash
BASE_MODEL=/data3/pengqingsong/Model/Qwen2.5-Coder-7B \
VLLM_SERVED_MODEL_NAME=qwen2.5-coder-7b \
VLLM_USE_LORA=0 \
bash scripts/ops/run_vllm.sh /data3/pengqingsong/Model/Qwen2.5-Coder-7B
```

启动后：
- 监听端口（默认）：`VLLM_PORT=8001`  
- OpenAI-compatible base url：`http://localhost:8001/v1`
- API `model` 字段应使用你设置的 served name：`qwen2.5-coder-7b`

如果你使用 LoRA 模式，则 served name 来自脚本里的默认 `LORA_SERVED_NAME`（或环境变量覆盖）。

## 2) evaluate.py 调用方式

`evaluate.py` 通过 OpenAI SDK 调用 `/v1/chat/completions`，关键参数：

- `--provider local`
- `--base-url http://localhost:8001/v1`（端口需与 vLLM 启动一致）
- `--model <served-model-name>`（必须等于 vLLM 对外暴露的 served name）

示例：

```bash
python evaluate.py \
  --dataset data/qualified_dataset.normalized.json \
  --results results/qualified_by_rule/T12 \
  --output eval_results/T12_verify \
  --provider local \
  --model qwen2.5-coder-7b \
  --base-url http://localhost:8001/v1 \
  --modes original adversarial
```

## 3) 常见坑

- 404 Not Found（模型不存在）：
  - `--model` 写成了原始权重目录名，而不是 served model name。
  - 或端口选错了（8000 vs 8001）。
- 404 Not Found（根路径不对）：
  - `--base-url` 应指向 `.../v1`，不要漏掉 `/v1`。

