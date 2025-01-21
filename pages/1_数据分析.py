import streamlit as st
import pandas as pd
import numpy as np
import geopandas as gpd
from shapely.geometry import Point

# 定义函数
def calculate_nearest_reach(df, target_point):
    """
    计算所有点到目标点的距离，返回最短距离对应的 reach_id
    """
    df['distance'] = np.sqrt(
        (df['x'] - target_point[0]) ** 2 + 
        (df['y'] - target_point[1]) ** 2
    )
    min_distance_row = df.loc[df['distance'].idxmin()]
    return min_distance_row['reach_id'], min_distance_row['distance']

def find_nearest_points_geopandas(gdf1, gdf2):
    """
    使用 GeoPandas 计算最近点，并返回最近点对的详细信息
    """
    # 确保 CRS 一致
    if gdf1.crs != gdf2.crs:
        gdf2 = gdf2.to_crs(gdf1.crs)
    
    # 转换为投影坐标系以获得更准确的距离计算
    if gdf1.crs.is_geographic:
        gdf1 = gdf1.to_crs('EPSG:3857')
        gdf2 = gdf2.to_crs('EPSG:3857')
    
    results = []
    for idx1, row1 in gdf1.iterrows():
        distances = [row1.geometry.distance(row2.geometry) for _, row2 in gdf2.iterrows()]
        min_distance = min(distances)
        min_idx = distances.index(min_distance)
        results.append({
            'df1_index': idx1,
            'df2_index': gdf2.index[min_idx],
            'distance_m': min_distance
        })
    
    result_df = pd.DataFrame(results)
    nearest_pair = result_df[result_df['distance_m'] == result_df['distance_m'].min()].copy()
    return nearest_pair

def process_trajectory_groups(csv_path, gdf_point_sword):
    """
    读取 CSV 文件，按 subgroup 分组处理轨迹，找到每组的最近点
    """
    df = pd.read_csv(csv_path)
    df = df.iloc[:-2, 0:-1]  # 去除最后两行和最后一列

    subgroups = df['subgroup'].unique()
    results = {}

    for subgroup in subgroups:
        group_data = df[df['subgroup'] == subgroup].reset_index(drop=True)
        gdf = gpd.GeoDataFrame(
            group_data,
            geometry=[Point(xy) for xy in zip(group_data['lon'], group_data['lat'])],
            crs="EPSG:4326"
        )
        nearest_pair = find_nearest_points_geopandas(gdf_point_sword, gdf)
        height = group_data['height'][nearest_pair['df2_index']].iloc[0]
        
        df1_idx = nearest_pair['df1_index'].iloc[0]
        df1_point = gdf_point_sword.iloc[df1_idx]
        
        df2_idx = nearest_pair['df2_index'].iloc[0]
        df2_point = gdf.iloc[df2_idx]
        
        results[subgroup] = {
            'nearest_pair': nearest_pair,
            'height': height,
            'point_details': {
                'sword': {
                    'lon': df1_point.geometry.x,
                    'lat': df1_point.geometry.y
                },
                'icesat': {
                    'lon': df2_point.geometry.x,
                    'lat': df2_point.geometry.y,
                }
            }
        }
    return results

def results_to_df(results):
    """
    将字典结果转换为 DataFrame
    """
    rows = []
    for subgroup, data in results.items():
        point_details = data['point_details']
        row = {
            'subgroup': subgroup,
            'sword_lon': point_details['sword']['lon'],
            'sword_lat': point_details['sword']['lat'],
            'icesat_lon': point_details['icesat']['lon'],
            'icesat_lat': point_details['icesat']['lat'],
            'icesat_height': data['height']
        }
        rows.append(row)
    return pd.DataFrame(rows)

# Streamlit App
st.title("数据分析")

# 上传数据
st.header("上传数据")
sword_file = st.file_uploader("上传 SWORD 数据 (CSV)", type=["csv"])
icesat_file = st.file_uploader("上传 ICESat-2 数据 (CSV)", type=["csv"])

if sword_file and icesat_file:
    try:
        # 读取数据
        sword_df = pd.read_csv(sword_file)
        icesat_df = pd.read_csv(icesat_file)

        # SWORD 数据处理
        gdf_point_sword = gpd.GeoDataFrame(
            geometry=[Point(x, y) for x, y in zip(sword_df['x'], sword_df['y'])],
            crs='EPSG:4326'
        )

        # 开始计算
        st.sidebar.write("开始计算 ICESat-2 数据与 SWORD 数据的最近点...")
        results = process_trajectory_groups(icesat_file, gdf_point_sword)

        # 转换结果为 DataFrame 并保存
        result_df = results_to_df(results)
        st.write("计算完成，结果如下：")
        st.dataframe(result_df)

        # 提供下载按钮
        csv = result_df.to_csv(index=False).encode('utf-8')
        st.download_button(
            label="下载结果 (CSV)",
            data=csv,
            file_name="filtered_result.csv",
            mime="text/csv"
        )

    except Exception as e:
        st.error(f"发生错误: {e}")