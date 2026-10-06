"""测试共享构造。只依赖标准库 + 契约层（gis.spec）。"""

from gis.spec import ArtifactSpec, RenderSpec, bbox_to_geojson

# 北京一带 AOI（经纬度外接框）
BEIJING_AOI = bbox_to_geojson(116.30, 39.90, 116.50, 40.10)


def make_spec(**over) -> ArtifactSpec:
    """字段齐全的基准 spec，测试里按需覆盖单个字段。"""
    kw = dict(
        id="s2_beijing_test",
        asset="COPERNICUS/S2_SR_HARMONIZED",
        band_expr=None,
        crs="EPSG:32650",
        scale=10.0,
        aoi=BEIJING_AOI,
        dtype="float32",
        nodata=None,
        bands=("B4", "B3", "B2"),
        time_range=("2024-01-01", "2024-12-31"),
        reducer="median",
        render=RenderSpec(bands=("B4", "B3", "B2")),
        note="unit-test",
        tags=("test",),
    )
    kw.update(over)
    return ArtifactSpec(**kw)
