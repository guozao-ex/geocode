# -*- coding: utf-8 -*-
"""
C8 冒烟：OSM 矢量源 → spec / GPKG / map 出口叠加（A5 / A8）。

用法（D8 串行顺序，网络项已逐条标注）：
    python tests/smoke_osm.py overlay-qgis    # A5：qgis renderer + 矢量叠加，
                                              #     .qgz 读回断言栅格+N 矢量图层
                                              #     【需网络·仅首轮】P0 缓存缺失时经
                                              #     GEE 建栅格；矢量源本身离线（fixture）
    python tests/smoke_osm.py overlay-arcpy   # A5：arcpy renderer 出 PDF/PNG 含矢量
                                              #     【需网络·仅首轮】同上
    python tests/smoke_osm.py network-fetch   # A8①：真实 Overpass 小范围拉取→GPKG 读回
                                              #     【需网络】Overpass API（代理经 geocode.json）
    python tests/smoke_osm.py mini-three-exits  # A8②：admin_aoi(110101) @100m 三出口 mini run
                                              #     【需网络】GEE（东城区 110101，时序窗口压到
                                              #     一个月；真实 _ref 边界经 geocode.json 覆盖路径）

前置：
    - geocode.json 为本地件（skip-worktree 占位模板不入库）——先从主工作区复制；
      其中 aoi.admin_data_dir 指向真实 _ref 边界数据、osm.endpoints 可放镜像。
    - overlay-qgis / overlay-arcpy 的矢量 GPKG 由入库 fixture 经假 transport 离线
      生成（真实录制的北京非边界水系，D2 合规）。
"""
import io
import json
import pathlib
import sys
import time
import zipfile
import xml.etree.ElementTree as ET

try:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, ".")

from gis.geoenv import ROOT
from gis.jobs import Job, bind_progress, run_emit
from gis.osm import fetch_osm
from gis.spec import ArtifactSpec, LayoutSpec, OverlaySpec, RenderSpec

FIXTURE = ROOT / "tests" / "unit" / "fixtures" / "osm_water_recorded.json"
AOI_TINY = ROOT / "tests" / "unit" / "fixtures" / "admin_tiny" / "china_county.geojson"

BBOX = (116.30, 39.90, 116.35, 39.95)

# P0 样本 spec（与 smoke_map_renderers 同款）—— layout/overlays 不参与指纹，
# 栅格缓存可与 P0 时代产物（s2_beijing_test.{fingerprint8}.tif）共用。
P0_SPEC = {
    "id": "s2_beijing_test",
    "asset": "COPERNICUS/S2_SR_HARMONIZED",
    "bands": ["B4", "B3", "B2"],
    "scale": 10,
    "crs": "EPSG:32650",
    "dtype": "uint16",
    "time_range": ["2024-06-01", "2024-08-31"],
    "reducer": "median",
    "aoi": {"type": "Polygon",
            "coordinates": [[[116.30, 39.95], [116.40, 39.95],
                             [116.40, 40.02], [116.30, 40.02], [116.30, 39.95]]]},
}


def _fixture_transport():
    payload = FIXTURE.read_text(encoding="utf-8")

    def tr(endpoint, ql, timeout):
        return 200, payload

    return tr


def _build_overlay_sources() -> list[OverlaySpec]:
    """离线生成矢量叠加源：真实 fixture → GPKG；合成县界 → GeoJSON。"""
    r = fetch_osm(query_id="smoke_osm_water", tags={"natural": ["water", "wetland"]},
                  bbox=BBOX, transport=_fixture_transport())
    print(f"overlay GPKG: {r['gpkg']} ({r['feature_count']} 要素, reused={r['reused']})")
    # GeoJSON 叠加源（属性表带 name 列 → 演示 label_field）
    import geopandas as gpd
    gdf = gpd.read_file(AOI_TINY)
    two = gdf[gdf["adcode"].isin(["110101", "110102"])]
    geojson_path = ROOT / "data" / "deliver" / "smoke_osm_aoi.geojson"
    two.to_file(geojson_path, driver="GeoJSON")
    return [OverlaySpec(source=str(r["gpkg"]), color="#1f6feb", width=2.5,
                        fill_color="#7aa7ff", opacity=0.9, label_field="name"),
            OverlaySpec(source=str(geojson_path), color="#e05252", width=1.5,
                        opacity=1.0)]


