# -*- coding: utf-8 -*-
"""
C4 冒烟：5 条新增预设 × 三出口（emit_file / emit_array / emit_map）。

用法：
    python tests/smoke_presets.py                    # 全部 5 条 × 三出口
    python tests/smoke_presets.py worldcover         # 只跑指定预设（红线 6：先串行试点）
    python tests/smoke_presets.py worldcover:file    # 只跑某预设的某出口
    python tests/smoke_presets.py s1_db s1_linear era5

数据来源：GEE（需网络 + 认证）。AOI 是北京小框（0.1°×0.07°，与 P0 样本同量级）。
逐条预设串行执行，每条先 file → array → map。

值检查不是"看着像"：对带单位换算的预设，脚本会**独立复算**一遍 GEE 原始值
（不走 source 的变换），再验证 「本产物 ≈ a×原始 + b」。这样 K→°C、m→mm、
Landsat 的 -0.2 offset 都有确定性的证据，不依赖当地气候恰好是多少度。
"""

import json
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, ".")

from gis import source
from gis.jobs import Job, bind_progress, run_emit
from gis.spec import ArtifactSpec, bbox_to_geojson

# 北京小框（中心城区 + 部分绿地/水系）
AOI = bbox_to_geojson(116.30, 39.95, 116.40, 40.02)

# ---------------------------------------------------------------- 预设与用例
#
# over  = 加在 defaults_for() 之上的字段（三个出口都需要网格与时间范围）
# name  = 命令行里用的短名
PRESETS = [
    dict(name="s1_db", asset="COPERNICUS/S1_GRD",
         over=dict(time_range=("2024-06-01", "2024-09-01"), reducer="median"),
         check="s1_db"),
    dict(name="s1_linear", asset="COPERNICUS/S1_GRD_FLOAT",
         over=dict(time_range=("2024-06-01", "2024-09-01"), reducer="median"),
         check="s1_linear"),
    dict(name="landsat89", asset="LANDSAT/LC08+LC09/C02/T1_L2",
         over=dict(time_range=("2024-06-01", "2024-09-01"), reducer="median"),
         check="transform"),
    dict(name="era5", asset="ECMWF/ERA5_LAND/DAILY_AGGR",
         over=dict(time_range=("2024-06-01", "2024-07-01"), reducer="mean"),
         check="transform"),
    dict(name="worldcover", asset="ESA/WorldCover/v200",
         over={},                                    # defaults 已带 reducer=mode
         check="classes"),
    # 2026-10-06 范围变更：既有两条 Landsat 预设补了官方 offset -0.2，纳入 smoke，
    # 用同一套"独立 GEE 复算"证明产物落在 DN*2.75e-05-0.2 量纲（验收 A2b）。
    dict(name="legacy_lc08", asset="LANDSAT/LC08/C02/T1_L2",
         over=dict(time_range=("2024-06-01", "2024-09-01"), reducer="median"),
         check="transform"),
    dict(name="legacy_lc09", asset="LANDSAT/LC09/C02/T1_L2",
         over=dict(time_range=("2024-06-01", "2024-09-01"), reducer="median"),
         check="transform"),
]


def make_spec(name: str, asset: str, over: dict) -> ArtifactSpec:
    d = source.defaults_for(asset, AOI)
    d.update(over)
    spec = ArtifactSpec.from_dict({"id": f"smoke_{name}", "crs": d["crs"], "aoi": AOI, **d})
    spec.validate("file")
    return spec


def run_exit(spec: ArtifactSpec, exit_: str, results: dict) -> dict:
    job = Job(id=f"smoke_presets_{spec.id}_{exit_}", kind="emit", spec=spec, exit=exit_)
    label = f"{spec.id}/{exit_}"

    def cb(_ev, p):
        print(f"    [{p.get('pct', 0):5.1f}%] {str(p.get('phase', ''))[:24]:24s} "
              f"{str(p.get('message', ''))[:58]}")

    bind_progress(job, cb)
    t0 = time.time()
    res = run_emit(job)
    dt = time.time() - t0
    if job.error:
        print(f"    ❌ {label} 失败：")
        for line in job.error.splitlines()[:8]:
            print("       " + line)
        results["errors"].append(f"{label}: {job.error.splitlines()[0] if job.error else 'error'}")
        return {}
    print(f"    ✅ {label} ({dt:.1f}s)")
    return res or {}


