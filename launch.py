# -*- coding: utf-8 -*-
"""
负载数据分析系统启动器
替代原来的 run.bat，避免中文乱码问题
"""

import os
import sys
import subprocess
import webbrowser
from time import sleep

def main():
    # 设置控制台编码为中文 GBK (代码页 936)
    os.system('chcp 936 >nul')
    
    # 设置 Python 环境变量
    os.environ["PYTHONIOENCODING"] = "gbk"
    os.environ["PYTHONUTF8"] = "1"
    
    print("启动负载数据分析系统...")
    
    # 检查是否需要安装依赖
    print("检查依赖包...")
    try:
        import streamlit
        import pandas
        import matplotlib
        import numpy
        print("所有依赖包已安装")
    except ImportError:
        print("缺少必要依赖包，正在安装...")
        result = subprocess.run([
            sys.executable, "-m", "pip", "install", 
            "streamlit", "pandas", "matplotlib", "numpy"
        ], capture_output=True, text=True)
        
        if result.returncode == 0:
            print("依赖包安装成功!")
        else:
            print("依赖包安装失败，错误信息:")
            print(result.stderr)
            input("按回车键退出...")
            return
    
    print("启动Streamlit应用...")
    print("应用将在浏览器中打开，请稍候...")
    
    # 启动 Streamlit 并打开浏览器
    try:
        # 先启动 Streamlit 服务器
        process = subprocess.Popen([
            sys.executable, "-m", "streamlit", "run", "main.py",
            "--server.port", "8501", "--browser.serverAddress", "localhost"
        ])
        
        # 等待服务器启动
        sleep(3)
        
        # 打开浏览器
        webbrowser.open("http://localhost:8501")
        
        print("Streamlit 应用已启动，按 Ctrl+C 可停止服务")
        
        # 等待用户中断
        try:
            process.wait()
        except KeyboardInterrupt:
            print("\n正在停止服务...")
            process.terminate()
            
    except Exception as e:
        print(f"启动失败: {e}")
    
    input("按回车键退出...")

if __name__ == "__main__":
    main()
