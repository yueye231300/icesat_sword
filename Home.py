import streamlit as st
import ee
import geopandas as gpd
from shapely.geometry import LineString, Point
import pandas as pd
import tempfile
import zipfile
import os
from shapely.ops import transform
import pyproj
import folium
from folium.plugins import MarkerCluster
import streamlit.components.v1 as components  # 用于嵌入 HTML

# 初始化 Google Earth Engine
def ee_initialize():
    try:
        credentials = ee.ServiceAccountCredentials(
            email=st.secrets["ee_service_account"],
            key_data=st.secrets["ee_token"]
        )
        # 初始化 Earth Engine
        ee.Initialize(credentials)
        return True
    except Exception as e:
        st.error(f"Earth Engine 认证失败: {str(e)}")
        return False

# 初始化 Earth Engine
is_authorized = ee_initialize()

if is_authorized:
    st.success("Earth Engine 认证成功!")
    # 这里添加你的主程序代码
else:
    st.error("请确保正确设置 Streamlit secrets")

# Streamlit 界面
st.title("基于 SWORD 数据集的河流提取与可视化工具")
st.markdown("输入坐标点，生成指定范围内的河流节点数据、河流中心线和河流形状，并导出为 CSV 和 Shapefile 文件。")

# 用户输入坐标点
latitude = st.number_input("输入纬度 (Latitude)", value=30.0, format="%.6f")  # 默认长江流域附近
longitude = st.number_input("输入经度 (Longitude)", value=114.0, format="%.6f")  # 默认长江流域附近
buffer_distance = st.number_input("缓冲区半径 (米)", value=2000, step=100)  # 默认2公里

# 地图容器
st.markdown("### 地图预览")
import streamlit as st
import ee
import folium
from folium.plugins import MarkerCluster
import pandas as pd
import geopandas as gpd
import pyproj
from shapely.geometry import Point, LineString
from shapely.ops import transform
import streamlit.components.v1 as components
import tempfile
import os
import zipfile

# 初始化 session_state
if 'nodes_df' not in st.session_state:
    st.session_state.nodes_df = None
if 'gdf_river' not in st.session_state:
    st.session_state.gdf_river = None
if 'node_data' not in st.session_state:
    st.session_state.node_data = None
if 'node_points' not in st.session_state:
    st.session_state.node_points = None
if 'center_line' not in st.session_state:
    st.session_state.center_line = None
if 'width_mean' not in st.session_state:
    st.session_state.width_mean = None

# 输入部分（假设已有这些变量）
longitude = st.number_input("经度", value=116.3)
latitude = st.number_input("纬度", value=39.9)
buffer_distance = st.number_input("缓冲区距离（米）", value=1000)

