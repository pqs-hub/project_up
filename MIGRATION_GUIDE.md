# 代码库迁移指南

## 📦 已上传到 Git

**仓库地址**: https://github.com/pqs-hub/project_up

### 已包含内容
- ✅ 所有 Python 代码
- ✅ 配置文件（YAML, requirements.txt, environment.yml）
- ✅ 文档和 Markdown 文件
- ✅ 脚本文件
- ✅ 小型结果文件

### 已排除内容（需要单独迁移）
- ❌ `data/` 目录中的大型数据集文件 (`.json`, `.jsonl`)
- ❌ `saves/` 目录中的模型文件 (`.safetensors`, `.bin`)
- ❌ 日志文件 (`*.log`, `wandb/`, `logs/`)
- ❌ Python 缓存 (`__pycache__/`)

---

## 🚀 在新服务器上部署

### 1. 克隆代码
```bash
git clone https://github.com/pqs-hub/project_up.git
cd project_up
```

### 2. 创建 Conda 环境
```bash
# 使用 environment.yml
conda env create -f environment.yml
conda activate llm_attack

# 或手动创建
conda create -n llm_attack python=3.10 -y
conda activate llm_attack
pip install -r requirements.txt
```

### 3. 传输大型数据文件（二选一）

#### 方法 A: 使用 rsync（推荐，支持断点续传）
```bash
# 在新服务器上执行
rsync -avP pengqingsong@uubn:/data3/pengqingsong/LLM_attack/data/ ./data/
rsync -avP pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/ ./saves/
```

#### 方法 B: 使用 scp
```bash
# 在新服务器上执行
scp -r pengqingsong@uubn:/data3/pengqingsong/LLM_attack/data ./
scp -r pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves ./
```

### 4. 验证环境
```bash
python -c "import torch; print('PyTorch:', torch.__version__)"
python -c "import transformers; print('Transformers:', transformers.__version__)"
```

---

## 📊 数据文件列表（需单独传输）

### 大型数据集文件（`data/` 目录）
- `adversarial_dataset.jsonl` (98 MB)
- `adversarial_dataset.metadata.jsonl` (68 MB)
- `obfuscation_sft.json` (114 MB)
- `obfuscation_sft_lite.json` (77 MB)
- `qualified_dataset.json` (99 MB)
- `qualified_dataset.normalized.json` (99 MB)
- `qualified_samples.json` (100 MB)
- `sft_attack_success.json` (321 MB)
- `sft_attack_success_lite.json` (76 MB)
- `sft_attack_success_balanced.jsonl` (73 MB)
- `sft_attack_success_registry.jsonl` (86 MB)
- `verilog_samples.json` (122 MB)
- `sft_by_rule/*.json` (多个大文件)

### 模型文件（`saves/` 目录，约 16GB）
- `saves/obfuscation_lora_merged/` - 合并后的 LoRA 模型
- `saves/obfuscation_lora_v1/` - 原始 LoRA 权重

---

## 🔑 SSH 密钥（已配置）

如果需要在新服务器配置 GitHub SSH：

1. 复制私钥到新服务器：
```bash
scp ~/.ssh/id_ed25519* new_server:~/.ssh/
```

2. 或在新服务器生成新密钥：
```bash
ssh-keygen -t ed25519 -C "your_email@example.com"
cat ~/.ssh/id_ed25519.pub  # 复制公钥到 GitHub
```

3. 添加公钥到 GitHub:
   - https://github.com/settings/keys

---

## ⚙️ 配置文件说明

### 主要配置文件
- `config.yaml` - 主配置文件
- `requirements.txt` - Python 依赖
- `environment.yml` - Conda 环境
- `configs/` - 各种实验配置

### vLLM 部署
```bash
# 使用已有脚本
./setup_vllm_env.sh
# 或手动安装
conda activate vllm_deploy
pip install vllm transformers accelerate
```

---

## 📝 注意事项

1. **数据完整性**: 传输大文件后验证 MD5/SHA256
   ```bash
   md5sum data/sft_attack_success.json
   ```

2. **磁盘空间**: 确保新服务器有足够空间
   - 代码: ~500 MB
   - 数据: ~1.5 GB
   - 模型: ~16 GB
   - **总计**: 至少 20 GB

3. **GPU 要求**: 模型推理需要足够显存
   - 建议: 24GB+ (A100/A6000)

4. **Python 版本**: 项目使用 Python 3.10

---

## 🔄 更新代码

在原服务器修改后：
```bash
git add .
git commit -m "Update description"
git push
```

在新服务器同步：
```bash
git pull
```

---

## 🆘 故障排查

### Git 推送失败
- 检查 SSH 密钥: `ssh -T git@github.com`
- 使用 HTTPS + Token 作为备选

### 依赖安装失败
```bash
pip install --upgrade pip
pip install -r requirements.txt --no-cache-dir
```

### 数据传输中断
- 使用 `rsync` 的 `-P` 参数支持断点续传
- 或使用 `screen`/`tmux` 防止连接断开
