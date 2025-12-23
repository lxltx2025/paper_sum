@echo off
chcp 65001 > nul
echo ========================================
echo   医学AI文献批量分析系统
echo   Ollama + Qwen2.5:14B + WSL2
echo ========================================
echo.

REM 使用WSL运行
wsl bash -c "cd /mnt$(echo %CD% | sed 's/\\/\//g' | sed 's/://') && bash run.sh"

pause