# 当点击按钮时触发
if st.button("生成河流数据并可视化"):
    try:
        # 创建缓冲区
        point = ee.Geometry.Point([longitude, latitude])
        buffer = point.buffer(buffer_distance)

        # 加载 SWORD 数据集
        nodes_merged = ee.FeatureCollection("projects/sat-io/open-datasets/SWORD/nodes_merged")

        # 在缓冲区内过滤节点
        filtered_nodes = nodes_merged.filterBounds(buffer)

        # 检查节点是否为空
        node_count = filtered_nodes.size().getInfo()
        st.write(f"找到的节点数量: {node_count}")

        if node_count == 0:
            st.error("指定范围内未找到河流节点数据，请调整坐标或缓冲区范围。")
            st.stop()

        # 获取节点数据
        node_features = filtered_nodes.getInfo()['features']
        node_points = []
        node_data = []

        for feature in node_features:
            coords = feature['geometry']['coordinates']
            properties = feature['properties']

            # 将节点地理信息存储为 Point
            node_points.append(Point(coords))

            # 保存所需属性（经纬度、河流水面高程和河宽）
            node_data.append({
                "longitude": coords[0],  # 经度
                "latitude": coords[1],  # 纬度
                "wse": properties.get("wse"),  # 水面高程
                "width": properties.get("width")  # 河宽
            })

        # 存储数据到 session_state
        st.session_state.node_data = node_data
        st.session_state.node_points = node_points
        
        # 计算平均河宽
        node_data_width = [node['width'] for node in node_data]
        st.session_state.width_mean = sum(node_data_width) / len(node_data_width)

        # 创建节点的 DataFrame
        nodes_df = pd.DataFrame(node_data)
        st.session_state.nodes_df = nodes_df  # 存储到 session_state

        # 将节点连成线
        if len(node_points) > 1:
            center_line = LineString(node_points)
            st.session_state.center_line = center_line
        else:
            st.error("节点数量不足以连成线。")
            st.stop()

        # 中心线向两侧扩展为河流多边形
        # 定义投影函数：将 WGS84 转换为一个局部投影（米）
        project = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:3857", always_xy=True).transform
        reverse_project = pyproj.Transformer.from_crs("EPSG:3857", "EPSG:4326", always_xy=True).transform

        # 将中心线投影到局部投影坐标系（以米为单位）
        expanded_center_line = transform(project, center_line)

        extension_distance = st.number_input("河流宽度扩展距离 (米)", value=st.session_state.width_mean, step=10.0)
        # 扩展中心线两侧的距离（河流宽度的一半）
        river_polygon = expanded_center_line.buffer(extension_distance)

        # 将结果投影回 WGS84 坐标系
        river_polygon_wgs84 = transform(reverse_project, river_polygon)

        # 创建河流多边形的 GeoDataFrame
        gdf_river = gpd.GeoDataFrame(
            [{'geometry': river_polygon_wgs84, 'name': 'River Polygon'}],
            crs="EPSG:4326"
        )
        st.session_state.gdf_river = gdf_river  # 存储到 session_state

        # 可视化数据（使用 Folium）
        folium_map = folium.Map(location=[latitude, longitude], zoom_start=12)

        # 添加输入点标记
        folium.Marker(
            location=[latitude, longitude],
            popup="输入点",
            icon=folium.Icon(color="red", icon="info-sign")
        ).add_to(folium_map)

        # 添加缓冲区
        buffer_geojson = buffer.getInfo()
        folium.GeoJson(
            buffer_geojson,
            name="缓冲区",
            style_function=lambda x: {"color": "green", "weight": 2, "fillOpacity": 0.1}
        ).add_to(folium_map)

        # 添加节点（使用 MarkerCluster 聚合显示）
        marker_cluster = MarkerCluster(name="节点 (Nodes)").add_to(folium_map)
        for node in node_data:
            folium.Marker(
                location=[node["latitude"], node["longitude"]],
                popup=f"水面高程: {node['wse']} 米<br>河宽: {node['width']} 米",
                icon=folium.Icon(color="blue", icon="info-sign")
            ).add_to(marker_cluster)

        # 添加河流中心线
        folium.PolyLine(
            locations=[[p.y, p.x] for p in node_points],
            color="blue",
            weight=3,
            popup="河流中心线"
        ).add_to(folium_map)

        # 添加河流多边形
        folium.GeoJson(
            data=gdf_river.geometry.to_json(),
            name="河流形状",
            style_function=lambda x: {"color": "blue", "weight": 1, "fillOpacity": 0.3}
        ).add_to(folium_map)

        # 添加图层控制
        folium.LayerControl().add_to(folium_map)

        # 渲染地图到 Streamlit（嵌入 HTML）
        map_html = folium_map._repr_html_()
        components.html(map_html, height=600)

        # 显示下载部分
        st.markdown("### 下载数据")
        
        col1, col2 = st.columns(2)
        
        with col1:
            # CSV 下载按钮
            csv_data = st.session_state.nodes_df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="下载节点数据 (CSV)",
                data=csv_data,
                file_name="river_nodes.csv",
                mime="text/csv"
            )
        
        with col2:
            # Shapefile 下载按钮
            def create_shapefile_zip():
                with tempfile.TemporaryDirectory() as tmpdir:
                    # 保存 Shapefile
                    shp_path = os.path.join(tmpdir, "river_polygon.shp")
                    st.session_state.gdf_river.to_file(shp_path)
                    
                    # 创建压缩文件
                    zip_path = os.path.join(tmpdir, "river_shapefile.zip")
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        for file in os.listdir(tmpdir):
                            if file.startswith("river_polygon"):
                                file_path = os.path.join(tmpdir, file)
                                zipf.write(file_path, file)
                    
                    # 读取压缩文件
                    with open(zip_path, 'rb') as f:
                        return f.read()
            
            shapefile_zip = create_shapefile_zip()
            st.download_button(
                label="下载河流形状 (Shapefile)",
                data=shapefile_zip,
                file_name="river_shapefile.zip",
                mime="application/zip"
            )

        # 添加合并下载选项
        st.markdown("---")
        
        if st.button("生成完整数据包"):
            with st.spinner("正在打包所有数据..."):
                with tempfile.TemporaryDirectory() as tmpdir:
                    # 保存 CSV
                    csv_path = os.path.join(tmpdir, "nodes.csv")
                    st.session_state.nodes_df.to_csv(csv_path, index=False)
                    
                    # 保存 Shapefile
                    shp_path = os.path.join(tmpdir, "river_polygon.shp")
                    st.session_state.gdf_river.to_file(shp_path)
                    
                    # 创建完整数据包
                    zip_path = os.path.join(tmpdir, "complete_river_data.zip")
                    with zipfile.ZipFile(zip_path, 'w') as zipf:
                        # 添加 CSV
                        zipf.write(csv_path, "nodes.csv")
                        # 添加 Shapefile 相关文件
                        for file in os.listdir(tmpdir):
                            if file.startswith("river_polygon"):
                                file_path = os.path.join(tmpdir, file)
                                zipf.write(file_path, os.path.join("shapefile", file))
                    
                    # 读取完整数据包
                    with open(zip_path, 'rb') as f:
                        complete_data = f.read()
                    
                    # 提供下载
                    st.download_button(
                        label="下载完整数据包 (CSV + Shapefile)",
                        data=complete_data,
                        file_name="complete_river_data.zip",
                        mime="application/zip"
                    )

            st.success("数据包生成成功！")

    except Exception as e:
        st.error(f"发生错误: {str(e)}")
        st.stop()