#!/bin/bash
# SSH 反向隧道 - 让两个无法互通的服务器可以通信

# 在内网服务器（infini）上运行此脚本
# 它会在外网服务器（uubn）上建立一个反向端口

REMOTE_SERVER="pengqingsong@uubn"
REMOTE_PORT=2222  # 在外网服务器上监听的端口
LOCAL_PORT=22     # 内网服务器的SSH端口

echo "建立反向SSH隧道..."
echo "外网服务器将可以通过 localhost:${REMOTE_PORT} 访问本机"

# -R: 反向端口转发
# -N: 不执行远程命令
# -f: 后台运行
# -o ServerAliveInterval=60: 保持连接
ssh -fN -R ${REMOTE_PORT}:localhost:${LOCAL_PORT} \
    -o ServerAliveInterval=60 \
    -o ServerAliveCountMax=3 \
    ${REMOTE_SERVER}

if [ $? -eq 0 ]; then
    echo "反向隧道已建立！"
    echo ""
    echo "现在在外网服务器（uubn）上可以这样访问内网服务器："
    echo "  ssh -p ${REMOTE_PORT} pqs@localhost"
    echo ""
    echo "同步模型示例："
    echo "  # 在外网服务器上执行"
    echo "  rsync -avP -e 'ssh -p ${REMOTE_PORT}' /path/to/model/ pqs@localhost:/path/to/dest/"
else
    echo "隧道建立失败！"
    exit 1
fi
