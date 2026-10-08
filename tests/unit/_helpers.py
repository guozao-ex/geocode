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
# 指纹金值按 PROCESSING_VERSION 时代取值（**不要在这里写死某个时代的常量**，
# 用下方 expected_p0_fingerprint() / GOLDEN_FINGERPRINTS 查表）：
#   PV2 时代 = c9243efd40318c85，锚定 data/derived/ 的既有缓存产物
#   （s2_beijing_test.c9243efd.tif / .nc）——改任何一个键都会废掉缓存对齐；
#   PV3 现行 = b91c09c9c6451c16（C4 预设表补 LC08/LC09 offset 后 bump 2→3）。
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

# P0 样本 spec 的指纹金值，**按 PROCESSING_VERSION 时代登记**（单一事实源：
# 单测、smoke 脚本与文档注释都从这里取值，不得各自硬编码——C10 A1 的教训是
# tests/smoke_array_chunking.py 曾硬编码 PV2 值 c9243efd，PV bump 后恒 FAIL 误报）。
#   PV 2 → c9243efd40318c85：云掩膜 + 反射率缩放时代，data/derived/ 既有缓存
#           s2_beijing_test.c9243efd.* 的锚点（PV≥3 起为历史时代值，仅作对照）。
#   PV 3 → b91c09c9c6451c16：C4 p2-presets（LC08/LC09 补官方 offset −0.2）bump 2→3
#           后的现行金值。
# 纪律：任何 PV bump 必须在此登记新金值（mock 实算后填入）；未登记的 PV 会被
# test_spec_fingerprint 的断言拦截 —— 这是红线 3（改变像素输出必须 bump）与
# 红线 8（指纹归属显式化）的联防。
GOLDEN_FINGERPRINTS: dict[int, str] = {
    2: "c9243efd40318c85",
    3: "b91c09c9c6451c16",
}


def expected_p0_fingerprint(version: int | None = None) -> str:
    """P0 样本 spec 在当前（或指定）PROCESSING_VERSION 时代的金指纹。

    单一事实源：断言与脚本一律经此取值，不硬编码某个时代的常量。
    """
    from gis.spec import PROCESSING_VERSION  # 延迟导入：便于测试替换/对照

    v = PROCESSING_VERSION if version is None else version
    if v not in GOLDEN_FINGERPRINTS:
        raise AssertionError(
            f"PROCESSING_VERSION={v} 未登记 P0 金指纹——按红线 3/8：bump 后用 mock "
            "实算 P0 spec 指纹并登记进 _helpers.GOLDEN_FINGERPRINTS，同时在 README §9.1 记一笔。"
        )
    return GOLDEN_FINGERPRINTS[v]


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
    """P0 样本 spec（金指纹按时代取值，见 GOLDEN_FINGERPRINTS）。时序字段缺省。"""
    kw = dict(P0_SPEC_DICT)
    kw.update(over)
    return ArtifactSpec.from_dict(kw)
