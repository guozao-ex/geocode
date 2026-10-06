"""测试共享构造。只依赖标准库 + 契约层（gis.spec）。"""

from gis.spec import ArtifactSpec, RenderSpec, bbox_to_geojson

# 北京一带 AOI（经纬度外接框）
BEIJING_AOI = bbox_to_geojson(116.30, 39.90, 116.50, 40.10)

# P0 验收样本的 AOI（smoke_emit.py 的小框）——金指纹锚定用，不可改动
P0_AOI = {
    "type": "Polygon",
    "coordinates": [[[116.30, 39.95], [116.40, 39.95],
                     [116.40, 40.02], [116.30, 40.02], [116.30, 39.95]]],
}

# P0 样本 spec（tests/smoke_emit.py 原样复刻）。
# 指纹金值 c9243efd40318c85 锚定 data/derived/ 的既有缓存产物
# （s2_beijing_test.c9243efd.tif / .nc）——改任何一个键都会废掉缓存对齐。
P0_SPEC_DICT = {
    "id": "s2_beijing_test",
    "asset": "COPERNICUS/S2_SR_HARMONIZED",
    "bands": ["B4", "B3", "B2"],
    "scale": 10,
    "crs": "EPSG:32650",
    "dtype": "uint16",
    "time_range": ["2024-06-01", "2024-08-31"],
    "reducer": "median",
    "aoi": P0_AOI,
}


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


def make_p0_spec(**over) -> ArtifactSpec:
    """P0 样本 spec（金指纹 c9243efd40318c85）。时序字段缺省。"""
    kw = dict(P0_SPEC_DICT)
    kw.update(over)
    return ArtifactSpec.from_dict(kw)