def _ensure_p0_raster(spec) -> None:
    """P0 缓存缺失时经 GEE 建栅格（A5 的【需网络·仅首轮】部分）。"""
    from gis.grid import compute_grid
    from gis import geoenv
    out = geoenv.data_path("derived", f"{spec.slug}.{spec.fingerprint()[:8]}.tif")
    if out.exists() and out.stat().st_size > 4096:
        print(f"P0 缓存命中: {out.name}")
        return
    print("P0 缓存缺失 → 走 GEE 下载（需网络，仅首轮）…")
    job = Job(id="smoke_osm_seed", kind="emit", spec=spec, exit="file")
    bind_progress(job, lambda ev, p: print(f"  [{p.get('pct', 0):5.1f}%] {p.get('phase', '')} {p.get('message', '')[:60]}"))
    run_emit(job)
    if job.error:
        print(job.error[:2000])
        sys.exit(1)


def _run_map(spec, renderer):
    job = Job(id=f"smoke_osm_{renderer}", kind="emit", spec=spec,
              exit="map", renderer=renderer)
    bind_progress(job, lambda ev, p: print(f"  [{p.get('pct', 0):5.1f}%] {p.get('phase', '')} {p.get('message', '')[:70]}"))
    return run_emit(job)


def _qgz_layer_counts(qgz_path: str) -> dict[str, int]:
    """读回 .qgz（zip 内 .qgs XML）：按 provider 统计图层（gdal=栅格, ogr=矢量）。"""
    counts: dict[str, int] = {}
    with zipfile.ZipFile(qgz_path) as z:
        qgs = next(n for n in z.namelist() if n.endswith(".qgs"))
        root = ET.fromstring(z.read(qgs))
        for ml in root.iter("maplayer"):
            provider = (ml.findtext("provider") or "").strip()
            counts[provider] = counts.get(provider, 0) + 1
    return counts


def cmd_overlay(renderer: str) -> int:
    base = ArtifactSpec.from_dict({**P0_SPEC,
                                   "render": {"bands": ["B4", "B3", "B2"],
                                              "stretch": "percentile",
                                              "percentile": [2, 98]},
                                   "layout": LayoutSpec(title="C8 矢量叠加验收").to_dict()})
    overlays = _build_overlay_sources()
    spec = base.with_(overlays=tuple(overlays))   # 呈现层更新，指纹不变
    print("fingerprint:", spec.fingerprint(), "| overlays:", len(spec.overlays))

    _ensure_p0_raster(ArtifactSpec.from_dict(P0_SPEC))   # 栅格种子（首轮需网络）
    t0 = time.time()
    result = _run_map(spec, renderer)
    print(f"elapsed: {time.time() - t0:.1f}s")
    if result is None or ("qgz_error" in result or "arcpy_error" in result):
        slim = {k: v for k, v in (result or {}).items()
                if k.endswith("_error") or k in ("arcpy_error",)}
        print("ERROR:", json.dumps(slim, ensure_ascii=False)[:1200])
        return 1

    if renderer == "qgis":
        counts = _qgz_layer_counts(result["qgz"])
        print("qgz 图层统计:", counts)
        if counts.get("ogr", 0) != len(overlays) or counts.get("gdal", 0) < 1:
            print(f"FAIL: 期望 gdal≥1 + ogr={len(overlays)}")
            return 1
        print(f"PASS: .qgz 含栅格 1 + 矢量 {counts.get('ogr')} 图层")
    else:
        pdf, png = result.get("pdf"), result.get("png")
        for p in (pdf, png):
            if not p or not pathlib.Path(p).is_file():
                print("FAIL: arcpy 导出缺失", pdf, png)
                return 1
        print("arcpy overlays:", result.get("overlays"),
              "errors:", result.get("overlay_errors"))
        n_overlays = result.get("overlays")
        if isinstance(n_overlays, list):   # 兼容 bridge 明细形态
            n_overlays = len(n_overlays)
        if n_overlays != len(overlays):
            print("FAIL: arcpy 叠加图层数不符")
            return 1
        print(f"PASS: .aprx + PDF/PNG 含 {n_overlays} 个矢量图层")
    return 0


