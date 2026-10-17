# -*- coding: utf-8 -*-
"""
在线冒烟：预设表 × 三出口（emit_file / emit_array / emit_map）。

用法：
    python tests/smoke_presets.py                    # 全部预设 × 三出口
    python tests/smoke_presets.py dem                # 只跑指定预设（红线 6：先串行试点）
    python tests/smoke_presets.py dem:file           # 只跑某预设的某出口
    python tests/smoke_presets.py s1_db s1_linear era5

C16 补齐的覆盖缺口（2026-10-18）：默认清单原先只有 7 条，**不含 DEM 与 GSW**，于是
`COPERNICUS/DEM/GLO30` 的装载缺陷（26076 片瓦片集合按单景走 → "is not an Image"）在
离线 257 条用例全绿的情况下潜伏到 2026-10-11 首次真跑才暴露。现两条均已纳入，
且各自带**语义校验**（不是只看"跑通"）：DEM 查高程量纲与取值域，GSW 查 occurrence 等波段取值域。

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

# DEM 高程的合理取值域（米）。覆盖地球陆地高程域（死海 -430 m ~ 珠峰 8849 m），
# 既能抓住量纲错误（如原始整数值当米、单位多乘 1e3），又不会换个 AOI 就假失败。
# 本 AOI（北京）实测 min≈24.45 / max≈95.57 / mean≈51.05；泰安玉皇顶一带实测最高 1531.93，
# 两级都在域内 —— 后者是 brief D4 记录的锚点旁证。
DEM_MIN_PLAUSIBLE = -500.0
DEM_MAX_PLAUSIBLE = 9000.0

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
    # --- C16 补齐的覆盖缺口（2026-10-18）------------------------------------
    # 这两条原先不在默认清单里，导致 GLO30 的装载缺陷在"离线全绿"的假象下潜伏到
    # 2026-10-11 首次真跑。两条都**不带 time_range / reducer**（不是时序集合）：
    #   · DEM  = 26076 片 1° 瓦片的 ImageCollection → 走 preset.tile_mosaic（按 AOI 过滤后 mosaic）
    #   · GSW  = 单景 Image → 走 ee.Image(asset) 单景分支（**不是**集合，不该标 collection_only）
    # 校验按语义而非"跑通"：DEM 查高程量纲/取值域，GSW 查各波段取值域（见 check_dem / check_gsw）。
    dict(name="dem", asset="COPERNICUS/DEM/GLO30",
         over={},
         check="dem"),
    dict(name="gsw", asset="JRC/GSW1_4/GlobalSurfaceWater",
         over={},
         check="gsw"),
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


def check_dem(spec: ArtifactSpec, results: dict, notes: list) -> None:
    """A2：DEM 的高程语义 —— 不是"跑通"，是"数值确实是 GLO-30 的高程"。

    断言四件事：
      1. 存在有效像素（非全 NaN）—— 防"跑通但全空"；
      2. 非恒定值 —— 防装载方式错导致只剩单片/单值的常数面；
      3. 极值落在合理区间 —— 防量纲错（如把 int16 原始值当米、或单位换算多乘了 1e3）；
      4. 与 GLO-30 语义一致：本 AOI（北京）实测 min≈24.45 / max≈95.57 / mean≈51.05。

    区间取 [-500, 9000]：覆盖地球陆地高程域（死海 -430 m ~ 珠峰 8849 m），既能抓住量纲错误，
    又不会因为换个 AOI 就假失败。泰安玉皇顶 ≈1531.9 m 的记录作为锚点合理性旁证（见 brief D4）。
    """
    import numpy as np
    nc = results.get("array", {}).get("path")
    if not nc:
        notes.append("缺 array 产物，跳过高程语义检查")
        results["errors"].append(f"{spec.id}: 缺 array 产物，无法校验高程语义")
        return
    _ds, means = _read_netcdf(nc)
    ds = _ds
    band = "DEM" if "DEM" in ds.data_vars else list(ds.data_vars)[0]
    vals = np.asarray(ds[band].values, dtype="float64")
    finite = vals[np.isfinite(vals)]
    if finite.size == 0:
        notes.append("❌ DEM 全为 NaN（没有有效像素）")
        results["errors"].append(f"{spec.id}: DEM 全为 NaN")
        return
    vmin, vmax, vmean = float(finite.min()), float(finite.max()), float(finite.mean())
    notes.append(f"DEM 高程：min={vmin:.2f} max={vmax:.2f} mean={vmean:.2f} "
                 f"有效像素={finite.size}/{vals.size}")
    # 1) 存在有效像素（上面已保证 finite.size > 0），2) 非恒定值
    if np.isclose(vmax, vmin):
        notes.append(f"❌ DEM 为恒定值 {vmin}（装载方式可能错：只剩单片或全填同一值）")
        results["errors"].append(f"{spec.id}: DEM 恒定值 {vmin}")
    # 3) 取值域
    if not (DEM_MIN_PLAUSIBLE <= vmin and vmax <= DEM_MAX_PLAUSIBLE):
        notes.append(f"❌ DEM 极值越界：期望 [{DEM_MIN_PLAUSIBLE}, {DEM_MAX_PLAUSIBLE}]，"
                     f"实得 [{vmin:.2f}, {vmax:.2f}]（量纲或单位换算有问题）")
        results["errors"].append(f"{spec.id}: DEM 极值越界 [{vmin:.2f}, {vmax:.2f}]")
    else:
        notes.append(f"✅ 高程取值域合理（[{DEM_MIN_PLAUSIBLE}, {DEM_MAX_PLAUSIBLE}] 内）、非恒定、有有效像素")


def check_gsw(spec: ArtifactSpec, results: dict, notes: list) -> None:
    """A3：GSW 的取值域语义 —— 防"接口跑通但内容错"。

    断言各波段落在 GEE 官方语义域内（按**全域**写，不绑定本 AOI 的观测极值，换个 AOI 也不假失败）：
      · occurrence  ∈ [0, 100]（水面出现频率百分比）
      · seasonality ∈ [0, 12] （月份数；0 表示无季节性）
      · max_extent  ∈ [0, 1]  （二值掩膜：是否曾被水覆盖）

    本 AOI（北京）实测观测值为 occurrence 0–89、seasonality 1–12、max_extent 0–1（2026-10-18），
    仅作输出说明，不作为断言上界。
    """
    import numpy as np
    nc = results.get("array", {}).get("path")
    if not nc:
        notes.append("缺 array 产物，跳过取值域检查")
        results["errors"].append(f"{spec.id}: 缺 array 产物，无法校验取值域")
        return
    ds, _means = _read_netcdf(nc)
    domains = {
        "occurrence": (0.0, 100.0),
        "seasonality": (0.0, 12.0),
        "max_extent": (0.0, 1.0),
    }
    checked = 0
    for band, (lo, hi) in domains.items():
        if band not in ds.data_vars:
            notes.append(f"⚠ 产物缺波段 {band}（跳过其取值域检查）")
            continue
        vals = np.asarray(ds[band].values, dtype="float64")
        finite = vals[np.isfinite(vals)]
        if finite.size == 0:
            notes.append(f"❌ {band} 全为 NaN")
            results["errors"].append(f"{spec.id}: {band} 全为 NaN")
            continue
        bmin, bmax = float(finite.min()), float(finite.max())
        ok = lo <= bmin and bmax <= hi
        notes.append(f"{band}: [{bmin:g}, {bmax:g}] 期望 ⊂ [{lo:g}, {hi:g}] {'✅' if ok else '❌'}")
        if not ok:
            results["errors"].append(f"{spec.id}: {band} 超出取值域 [{lo:g}, {hi:g}]，实得 [{bmin:g}, {bmax:g}]")
        checked += 1
    if checked == 0:
        results["errors"].append(f"{spec.id}: 三个语义波段一个都没验到")
    else:
        notes.append(f"✅ {checked} 个波段的取值域全部合理")


def check_for(entry: dict, spec: ArtifactSpec, results: dict, notes: list) -> None:
    kind = entry["check"]
    if kind == "dem":
        check_dem(spec, results, notes)
        return
    if kind == "gsw":
        check_gsw(spec, results, notes)
        return
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
