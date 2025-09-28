import streamlit as st
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta
import re
import math
import io

# 设置页面配置
st.set_page_config(
    page_title="负载数据分析系统",
    page_icon="📊",
    layout="wide"
)

# 自定义CSS样式
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 2rem;
    }
    .section-header {
        font-size: 1.5rem;
        color: #2c3e50;
        margin-top: 2rem;
        margin-bottom: 1rem;
    }
    .metric-container {
        background-color: #f8f9fa;
        padding: 1rem;
        border-radius: 0.5rem;
        border-left: 4px solid #1f77b4;
    }
</style>
""", unsafe_allow_html=True)

def truncate_decimal(value, decimals=1):
    """截断小数到指定位数（不四舍五入）"""
    multiplier = 10 ** decimals
    return math.floor(value * multiplier) / multiplier

def parse_time_to_seconds(time_str):
    """将时间字符串转换为秒数"""
    try:
        time_parts = time_str.split(':')
        if len(time_parts) != 3:
            raise ValueError("时间格式错误")
        hours = int(time_parts[0])
        minutes = int(time_parts[1])
        seconds = int(time_parts[2])
        return hours * 3600 + minutes * 60 + seconds
    except:
        raise ValueError(f"无效的时间格式: {time_str}")

def parse_k_expression(k_str, lambda_val):
    """解析k表达式，容错：
    - 支持 "^" 作为幂运算（转换为 **）
    - 当表达式中存在除以 λ 且 λ=0 时，使用极小正数代替避免报错
    - 对于非法表达式，返回默认值 0.01
    """
    try:
        if k_str is None:
            return 0.01

        # 预处理：去空格、支持 ^ 幂
        expr = str(k_str).strip().replace(' ', '')
        expr = expr.replace('^', '**')

        # 纯数字直接返回
        if expr.replace('.', '').replace('-', '').isdigit():
            return float(expr)

        # 避免除零：当 λ=0 时，用极小正数替代以避免 1/0 报错
        lam_safe = lambda_val if lambda_val != 0 else 1e-9

        # 用占位符替换，确保所有写法统一
        expr = expr.replace('lambda', str(lam_safe))
        expr = expr.replace('λ', str(lam_safe))

        # 允许的字符集合（在替换后再校验）
        allowed_chars = set('0123456789+-*/.()eE')
        if not all(c in allowed_chars for c in expr):
            # 若仍包含其它字符，直接回退默认值
            return 0.01

        # 安全求值：禁用内建，仅允许基本运算
        result = eval(expr, {"__builtins__": None}, {})
        return float(result)
    except Exception:
        # 不报错给用户，直接使用默认值
        return 0.01  # 默认值

def read_csv_with_encoding(file_obj_or_path, user_encoding=None):
    """优先使用用户选择的编码；否则按常见中文编码优先尝试"""
    # 如果用户手动指定了编码，先用它
    if user_encoding and user_encoding != "自动检测(建议)":
        return pd.read_csv(
            file_obj_or_path,
            encoding=user_encoding,
            engine='python',
            on_bad_lines='skip'
        )

    # 自动检测顺序：GBK/GB2312 优先，其次 UTF-8
    encodings = ['gbk', 'gb2312', 'utf-8-sig', 'utf-8', 'latin1']
    last_err = None
    for enc in encodings:
        try:
            df = pd.read_csv(
                file_obj_or_path,
                encoding=enc,
                engine='python',
                on_bad_lines='skip'
            )
            if df.shape[1] >= 5:
                return df
        except Exception as e:
            last_err = e
            continue
    raise ValueError(f"无法读取CSV，请确认文件编码（建议GBK/GB2312）。最后错误：{last_err}")

def filter_data_by_time(df, start_time, end_time):
    """根据时间范围过滤数据"""
    try:
        start_seconds = parse_time_to_seconds(start_time)
        end_seconds = parse_time_to_seconds(end_time)
        
        # 提取UTC时间列的时间部分
        df['time_only'] = pd.to_datetime(df.iloc[:, 1]).dt.time
        df['time_seconds'] = df['time_only'].apply(lambda x: x.hour * 3600 + x.minute * 60 + x.second)
        
        # 过滤数据
        filtered_df = df[(df['time_seconds'] >= start_seconds) & (df['time_seconds'] <= end_seconds)].copy()
        
        if len(filtered_df) == 0:
            st.error("在指定时间范围内没有找到数据")
            return None
        
        return filtered_df.reset_index(drop=True)
    except Exception as e:
        st.error(f"时间过滤错误: {str(e)}")
        return None

def calculate_inverter_power(df, initial_inv_power, k_expression):
    """按新逻辑计算：
    - 每个时刻 i：用当前负载 load_i 与当前逆变器发电量 inv_curr 计算 grid、λ、调节量、激进调节量、比例、百分比（均截断一位小数）
    - 记录该时刻结果（不变列+变化列，中文标题）
    - 用调节量更新 inv_curr += 调节量，进入下一时刻
    - 每个时刻开始按当前负载做约束：inv_curr = min(max(0, inv_curr), load_i)
    """
    results = []

    # 负载序列（第5列）
    load_series = df.iloc[:, 4].astype(float).values

    # 初值：按第一个负载做约束
    inv_curr = min(max(0.0, float(initial_inv_power)), float(load_series[0]))

    for i in range(len(load_series)):
        load_i = float(load_series[i])

        # 约束：当前时刻开始时先截断到当前负载范围
        inv_curr = min(max(0.0, inv_curr), load_i)
        inv_curr = truncate_decimal(inv_curr)

        # 购电、λ
        grid_i = truncate_decimal(load_i - inv_curr)
        lam_i = truncate_decimal(0.0 if load_i <= 0 else grid_i / load_i)

        # k(λ) 解析
        k_val = parse_k_expression(k_expression, lam_i)

        # 逆变器发电调节量（Δt=1s）
        inc_i = k_val * (lam_i ** 2) * load_i * 1.0
        inc_i = truncate_decimal(inc_i)

        # 激进调节量
        aggressive_i = truncate_decimal(load_i - inv_curr)

        # 比率
        if aggressive_i == 0:
            ratio_i = 999.9 if inc_i > 0 else 0.0
        else:
            ratio_i = truncate_decimal(inc_i / aggressive_i)

        # 百分比
        inv_percent_i = truncate_decimal(0.0 if load_i <= 0 else (inv_curr / load_i) * 100.0)

        # 记录（中文标题 + 不变列）
        results.append({
            '时间戳': df.iloc[i, 0],
            'UTC时间': df.iloc[i, 1],
            '设备地址': df.iloc[i, 2],
            '设备类型': df.iloc[i, 3],
            '负载数据': truncate_decimal(load_i),
            '逆变器发电量': inv_curr,
            '逆变器发电量占负载的百分比': inv_percent_i,
            '逆变器发电调节量': inc_i,
            '激进调节量': aggressive_i,
            '逆变器发电调节量/激进调节量': ratio_i,
        })

        # 用本时刻的“调节量”更新下一时刻的逆变器发电量
        inv_curr = inv_curr + inc_i

        # 新增：若下一时刻负载更小，导致当前更新后的逆变器发电量过大，则提前截断为下一时刻负载
        if i + 1 < len(load_series):
            next_load = float(load_series[i + 1])
            if inv_curr > next_load:
                inv_curr = truncate_decimal(next_load)

    return pd.DataFrame(results)

def main():
    st.markdown('<h1 class="main-header">🤖 负载数据分析系统</h1>', unsafe_allow_html=True)
    
    # 侧边栏 - 参数设置
    st.sidebar.markdown("## ⚙️ 参数设置")

    # 文件编码选择（新增）
    encoding_choice = st.sidebar.selectbox(
        "文件编码",
        ["自动检测(建议)", "gbk", "gb2312", "utf-8-sig", "utf-8", "latin1"],
        index=0
    )

    # 文件上传
    uploaded_file = st.sidebar.file_uploader(
        "上传CSV文件",
        type=['csv'],
        help="请上传包含负载数据的CSV文件"
    )

    if uploaded_file is not None:
        try:
            # uploaded_file 为文件对象，可直接传入
            df = read_csv_with_encoding(uploaded_file, user_encoding=encoding_choice)
            st.sidebar.success(f"成功读取文件，共 {len(df)} 行数据")
            st.sidebar.markdown("**文件列名：**")
            for i, col in enumerate(df.columns):
                st.sidebar.text(f"列{i+1}: {col}")
        except Exception as e:
            st.error(f"读取文件失败: {str(e)}")
            return
    else:
        # 使用默认文件（含中文路径/文件名）
        try:
            df = read_csv_with_encoding("500KW不同模式的测试数据（负载）.csv", user_encoding=encoding_choice)
            st.sidebar.success(f"使用默认文件，共 {len(df)} 行数据")
        except Exception as e:
            st.error(f"无法读取默认文件: {str(e)}")
            st.info("请通过侧边栏上传CSV文件或切换编码为 GBK/GB2312 再试")
            return
    
    # 时间范围选择
    st.sidebar.markdown("### 🕐 时间范围设置")
    
    col1, col2 = st.sidebar.columns(2)
    with col1:
        start_time = st.text_input(
            "开始时间 (HH:MM:SS)",
            value="08:00:00",
            help="格式: HH:MM:SS"
        )
    with col2:
        end_time = st.text_input(
            "结束时间 (HH:MM:SS)",
            value="08:10:00",
            help="格式: HH:MM:SS"
        )
    
    # 初始逆变器发电量
    st.sidebar.markdown("### ⚡ 初始设置")
    initial_inv_power = st.sidebar.number_input(
        "初始逆变器发电量 (kW)",
        min_value=0.0,
        value=10.0,
        step=0.1,
        help="初始时刻的逆变器发电量"
    )
    
    # k表达式
    st.sidebar.markdown("### 🔢 k表达式设置")
    k_expression = st.sidebar.text_input(
        "k表达式",
        value="0.01",
        help="支持常数或关于λ的表达式，如: 0.01, 0.01*λ, 0.01*λ^2"
    )
    
    # 计算按钮
    if st.sidebar.button("🚀 开始计算", type="primary"):
        try:
            # 过滤数据
            filtered_df = filter_data_by_time(df, start_time, end_time)
            if filtered_df is None:
                return
            
            # 计算逆变器发电量
            with st.spinner("正在计算..."):
                results_df = calculate_inverter_power(filtered_df, initial_inv_power, k_expression)
            
            st.success(f"计算完成！共处理 {len(results_df)} 个数据点")
            
            # 显示结果
            st.markdown('<h2 class="section-header">🧮 计算结果</h2>', unsafe_allow_html=True)
            
            # 关键指标
            col1, col2, col3, col4 = st.columns(4)
            with col1:
                st.metric("数据点数", len(results_df))
            with col2:
                avg_percent = results_df['逆变器发电量占负载的百分比'].mean()
                st.metric("平均发电百分比", f"{avg_percent:.1f}%")
            with col3:
                max_percent = results_df['逆变器发电量占负载的百分比'].max()
                st.metric("最大发电百分比", f"{max_percent:.1f}%")
            with col4:
                total_increase = results_df['逆变器发电调节量'].sum()
                st.metric("总发电增加量", f"{total_increase:.1f} kW")
            
            # 可视化
            st.markdown('<h2 class="section-header">📊 可视化图表</h2>', unsafe_allow_html=True)
            
            # 创建时间轴（转换为秒，确保为整数）
            time_seconds = []
            for i, time_str in enumerate(results_df['UTC时间']):
                time_obj = pd.to_datetime(time_str).time()
                seconds = time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second
                time_seconds.append(int(seconds))

            # 绘图前统一做一位小数“截断”，避免浮点微差导致视觉高度差异
            def trunc_series(s):
                return pd.to_numeric(s, errors='coerce').apply(lambda v: truncate_decimal(float(v)))

            y_percent = trunc_series(results_df['逆变器发电量占负载的百分比'])
            y_load = trunc_series(results_df['负载数据'])
            y_inv = trunc_series(results_df['逆变器发电量'])
            y_inc = trunc_series(results_df['逆变器发电调节量'])
            
            # 逆变器发电量百分比散点图
            fig = go.Figure()
            
            fig.add_trace(go.Scatter(
                x=time_seconds,
                y=y_percent,
                mode='markers+lines',
                name='逆变器发电百分比',
                marker=dict(
                    size=6,
                    color=y_percent,
                    colorscale='Viridis',
                    showscale=True,
                    colorbar=dict(title="百分比 (%)")
                ),
                line=dict(width=2)
            ))
            
            fig.update_layout(
                title='逆变器发电量占负载百分比随时间变化',
                xaxis_title='时间 (秒)',
                yaxis_title='发电百分比 (%)',
                hovermode='x unified',
                width=800,
                height=500
            )
            
            st.plotly_chart(fig, use_container_width=True)
            
            # 多指标对比图：负载数据、逆变器发电量、发电量增加量
            fig2 = go.Figure()

            # 1) 先画“发电量增加量”——最不显著，放最底层，马卡龙浅色
            fig2.add_trace(go.Scatter(
                x=time_seconds,
                y=y_inc,
                mode='lines+markers',
                name='发电量增加量 (kW)',
                yaxis='y2',
                line=dict(color='#FFDAC1', width=2),  # 马卡龙浅桃色
                marker=dict(color='#FFDAC1', size=5),
                opacity=0.7
            ))

            # 2) 再画“逆变器发电量”——次显著，马卡龙浅蓝绿
            fig2.add_trace(go.Scatter(
                x=time_seconds,
                y=y_inv,
                mode='lines+markers',
                name='逆变器发电量 (kW)',
                yaxis='y',
                line=dict(color='#A0CED9', width=2.5),  # 马卡龙浅青蓝
                marker=dict(color='#A0CED9', size=6),
                opacity=0.85
            ))

            # 3) 最后画“负载数据”——最显著，置顶，马卡龙浅粉
            fig2.add_trace(go.Scatter(
                x=time_seconds,
                y=y_load,
                mode='lines+markers',
                name='负载数据 (kW)',
                yaxis='y',
                line=dict(color='#FF9AA2', width=3.5),  # 马卡龙浅粉
                marker=dict(color='#FF9AA2', size=6),
                opacity=1.0
            ))

            fig2.update_layout(
                title='负载、逆变器发电量与发电量增加量对比',
                xaxis_title='时间 (秒)',
                yaxis=dict(title='功率 (kW)', side='left'),
                yaxis2=dict(title='增加量 (kW)', side='right', overlaying='y'),
                hovermode='x unified',
                width=900,
                height=520,
                legend=dict(orientation='h', yanchor='bottom', y=1.02, xanchor='right', x=1)
            )
            
            st.plotly_chart(fig2, use_container_width=True)
            
            # 数据表格
            st.markdown('<h2 class="section-header">📋 详细数据表</h2>', unsafe_allow_html=True)
            
            # 选择显示的列
            display_columns = [
                '时间戳', 'UTC时间', '设备地址', '设备类型', '负载数据', '逆变器发电量',
                '逆变器发电量占负载的百分比', '逆变器发电调节量', '激进调节量', '逆变器发电调节量/激进调节量'
            ]
            
            st.dataframe(results_df[display_columns], use_container_width=True, height=400)
            
            # 下载CSV
            csv_data = results_df.to_csv(index=False, encoding='utf-8-sig')
            st.download_button(
                label="📥 下载结果CSV文件",
                data=csv_data,
                file_name=f"计算结果_{start_time.replace(':', '')}_{end_time.replace(':', '')}.csv",
                mime="text/csv"
            )
            
        except Exception as e:
            st.error(f"计算过程中出现错误: {str(e)}")
            st.exception(e)

if __name__ == "__main__":
    main()