def cmd_network_fetch() -> int:
    """A8①：真实 Overpass 小范围拉取 → GPKG 读回。【需网络】"""
    from gis.osm import _endpoints  # noqa
    print("endpoints:", _endpoints())
    r = fetch_osm(query_id="smoke_osm_live", tags={"natural": ["water", "wetland"]},
                  bbox=BBOX, timeout=30)
    print(f"features: {r['feature_count']} skipped: {r['skipped_count']} "
          f"hash8: {r['hash8']} ts: {r['osm3s_timestamp']}")
    print("gpkg:", r["gpkg"])
    import geopandas as gpd
    back = gpd.read_file(r["gpkg"], layer=r["layer"])
    assert len(back) == r["feature_count"], "读回要素数与 sidecar 不一致"
    assert back.crs.to_epsg() == 4326
    print(f"PASS: 真实拉取 {len(back)} 要素 → GPKG 读回一致（EPSG:4326）")
    return 0


def cmd_mini_three_exits() -> int:
    """A8②：admin_aoi(110101) @100m 三出口 mini run。【需网络·GEE】"""
    from gis.aoi import admin_aoi

    aoi = admin_aoi("110101")   # 真实 _ref 合规边界（geocode.json 覆盖路径）
    water_gpkg = _build_overlay_sources()[0].source   # 真实交付名 {id}.{hash8}.gpkg
    spec = ArtifactSpec(
        id="c8_mini_dongcheng", asset="COPERNICUS/S2_SR_HARMONIZED",
        bands=("B4", "B3", "B2"), scale=100.0, crs="EPSG:32650",
        dtype="uint16", time_range=("2024-06-01", "2024-06-30"),
        reducer="median", aoi=aoi,
        render=RenderSpec(bands=("B4", "B3", "B2"), stretch="percentile",
                          percentile=(2.0, 98.0)),
        note="C8 A8 mini run: admin_aoi(110101) @100m",
        overlays=(OverlaySpec(source=water_gpkg,
                              color="#1f6feb", width=2.0, opacity=0.9),),
    )
    spec.validate()
    print("fingerprint:", spec.fingerprint())
    from gis.grid import compute_grid
    g = compute_grid(spec)
    print(f"grid: {g.width}x{g.height} @{spec.scale}m")

    results = {}
    for ex in ("file", "array", "map"):
        job = Job(id=f"smoke_osm_mini_{ex}", kind="emit", spec=spec, exit=ex,
                  renderer="qgis" if ex == "map" else None)
        bind_progress(job, lambda ev, p: print(f"  [{ex:5s}][{p.get('pct', 0):5.1f}%] "
                                               f"{p.get('phase', '')} {p.get('message', '')[:60]}"))
        result = run_emit(job)
        if job.error:
            print(f"{ex} ERROR:")
            print(job.error[:1500])
            return 1
        results[ex] = result or {}

    fps = {ex: r.get("spec_fingerprint") for ex, r in results.items()}
    print("三出口指纹:", fps)
    if len(set(fps.values())) != 1:
        print("FAIL: 三出口指纹不一致")
        return 1
    for ex, r in results.items():
        arts = [k for k in ("path", "qgz", "png", "values") if r.get(k)]
        print(f"  {ex:6s} → {arts}")
    print("PASS: OSM/边界矢量进入 spec 与三出口链路（东城区 110101 @100m）")
    return 0


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "overlay-qgis":
        return cmd_overlay("qgis")
    if cmd == "overlay-arcpy":
        return cmd_overlay("arcpy")
    if cmd == "network-fetch":
        return cmd_network_fetch()
    if cmd == "mini-three-exits":
        return cmd_mini_three_exits()
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
