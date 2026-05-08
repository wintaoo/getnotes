#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

echo ""
echo "========================================"
echo "  GetNotes - URL 转笔记工具"
echo "========================================"
echo ""

# 检查 Python
if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
    echo "[错误] 未找到 Python，请先安装 Python 3.9+"
    exit 1
fi

PYTHON=$(command -v python3 || command -v python)

# 创建虚拟环境 (如果不存在)
if [ ! -d "venv" ]; then
    echo "[创建虚拟环境...]"
    $PYTHON -m venv venv
fi

# 激活虚拟环境 (兼容 Windows Git Bash 和 Linux/macOS)
if [ -f "venv/Scripts/activate" ]; then
    source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
    source venv/bin/activate
else
    echo "[错误] 未找到虚拟环境激活脚本"
    exit 1
fi

# 安装依赖
echo "[检查依赖...]"
pip install -r requirements.txt -q

# 检查 .env 文件
if [ ! -f ".env" ]; then
    echo "[警告] 未找到 .env 文件，请复制 .env.example 并填入 API Key"
    cp .env.example .env
fi

echo ""
echo "[启动] http://127.0.0.1:5000"
echo "========================================"
echo ""

python app.py
