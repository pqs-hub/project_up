# 模型迁移指南

将训练好的模型从当前服务器传输到另一个服务器。

---

## 📊 模型信息

### 当前服务器模型位置
```
/data3/pengqingsong/LLM_attack/saves/
├── obfuscation_lora_merged/    # 15GB - 合并后的完整模型
└── obfuscation_lora_v1/        # 833MB - LoRA 权重
```

### 模型大小
- **完整模型** (`obfuscation_lora_merged/`): ~15GB
- **LoRA 权重** (`obfuscation_lora_v1/`): ~833MB

---

## 🚀 方法 1: 使用 rsync（推荐）

### 优点
- ✅ 支持断点续传
- ✅ 增量传输（只传输变化的文件）
- ✅ 显示传输进度
- ✅ 保留文件权限和时间戳
- ✅ 可以压缩传输

### 传输完整模型

```bash
# 在新服务器上执行
rsync -avP --compress \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged/ \
  ~/LLM_attack/saves/obfuscation_lora_merged/
```

### 传输 LoRA 权重

```bash
# 在新服务器上执行
rsync -avP --compress \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_v1/ \
  ~/LLM_attack/saves/obfuscation_lora_v1/
```

### 传输整个 saves 目录

```bash
# 在新服务器上执行
rsync -avP --compress \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/ \
  ~/LLM_attack/saves/
```

### rsync 参数说明
- `-a`: 归档模式（保留权限、时间戳等）
- `-v`: 显示详细信息
- `-P`: 显示进度 + 支持断点续传
- `--compress`: 传输时压缩（节省带宽）

### 断点续传
如果传输中断，重新运行相同的命令即可从断点继续。

---

## 🔄 方法 2: 使用 scp

### 优点
- ✅ 简单直接
- ✅ 系统自带，无需额外安装

### 缺点
- ❌ 不支持断点续传
- ❌ 传输中断需要重新开始

### 传输完整模型

```bash
# 在新服务器上执行
scp -r pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged \
  ~/LLM_attack/saves/
```

### 传输 LoRA 权重

```bash
# 在新服务器上执行
scp -r pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_v1 \
  ~/LLM_attack/saves/
```

### 使用压缩传输

```bash
# 在新服务器上执行
scp -C -r pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged \
  ~/LLM_attack/saves/
```

参数 `-C` 启用压缩。

---

## 📦 方法 3: 打包后传输（适合网络不稳定）

### 步骤 1: 在原服务器打包

```bash
# 在原服务器执行
cd /data3/pengqingsong/LLM_attack

# 打包完整模型
tar -czf obfuscation_lora_merged.tar.gz saves/obfuscation_lora_merged/

# 或打包 LoRA 权重
tar -czf obfuscation_lora_v1.tar.gz saves/obfuscation_lora_v1/

# 查看打包后的大小
ls -lh *.tar.gz
```

### 步骤 2: 传输压缩包

```bash
# 在新服务器执行
scp pengqingsong@uubn:/data3/pengqingsong/LLM_attack/obfuscation_lora_merged.tar.gz ~/

# 或使用 rsync（支持断点续传）
rsync -avP --compress \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/obfuscation_lora_merged.tar.gz \
  ~/
```

### 步骤 3: 在新服务器解压

```bash
# 在新服务器执行
cd ~/LLM_attack
mkdir -p saves
tar -xzf ~/obfuscation_lora_merged.tar.gz -C .

# 验证文件
ls -lh saves/obfuscation_lora_merged/
```

### 步骤 4: 清理压缩包（可选）

```bash
# 原服务器
rm /data3/pengqingsong/LLM_attack/obfuscation_lora_merged.tar.gz

# 新服务器
rm ~/obfuscation_lora_merged.tar.gz
```

---

## 🌐 方法 4: 使用云存储中转（适合跨网络传输）

### 使用场景
- 两台服务器不在同一网络
- 无法直接 SSH 连接
- 需要多次下载

### 步骤

#### 1. 上传到云存储

```bash
# 使用 rclone（支持多种云存储）
# 安装 rclone: https://rclone.org/install/

# 配置云存储
rclone config

# 上传模型
rclone copy saves/obfuscation_lora_merged/ \
  remote:bucket/models/obfuscation_lora_merged/ \
  --progress
```

#### 2. 在新服务器下载

```bash
# 下载模型
rclone copy remote:bucket/models/obfuscation_lora_merged/ \
  ~/LLM_attack/saves/obfuscation_lora_merged/ \
  --progress
```

### 支持的云存储
- Google Drive
- Dropbox
- OneDrive
- Amazon S3
- 阿里云 OSS
- 腾讯云 COS
- 等等

---

## ⚡ 方法 5: 使用 screen/tmux 防止传输中断

### 为什么需要？
- 传输大文件可能需要数小时
- SSH 连接可能断开
- 使用 screen/tmux 可以让传输在后台继续

### 使用 screen

```bash
# 在新服务器上创建 screen 会话
screen -S model_transfer

# 在 screen 中执行传输命令
rsync -avP --compress \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged/ \
  ~/LLM_attack/saves/obfuscation_lora_merged/

# 按 Ctrl+A 然后按 D 分离会话（传输继续在后台运行）

# 重新连接到会话
screen -r model_transfer

# 查看所有会话
screen -ls
```

### 使用 tmux

```bash
# 创建 tmux 会话
tmux new -s model_transfer

# 执行传输命令
rsync -avP --compress \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged/ \
  ~/LLM_attack/saves/obfuscation_lora_merged/

# 按 Ctrl+B 然后按 D 分离会话

# 重新连接
tmux attach -t model_transfer

# 查看所有会话
tmux ls
```