# ---------------------------------------------------------------- 值检查

def _read_netcdf(path: str):
    """产物 .nc → (xarray.Dataset, 每波段均值 dict)。"""
    import xarray as xr
    ds = xr.open_dataset(path)
    means = {str(v): float(ds[v].mean(skipna=True).values) for v in ds.data_vars}
    return ds, means


def _gee_raw_means(spec: ArtifactSpec, preset) -> dict:
    """
    独立复算：同一集合、同一时间窗口、同一波段、同一 reducer，但**不做任何单位变换**。
    用于验证产物 = a×原始 + b（不依赖当地实际温度/降水）。
    """
    from gis import geoenv
    ee, _ = geoenv.init_ee()

    if preset.merge_assets:
        col = ee.ImageCollection(preset.merge_assets[0])
        for other in preset.merge_assets[1:]:
            col = col.merge(ee.ImageCollection(other))
    else:
        col = ee.ImageCollection(preset.asset)
    if spec.time_range:
        col = col.filterDate(*spec.time_range)
    aoi = ee.Geometry(spec.aoi)
    col = col.filterBounds(aoi)
    if preset.cloud_mask:
        col = source.mask_clouds(col, preset.cloud_mask)
    col = source._filter_collection(ee, preset, col, tuple(spec.bands))
    col = col.select(list(spec.bands))
    img = getattr(col, spec.reducer)()
    return img.reduceRegion(ee.Reducer.mean(), aoi, spec.scale, crs=spec.crs,
                            maxPixels=int(1e9), bestEffort=True).getInfo() or {}


def check_transform(spec: ArtifactSpec, results: dict, notes: list) -> None:
    """A2/A3 的量纲证据：产物均值 ≈ preset 的 (scale, offset) 作用在 GEE 原始均值上。"""
    preset = source.preset_for(spec.asset)
    nc = results.get("array", {}).get("path")
    if not nc:
        notes.append("缺 array 产物，跳过量纲复算")
        return
    _ds, means = _read_netcdf(nc)
    raw = _gee_raw_means(spec, preset)
    bad = []
    for band in spec.bands:
        if band not in means or band not in raw:
            continue
        a, b = source.band_transforms_for(preset, (band,)).get(band, (1.0, 0.0))
        want = a * raw[band] + b
        tol = max(0.01, 0.10 * abs(want))
        ok = abs(means[band] - want) <= tol
        notes.append(f"{band}: 产物 {means[band]:.4f} vs 复算 {want:.4f} "
                     f"(a={a}, b={b}) {'OK' if ok else '❌'}")
        if not ok:
            bad.append(band)
    if bad:
        notes.append(f"❌ 量纲不一致：{bad}")
        results["errors"].append(f"{spec.id}: 量纲复算不一致 {bad}")


def check_classes(spec: ArtifactSpec, results: dict, notes: list) -> None:
    """A4 的分类语义证据：全部像元都是精确类码（无 mean 产生的插值值）。"""
    import numpy as np
    preset = source.preset_for(spec.asset)
    nc = results.get("array", {}).get("path")
    if not nc:
        notes.append("缺 array 产物，跳过类码检查")
        return
    ds, _means = _read_netcdf(nc)
    var = list(ds.data_vars)[0]
    vals = np.unique(np.round(ds[var].values[~np.isnan(ds[var].values)]))
    allowed = np.asarray(preset.class_values, dtype="float64")
    bad = [float(v) for v in vals if not np.any(np.isclose(v, allowed, atol=0.5))]
    notes.append(f"类码取值：{sorted(float(v) for v in vals)}")
    if bad:
        notes.append(f"❌ 出现非类码值：{bad}")
        results["errors"].append(f"{spec.id}: 出现非类码值 {bad}")
    else:
        notes.append(f"✅ 全部落在 {len(allowed)} 个类码内")


