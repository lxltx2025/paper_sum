#!/bin/bash
# 医学AI文献分析系统 - 启动脚本

echo "========================================"
echo "  医学AI文献批量分析系统"
echo "  Ollama + Qwen2.5:14B + WSL2"
echo "========================================"

# 检查Python
if ! command -v python3 &> /dev/null; then
    echo "❌ 未找到Python3，请先安装"
    exit 1
fi

# 检查Ollama服务
echo "检查Ollama服务..."
if ! curl -s http://localhost:11434/api/tags > /dev/null 2>&1; then
    echo "⚠️ Ollama服务未运行，尝试启动..."
    ollama serve &
    sleep 5
fi

# 检查模型
echo "检查Qwen2.5:14b模型..."
if ! ollama list | grep -q "qwen2.5:14b"; then
    echo "📥 下载Qwen2.5:14b模型（可能需要一些时间）..."
    ollama pull qwen2.5:14b
fi

# 安装依赖
echo "检查Python依赖..."
pip install -q -r requirements.txt

# 运行分析
echo ""
echo "开始分析..."
python3 analyzer.py

echo ""
echo "========================================"
echo "分析完成！"
echo "========================================"