---

## 📋 传输前检查清单

### 1. 检查磁盘空间

```bash
# 在新服务器检查可用空间
df -h ~

# 确保至少有 20GB 可用空间（完整模型需要 15GB）
```

### 2. 测试 SSH 连接

```bash
# 在新服务器测试连接
ssh pengqingsong@uubn "echo 'Connection OK'"
```

### 3. 检查网络速度

```bash
# 测试传输速度（传输一个小文件）
time scp pengqingsong@uubn:/data3/pengqingsong/LLM_attack/README.md /tmp/

# 估算传输时间
# 15GB ÷ 网络速度 = 预计时间
# 例如：100MB/s 网络 → 15GB ÷ 100MB/s ≈ 150 秒 ≈ 2.5 分钟
# 例如：10MB/s 网络 → 15GB ÷ 10MB/s ≈ 1500 秒 ≈ 25 分钟
```

---

## ✅ 传输后验证

### 1. 检查文件数量

```bash
# 原服务器
find /data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged/ -type f | wc -l

# 新服务器
find ~/LLM_attack/saves/obfuscation_lora_merged/ -type f | wc -l

# 两者应该相同
```

### 2. 检查总大小

```bash
# 原服务器
du -sh /data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged/

# 新服务器
du -sh ~/LLM_attack/saves/obfuscation_lora_merged/

# 大小应该接近（可能有细微差别）
```

### 3. 验证关键文件

```bash
# 检查模型配置文件
cat ~/LLM_attack/saves/obfuscation_lora_merged/config.json

# 检查模型权重文件
ls -lh ~/LLM_attack/saves/obfuscation_lora_merged/*.safetensors
```

### 4. 测试模型加载

```bash
# 在新服务器上测试加载模型
cd ~/LLM_attack

python -c "
from transformers import AutoModelForCausalLM, AutoTokenizer

model_path = 'saves/obfuscation_lora_merged'
print(f'Loading model from {model_path}...')

tokenizer = AutoTokenizer.from_pretrained(model_path)
model = AutoModelForCausalLM.from_pretrained(model_path)

print('✓ Model loaded successfully!')
print(f'Model type: {type(model).__name__}')
print(f'Vocab size: {len(tokenizer)}')
"
```

---

## 🔧 故障排查

### 问题 1: 权限被拒绝

```bash
# 确保 SSH 密钥配置正确
ssh-copy-id pengqingsong@uubn

# 或手动添加公钥到原服务器
cat ~/.ssh/id_rsa.pub | ssh pengqingsong@uubn "cat >> ~/.ssh/authorized_keys"
```

### 问题 2: 磁盘空间不足

```bash
# 清理不必要的文件
# 或选择传输 LoRA 权重（只需 833MB）而不是完整模型
```

### 问题 3: 传输速度慢

```bash
# 使用压缩传输
rsync -avP --compress ...

# 或限制带宽（避免占满网络）
rsync -avP --bwlimit=10000 ...  # 限制为 10MB/s
```

### 问题 4: 传输中断

```bash
# 使用 rsync 重新运行相同命令即可继续
# 或使用 screen/tmux 防止中断
```

---

## 💡 最佳实践建议

### 1. 优先传输 LoRA 权重
- 如果新服务器已有基础模型（如 Qwen2.5-Coder-7B）
- 只需传输 LoRA 权重（833MB）
- 在新服务器上重新合并

```bash
# 传输 LoRA 权重
rsync -avP --compress \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_v1/ \
  ~/LLM_attack/saves/obfuscation_lora_v1/

# 在新服务器上合并
cd ~/LLM_attack
bash scripts/ops/merge_lora.sh
```

### 2. 使用 rsync + screen/tmux
- 最可靠的组合
- 支持断点续传 + 防止连接断开

### 3. 验证 MD5/SHA256
```bash
# 原服务器生成校验和
find saves/obfuscation_lora_merged/ -type f -exec md5sum {} \; > model_checksums.txt

# 传输校验和文件
scp model_checksums.txt new_server:~/

# 新服务器验证
cd ~/LLM_attack
md5sum -c ~/model_checksums.txt
```

### 4. 分批传输
如果网络不稳定，可以分批传输：

```bash
# 只传输 .safetensors 文件
rsync -avP --include='*.safetensors' --exclude='*' \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged/ \
  ~/LLM_attack/saves/obfuscation_lora_merged/

# 然后传输其他文件
rsync -avP --exclude='*.safetensors' \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged/ \
  ~/LLM_attack/saves/obfuscation_lora_merged/
```

---

## 📝 快速参考

### 推荐命令（复制即用）

```bash
# 在新服务器上执行以下命令：

# 1. 创建 screen 会话
screen -S model_transfer

# 2. 传输完整模型（15GB）
rsync -avP --compress \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_merged/ \
  ~/LLM_attack/saves/obfuscation_lora_merged/

# 或传输 LoRA 权重（833MB）
rsync -avP --compress \
  pengqingsong@uubn:/data3/pengqingsong/LLM_attack/saves/obfuscation_lora_v1/ \
  ~/LLM_attack/saves/obfuscation_lora_v1/

# 3. 分离 screen（Ctrl+A, D）

# 4. 稍后重新连接查看进度
screen -r model_transfer
```

---

## 📞 需要帮助？

如果遇到问题，可以：
1. 检查本文档的故障排查部分
2. 查看传输日志和错误信息
3. 确认网络连接和权限设置
