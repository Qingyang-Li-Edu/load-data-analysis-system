import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import math
from datetime import datetime

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei']
plt.rcParams['axes.unicode_minus'] = False

def truncate_decimal(value, decimals=1):
    """截断小数到指定位数（不四舍五入）"""
    multiplier = 10 ** decimals
    return math.floor(value * multiplier) / multiplier

def parse_k_expression(k_str, lambda_val):
    """解析k表达式"""
    try:
        k_str = k_str.replace(' ', '').replace('λ', str(lambda_val))
        return float(eval(k_str))
    except:
        return 0.01

def analyze_load_data(csv_file, start_time, end_time, initial_inv_power, k_expression):
    """分析负载数据的主函数"""
    
    # 读取CSV文件
    try:
        df = pd.read_csv(csv_file, encoding='utf-8')
    except:
        try:
            df = pd.read_csv(csv_file, encoding='gbk')
        except:
            df = pd.read_csv(csv_file, encoding='latin1')
    
    print(f"成功读取文件，共 {len(df)} 行数据")
    
    # 时间过滤
    df['time_only'] = pd.to_datetime(df.iloc[:, 1]).dt.time
    start_seconds = sum(x * int(t) for x, t in zip([3600, 60, 1], start_time.split(':')))
    end_seconds = sum(x * int(t) for x, t in zip([3600, 60, 1], end_time.split(':')))
    
    df['time_seconds'] = df['time_only'].apply(lambda x: x.hour * 3600 + x.minute * 60 + x.second)
    filtered_df = df[(df['time_seconds'] >= start_seconds) & (df['time_seconds'] <= end_seconds)].copy()
    
    print(f"时间过滤后，共 {len(filtered_df)} 行数据")
    
    # 计算逆变器发电量
    results = []
    load_data = filtered_df.iloc[:, 4].values
    
    # 第一个时间戳
    load0 = load_data[0]
    inv_power0 = min(max(0, initial_inv_power), load0)
    grid_power0 = load0 - inv_power0
    lambda0 = truncate_decimal(grid_power0 / load0 if load0 > 0 else 0)
    
    results.append({
        'time': filtered_df.iloc[0, 1],
        'load': load0,
        'inv_power': truncate_decimal(inv_power0),
        'inv_percent': truncate_decimal((inv_power0 / load0) * 100 if load0 > 0 else 0),
        'lambda': lambda0
    })
    
    # 后续时间戳
    prev_lambda = lambda0
    prev_inv_power = inv_power0
    
    for i in range(1, len(load_data)):
        load_i = load_data[i]
        k = parse_k_expression(k_expression, prev_lambda)
        
        inc_inv_i = truncate_decimal(k * (prev_lambda ** 2) * load_i)
        inv_power_i = truncate_decimal(min(max(0, prev_inv_power + inc_inv_i), load_i))
        
        grid_power_i = truncate_decimal(load_i - inv_power_i)
        lambda_i = truncate_decimal(grid_power_i / load_i if load_i > 0 else 0)
        
        inv_percent_i = truncate_decimal((inv_power_i / load_i) * 100 if load_i > 0 else 0)
        
        results.append({
            'time': filtered_df.iloc[i, 1],
            'load': load_i,
            'inv_power': inv_power_i,
            'inv_percent': inv_percent_i,
            'lambda': lambda_i
        })
        
        prev_lambda = lambda_i
        prev_inv_power = inv_power_i
    
    # 创建结果DataFrame
    results_df = pd.DataFrame(results)
    
    # 可视化
    plt.figure(figsize=(12, 8))
    
    # 子图1：逆变器发电百分比
    plt.subplot(2, 1, 1)
    time_indices = range(len(results_df))
    plt.scatter(time_indices, results_df['inv_percent'], alpha=0.7, s=30)
    plt.plot(time_indices, results_df['inv_percent'], alpha=0.5)
    plt.title('逆变器发电量占负载百分比')
    plt.xlabel('时间索引')
    plt.ylabel('百分比 (%)')
    plt.grid(True, alpha=0.3)
    
    # 子图2：负载和逆变器发电量对比
    plt.subplot(2, 1, 2)
    plt.plot(time_indices, results_df['load'], label='负载 (kW)', linewidth=2)
    plt.plot(time_indices, results_df['inv_power'], label='逆变器发电量 (kW)', linewidth=2)
    plt.title('负载与逆变器发电量对比')
    plt.xlabel('时间索引')
    plt.ylabel('功率 (kW)')
    plt.legend()
    plt.grid(True, alpha=0.3)
    
    plt.tight_layout()
    plt.savefig('analysis_results.png', dpi=300, bbox_inches='tight')
    plt.show()
    
    # 保存结果
    results_df.to_csv('analysis_results.csv', index=False, encoding='utf-8-sig')
    print("结果已保存到 analysis_results.csv 和 analysis_results.png")
    
    return results_df

# 使用示例
if __name__ == "__main__":
    # 参数设置
    csv_file = "500KW不同模式的测试数据（负载）.csv"
    start_time = "08:00:00"
    end_time = "08:10:00"
    initial_inv_power = 10.0
    k_expression = "0.01"
    
    # 运行分析
    results = analyze_load_data(csv_file, start_time, end_time, initial_inv_power, k_expression)
    print("\n分析完成！")
    print(f"平均发电百分比: {results['inv_percent'].mean():.1f}%")
    print(f"最大发电百分比: {results['inv_percent'].max():.1f}%")