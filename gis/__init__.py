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

from . import aoi, crs_rules, emit, geoenv, jobs, osm, source, spec  # noqa: F401

__all__ = ["aoi", "crs_rules", "emit", "geoenv", "jobs", "osm", "preflight", "source", "spec"]


def __getattr__(name):
    """惰性导入 preflight。

    `python -m gis.preflight` 是本文档化的入门命令；若 preflight 在包 __init__ 里被预先
    导入，runpy 启动时会打 "found in sys.modules after import of package 'gis'" 的
    RuntimeWarning —— 看着像出错，其实只是噪声。惰性化后属性访问语义不变。
    """
    if name == "preflight":
        import importlib

        # 必须用 importlib 而不是 `from . import preflight`：后者会再对包做属性查找，
        # 又回到本函数，直接 RecursionError。
        return importlib.import_module(".preflight", __name__)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
__version__ = "0.1.0"