def check_s1(spec: ArtifactSpec, results: dict, notes: list, *, linear: bool) -> None:
    """A1：dB 与线性各自的量纲 + 产物非空。"""
    nc = results.get("array", {}).get("path")
    if not nc:
        notes.append("缺 array 产物，跳过量纲检查")
        return
    _ds, means = _read_netcdf(nc)
    notes.append("波段均值：" + ", ".join(f"{k}={v:.3f}" for k, v in means.items()))
    for band, v in means.items():
        if linear:
            ok = 1e-6 < v < 100
            want = "线性后向散射应在 (0, 100] 量级"
        else:
            ok = -60 < v < 5
            want = "dB 后向散射应在 (-60, 5) 量级"
        if not ok:
            notes.append(f"❌ {band}={v} 不在{want}")
            results["errors"].append(f"{spec.id}: {band}={v} 不在{want}")
            return
    notes.append("✅ 量纲符合" + ("线性" if linear else "dB"))


def check_for(entry: dict, spec: ArtifactSpec, results: dict, notes: list) -> None:
    kind = entry["check"]
    if kind == "transform":
        check_transform(spec, results, notes)
    elif kind == "classes":
        check_classes(spec, results, notes)
    elif kind == "s1_db":
        check_s1(spec, results, notes, linear=False)
    elif kind == "s1_linear":
        check_s1(spec, results, notes, linear=True)


# ---------------------------------------------------------------- 主流程

def selected(argv: list) -> list:
    if not argv:
        return PRESETS
    want = [a.split(":")[0] for a in argv]
    out = [e for e in PRESETS if e["name"] in want]
    missing = set(want) - {e["name"] for e in out}
    if missing:
        print(f"未知预设：{sorted(missing)}；可选：{[e['name'] for e in PRESETS]}")
        sys.exit(2)
    return out


def main(argv: list) -> int:
    entries = selected(argv)
    only_exit = None
    for a in argv:
        if ":" in a:
            only_exit = a.split(":", 1)[1]
    exits = [only_exit] if only_exit else ["file", "array", "map"]

    print(f"AOI: {json.dumps(AOI['coordinates'])}")
    print(f"预设: {[e['name'] for e in entries]} | 出口: {exits}\n")

    results = {"errors": [], "summary": []}
    for entry in entries:
        spec = make_spec(entry["name"], entry["asset"], dict(entry["over"]))
        print(f"=== {entry['name']}  ({entry['asset']})")
        print(f"    指纹 {spec.fingerprint()} | scale={spec.scale} | bands={list(spec.bands)} "
              f"| reducer={spec.reducer} | dtype={spec.dtype}")
        got: dict = {}
        for ex in exits:
            got[ex] = run_exit(spec, ex, results)

        notes: list = []
        if "array" in got and got["array"]:
            try:
                check_for(entry, spec, got, notes)
            except Exception as e:                     # 检查本身失败也要报出来
                notes.append(f"❌ 检查抛异常：{type(e).__name__}: {e}")
                results["errors"].append(f"{entry['name']}: 检查抛异常 {type(e).__name__}: {e}")

        fps = {ex: r.get("spec_fingerprint") for ex, r in got.items() if r}
        if len(set(fps.values())) > 1:
            notes.append(f"❌ 三出口指纹不一致：{fps}")
            results["errors"].append(f"{entry['name']}: 三出口指纹不一致 {fps}")
        elif fps:
            notes.append(f"三出口指纹一致：{list(fps.values())[0]}")

        grids = {ex: (r.get("grid") or {}).get("width") for ex, r in got.items() if r}
        if len(set(grids.values())) > 1:
            notes.append(f"❌ 出口网格宽度不一致：{grids}")
            results["errors"].append(f"{entry['name']}: 出口网格不一致 {grids}")

        for line in notes:
            print("    " + line)
        artifacts = [p for r in got.values() if r for p in
                     [r.get("path"), r.get("qgz"), r.get("png")] if p]
        print(f"    产物：{artifacts}\n")
        results["summary"].append(dict(name=entry["name"], notes=notes, artifacts=artifacts))

    print("=" * 78)
    if results["errors"]:
        print(f"❌ 失败 {len(results['errors'])} 项：")
        for e in results["errors"]:
            print("   - " + e)
        return 1
    print(f"✅ 全部通过：{len(results['summary'])} 条预设 × {len(exits)} 出口")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
