@echo off
setlocal
cd /d "%~dp0"

chcp 936 >nul
set "PYTHONIOENCODING=gbk"
set "PYTHONUTF8=1"

echo 启动负载数据分析系统...
REM 如需安装依赖，去掉下两行前面的 REM
REM python -m pip install --upgrade pip
REM python -m pip install -r requirements.txt

echo 启动Streamlit应用...
python -m streamlit run main.py

pause