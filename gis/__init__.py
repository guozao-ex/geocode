"""
gis —— GeoCode 的 Python 侧能力库。

分层：
    geoenv      环境事实（路径 / 解释器 / GDAL / GEE 认证 / 代理）
    osm         Overpass 矢量源（C8：拉取装配 → GPKG 交付）
    aoi         行政区 AOI 供给（C8：合规边界 adcode / 非中国 OSM 边界）
    spec        ★ ArtifactSpec —— 三出口共用的唯一产物契约
    crs_rules   CRS 纪律
    preflight   环境探测 + 失败分类
    source      GEE 计算图构建 + 资产发现
    emit        三出口统一入口
    jobs        任务模型 + 执行器
    daemon      HTTP 服务（/mcp + /rpc）
    tui         终端界面
"""

from . import aoi, crs_rules, emit, geoenv, jobs, osm, preflight, source, spec  # noqa: F401

__all__ = ["aoi", "crs_rules", "emit", "geoenv", "jobs", "osm", "preflight", "source", "spec"]
__version__ = "0.1.0"
