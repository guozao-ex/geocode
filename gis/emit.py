"""
三出口：把同一个 ee 对象物化成三种形态。

    emit_array → xarray / NetCDF   （服务：我算）
    emit_file  → GeoTIFF / COG     （服务：下游接）
    emit_map   → .qgz / PNG        （服务：人看）

★ 核心约束：三个函数都从同一份 spec 出发、调同一个 source.build_image()、
  用同一个 grid.compute_grid() 定网格。因此三者的
  CRS / 分辨率 / 范围 / 像素值必须一致 —— 这是可验证的验收判据。

依赖方向（有意为之）：
    emit_map 在需要时**复用** emit_file 的产物，而不是自己再下一次。
    这保证"图"和"文件"看到的绝对是同一份数据。
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path

from . import geoenv, qgis_bridge as _qb
from .grid import Grid, compute_grid
from .jobs import Job, JobCancelled
from .spec import ArtifactSpec, Exit

# getDownloadURL 单次请求的像素上限（经验值）
MAX_DIRECT_PIXELS = 64_000_000


# ---------------------------------------------------------------------------
# 调度
# ---------------------------------------------------------------------------

def dispatch(job: Job) -> dict:
    if job.exit == "file":
        return emit_file(job)
    if job.exit == "array":
        return emit_array(job)
    if job.exit == "map":
        return emit_map(job)
    raise ValueError(f"未知出口：{job.exit!r}")


# ---------------------------------------------------------------------------
# 公共：准备栅格文件
# ---------------------------------------------------------------------------

def _ensure_raster(job: Job) -> tuple[Path, Grid]:
    """
    确保磁盘上有这个 spec 的栅格，返回 (路径, 网格)。
    已存在就直接复用 —— 不重复下载，也保证下游拿到同一份数据。
    """
    spec = job.spec
    assert spec is not None
    grid = compute_grid(spec)
    out = _output_path(spec, "derived", ".tif")
    if out.exists() and out.stat().st_size > 4096:
        job.progress("复用已有栅格", 25, f"{out.name} ({out.stat().st_size/1024/1024:.1f} MB)")
        return out, grid
    return _download_to(job, out, grid), grid


def _output_path(spec: ArtifactSpec, kind: str, ext: str) -> Path:
    return geoenv.data_path(kind, f"{spec.slug}.{spec.fingerprint()[:8]}{ext}")


# ---------------------------------------------------------------------------
# 出口 C：文件
# ---------------------------------------------------------------------------

def emit_file(job: Job) -> dict:
    spec = job.spec
    assert spec is not None
    grid = compute_grid(spec)

    out = _output_path(spec, "derived", ".tif")
    if out.exists() and out.stat().st_size > 4096:
        job.progress("已存在，跳过下载", 90, out.name)
    else:
        _download_to(job, out, grid)

    info = _describe_raster(out)
    # 校验 GEE 是否照我们给的网格执行 —— 不对齐要报出来，不装作没事
    ok, problems = grid.matches(
        crs=info.get("crs"), bounds=tuple(info.get("bounds") or (0, 0, 0, 0)),
        shape=(info.get("height") or 0, info.get("width") or 0),
    )

    job.artifacts.append(str(out))
    size_mb = out.stat().st_size / 1024 / 1024
    job.progress("完成", 100, f"{out.name} ({size_mb:.1f} MB)")

    return {
        "exit": "file",
        "path": str(out),
        "size_mb": round(size_mb, 2),
        "spec_fingerprint": spec.fingerprint(),
        "grid": grid.to_dict(),
        "grid_aligned": ok,
        "grid_problems": problems,
        "raster": info,
    }


def _download_to(job: Job, out_path: Path, grid: Grid) -> Path:
    from . import source

    spec = job.spec
    assert spec is not None

    job.progress("构建计算图", 5, f"{spec.asset} → ee.Image")
    img = source.build_image(spec)
    job.check_cancelled()

    est = grid.width * grid.height
    if est > MAX_DIRECT_PIXELS:
        raise ValueError(
            f"网格太大，不适合直下：{grid.width}×{grid.height} = {est/1e6:.1f} 百万像素，"
            f"上限约 {MAX_DIRECT_PIXELS/1e6:.0f} 百万。\n"
            f"  三条出路：\n"
            f"    1. 放大 scale（当前 {spec.scale}m）—— 降分辨率最省事\n"
            f"    2. 缩小 AOI\n"
            f"    3. 改用批处理导出（Export.image.toCloudStorage）—— 待接\n"
            f"  注：geemap 作者也是这个意思 —— download_ee_image 适合『下载原始影像』"
            f"而非『下载重计算结果』。"
        )

    job.progress("申请下载链接", 15, f"{grid.width}×{grid.height} @ {grid.scale}m")
    # getDownloadURL 的 params 直接透传 REST API，两个坑：
    #
    # ⚠️ region 必须是 **EPSG:4326 经纬度**，不是投影坐标。
    #    之前传的是 grid.bounds（米），能"work"纯属巧合 ——
    #    .clip(aoi) 让影像拿到了 AOI 的 footprint，EE 用的是 footprint，
    #    我那个错误的 region 根本没被理。加了云掩膜后 updateMask 丢了
    #    footprint，才暴露成 "Image is unbounded"。
    #
    # ⚠️ bands 必须是列表（json.dumps 出来会被当成单个波段名）
    from .spec import aoi_bbox as _aoi_bbox
    region = list(_aoi_bbox(spec.aoi) or ())
    if not region:
        raise ValueError(
            "spec.aoi 为空，无法构造下载 region。\n"
            "  getDownloadURL 需要 EPSG:4326 的 (west, south, east, north)。"
        )
    params = {
        "name": spec.slug,
        "scale": grid.scale,
        "crs": grid.crs,
        "region": region,                     # 经纬度 bbox
        "format": "GEO_TIFF",
        "filePerBand": False,
    }
    if spec.bands:
        params["bands"] = list(spec.bands)
    job.check_cancelled()

    url = img.getDownloadURL(params)

    job.progress("下载中", 30, out_path.name)
    # 临时文件放**目标同目录**：
    #   同卷 rename 原子（跨盘 os.replace 会 WinError 17）
    #   不在 C: 留大文件残留
    #   下游只会看到完整的最终文件
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".part")
    try:
        _download(url, tmp, job)
        job.check_cancelled()
        tmp.replace(out_path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    job.progress("落盘完成", 92, f"{out_path.name} ({out_path.stat().st_size/1024/1024:.1f} MB)")
    return out_path


def _download(url: str, dest: Path, job: Job) -> None:
    req = urllib.request.Request(url, headers={"User-Agent": "geocode/0.1"})
    with urllib.request.urlopen(req, timeout=600) as r:
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        last = -1
        with open(dest, "wb") as f:
            while True:
                job.check_cancelled()
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = 30 + (done / total) * 58
                    if int(pct) != last:
                        last = int(pct)
                        job.progress("下载中", pct, f"{done/1048576:.1f} / {total/1048576:.1f} MB")
                else:
                    job.progress("下载中", None, f"{done/1048576:.1f} MB")
    if dest.stat().st_size < 4096:
        head = dest.read_bytes()
        if head.lstrip().startswith((b"{", b"[")):
            raise RuntimeError(
                f"GEE 返回的不是影像，而是错误信息：\n{head.decode('utf-8', 'replace')[:800]}"
            )


def _describe_raster(p: Path) -> dict:
    try:
        import rasterio
        with rasterio.open(p) as ds:
            return {
                "crs": str(ds.crs), "width": ds.width, "height": ds.height,
                "bands": ds.count, "dtype": ds.dtypes[0],
                "bounds": [round(float(v), 4) for v in tuple(ds.bounds)],
                "transform": [round(float(v), 6) for v in tuple(ds.transform)[:6]],
                "nodata": ds.nodata,
                "band_names": list(ds.descriptions) if ds.descriptions else None,
            }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


# ---------------------------------------------------------------------------
# 出口 B：数组
# ---------------------------------------------------------------------------

def emit_array(job: Job) -> dict:
    """
    xee 把 ee.Image 变成惰性 xarray，Dask 分块拉像素。

    与 emit_file 共用同一份 grid —— 所以数组和 GeoTIFF 是**同一个网格**，
    可以逐像素做算术。
    """
    import xarray as xr

    spec = job.spec
    assert spec is not None
    grid = compute_grid(spec)

    job.progress("构建计算图", 8, f"{spec.asset} → ee.Image")
    from . import source
    ee, _ = geoenv.init_ee()
    ee.Initialize()  # 幂等
    img = source.build_image(spec)
    job.check_cancelled()

    job.progress("打开 xee 数据集", 20, f"{grid.width}×{grid.height} @ {grid.scale}m")
    # xee 需要 dask 才不会在 open_dataset 时就拉全量
    #
    # ⚠️ shape_2d 是 (width, height)，**不是** (height, width)。
    # 传反了不会报错，只会给你一个转置的数组 —— 尺寸对不上时就发现了，
    # 但当网格恰为正方形时（w==h）它会静默地错下去。
    # 已用逐像素比对验证：传 (w,h) 时与 GeoTIFF 完全一致。
    ds = xr.open_dataset(
        img,
        engine="ee",
        crs=grid.crs,
        crs_transform=tuple(grid.transform),   # xee 要 tuple/Affine，list 会 TypeError
        shape_2d=(grid.width, grid.height),    # ← (x, y)，已实测确认
        ee_init_if_necessary=False,
    )

    job.progress("计算中（分块拉像素）", 35, "这一步可能较慢，取决于范围")
    job.check_cancelled()

    # 不要手动 .chunk() —— 实测它会触发 xee 内部的 select('*')，
    # 而当前 EE API 拒绝 '*' 通配符（Invalid regular expression）。
    # 需要分块时应在 open_dataset 时用 io_chunks/chunks 参数，
    # 而不是事后 .chunk()。此处网格仅 860×784，直接 compute 即可。
    try:
        arr = ds.compute()
    except Exception as e:
        raise RuntimeError(
            f"xee 拉取失败：{type(e).__name__}: {e}\n"
            f"  范围 {grid.width}×{grid.height}，{len(spec.bands) or '?'} 个波段。\n"
            f"  常见原因：\n"
            f"    - 范围太大 → 放大 scale、缩小 AOI，或改用 exit='file' + 本地读取\n"
            f"    - 触发配额（429）→ 减少 DASK_NUM_WORKERS\n"
            f"  注意：xee 是『把像素拉到本地算』，不是『服务端算完只回结果』。"
        ) from e

    job.check_cancelled()
    job.progress("落盘", 80, "NetCDF")

    out = _output_path(spec, "derived", ".nc")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".part")
    try:
        arr.to_netcdf(tmp)
        tmp.replace(out)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    sample = _array_sample(arr)
    job.artifacts.append(str(out))
    nbytes = out.stat().st_size
    job.progress("完成", 100, f"{out.name} ({nbytes/1048576:.1f} MB)")

    return {
        "exit": "array",
        "path": str(out),
        "size_mb": round(nbytes / 1048576, 2),
        "spec_fingerprint": spec.fingerprint(),
        "grid": grid.to_dict(),
        "dims": dict(arr.sizes),
        "vars": list(arr.data_vars),
        "sample": sample,
    }


def _array_sample(arr, rows: int = 3, cols: int = 3) -> dict:
    """
    取中心一小块作为对齐证据。
    与 emit_file 的栅格抽样对比，即可判定"数组与文件是否同一份数据"。
    """
    out: dict = {}
    try:
        import numpy as np
        ny, nx = arr.sizes.get("y", 0), arr.sizes.get("x", 0)
        y0 = max(0, ny // 2 - rows // 2)
        x0 = max(0, nx // 2 - cols // 2)
        sub = arr.isel(y=slice(y0, y0 + rows), x=slice(x0, x0 + cols))
        out["offset"] = [int(y0), int(x0)]
        out["shape"] = [int(min(rows, ny - y0)), int(min(cols, nx - x0))]
        values = {}
        for name in arr.data_vars:
            v = sub[name].values
            values[str(name)] = [
                [None if (isinstance(x, float) and np.isnan(x)) else float(x) for x in row]
                for row in np.atleast_2d(v)
            ]
        out["values"] = values
    except Exception as e:
        out["error"] = f"{type(e).__name__}: {e}"
    return out


# ---------------------------------------------------------------------------
# 出口 A：地图 / 工程
# ---------------------------------------------------------------------------

def emit_map(job: Job) -> dict:
    """
    两条分支，都产出"人能直接看"的东西：
      1. .qgz  QGIS 工程 —— 双击打开，图层/CRS/拉伸都配好
      2. .png  静态预览  —— 不用打开任何软件就能看

    数据复用 emit_file 的产物，不重复下载。
    """
    spec = job.spec
    assert spec is not None

    raster, grid = _ensure_raster(job)
    job.check_cancelled()

    results: dict = {
        "exit": "map",
        "spec_fingerprint": spec.fingerprint(),
        "grid": grid.to_dict(),
        "source_raster": str(raster),
        "artifacts": [],
    }

    # --- 先烘焙显示用 8bit RGB：拉伸固定进像素，QGIS 零解释 ---
    job.progress("烘焙显示用 8bit RGB", 50, "拉伸写入像素")
    visual = write_visual_rgb(spec, raster, grid)
    results["visual_raster"] = str(visual)
    results["artifacts"].append(str(visual))
    job.artifacts.append(str(visual))

    # --- 分支 1：.qgz —— 指向**显示用**栅格，不是浮点分析用栅格 ---
    job.progress("生成 QGIS 工程", 62, ".qgz")
    try:
        qgz = _qb.write_qgz(spec, visual, grid, _output_path(spec, "deliver", ".qgz"), timeout=240)
        qgz = Path(qgz["path"])
        results["qgz"] = str(qgz)
        results["artifacts"].append(str(qgz))
        job.artifacts.append(str(qgz))
    except Exception as e:
        results["qgz_error"] = f"{type(e).__name__}: {e}"
        job.progress("QGIS 工程生成失败，继续做预览图", 62, str(e)[:80])

    # --- 分支 2：静态 PNG ---
    job.check_cancelled()
    job.progress("渲染预览图", 78, ".png")
    try:
        png = _render_png(spec, raster, grid, job)
        results["png"] = str(png)
        results["artifacts"].append(str(png))
        job.artifacts.append(str(png))
    except Exception as e:
        results["png_error"] = f"{type(e).__name__}: {e}"

    if not results["artifacts"]:
        raise RuntimeError(
            "两个分支都没产出。\n"
            f"  .qgz 失败：{results.get('qgz_error')}\n"
            f"  .png 失败：{results.get('png_error')}"
        )

    job.progress("完成", 100, f"{len(results['artifacts'])} 个产物")
    return results


# --- .qgz -----------------------------------------------------------------

def _qgis_python() -> Path | None:
    """定位 QGIS 的 python 启动脚本（python-qgis.bat）。"""
    cfg = geoenv.load_config()
    override = (cfg.get("qgis") or {}).get("prefix")
    candidates: list[Path] = []
    if override:
        candidates.append(Path(override) / "bin" / "python-qgis.bat")
    for root in (Path("C:/Program Files"), Path("C:/OSGeo4W"), Path("C:/OSGeo4W64")):
        if not root.is_dir():
            continue
        for d in sorted(root.glob("QGIS*"), reverse=True):
            candidates.append(d / "bin" / "python-qgis.bat")
    for c in candidates:
        if c.is_file():
            return c
    return None


# --- PNG 预览 --------------------------------------------------------------

def _render_png(spec: ArtifactSpec, raster: Path, grid: Grid, job: Job) -> Path:
    """
    栅格 → 带地理参考的 PNG。

    ⚠️ 不用 matplotlib。实测在本环境里 matplotlib 的 savefig() 会**静默段错误**
    （连 `fig, ax = plt.subplots(); ax.plot(); fig.savefig()` 这种最小用例都崩），
    而 PIL 和 GDAL 均正常。根因在 matplotlib 自己的 agg/freetype 扩展，
    本环境有 3 个 zlib DLL 并存（zlib.dll / zlib1.dll / zlib-ng2.dll），
    不去跟 conda 的 DLL 地狱搏斗。

    改法：numpy 自己做拉伸/合成 → GDAL PNG 驱动写出，
    顺带把 geotransform + CRS 嵌进去，QGIS 能就地打开。
    """
    import numpy as np
    import rioxarray

    out = _output_path(spec, "deliver", ".png")
    out.parent.mkdir(parents=True, exist_ok=True)

    da = rioxarray.open_rasterio(raster, masked=True)
    render = spec.render
    want = list(render.bands) if render and render.bands else []

    # 波段名 → 数组下标
    names = list(spec.bands) or [f"b{i}" for i in range(1, da.sizes["band"] + 1)]
    pos = {n: i for i, n in enumerate(names)}
    picks = [pos[b] for b in want if b in pos][:3]

    if len(picks) >= 3:
        channels = [_stretch(da.isel(band=i).values, render) for i in picks]
        rgb8 = (np.stack(channels, axis=-1) * 255.0).astype("uint8")
    else:
        data = _stretch(da.isel(band=(picks[0] if picks else 0)).values, render)
        rgb8 = (_apply_colormap(data) * 255.0).astype("uint8")

    _write_geopng(out, rgb8, grid, spec)
    job.progress("渲染预览图", 92, f"{out.name} ({out.stat().st_size/1024:.0f} KB)")
    return out


def _write_geopng(path: Path, rgb8: "np.ndarray", grid: Grid, spec: ArtifactSpec) -> None:
    """用 GDAL 写 PNG，并把 geotransform + CRS 嵌进去。"""
    from osgeo import gdal, osr

    h, w = rgb8.shape[0], rgb8.shape[1]
    drv = gdal.GetDriverByName("MEM")
    ds = drv.Create("", w, h, 3, gdal.GDT_Byte)
    for i in range(3):
        ds.GetRasterBand(i + 1).WriteArray(rgb8[:, :, i])
    ds.SetGeoTransform(grid.transform_gdal)
    srs = osr.SpatialReference()
    try:
        srs.ImportFromEPSG(int(grid.crs.split(":")[-1]))
    except Exception:
        srs.SetFromUserInput(grid.crs)
    ds.SetProjection(srs.ExportToWkt())

    tmp = str(path.with_suffix(".png.part"))
    png = gdal.GetDriverByName("PNG").CreateCopy(tmp, ds)
    png = None
    ds = None
    # GDAL 会把地理参考写进旁挂的 <name>.aux.xml。
    # 只重命名 .part 会留下孤儿 aux —— 连带把 aux 也搬过去。
    tmp_path = Path(tmp)
    tmp_aux = tmp_path.with_name(tmp_path.name + ".aux.xml")
    tmp_path.replace(path)
    if tmp_aux.exists():
        tmp_aux.replace(path.with_name(path.name + ".aux.xml"))


def _apply_colormap(data: "np.ndarray") -> "np.ndarray":
    """单波段 → RGB。用一个固定色带，不依赖 matplotlib。"""
    import numpy as np

    # viridis 的 8 个采样点，足够平滑
    stops = np.array([
        [0.267, 0.005, 0.329], [0.283, 0.141, 0.458], [0.254, 0.265, 0.530],
        [0.207, 0.372, 0.553], [0.164, 0.471, 0.558], [0.128, 0.567, 0.551],
        [0.135, 0.659, 0.518], [0.267, 0.749, 0.441], [0.478, 0.821, 0.318],
        [0.741, 0.873, 0.150], [0.993, 0.906, 0.144],
    ])
    idx = np.clip(data, 0, 1) * (len(stops) - 1)
    lo = np.floor(idx).astype(int)
    hi = np.clip(lo + 1, 0, len(stops) - 1)
    t = (idx - lo)[..., None]
    return stops[lo] * (1 - t) + stops[hi] * t


def _stretch(arr, render) -> "np.ndarray":
    """把原始 DN 拉到 0-1。策略跟着 RenderSpec 走。"""
    import numpy as np
    a = arr.astype("float32")
    finite = np.isfinite(a)
    if not finite.any():
        return np.zeros_like(a)

    mode = (render.stretch if render else "stddev") or "stddev"
    vmin = render.vmin if render else None
    vmax = render.vmax if render else None

    if vmin is None or vmax is None:
        vals = a[finite]
        if mode == "minmax":
            lo, hi = float(vals.min()), float(vals.max())
        elif mode == "percentile":
            p = (render.percentile if render and render.percentile else (2.0, 98.0))
            lo, hi = (float(v) for v in np.percentile(vals, p))
        else:  # stddev
            m, s = float(vals.mean()), float(vals.std())
            lo, hi = m - 2 * s, m + 2 * s
            lo = max(lo, float(vals.min()))
            hi = min(hi, float(vals.max()))
        vmin = vmin if vmin is not None else lo
        vmax = vmax if vmax is not None else hi

    if not (vmax > vmin):
        return np.zeros_like(a)
    return np.clip((a - vmin) / (vmax - vmin), 0, 1)


# ---------------------------------------------------------------------------
# 已知差异：文件出口的 int32 量化
# ---------------------------------------------------------------------------
#
# 实测结论（2026-10，EE 1.7.46）：
#
#   GEE 的 getDownloadURL(format='GEO_TIFF') **总是写 Int32**，
#   即使 ee.Image 的 bandTypes 已经是 float（已验证：toFloat() 后
#   bandTypes 报 'precision': 'float'，下载回来仍是 Int32 + nodata=-2147483648）。
#
#   而 xee 走 computePixels，保留 float32。
#
#   结果：同一个 spec，
#       exit='file'  → 881.0  （Int32，小数被截）
#       exit='array' → 881.5  （float32，保留）
#   差异恒为 0.5（int32 取整），出现在约 4% 的像素上。
#
# 影响评估：
#   Sentinel-2 反射率量纲 0–10000，0.5 相当于 5e-5 相对误差。
#   对分类、指数计算、统计无实质影响；但对要求逐位一致的回归测试有影响。
#
# 因此对齐判据用**容差**而不是逐位相等：
#
#   ALIGN_TOLERANCE = 0.5     # 文件出口的 int32 量化步长
#
# 若要逐位一致，可选路线（未实现）：
#   1. format='NPY' —— 保留浮点，但丢失地理参考，需另写 .pgw + .prj
#   2. Export.image.toCloudStorage —— 服务端任务，尊重波段类型，但异步且要 GCS
#   3. 文件出口后处理：下载后用 rasterio 重写为 float32 —— 治标，
#      因为精度已经在 GEE 侧丢了

ALIGN_TOLERANCE = 0.5


def compare_exits(spec: ArtifactSpec) -> dict:
    """
    对同一个 spec 的三个出口产物做逐像素比对，返回对齐报告。

    file ↔ array 用 ALIGN_TOLERANCE；map 比的是范围（它复用 file 的数据，
    所以不需要再比像素）。
    """
    import numpy as np

    b = spec.fingerprint()[:8]
    tif = _output_path(spec, "derived", ".tif")
    nc = _output_path(spec, "derived", ".nc")
    report: dict = {"tolerance": ALIGN_TOLERANCE, "fingerprint": spec.fingerprint()}

    if not (tif.is_file() and nc.is_file()):
        report["ok"] = False
        report["reason"] = f"缺少产物：tif={tif.is_file()} nc={nc.is_file()}。先跑两个出口。"
        return report

    import rioxarray
    import xarray as xr

    rt = rioxarray.open_rasterio(tif, masked=True).squeeze()
    ds = xr.open_dataset(nc).squeeze()

    per_band = {}
    worst = 0.0
    mask_ok = True
    for i, name in enumerate(spec.bands):
        if i >= rt.sizes.get("band", 0) or name not in ds:
            continue
        a = np.ma.filled(rt.isel(band=i).values.astype("float64"), np.nan)
        c = np.asarray(ds[name].values, dtype="float64")
        if a.shape != c.shape:
            per_band[name] = {"shape_mismatch": [list(a.shape), list(c.shape)]}
            mask_ok = False
            continue
        ma, mc = np.isfinite(a), np.isfinite(c)
        same_mask = bool((ma == mc).all())
        mask_ok &= same_mask
        d = np.abs(a[ma] - c[ma]) if ma.any() else np.array([0.0])
        mx = float(d.max()) if d.size else 0.0
        worst = max(worst, mx)
        per_band[name] = {
            "shape": list(a.shape),
            "mask_match": same_mask,
            "n_valid": int(ma.sum()),
            "n_diff": int((d > 0).sum()),
            "max_abs_diff": mx,
        }

    report["bands"] = per_band
    report["max_abs_diff"] = worst
    report["mask_match"] = mask_ok
    report["within_tolerance"] = bool(mask_ok and worst <= ALIGN_TOLERANCE)
    report["ok"] = report["within_tolerance"]
    if not report["ok"]:
        report["reason"] = (
            f"最大差 {worst} 超过容差 {ALIGN_TOLERANCE}；掩膜一致={mask_ok}。\n"
            "  若超出容差，说明不是已知的 int32 量化，需要排查网格或波段选取。"
        )
    return report


# ---------------------------------------------------------------------------
# 显示用 8bit RGB GeoTIFF
# ---------------------------------------------------------------------------
#
# 为什么不把拉伸交给 QGIS：
#   试过三条路都不行 ——
#     1. 手搓 QgsContrastEnhancement（算法与手动 setMin/Max 混用）→ 彩色噪点
#     2. UserDefinedEnhancement + 显式 2/98 分位 → 整幅白图
#     3. QgsRasterMinMaxOrigin(CumulativeCut) → 工程文件里 minMaxOrigin
#        序列化完全正确，但 QGIS 渲染仍是噪点（怀疑 Estimated 统计采样
#        把 nodata=-2147483648 算进了区间）
#
#   结论：拉伸是我们的业务逻辑，不该外包给 QGIS 的统计机制去猜。
#   烘焙进像素 → QGIS 零解释 → 所见即所得。
#
# 副产品：这其实是更正确的分层 ——
#   derived/*.tif   浮点，分析用（16/32 位精度，可做算术）
#   deliver/*.tif   8 位 RGB，显示用（拉伸已定，任何软件打开都一样）

VISUAL_SUFFIX = ".rgb8.tif"
_VISUAL_TAG = "geocode:visual-rgb8"


def write_visual_rgb(spec: ArtifactSpec, raster: Path, grid: Grid) -> Path:
    """
    按 RenderSpec 把浮点栅格烘焙成 8 位 RGB GeoTIFF。
    与 _render_png 用**完全同一套**拉伸逻辑，所以图与文件必然一致。
    """
    import numpy as np
    import rioxarray
    from osgeo import gdal, osr

    src = rioxarray.open_rasterio(raster, masked=True)
    render = spec.render
    want = list(render.bands) if render and render.bands else []

    names = list(spec.bands) or [f"b{i}" for i in range(1, src.sizes["band"] + 1)]
    pos = {n: i for i, n in enumerate(names)}
    picks = [pos[b] for b in want if b in pos][:3]

    if len(picks) >= 3:
        ch = [_stretch(src.isel(band=i).values, render) for i in picks]
        rgb8 = (np.stack(ch, axis=-1) * 255.0).astype("uint8")
    else:
        d = _stretch(src.isel(band=(picks[0] if picks else 0)).values, render)
        rgb8 = (_apply_colormap(d) * 255.0).astype("uint8")

    out = _output_path(spec, "deliver", VISUAL_SUFFIX)
    out.parent.mkdir(parents=True, exist_ok=True)

    # 用 rasterio + Affine 写，而不是手工拼 GDAL 的 6 元组 ——
    # 手拼元组实测会被 GDAL 错位解释（bounds 变 (10,-8600,3.45e8,3.47e9)，像素大小 0）。
    # Affine 的字段名是显式的，不会错位。
    import rasterio
    from rasterio.transform import Affine

    transform = Affine(grid.scale, 0.0, grid.xmin, 0.0, -grid.scale, grid.ymax)
    tmp = out.with_suffix(out.suffix + ".part")
    try:
        with rasterio.open(
            tmp, "w", driver="GTiff",
            width=grid.width, height=grid.height, count=3, dtype="uint8",
            crs=grid.crs, transform=transform, nodata=None,
            photometric="RGB", tiled=True, blockxsize=256, blockysize=256,
            compress="deflate",
        ) as dst:
            for i in range(3):
                dst.write(rgb8[:, :, i], i + 1)
            dst.update_tags(src=_VISUAL_TAG, stretch=(render.stretch if render else "stddev"))
        try:
            tmp.replace(out)
        except PermissionError as e:
            raise RuntimeError(
                f"无法写入 {out.name} —— 文件被其他程序占用。\n"
                f"  报错：{e}\n"
                "  最常见原因：这个产物正在 QGIS / ArcGIS Pro 里打开着。\n"
                "  Windows 不允许覆盖被打开的文件。\n"
                "  处理：关闭打开该栅格的窗口（或直接关掉 QGIS / ArcGIS Pro），再重跑。"
            ) from e
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return out
