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
import math
import os
import time
import urllib.request
from pathlib import Path
from typing import TYPE_CHECKING

from . import container as _container
from . import export_chunks as _chunks
from . import geoenv
from . import qgis_bridge as _qb
from .grid import Grid, compute_grid
from .jobs import Job
from .spec import ArtifactSpec, SpecError, time_periods

if TYPE_CHECKING:  # 仅用于注解；运行时仍是各函数内的惰性导入
    import numpy as np
    import xarray as xr

# getDownloadURL 单次请求的像素上限（经验值）
MAX_DIRECT_PIXELS = 64_000_000

# getDownloadURL 单次请求的**字节**上限（GEE 硬限）。实测报错原文：
#   "Total request size (91916930 bytes) must be less than or equal to 50331648 bytes"
# 每像素每波段按 float32(4B) + mask(1B) = 5B 计：实测 18,383,386 px × 5B = 91,916,930B，
# 与 GEE 报的数字逐字节吻合。像素守卫（64M）管不到这个维度 —— 泰安市 30m DEM 只有
# 18.4M 像素轻松过闸，下载时照样被 48MB 拍死（2026-10-11 真实数据运行实测）。
#
# C15：超限不再直接报错 —— 改走**分块下载 + 本地拼接**（gis/export_chunks.py）。
# 像素守卫（MAX_DIRECT_PIXELS）从此是**直写路径**的上限：直写要求
#   像素 ≤ 64M 且 体积 ≤ 48 MiB，任一超限都走分块。
MAX_DOWNLOAD_BYTES = _chunks.MAX_DOWNLOAD_BYTES            # 50,331,648 B = 48 MiB
MAX_DOWNLOAD_BYTES_PER_PIXEL_BAND = _chunks.BYTES_PER_PIXEL_BAND

# 下载重试（C15 A3）：瞬时错误有界退避。总尝试次数与退避序列显式写死，
# 不进 spec / 不进指纹（运行时决策，非产品行为）。
# A1 真数据实测：GEE 在长任务里会连发 RemoteDisconnected / SSL EOF / HTTP 503，
# 3 次尝试不够 —— 提到 5 次、退避拉到 2/5/15/30s。
DOWNLOAD_ATTEMPTS = 5
DOWNLOAD_BACKOFF_SECONDS = (2.0, 5.0, 15.0, 30.0)

# 整片重试（外层）：单请求内重试耗尽后，整个分片再来一轮（重新取 URL + 重下）。
# 进制上界：CHUNK_ATTEMPTS 次整片尝试，耗尽后走 A3 失败文案。
CHUNK_ATTEMPTS = 3
CHUNK_BACKOFF_SECONDS = (10.0, 45.0)

# 本地文件瞬时错误重试（C15 实测：刚写下的栅格可能被 AV / 索引扫描短暂锁住，
# GDAL 报 “Read failed” —— 重试即过）。只包住“回读本地文件”的步骤，
# 不改变任何产物语义；退避渐进（0.5s → 2s）。
LOCAL_IO_ATTEMPTS = 3
LOCAL_IO_DELAYS = (0.5, 2.0)

# 波段参数哨兵：单期路径沿用 spec.bands；时序堆叠路径显式传 None
# （toBands() 后波段名是 期前缀_波段，再传 spec.bands 会 band-not-found）
_SPEC_BANDS = object()

# 容器契约的量纲自证采样窗口（c18）：只读左上角这么多行 —— 1200 万像素 × 3 波段的
# 真彩色产物也不会因为守卫整份入内存（守卫看的是"目标容器装不装得下"，不是全量统计）。
CONTAINER_GUARD_ROWS = 64

# map 出口的渲染引擎
RENDERERS = ("qgis", "arcpy")


# ---------------------------------------------------------------------------
# C6：emit_array 大网格分块（运行时决策，不进 spec / 不进指纹）
#
#   现状（direct）：open_dataset 不传 io_chunks → ds.compute() 一次性拼装全量数组，
#   内存峰值 = 全网格×期×波段×4B，随网格线性涨。
#   分块（chunked）：open_dataset 时传 io_chunks（xee 原生参数，0.1.2 已核实），
#   读取循环 + netCDF4 增量落盘，内存峰值 = 单块驻留（常数）。
#
#   ⚠️ 分块只准在 open_dataset 时进入 —— 事后 .chunk() 实测触发 xee 内部
#   select('*')，被 EE 拒绝（Invalid regular expression，见下方 direct 路径注释）。
# ---------------------------------------------------------------------------

# xee 数组固定 float32（本地驻留 4 B/像素）；GEE computePixels 请求侧按
# (dtype+1) B 计费掩膜字节，单请求上限 48 MiB（README §9.5 / emit_file 实测同限）。
_XEE_DTYPE_BYTES = 4
_GEE_MASK_BYTES = 1
_GEE_REQUEST_BYTE_LIMIT = 48 * 1024 * 1024

# 单块驻留预算（块内全部波段同时驻留的最坏情形）。32 MiB → ≈8.39M 像素/块，
# 请求侧 8.39M × 5B ≈ 41.9 MB < 48 MB 天然满足；plan_chunks 内断言防预算上调越限。
_ARRAY_BLOCK_BUDGET_BYTES = 32 * 1024 * 1024

# 路径选择环境变量（测试钩子）：auto=按阈值；direct/chunked=强制；其他值报可读错误。
# 不进 ArtifactSpec、不进指纹、不进 daemon/TUI 工具面（运行时决策，非产品行为）。
ARRAY_PATH_ENV = "GEOCODE_ARRAY_PATH"


def plan_chunks(
    width: int,
    height: int,
    n_periods: int = 1,
    n_bands: int = 1,
    *,
    budget_bytes: int = _ARRAY_BLOCK_BUDGET_BYTES,
    request_byte_limit: int = _GEE_REQUEST_BYTE_LIMIT,
) -> dict[str, int]:
    """
    计算大网格分块形状（纯函数：无 IO、无全局态，同输入同输出）。

    内存账（xee 数组固定 float32）：
      - 驻留：块像素 × 波段 × 4 B ≤ budget_bytes（块内全部波段同时驻留的最坏情形）；
      - 请求：块像素 × (4+1) B ≤ GEE 单请求上限（掩膜字节计费）。

    形状策略：期维优先装满（一块装下尽量多的整期），剩余预算给空间，空间块方形化；
    块尺寸不要求整除网格（xee 自行处理边缘块）。

    返回 {"index": 期块, "width": x块, "height": y块}，直接作为
    xr.open_dataset(..., engine="ee", io_chunks=...) 的 io_chunks。
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"网格尺寸非法：{width}×{height}")
    t_total = max(1, int(n_periods))
    bands = max(1, int(n_bands))

    # 单块（单波段）像素上限：驻留账与请求账取严
    resident_cap = budget_bytes // (_XEE_DTYPE_BYTES * bands)
    request_cap = request_byte_limit // (_XEE_DTYPE_BYTES + _GEE_MASK_BYTES)
    block_px = min(resident_cap, request_cap)
    if block_px < 1:
        raise ValueError(
            f"块预算过小：budget={budget_bytes}B / 波段 {bands} → 单块像素上限 {block_px}"
        )

    # 期维装满：一块能装几整期；装不下整期就按 1 期切空间
    grid_px = width * height
    t_blk = min(t_total, max(1, block_px // grid_px))
    spatial_px = block_px // t_blk

    # 空间块方形化（空间优先大块），钳制到网格内
    side = math.isqrt(max(spatial_px, 1))
    h_blk = min(height, max(side, 1))
    w_blk = min(width, max(spatial_px // h_blk, 1))

    # 请求侧硬校验（防御预算/形状参数改动越过 GEE 单请求上限）
    req_bytes = t_blk * h_blk * w_blk * (_XEE_DTYPE_BYTES + _GEE_MASK_BYTES)
    if req_bytes > request_byte_limit:
        raise AssertionError(
            f"分块请求侧超限：{t_blk}×{w_blk}×{h_blk} 像素 × "
            f"({_XEE_DTYPE_BYTES}+{_GEE_MASK_BYTES})B = {req_bytes} B "
            f"> GEE 单请求上限 {request_byte_limit} B"
        )
    return {"index": int(t_blk), "width": int(w_blk), "height": int(h_blk)}


def _array_path_mode(spec: ArtifactSpec, grid: Grid, periods) -> str:
    """
    运行时路径选择：est ≥ MAX_DIRECT_PIXELS 走分块，否则现状直读。
    GEOCODE_ARRAY_PATH 可强制 direct/chunked（A5 交叉验证用测试钩子）。
    """
    mode = (os.environ.get(ARRAY_PATH_ENV) or "auto").strip().lower()
    if mode == "auto":
        est = (
            grid.width
            * grid.height
            * (len(periods) if periods else 1)
            * (len(spec.bands) if spec.bands else 1)
        )
        return "chunked" if est >= MAX_DIRECT_PIXELS else "direct"
    if mode in ("direct", "chunked"):
        return mode
    raise ValueError(
        f"环境变量 {ARRAY_PATH_ENV}={mode!r} 不认识。可选：auto / direct / chunked。"
    )


def _open_ee_dataset_lazy(obj, grid: Grid, n_images: int, io_chunks):
    """
    xee 惰性打开（分块路径专用打开纪律，与 direct 路径逐项同参——README §8.2 #6/#7）：
    crs_transform 传 tuple、shape_2d=(width, height)（(x,y) 序）、不做事后 .chunk()。
    io_chunks 在 open_dataset 时传入 —— 这是分块唯一合法入口。
    """
    import warnings

    import xarray as xr

    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message=r"Unable to retrieve 'system:time_start'",
        )
        return xr.open_dataset(
            obj,
            engine="ee",
            crs=grid.crs,
            crs_transform=tuple(grid.transform),   # xee 要 tuple/Affine，list 会 TypeError
            shape_2d=(grid.width, grid.height),    # ← (x, y)，已实测确认
            n_images=n_images,
            io_chunks=io_chunks,                   # None → xee 自动分块（仅请求侧）
            ee_init_if_necessary=False,
        )


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

def _cast_product_container(job: Job, path: Path, spec: ArtifactSpec, *,
                            cache_hit: bool) -> dict | None:
    """
    产物容器归一（c18 容器契约）：把既有产物的容器改成 `spec.container_dtype`。

    - GeoTIFF：就地重写容器（同目录 `.part` + 原子替换）；
    - NetCDF：只读改写（xarray → 临时件 → 原子替换），与 GeoTIFF 同款留痕；
      改写按**有界块**流式写（dask chunked），不为归一引入整份驻留。

    与 C15 的 nodata 归一同一哲学：**缓存命中时就地归一 + 留痕**，不删缓存、不重生成。
    `cache_hit=False`（下载路径）不该走到这里（新写的产物本就按契约落容器），
    真遇到不一致时抛出 —— 不能静默交付与契约不符的产物。
    """
    problems = _container.assert_product_container(path, spec)
    if not problems:
        return None
    want = _container.resolve_container(spec)
    job.progress("既有产物容器不符契约", None, "；".join(problems[:3]))
    assert job.spec is not None
    try:
        if path.suffix.lower() == ".nc":
            info = _rewrite_ncdf_container(path, want)
        else:
            info = _container.rewrite_geotiff_container(path, want)
    except Exception as e:                       # noqa: BLE001 — 归一失败不该挡住复用
        if cache_hit:
            # 1 GB 级的既有产物上，归一可能因为磁盘空间/权限失败 —— 复用不该因此被挡住，
            # 但必须留痕（进度 + 警告），不能静默交付与契约不符的产物。
            job.progress("既有产物容器归一失败", None,
                         f"{path.name}: {type(e).__name__}: {str(e)[:120]}")
            import warnings

            warnings.warn(
                f"既有产物容器归一失败（复用继续，容器仍为 {problems[0]}）："
                f"{path.name}: {type(e).__name__}: {str(e)[:160]}",
                RuntimeWarning, stacklevel=2,
            )
            return None
        raise
    return info


def _rewrite_ncdf_container(path: Path, container: str) -> dict:
    """把 NetCDF 的数据变量容器改成 `container`（streaming 逐变量 copy + 原子替换）。"""
    import xarray as xr

    path = Path(path)
    tmp = path.with_suffix(path.suffix + ".part")
    before: dict[str, str] = {}
    try:
        with xr.open_dataset(path, chunks={}) as ds:
            before = {name: str(var.dtype) for name, var in ds.data_vars.items()}
            out = ds.copy()
            for name in list(out.data_vars):
                out[name] = out[name].astype(container)
            # chunks={} 让 dask 按单变量块流式写：归一不引入整份驻留（2 GB 的
            # 真彩色 10m 产物也走这条；与 c15 的 .part + 原子替换同款发布语义）。
            out.to_netcdf(tmp)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return {"changed": True, "kind": "nc", "from": before, "to": container}


def _apply_container_to_geotiff(job: Job, path: Path, spec: ArtifactSpec) -> dict | None:
    """
    下载/合并后的 GeoTIFF 按契约落容器（c18 容器契约）。

    写盘前先做一次**量纲自证**（有界采样）：容器装不下这份数据就当场报错，
    不留下一份被静默量化/截断的产物。容器一致时短路（不重写）。
    """
    want = _container.resolve_container(spec)
    _container.guard_container_capacity(
        _container.read_bounded_sample(path, block_rows=int(CONTAINER_GUARD_ROWS)),
        want, context=f"{path.name}:",
    )
    info = _container.rewrite_geotiff_container(path, want)
    if info.get("changed"):
        job.progress("容器契约落盘", 94,
                     f"{path.name}: 容器 {info.get('from')} → {want}")
    return info


def _normalize_nodata(job: Job, path: Path, *, cache_hit: bool = False,
                      spec: ArtifactSpec | None = None) -> dict | None:
    """
    nodata 归一 → NaN（C15 A4），带**本地瞬时错误重试**；随后按契约归容器（c18）。

    刚写下的栅格可能被 AV / 索引扫描短暂锁住（GDAL “Read failed”，实测 2/6 次）；
    `cache_hit=True`（复用既有产物）时最终失败只报进度、不抛 —— 归一失败不该挡住复用；
    下载路径（`cache_hit=False`）则抛出 —— 不能静默留下非 NaN 语义的产物。

    `spec` 给了就顺带做**容器归一**（c18）：既有产物容器与契约不符时就地改写并留痕 ——
    指纹分不出"float64 的旧缓存"与"float32 的新产物"（容器不进指纹），这条是显式处置。
    """
    last: Exception | None = None
    for i in range(max(1, LOCAL_IO_ATTEMPTS)):
        try:
            info = _chunks.normalize_nodata_to_nan(path)
            if spec is not None:
                cinfo = _cast_product_container(job, path, spec, cache_hit=cache_hit)
                if cinfo and cinfo.get("changed"):
                    job.progress("既有产物容器归一", None,
                                 f"{path.name}: 容器 {cinfo.get('from')} → "
                                 f"{cinfo.get('to')}（按 container_dtype 契约）")
            return info
        except Exception as e:                 # noqa: BLE001 — 瞬时锁 / GDAL 读错误
            last = e
            if i + 1 < max(1, LOCAL_IO_ATTEMPTS):
                delay = LOCAL_IO_DELAYS[min(i, len(LOCAL_IO_DELAYS) - 1)]
                job.progress("重试", None,
                             f"本地回读 {path.name} 失败（{type(e).__name__}: {str(e)[:80]}），"
                             f"{delay}s 后重试")
                time.sleep(delay)
    if cache_hit:
        job.progress("既有产物 nodata 归一失败", None,
                     f"{path.name}: {type(last).__name__}: {str(last)[:120]}")
        return None
    assert last is not None
    raise last


def _reuse_cached_raster(job: Job, path: Path) -> None:
    """
    复用既有栅格前的 C15 A4 检查：nodata 语义必须是 NaN；并按 c18 容器契约归容器。

    历史产物是 GEE 原始下载，nodata 为 `-inf`（float32）/ `0.0`（float64）/
    整数哨兵；直接复用会让同一 spec 的 GeoTIFF 与 NetCDF 掩膜语义分歧
    （A4 要求两边都是 NaN、masked read 一致）。这里就地把既有产物归一
    （同目录 .part + 原子替换）—— 失败只报进度、不挡住复用。
    """
    info = _normalize_nodata(job, path, cache_hit=True, spec=job.spec)
    if info and info.get("changed"):
        job.progress("既有产物 nodata 归一", None,
                     f"{path.name}: nodata {info.get('nodata')} → NaN（{info.get('dtype')}）")


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
        _reuse_cached_raster(job, out)
        job.progress("复用已有栅格", 25, f"{out.name} ({out.stat().st_size/1024/1024:.1f} MB)")
        return out, grid
    return _download_to(job, out, grid), grid


def _output_path(spec: ArtifactSpec, kind: str, ext: str) -> Path:
    return geoenv.data_path(kind, f"{spec.slug}.{spec.fingerprint()[:8]}{ext}")


def _record_cache_current(job: Job, spec: ArtifactSpec) -> None:
    """
    C15 A6：把「slug → 当代指纹」记进产物根的缓存索引（.cache-index.json）。

    `scripts/prune_cache.py` 靠它区分当代 / 历史指纹。写入失败只报进度、
    不抛出 —— 索引是维护性元数据，绝不能因为写不进去就毁掉一次成功的产物。
    """
    try:
        from . import cache_manage
        cache_manage.record_current(
            geoenv.data_path("derived"), spec.slug, spec.fingerprint(),
        )
    except Exception as e:                     # noqa: BLE001 — 见 docstring
        job.progress("缓存索引写入失败", None, f"{type(e).__name__}: {str(e)[:120]}")


# ---------------------------------------------------------------------------
# 出口 C：文件
# ---------------------------------------------------------------------------

def emit_file(job: Job) -> dict:
    spec = job.spec
    assert spec is not None
    grid = compute_grid(spec)

    # --- 时序模式：期×波段堆叠 GeoTIFF（C3）---
    if spec.is_timeseries:
        out = _output_path(spec, "derived", ".tif")
        if out.exists() and out.stat().st_size > 4096:
            _reuse_cached_raster(job, out)
            job.progress("已存在，跳过下载", 90, out.name)
        else:
            _download_stack_to(job, out, grid)

        periods = time_periods(spec)
        info = _describe_raster(out)
        ok, problems = grid.matches(
            crs=info.get("crs"), bounds=tuple(info.get("bounds") or (0, 0, 0, 0)),
            shape=(info.get("height") or 0, info.get("width") or 0),
        )
        # 期×波段 数目对不上说明期集合与下载产物脱节，必须报出来
        expected_bands = len(periods) * len(spec.bands) if spec.bands else None
        if expected_bands and info.get("bands") != expected_bands:
            ok = False
            problems = list(problems) + [
                f"波段数 {info.get('bands')} != 期数×波段 {expected_bands} "
                f"（{len(periods)} 期 × {len(spec.bands)} 波段）"
            ]

        job.artifacts.append(str(out))
        size_mb = out.stat().st_size / 1024 / 1024
        job.progress("完成", 100, f"{out.name} ({size_mb:.1f} MB, {len(periods)} 期堆叠)")
        _record_cache_current(job, spec)

        return {
            "exit": "file",
            "path": str(out),
            "size_mb": round(size_mb, 2),
            "spec_fingerprint": spec.fingerprint(),
            "grid": grid.to_dict(),
            "grid_aligned": ok,
            "grid_problems": problems,
            "raster": info,
            "timeseries": {
                "n_periods": len(periods),
                "periods": [list(p) for p in periods],
                "band_layout": f"{len(periods)} 期 × {len(spec.bands)} 波段，"
                               "第 i 期波段区间 = [i*B, (i+1)*B)，波段名 = 期起点YYYYMMDD_波段",
            },
        }

    out = _output_path(spec, "derived", ".tif")
    if out.exists() and out.stat().st_size > 4096:
        _reuse_cached_raster(job, out)
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
    _record_cache_current(job, spec)

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


def _download_to(
    job: Job,
    out_path: Path,
    grid: Grid,
    *,
    img=None,
    pixels: int | None = None,
    bands=_SPEC_BANDS,
) -> Path:
    """
    单期 getDownloadURL 直下（保持旧行为）。时序堆叠请走 _download_stack_to。
    """
    from . import source

    spec = job.spec
    assert spec is not None

    if img is None:
        job.progress("构建计算图", 5, f"{spec.asset} → ee.Image")
        img = source.build_image(spec)
    out = _fetch_tif(job, out_path, grid, spec, img, pixels=pixels, bands=bands)
    job.progress("落盘完成", 92, f"{out_path.name} ({out_path.stat().st_size/1024/1024:.1f} MB)")
    return out


class ChunkAlignmentError(RuntimeError):
    """分块返回的栅格与目标网格不对齐（错位/覆盖不足）—— 绝不凑合拼。"""


def _retry(fn, *, job: Job, label: str, attempts: int | None = None, backoff=None):
    """
    有界退避重试（C15 A3）：只对瞬时错误重试，确定性错误立刻抛。

    返回 `(结果, 重试次数)`。最终失败时把尝试次数/重试次数挂在异常的
    `geocode_attempts` / `geocode_retries` 上，供分块失败文案统计。
    """
    n = max(1, int(DOWNLOAD_ATTEMPTS if attempts is None else attempts))
    waits = DOWNLOAD_BACKOFF_SECONDS if backoff is None else tuple(backoff)
    for i in range(n):
        if i:
            job.check_cancelled()
        try:
            return fn(), i
        except BaseException as e:             # noqa: BLE001 — 分类后原样重抛
            if i + 1 >= n or not _chunks.is_retryable_error(e):
                for attr, val in (("geocode_attempts", i + 1), ("geocode_retries", i)):
                    try:
                        setattr(e, attr, val)
                    except Exception:
                        pass
                raise
            wait = float(waits[min(i, len(waits) - 1)]) if waits else 0.0
            job.progress(
                "重试", None,
                f"{label}：第 {i + 1}/{n} 次尝试失败"
                f"（{type(e).__name__}: {str(e)[:100]}），{wait:.1f}s 后重试",
            )
            if wait > 0:
                time.sleep(wait)
    raise AssertionError("unreachable")           # pragma: no cover


def _region_4326(grid: Grid, window: dict, to_ll) -> dict:
    """
    像素窗口 → EPSG:4326 的**加密多边形** region（getDownloadURL 的 region 参数）。

    为什么不用 bbox（C15 实测）：投影坐标下的矩形在 4326 里是曲边，
    取它的 bbox 再交给 GEE 反投影回来，得到的 UTM bbox 会比目标窗口大
    1–4%（实测 17680×103 的整行片 → GEE 网格是该窗口的 1.9 倍，直径 95 MB 直接撞上限）。
    加密多边形（每边 16 段）把反投影误差压到亚米级，GEE 网格 = 窗口 + 1 px/边。

    这是坐标变换，不是采样重采 —— 像素值仍然逐像元对齐（A2 实测 max|diff| = 0）。
    """
    x0, y0, x1, y1 = _chunks.window_bounds(grid, window)
    pad = _chunks.CHUNK_MARGIN_PIXELS * grid.scale
    x0, y0, x1, y1 = x0 - pad, y0 - pad, x1 + pad, y1 + pad
    n = 16
    ring: list[tuple[float, float]] = []
    for k in range(n):                                  # 南边（西→东）
        ring.append(to_ll.transform(x0 + (x1 - x0) * k / n, y0))
    for k in range(n):                                  # 东边（南→北）
        ring.append(to_ll.transform(x1, y0 + (y1 - y0) * k / n))
    for k in range(n):                                  # 北边（东→西）
        ring.append(to_ll.transform(x1 - (x1 - x0) * k / n, y1))
    for k in range(n):                                  # 西边（北→南）
        ring.append(to_ll.transform(x0, y1 - (y1 - y0) * k / n))
    ring.append(ring[0])                                # 闭合环
    return {
        "type": "Polygon",
        "coordinates": [[[float(lon), float(lat)] for lon, lat in ring]],
    }


def _image_band_names(img) -> list[str]:
    """影像的显式波段名（掩膜带必须按名字附加；一次 EE 往返）。"""
    return [str(n) for n in (img.bandNames().getInfo() or [])]


def _request_bytes_per_band(img, bands) -> int:
    """
    单请求计费：值波段（输出 dtype + 1 B mask）+ 逐波段 byte 掩膜带（1 B + 1 B mask）。

    C15 A1 追加：下载请求现在同时带掩膜带（见 export_chunks.MASK_BAND_BYTES_PER_BAND），
    分块预算必须把它算进去 —— 否则分片会超 GEE 的 48 MiB 上限（实测直接 400）。
    """
    return _image_bytes_per_band(img, bands) + _chunks.MASK_BAND_BYTES_PER_BAND


def _resolve_bands(spec: ArtifactSpec, bands) -> list[str] | None:
    """把 bands 参数（含 `_SPEC_BANDS` 哨兵）解析成实际要请求的波段列表 / None。

    band_expr 之后影像只剩表达式产出的波段，不能再按 spec.bands 去要
    （否则报 `Image has no band named ...`）→ 返回 None（不传 bands）。
    """
    if bands is _SPEC_BANDS:
        return None if spec.band_expr else (list(spec.bands) or None)
    return list(bands) if bands else None


def _image_bytes_per_band(img, bands: list[str] | None = None) -> int:
    """
    GEE 单请求的计费口径：**输出波段精度字节 + 1 B mask**。

    实测（2026-10-11，C15 真数据）：
      - float32 单波段 DEM：5 B/px（1,803×1,112 与 18,383,386 px 两处逐字节吻合）
      - double  单波段 NDVI：8.996 B/px；double 三波段真彩色：26.98 B/px

    所以**不能按 spec.dtype 猜**：真彩色 spec 写 `uint16`，GEE 实际输出 double
    （14.1 MB 的 float32 估算 → 实际被要求 54.1 MB，第一片就拒）。
    查不到精度时按最坏（double = 9 B）算：分片偏小只多几次请求，不会失败。
    """
    try:
        info = img.bandTypes().getInfo() or {}
    except Exception:                      # noqa: BLE001 — 查不到就按最坏算
        return _chunks.BYTES_PER_PIXEL_BAND_UNKNOWN
    want = set(bands) if bands else None
    costs = [
        _chunks.bytes_per_pixel_band((meta or {}).get("precision"))
        for name, meta in info.items()
        if want is None or name in want
    ]
    return max(costs) if costs else _chunks.BYTES_PER_PIXEL_BAND_UNKNOWN


def _chunk_failure(
    index: int, total: int, window: dict, n_bands: int, chunk_est: int,
    est_total: int, limit: int, err: BaseException, spec: ArtifactSpec,
) -> RuntimeError:
    """A3 失败文案：片号/片数、估算体积、上限、已重试次数 + 四条出路。"""
    attempts = int(getattr(err, "geocode_attempts", DOWNLOAD_ATTEMPTS))
    retries = int(getattr(err, "geocode_retries", 0))
    return RuntimeError(
        f"分块下载失败：第 {index}/{total} 片"
        f"（窗口 {window['width']}×{window['height']} @ 像素 "
        f"({window['x']},{window['y']})，{n_bands} 波段，单片估算 "
        f"{chunk_est/1048576:.1f} MB；整幅估算 {est_total/1048576:.0f} MB，"
        f"单请求上限 {limit/1048576:.0f} MB）；已重试 {retries} 次"
        f"（共 {attempts} 次尝试）仍失败：{type(err).__name__}: {err}\n"
        f"  已清理分片临时文件与半成品，不留 .part。\n"
        f"  出路（按省事排序）：\n"
        f"    1. 放大 scale（当前 {spec.scale}m；放大一倍，体积降到 1/4）\n"
        f"    2. 缩小 AOI\n"
        f"    3. 该出口改用 array（emit_array 走 xee computePixels，无此上限）\n"
        f"    4. 批处理导出 Export.image.toDrive（异步任务，未接）"
    )


def _fetch_chunk_with_retry(
    job: Job, tile: Path, grid: Grid, spec: ArtifactSpec, img, win: dict,
    *, bands, bpp: int, limit: int, index: int, total: int,
    chunk_est: int, est_total: int, attempts: int | None, backoff, to_ll,
) -> None:
    """
    单片取数（外层整片重试）：`_fetch_tif` 单请求内已有重试；这里再包一层整片重试
    （重新取 URL + 重下），只为扛住 GEE 长任务里的连发 503/SSL EOF（A1 实测）。
    确定性错误不重试；耗尽后原样抛出，由调用方包成 A3 失败文案。
    """
    for chunk_try in range(1, max(1, CHUNK_ATTEMPTS) + 1):
        try:
            _fetch_tif(
                job, tile, grid, spec, img,
                pixels=win["width"] * win["height"], bands=bands,
                region_override=_region_4326(grid, win, to_ll),
                max_bytes=limit, bytes_per_band=bpp,
                attempts=attempts, backoff=backoff,
            )
            return
        except Exception as e:                  # noqa: BLE001 — 分类后决定
            if chunk_try >= max(1, CHUNK_ATTEMPTS) or not _chunks.is_retryable_error(e):
                raise
            delay = CHUNK_BACKOFF_SECONDS[min(chunk_try - 1, len(CHUNK_BACKOFF_SECONDS) - 1)]
            job.progress(
                "重试", None,
                f"第 {index}/{total} 片整体重试（{type(e).__name__}: {str(e)[:80]}），"
                f"{delay:.0f}s 后重来（单片估算 {chunk_est/1048576:.1f} MB / 上限 "
                f"{limit/1048576:.0f} MB，整幅 {est_total/1048576:.0f} MB）",
            )
            time.sleep(delay)


def _to_ll(grid: Grid):
    """网格 CRS → EPSG:4326 的变换器（region 必须是经纬度几何）。"""
    from pyproj import CRS, Transformer

    return Transformer.from_crs(
        CRS.from_user_input(grid.crs), CRS.from_epsg(4326), always_xy=True,
    )


def _download_chunked(
    job: Job,
    out_path: Path,
    grid: Grid,
    spec: ArtifactSpec,
    img,
    *,
    bands=_SPEC_BANDS,
    bytes_per_band: int | None = None,
    attempts: int | None = None,
    backoff=None,
) -> Path:
    """
    C15 分块下载：目标网格切窗口 → 逐片 getDownloadURL → 本地按**目标网格**拼接。

    落盘纪律：整幅写 `<out>.part`，全部成功才原子 rename —— 中途失败不留半截产物，
    分片临时文件逐片用完即删（长任务不累占临时空间）。

    对齐纪律：每片按 GEE **实际返回的 transform** 定位（允许边界余量），
    错位/覆盖不足立即报 ChunkAlignmentError，不重采样、不猜测
    （红线：不得另建网格）。
    """
    import numpy as np
    import rasterio
    from rasterio.transform import Affine
    from rasterio.windows import Window

    bands = _resolve_bands(spec, bands)
    if bands is None:
        bands = _image_band_names(img)
    n_bands = len(bands)
    bpp = int(bytes_per_band) if bytes_per_band else _request_bytes_per_band(img, bands)

    windows = _chunks.plan_download_chunks(
        grid.width, grid.height, n_bands,
        max_bytes=int(MAX_DOWNLOAD_BYTES), bytes_per_pixel_band=bpp,
    )
    total = len(windows)
    limit = int(MAX_DOWNLOAD_BYTES)
    est_total = grid.width * grid.height * n_bands * bpp
    job.progress(
        "分块下载", 12,
        f"{grid.width}×{grid.height} @ {grid.scale}m → {total} 片"
        f"（{n_bands} 波段 × {bpp} B/像素计费（含掩膜带），估算 {est_total/1048576:.0f} MB"
        f" > 直写上限 {limit/1048576:.0f} MB）",
    )

    to_ll = _to_ll(grid)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    dst_path = out_path.with_suffix(out_path.suffix + ".part")
    tiles: list[Path] = []
    dst = None
    try:
        for i, win in enumerate(windows, 1):
            job.check_cancelled()
            tile = out_path.with_name(f"{out_path.name}.c{i:04d}.part")
            tiles.append(tile)
            chunk_est = _chunks.chunk_request_bytes(win, n_bands, bytes_per_pixel_band=bpp)
            try:
                _fetch_chunk_with_retry(
                    job, tile, grid, spec, img, win, bands=bands, bpp=bpp,
                    limit=limit, index=i, total=total, chunk_est=chunk_est,
                    est_total=est_total, attempts=attempts, backoff=backoff,
                    to_ll=to_ll,
                )
            except Exception as e:              # noqa: BLE001 — 统一成 A3 失败文案
                raise _chunk_failure(
                    i, total, win, n_bands, chunk_est, est_total, limit, e, spec,
                ) from e

            # 本地回读带瞬时错误重试（刚下载的分片可能被 AV/索引短暂锁住）
            for io_attempt in range(1, max(1, LOCAL_IO_ATTEMPTS) + 1):
                try:
                    with rasterio.open(tile) as src:
                        loc = _chunks.locate_actual_window(
                            grid, win, transform=src.transform,
                            size=(src.width, src.height),
                        )
                        if loc is None:
                            raise ChunkAlignmentError(
                                f"分块下载失败：第 {i}/{total} 片返回的栅格与目标网格不对齐 —— "
                                f"实际 {src.width}×{src.height} @ {tuple(src.transform)[:6]}，"
                                f"目标窗口 {win['width']}×{win['height']} @ "
                                f"({win['x']},{win['y']})，网格 {grid.width}×{grid.height} / "
                                f"{grid.scale}m / {grid.crs}。\n"
                                "  这属于 GEE 侧网格吸附异常；不重采样凑合，请重跑或改用 array 出口。"
                            )
                        col0, row0, bw, bh = loc
                        block = src.read(window=Window(col0, row0, bw, bh))
                        if dst is None:
                            dtype = src.dtypes[0]
                            if not np.issubdtype(np.dtype(dtype), np.floating):
                                dtype = "float32"        # NaN 需要浮点容器
                            dst = rasterio.open(
                                dst_path, "w", driver="GTiff",
                                width=grid.width, height=grid.height, count=n_bands,
                                dtype=dtype, crs=grid.crs,
                                transform=Affine(
                                    grid.scale, 0.0, grid.xmin,
                                    0.0, -grid.scale, grid.ymax,
                                ),
                                nodata=float("nan"),
                                tiled=True, blockxsize=256, blockysize=256,
                                compress="deflate",
                            )
                            for k, name in enumerate(src.descriptions or (), start=1):
                                if name and k <= n_bands:
                                    dst.set_band_description(k, name)
                        # C15 A4 + A1 修正：多波段必须用**整文件级**哨兵判据
                        # （单波段判据会把真值恰为 0 的像素误抹，A1 实测 7/165.4M）
                        dst.write(
                            _chunks.coerce_nan_stack(block, src.nodata),
                            window=Window(win["x"], win["y"],
                                          win["width"], win["height"]),
                        )
                    break
                except Exception as e:          # noqa: BLE001 — 本地瞬时读锁
                    if io_attempt >= max(1, LOCAL_IO_ATTEMPTS):
                        raise
                    delay = LOCAL_IO_DELAYS[min(io_attempt - 1, len(LOCAL_IO_DELAYS) - 1)]
                    job.progress(
                        "重试", None,
                        f"第 {i}/{total} 片本地回读失败（{type(e).__name__}: "
                        f"{str(e)[:80]}），{delay}s 后重试",
                    )
                    time.sleep(delay)
            # 用完即删：分片临时文件不随片数累积（否则大网格长任务会攥出 GB 级临时空间）
            tile.unlink(missing_ok=True)
            tile.with_name(tile.name + ".part").unlink(missing_ok=True)
            job.progress(
                "分块下载", 12 + 76 * i // total,
                f"片 {i}/{total}（{win['width']}×{win['height']}）",
            )

        if dst is None:                            # pragma: no cover — 防御
            raise RuntimeError("分块下载没有产出任何分片（内部错误）")
        dst.close()
        dst = None
        dst_path.replace(out_path)
    except BaseException:
        if dst is not None:
            try:
                dst.close()
            except Exception:
                pass
        dst_path.unlink(missing_ok=True)
        raise
    finally:
        for t in tiles:
            t.unlink(missing_ok=True)
            t.with_name(t.name + ".part").unlink(missing_ok=True)

    job.progress("落盘完成", 92,
                 f"{out_path.name} ({out_path.stat().st_size/1048576:.1f} MB, {total} 片拼接)")
    return out_path


def _fetch_tif(
    job: Job,
    out_path: Path,
    grid: Grid,
    spec: ArtifactSpec,
    img,
    *,
    pixels: int | None = None,
    bands=_SPEC_BANDS,
    region_override: dict | tuple[float, float, float, float] | None = None,
    max_bytes: int | None = None,
    bytes_per_band: int | None = None,
    attempts: int | None = None,
    backoff=None,
) -> Path:
    """
    getDownloadURL 单请求核心：region/params → 下载 → 原子落 out_path。

    ⚠️ region 必须是 **EPSG:4326 经纬度**（红线 5）—— 投影坐标能"work"纯属
    .clip(aoi) footprint 的巧合，加云掩膜后 updateMask 丢了 footprint 才暴露。
    ⚠️ bands 必须是列表（json.dumps 出来会被当成单个波段名）。
    bands 传 _SPEC_BANDS 哨兵 = 沿用 spec.bands；显式 None = 不传（吃全部波段）。

    C15 路径选择：直写要求 **像素 ≤ MAX_DIRECT_PIXELS 且 估算体积 ≤ 48 MiB**；
    任一超限 → `_download_chunked`（分块 + 本地拼接）。分片调用自带
    `region_override`（片窗口）与 `max_bytes`（单片预算），不再递归分块。
    """
    est = pixels if pixels is not None else grid.width * grid.height
    # 波段选择与计费口径（band_expr / bands=None 也要落到**显式波段名**：
    # 掩膜带必须按名字附加，不能再走「不传 bands 吃全部波段」）
    band_sel = _resolve_bands(spec, bands)
    if band_sel is None:
        band_sel = _image_band_names(img)
    n_bands_est = len(band_sel)
    bpp = int(bytes_per_band) if bytes_per_band else _request_bytes_per_band(img, band_sel)
    limit = int(MAX_DOWNLOAD_BYTES if max_bytes is None else max_bytes)
    est_download = est * n_bands_est * bpp

    # --- 路径选择（C15）---------------------------------------------------
    # 直写路径的两道守卫（像素 64M / 字节 48 MiB）都是"直写"的上限：
    # 任一超限 → 分块下载 + 本地拼接（不再直接报错）。
    # ⚠️ 必须先判分块、再判像素守卫 —— 否则 165.4M 像素的真彩色在像素守卫
    #    处就被拒，永远到不了分块路径（A1 验收正是这个规模）。
    if region_override is None and (est > MAX_DIRECT_PIXELS or est_download > limit):
        return _download_chunked(
            job, out_path, grid, spec, img,
            bands=band_sel, bytes_per_band=bpp, attempts=attempts, backoff=backoff,
        )

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

    # 单片字节守卫（分片调用走这里）：体积仍超限 = 分块预算被外部调小
    if est_download > limit:
        raise ValueError(
            f"下载体积估算 {est_download/1048576:.1f} MB 超单请求上限 "
            f"{limit/1048576:.1f} MB"
            f"（{grid.width}×{grid.height} × {n_bands_est} 波段 × {bpp} B/像素（含掩膜带））。\n"
            f"  出路（按省事排序）：\n"
            f"    1. 放大 scale（当前 {spec.scale}m；放大一倍，体积降到 1/4）\n"
            f"    2. 缩小 AOI（按区县切分，产物本地拼接）\n"
            f"    3. 该出口改用 array（emit_array 走 xee computePixels，无此上限）\n"
            f"    4. 批处理导出 Export.image.toDrive（异步任务，未接）"
        )

    job.progress("申请下载链接", 15, f"{grid.width}×{grid.height} @ {grid.scale}m")
    if region_override is not None:
        region = region_override
    else:
        from .spec import aoi_bbox as _aoi_bbox
        region = list(_aoi_bbox(spec.aoi) or ())
    if not region:
        raise ValueError(
            "spec.aoi 为空，无法构造下载 region。\n"
            "  getDownloadURL 需要 EPSG:4326 的 (west, south, east, north)。"
        )
    # C15 A1 追加：值波段 + 逐波段 byte 掩膜带同请求下载（同一趟）。
    # 掩膜带是「真值 0 vs 哨兵 0」的唯一可靠区分来源（单波段 float64 尤其）。
    # ⚠️ 必须 `gt(0).byte()` 而不是 `byte()`：AOI 边界的**半覆盖像素**掩膜是小数
    # （如 0.5），直接转 byte 会截断成 0 而误抹（A4 实测多抹 1215 px）。
    mask_names = [_chunks.mask_band_name(b) for b in band_sel]
    value_sel = img.select(list(band_sel))
    msk = value_sel.mask()
    req_img = value_sel.addBands(msk.gt(0).byte().rename(mask_names))
    params = {
        "name": spec.slug,
        "scale": grid.scale,
        "crs": grid.crs,
        "region": region,                     # 经纬度 bbox
        "format": "GEO_TIFF",
        "filePerBand": False,
        "bands": list(band_sel) + mask_names,
    }
    job.check_cancelled()

    url, n_url_retries = _retry(
        lambda: req_img.getDownloadURL(params), job=job, label="申请下载链接",
        attempts=attempts, backoff=backoff,
    )
    if n_url_retries:
        job.progress("申请下载链接", 15, f"重试 {n_url_retries} 次后成功")

    job.progress("下载中", 30, out_path.name)
    # 临时文件放**目标同目录**：
    #   同卷 rename 原子（跨盘 os.replace 会 WinError 17）
    #   不在 C: 留大文件残留
    #   下游只会看到完整的最终文件
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(out_path.suffix + ".part")
    try:
        _retry(lambda: _download(url, tmp, job), job=job, label="下载",
               attempts=attempts, backoff=backoff)
        job.check_cancelled()
        # C15 A1 追加：用**真实掩膜带**定 NaN 并丢弃掩膜带（比哨兵猜测可靠：
        # 单波段 float64 的哨兵 0.0 与真值 0 在 TIFF 里无法区分）。
        # 在 .part 上做，rename 即“发布”。
        _chunks.collapse_mask_bands(tmp, n_bands_est)
        tmp.replace(out_path)
        # c18 容器契约：新产物按 container_dtype 落容器（写盘后立刻自证；
        # 非法组合由 container.resolve/guard 在写盘前拦下）。
        _apply_container_to_geotiff(job, out_path, spec)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    return out_path


def _download_stack_to(job: Job, out_path: Path, grid: Grid) -> Path:
    """
    时序堆叠下载：逐期 getDownloadURL 拉取 → **本地合并**成单张 N×B 波段
    GeoTIFF（期主序，波段名 = 期起点YYYYMMDD_波段，与单期同名约定兼容）。

    为什么不 toBands() 单请求（2026-10-06 实测）：
        9 波段堆叠的 getDownloadURL 请求 54,613,440 字节 > GEE 的
        50,331,648 字节上限，直接 400。逐期请求与单期同限，稳。
    这是 spec.md Constraints 已授权的等价实现（验收判据不变：单张 N×B、
    期前缀命名、逐期与单期产物对齐 ≤0.5）。
    """
    from . import source

    spec = job.spec
    assert spec is not None
    periods = time_periods(spec)
    n_bands = len(spec.bands) if spec.bands else 1

    # 总量护栏（合并时的内存与请求次数）
    est = grid.width * grid.height * len(periods) * n_bands
    if est > MAX_DIRECT_PIXELS:
        raise ValueError(
            f"时序堆叠太大：{grid.width}×{grid.height} × {len(periods)} 期 × {n_bands} 波段"
            f" = {est/1e6:.1f} 百万像素，上限约 {MAX_DIRECT_PIXELS/1e6:.0f} 百万。\n"
            f"  出路：放大 scale、缩小 AOI、减少期数，或等 C5 批处理导出。"
        )

    job.progress("构建时序计算图", 5, f"{spec.asset} → {len(periods)} 期")
    images = source.build_cube_periods(spec)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_final = out_path.with_suffix(out_path.suffix + ".part")
    period_files: list[Path] = []
    try:
        for i, img_i in enumerate(images):
            pf = out_path.with_name(f"{out_path.stem}.p{i}.tmp.tif")
            job.progress(
                "逐期下载", 10 + 60 * i // max(len(images), 1),
                f"期 {i + 1}/{len(images)}（{periods[i][0]} 起）",
            )
            _fetch_tif(job, pf, grid, spec, img_i)
            period_files.append(pf)

        job.progress("本地合并", 85, f"{len(period_files)} 期 → 单张 {len(periods)}×{n_bands} 波段")
        _merge_stack(period_files, tmp_final, grid, periods, list(spec.bands) or None,
                     container=_container.resolve_container(spec))
        tmp_final.replace(out_path)
    except BaseException:
        tmp_final.unlink(missing_ok=True)
        raise
    finally:
        for pf in period_files:
            pf.unlink(missing_ok=True)
            Path(str(pf) + ".part").unlink(missing_ok=True)

    job.progress("落盘完成", 92, f"{out_path.name} ({out_path.stat().st_size/1024/1024:.1f} MB)")
    return out_path


def _merge_stack(
    period_files: list[Path],
    dst: Path,
    grid: Grid,
    periods: list,
    bands: list[str] | None,
    *,
    container: str | None = None,
) -> None:
    """逐期 GeoTIFF → 单张期主序 N×B GeoTIFF（rasterio + Affine，字段名显式）。

    `container` 给了就用它当落盘容器（c18 容器契约）；缺省沿用首期容器的历史行为。
    """
    import rasterio
    from rasterio.transform import Affine

    n_periods = len(period_files)
    n_bands = len(bands) if bands else 1

    with rasterio.open(period_files[0]) as p0:
        src_dtype = p0.dtypes[0]
        dtype = container or src_dtype
        # C15 A4：期文件已由 _fetch_tif 归一为 NaN；这里强制 NaN，
        # 防止历史期产物残留 -inf / 0 哨兵渗进堆叠产物
        nodata = float("nan")

    descriptions = [
        f"{ps.replace('-', '')}_{bd}"
        for (ps, _pe) in periods
        for bd in (bands or [f"b{i}" for i in range(1, n_bands + 1)])
    ]

    with rasterio.open(
        dst, "w", driver="GTiff",
        width=grid.width, height=grid.height,
        count=n_periods * n_bands, dtype=dtype,
        crs=grid.crs,
        transform=Affine(grid.scale, 0.0, grid.xmin, 0.0, -grid.scale, grid.ymax),
        nodata=nodata,
        tiled=True, blockxsize=256, blockysize=256,
        compress="deflate",
    ) as dst_ds:
        k = 0
        for pf in period_files:
            with rasterio.open(pf) as src:
                if src.height != grid.height or src.width != grid.width:
                    raise RuntimeError(
                        f"期文件 {pf.name} 网格 {src.width}×{src.height} 与 "
                        f"{grid.width}×{grid.height} 不符 —— GEE 未按请求网格返回。"
                    )
                if src.dtypes[0] != src_dtype:
                    raise RuntimeError(
                        f"期文件 {pf.name} dtype {src.dtypes[0]} 与首期 {src_dtype} 不一致 —— "
                        "GEE 逐期返回类型漂移，拒绝合并以免堆叠错位。"
                    )
                for j in range(1, src.count + 1):
                    k += 1
                    block = src.read(j)
                    _container.guard_container_capacity(block, dtype, context=f"{pf.name}:")
                    dst_ds.write(block.astype(dtype, copy=False), k)
                    if k <= len(descriptions):
                        dst_ds.set_band_description(k, descriptions[k - 1])


def _download(url: str, dest: Path, job: Job, *,
              pct_lo: float = 30.0, pct_hi: float = 88.0,
              label: str = "下载中") -> None:
    """单次 HTTP 下载 → dest。进度区间可参数化（分块路径每片一段，不互相抢进度）。"""
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
                    pct = pct_lo + (done / total) * (pct_hi - pct_lo)
                    if int(pct) != last:
                        last = int(pct)
                        job.progress(label, pct, f"{done/1048576:.1f} / {total/1048576:.1f} MB")
                else:
                    job.progress(label, None, f"{done/1048576:.1f} MB")
    # ⚠️ C15 实测（A1 第 71/98 片）：连接提前关闭时 `HTTPResponse.read(amt)` 会**静默返回
    # 空**（不抛 IncompleteRead），于是截断的 GeoTIFF 落到磁盘，直到 GDAL 读它才报
    # “Read failed”—— 而且回读重试对截断文件永远无效。有 Content-Length 就必须核对。
    got = dest.stat().st_size
    if total and got != total:
        from http.client import IncompleteRead
        raise IncompleteRead(bytes(got), total - got)
    if got < 4096:
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

def _write_ncdf_with_container(arr, tmp: Path, spec: ArtifactSpec) -> None:
    """
    把 xarray 数据集按容器契约写成 NetCDF（c18）。

    不用 `arr.to_netcdf` 一把梭，而是先把数据变量 cast 到契约容器再写 ——
    NetCDF4 的自动 dtype 转换在带 `scale_factor` 属性时会把值重新缩放，
    显式 cast 后写可保持"只改容器、不改值"的语义（与 GeoTIFF 侧同款自证）。
    """
    container = _container.resolve_container(spec)
    out = arr.copy()
    for name in list(out.data_vars):
        block = out[name].values
        _container.guard_container_capacity(
            block, container, context=f"{getattr(spec, 'slug', 'spec')}:{name}:",
        )
        out[name] = out[name].astype(container)
    out.to_netcdf(tmp)


def emit_array(job: Job) -> dict:
    """
    xee 把 ee.Image / ee.ImageCollection 变成惰性 xarray，Dask 分块拉像素。

    与 emit_file 共用同一份 grid —— 所以数组和 GeoTIFF 是**同一个网格**，
    可以逐像素做算术。时序 spec 走 source.build_cube() 的期集合，
    输出沿时间维堆栈的 (time, y, x) 立方体。
    """
    import xarray as xr

    spec = job.spec
    assert spec is not None
    grid = compute_grid(spec)

    periods = time_periods(spec) if spec.is_timeseries else None

    out = _output_path(spec, "derived", ".nc")
    out.parent.mkdir(parents=True, exist_ok=True)

    arr: "xr.Dataset | None" = None
    if out.exists() and out.stat().st_size > 4096:
        # 产物缓存：.nc 与 .tif 一样是指纹化的确定性产物（xee computePixels
        # 对同图同参逐位一致），命中即复用 —— 与 _ensure_raster 同一哲学。
        cinfo = _cast_product_container(job, out, spec, cache_hit=True)
        if cinfo and cinfo.get("changed"):
            job.progress("既有产物容器归一", None,
                         f"{out.name}: 容器 {cinfo.get('from')} → {cinfo.get('to')}"
                         "（按 container_dtype 契约）")
        job.progress("复用已有数组产物", 80,
                     f"{out.name} ({out.stat().st_size/1048576:.1f} MB)")
        with xr.open_dataset(out) as _ds:
            arr = _ds.load()
    else:
        # C6 运行时路径选择（阈值 + 测试钩子），不进 spec/指纹
        mode = _array_path_mode(spec, grid, periods)
        tmp = out.with_suffix(out.suffix + ".part")
        try:
            if mode == "chunked":
                _compute_array_chunked_to_ncdf(job, spec, grid, periods, tmp)
                tmp.replace(out)
            else:
                arr = _compute_array_via_xee(job, spec, grid, periods)
                job.progress("落盘", 80, f"NetCDF（容器 {_container.resolve_container(spec)}）")
                _write_ncdf_with_container(arr, tmp, spec)
                tmp.replace(out)
        except BaseException:
            tmp.unlink(missing_ok=True)
            raise

    job.check_cancelled()

    if arr is not None:
        dims = dict(arr.sizes)
        band_vars = list(arr.data_vars)
        sample = _array_sample(arr)
        time_vals = (
            arr["time"].values
            if periods is not None and "time" in arr.coords else None
        )
    else:
        # 分块路径：产物已落盘，元数据惰性读回（只取尺寸/坐标/中心 3×3 样本，
        # 不 load 全量 —— 大网格读回阶段同样内存有界）。复用 _array_sample
        # 本身保证样本语义与 direct 逐位一致。
        with xr.open_dataset(out) as _ds:
            dims = dict(_ds.sizes)
            band_vars = list(_ds.data_vars)
            sample = _array_sample(_ds)
            time_vals = (
                _ds["time"].values
                if periods is not None and "time" in _ds.coords else None
            )

    timeseries_info: dict | None = None
    if periods is not None:
        if "time" not in dims or dims["time"] != len(periods):
            raise RuntimeError(
                f"时序立方体期数不符：期望 {len(periods)} 期，"
                f"实际 time 维 = {dims.get('time')}。\n"
                "  常见原因：某期窗口内没有影像（空期塌缩失败）或波段名不一致。"
            )
        timeseries_info = {
            "n_periods": len(periods),
            "periods": [list(p) for p in periods],
            "time_coords": [
                str(t)[:10] for t in time_vals
            ] if time_vals is not None else None,
        }
        job.progress("期数校验", 90, f"{len(periods)} 期堆叠完成")

    job.artifacts.append(str(out))
    nbytes = out.stat().st_size
    job.progress("完成", 100, f"{out.name} ({nbytes/1048576:.1f} MB)")
    _record_cache_current(job, spec)

    return {
        "exit": "array",
        "path": str(out),
        "size_mb": round(nbytes / 1048576, 2),
        "spec_fingerprint": spec.fingerprint(),
        "grid": grid.to_dict(),
        "dims": dims,
        "vars": band_vars,
        "sample": sample,
        **({"timeseries": timeseries_info} if timeseries_info else {}),
    }


def _compute_array_via_xee(job: Job, spec: ArtifactSpec, grid: Grid, periods) -> "xr.Dataset":
    """构建计算图 → xee 拉像素 → 内存数组（emit_array 的下载路径，无缓存分支）。"""
    import warnings

    import xarray as xr

    from . import source
    ee, _ = geoenv.init_ee()
    ee.Initialize()  # 幂等

    job.progress("构建计算图", 8, f"{spec.asset} → ee.Image")
    n_images = -1
    if spec.is_timeseries:
        obj = source.build_cube(spec)
        n_images = len(periods)   # 期数已知 → 免掉 xee 内部的 collection.size() 慢扫描
        job.progress("构建计算图", 8, f"{spec.asset} → {len(periods)} 期 ee.ImageCollection")
    else:
        obj = source.build_image(spec)
    job.check_cancelled()

    job.progress("打开 xee 数据集", 20, f"{grid.width}×{grid.height} @ {grid.scale}m")
    # xee 需要 dask 才不会在 open_dataset 时就拉全量
    #
    # ⚠️ shape_2d 是 (width, height)，**不是** (height, width)。
    # 传反了不会报错，只会给你一个转置的数组 —— 尺寸对不上时就发现了，
    # 但当网格恰为正方形时（w==h）它会静默地错下去。
    # 已用逐像素比对验证：传 (w,h) 时与 GeoTIFF 完全一致。
    #
    # ⚠️ "Unable to retrieve 'system:time_start'" 是 xee 0.1.2 内部双路径的
    # 良性 UserWarning —— 时间坐标实测正确（emit_array 的期数/坐标断言兜底），
    # 这里定向抑制，避免污染任务日志。
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore", message=r"Unable to retrieve 'system:time_start'",
        )
        ds = xr.open_dataset(
            obj,
            engine="ee",
            crs=grid.crs,
            crs_transform=tuple(grid.transform),   # xee 要 tuple/Affine，list 会 TypeError
            shape_2d=(grid.width, grid.height),    # ← (x, y)，已实测确认
            n_images=n_images,
            ee_init_if_necessary=False,
        )

    job.progress("计算中（分块拉像素）", 35, "这一步可能较慢，取决于范围")
    job.check_cancelled()

    # 不要手动 .chunk() —— 实测它会触发 xee 内部的 select('*')，
    # 而当前 EE API 拒绝 '*' 通配符（Invalid regular expression）。
    # 需要分块时应在 open_dataset 时用 io_chunks/chunks 参数，
    # 而不是事后 .chunk()。此处网格仅 860×784，直接 compute 即可。
    try:
        return ds.compute()
    except Exception as e:
        diag = ""
        if periods is not None:
            # 失败路径才做逐期影像数诊断（成功路径不付元数据扫描的开销）
            try:
                d = source.diagnose_cube(spec)
                empties = [p["period"][0] for p in d["periods"] if p["n_scenes"] == 0]
                diag = (
                    "\n  逐期影像数诊断：" + json.dumps(d["periods"], ensure_ascii=False)
                    + (f"\n  ⚠️ 空期（窗内 0 景）：{empties}" if empties else "")
                )
            except Exception:
                pass
        raise RuntimeError(
            f"xee 拉取失败：{type(e).__name__}: {e}\n"
            f"  范围 {grid.width}×{grid.height}，"
            f"{len(spec.bands) or '?'} 个波段"
            + (f"，{len(periods)} 期。" if periods else ".") + "\n"
            f"  常见原因：\n"
            f"    - 范围太大 → 放大 scale、缩小 AOI，或改用 exit='file' + 本地读取\n"
            f"    - 触发配额（429）→ 减少 DASK_NUM_WORKERS\n"
            f"    - 空期（窗内 0 景）→ 调整期窗口或换数据集{diag}\n"
            f"  注意：xee 是『把像素拉到本地算』，不是『服务端算完只回结果』。"
        ) from e


def _compute_array_chunked_to_ncdf(
    job: Job, spec: ArtifactSpec, grid: Grid, periods, tmp_path: Path,
) -> None:
    """
    C6 大网格分块路径：lazy 打开（io_chunks）→ 期×空间两级块循环
    isel→values→ netCDF4 直写，最后由调用方原子替换。

    内存上界 = 单块驻留（plan_chunks 预算，块内全部波段最坏同时驻留 ≤ 32 MiB）：
    不做 ds.compute()、不整期/全量驻留；每块一检查点（取消响应）。
    计算图构建与 direct 同一 source 函数（红线 1），网格同一 compute_grid（红线 2）。

    产物结构与 direct（arr.to_netcdf）逐项对齐：
      dims (time,y,x)｜float32 波段变量 + xee 原始 attrs｜_FillValue=nan｜
      scale_factor 属性（float32 下惰性：写不缩放读不缩放，实测）｜
      time：datetime64 → xarray CF 编码（encode_cf_datetime 与 to_netcdf 同路径），
      数值型（单期 xee 回退 np.arange）→ 原样 int64 无 units。
    """
    import netCDF4 as nc
    import numpy as np
    from xarray.coding.times import encode_cf_datetime as _encode_cf_datetime

    from . import source
    ee, _ = geoenv.init_ee()
    ee.Initialize()  # 幂等

    job.progress("构建计算图", 8, f"{spec.asset} → ee.Image")
    n_images = -1
    if spec.is_timeseries:
        obj = source.build_cube(spec)
        n_images = len(periods)   # 期数已知 → 免掉 xee 内部的 collection.size() 慢扫描
        job.progress("构建计算图", 8, f"{spec.asset} → {len(periods)} 期 ee.ImageCollection")
    else:
        obj = source.build_image(spec)
    job.check_cancelled()

    n_periods = len(periods) if periods else 1
    if spec.bands:
        io_chunks = plan_chunks(grid.width, grid.height, n_periods, len(spec.bands))
        ds = _open_ee_dataset_lazy(obj, grid, n_images, io_chunks)
    else:
        # bands=None（吃全部波段）：波段数要进驻留账，先按 xee 自动分块开一次
        # 只取元数据（波段名），再按真实波段数重开。分块参数必须在 open 时给定。
        with _open_ee_dataset_lazy(obj, grid, n_images, None) as probe:
            n_bands = len(probe.data_vars)
        io_chunks = plan_chunks(grid.width, grid.height, n_periods, n_bands)
        ds = _open_ee_dataset_lazy(obj, grid, n_images, io_chunks)

    try:
        t_total = int(ds.sizes["time"])
        if periods is not None and t_total != len(periods):
            raise RuntimeError(
                f"时序立方体期数不符：期望 {len(periods)} 期，"
                f"实际 time 维 = {t_total}。\n"
                "  常见原因：某期窗口内没有影像（空期塌缩失败）或波段名不一致。"
            )
        h_total = int(ds.sizes["y"])
        w_total = int(ds.sizes["x"])
        bands = [str(b) for b in ds.data_vars]
        # c18 容器契约：分块路径的变量容器也按契约落（原硬编码 float32）
        container = _container.resolve_container(spec)
        t_blk = io_chunks["index"]
        h_blk = io_chunks["height"]
        w_blk = io_chunks["width"]
        n_blocks = (
            -(-t_total // t_blk) * -(-h_total // h_blk) * -(-w_total // w_blk)
        )

        job.progress(
            "打开 xee 数据集", 20,
            f"{w_total}×{h_total} @ {grid.scale}m，io_chunks={io_chunks}",
        )

        # 坐标是 xee 本地生成的 numpy 数组（仿射推导），取值不触发 EE 请求
        time_vals = np.asarray(ds["time"].values)
        y_vals = np.asarray(ds["y"].values, dtype=np.float64)
        x_vals = np.asarray(ds["x"].values, dtype=np.float64)

        with nc.Dataset(tmp_path, "w", format="NETCDF4") as f:
            f.createDimension("time", t_total)
            f.createDimension("y", h_total)
            f.createDimension("x", w_total)

            # 变量创建顺序 = 文件变量序。波段在前、坐标在后，与 direct 路径
            # （arr.to_netcdf 的 data_vars→coords 顺序 B4,B3,B2,time,y,x）逐一对齐，
            # 消除两路径产物的布局着色歧义（修复轮：Verifier 风险①）。
            for b in bands:
                src = ds[b]
                bv = f.createVariable(
                    b, np.dtype(container), ("time", "y", "x"),
                    fill_value=np.dtype(container).type(np.nan),
                )
                for k in src.attrs:
                    try:
                        bv.setncattr(k, src.attrs[k])
                    except Exception:
                        pass  # 个别不可序列化的 attr 不阻塞产物
                sf = src.encoding.get("scale_factor", src.attrs.get("scale_factor"))
                if sf is not None:
                    bv.scale_factor = sf

            tv = f.createVariable("time", np.int64, ("time",))
            if time_vals.dtype.kind == "M":   # datetime64 → CF 编码（与 to_netcdf 同路径）
                num, units, calendar = _encode_cf_datetime(time_vals)
                tv[:] = np.asarray(num, dtype=np.int64)
                tv.units = units
                tv.calendar = calendar
            else:
                tv[:] = time_vals.astype(np.int64)

            for name, vals in (("y", y_vals), ("x", x_vals)):
                cv = f.createVariable(
                    name, np.float64, (name,), fill_value=np.float64(np.nan),
                )
                cv[:] = vals

            done = 0
            for t0 in range(0, t_total, t_blk):
                t1 = min(t0 + t_blk, t_total)
                for y0 in range(0, h_total, h_blk):
                    y1 = min(y0 + h_blk, h_total)
                    for x0 in range(0, w_total, w_blk):
                        x1 = min(x0 + w_blk, w_total)

                        # 单块取数包一层有界重试（与下载路径同口径，复用 _retry 的
                        # 瞬时错误分类）。实测教训（A1 第 6 次，2026-10-12）：本机
                        # 代理瞬时拒连（`WinError 10061`）让第 29/66 块当场失败，
                        # 而一块值数分钟 GEE 渲染 —— 瞬时抖动必须能自愈。
                        # 重放安全：块内逐波段写回同一区间，重复写入幂等。
                        def _fetch_block(t0=t0, t1=t1, y0=y0, y1=y1,
                                         x0=x0, x1=x1) -> None:
                            for b in bands:
                                block = ds[b].isel(
                                    time=slice(t0, t1),
                                    y=slice(y0, y1), x=slice(x0, x1),
                                ).values
                                block = np.asarray(block)
                                _container.guard_container_capacity(
                                    block, container,
                                    context=f"{getattr(spec, 'slug', 'spec')}:{b}:",
                                )
                                f.variables[b][t0:t1, y0:y1, x0:x1] = np.asarray(
                                    block, dtype=np.dtype(container),
                                )

                        _retry(
                            _fetch_block, job=job,
                            label=f"分块拉取 块 {done + 1}/{n_blocks}",
                        )
                        done += 1
                        job.check_cancelled()
                        job.progress(
                            "分块拉取+落盘", 20 + 60 * done // n_blocks,
                            f"块 {done}/{n_blocks}（io_chunks={io_chunks}）",
                        )
    finally:
        ds.close()


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

def _expected_map_artifacts(spec: ArtifactSpec, renderer: str) -> tuple[list[str], list[str]]:
    """按 spec 的真实配置推出「预期产物」键名，返回 (预期键列表, 问题列表)。

    c17：渲染失败判定不能再写死「某几个产物」——LayoutSpec.formats 允许只要求单一格式
    （如 ("pdf",)），layout 缺席（nolayout）时 arcpy 本就不导出 PDF/PNG。判据必须从 spec 推导，
    否则会把合法配置误判为失败。

    键名与 emit_map 写进 results 的键一一对应：qgis → qgz/png；arcpy → aprx + formats 里的导出。
    """
    problems: list[str] = []
    if renderer == "arcpy":
        expected = ["aprx"]
        layout = spec.layout
        if layout is not None:
            # formats=() 是合法构造（校验只查非法值、不查空）。bridge 侧口径是
            # `lay.get("formats") or ["pdf","png"]`（arcpy_bridge.py），即空值回落成 pdf+png
            # 并真的导出 —— 判据必须跟着回落，否则会把一次成功的渲染判成失败。
            formats = tuple(layout.formats or ()) or ("pdf", "png")
            expected.extend(f for f in formats if f in ("pdf", "png", "jpg"))
        return expected, problems
    # qgis：现状产物面就是 .qgz 工程 + .png 预览图，与 LayoutSpec 无关
    return ["qgz", "png"], problems


def emit_map(job: Job) -> dict:
    """
    两条 renderer 路径，都产出"人能直接看"的东西：
      qgis（默认）: .qgz 工程 + .png 静态预览 —— 现状行为；有 LayoutSpec 时
                    工程内嵌打印布局（图廓/比例尺/指北针/图例/标题）
      arcpy:        .aprx 工程 + 出版级 PDF/PNG（LayoutSpec 五要素）

    矢量叠加（C8 W3）：spec.overlays 同时分发两个 bridge，共同消费同一
    OverlaySpec（样式参数同源，禁止私有矢量参数）。⚠️ .png 静态预览保持
    **纯栅格烘焙**不变 —— 矢量可见性由 .qgz 工程与 arcpy PDF/PNG 承载，
    不烘焙进 .png（呈现层口径，见 tests/unit/test_overlay_spec.py 与 brief）。

    数据复用 emit_file 的产物，不重复下载。
    """
    renderer = (job.renderer or "qgis").lower()
    if renderer not in RENDERERS:
        raise ValueError(
            f"renderer={job.renderer!r} 不认识。可选：{', '.join(RENDERERS)}。\n"
            "  'qgis'（默认）出 .qgz + PNG；'arcpy' 出 .aprx + PDF/PNG 出版级图。"
        )

    spec = job.spec
    assert spec is not None

    # 时序 spec 拒绝出图（C3 Shape 裁决：拒绝而非静默塌缩成全期合成，
    # 否则同一 spec 三出口产物语义静默分歧）。多期渲染留待后续 change。
    if spec.is_timeseries:
        raise SpecError(
            "emit_map 暂不支持时序 spec（time_step / time_ranges）。\n"
            "  出路：\n"
            "    1. 对单个时间窗口用不含时序字段的 spec 出图；\n"
            "    2. 时序数据本身走 emit_array（NetCDF 立方体）或"
            " emit_file（堆叠 GeoTIFF）；\n"
            "    3. 多期渲染（动画 / 分幅）留待后续 change。"
        )

    raster, grid = _ensure_raster(job)
    job.check_cancelled()

    results: dict = {
        "exit": "map",
        "renderer": renderer,
        "spec_fingerprint": spec.fingerprint(),
        "grid": grid.to_dict(),
        "source_raster": str(raster),
        "artifacts": [],
    }
    if spec.overlays:
        results["overlays"] = len(spec.overlays)

    # --- 先烘焙显示用 8bit RGB：拉伸固定进像素，渲染端零解释 ---
    job.progress("烘焙显示用 8bit RGB", 50, "拉伸写入像素")
    visual = write_visual_rgb(spec, raster, grid)
    results["visual_raster"] = str(visual)
    results["artifacts"].append(str(visual))
    job.artifacts.append(str(visual))

    if renderer == "arcpy":
        # --- arcpy 分支：.aprx + 出版级 PDF/PNG（LayoutSpec 五要素）---
        from . import arcpy_bridge as _ab
        job.check_cancelled()
        job.progress("生成 ArcGIS Pro 工程", 62, ".aprx + PDF/PNG")
        try:
            # overlays：同一 OverlaySpec 分发两个 bridge —— 样式参数同源（C8 W3）
            res = _ab.write_aprx(spec, visual, grid, layout=spec.layout,
                                 overlays=spec.overlays)
            # c17：登记面必须与「预期产物」同源 —— 旧代码写死 ("aprx","pdf","png")，
            # 而 layout.formats 合法值含 jpg（spec.py:LAYOUT_FORMATS，arcpy_bridge 有
            # exportToJPEG 分支），于是 formats 里只要出现 jpg 就必然被判「缺失」。
            expected_arcpy, _ = _expected_map_artifacts(spec, "arcpy")
            for key in ["aprx"] + [k for k in ("pdf", "png", "jpg") if k in expected_arcpy]:
                val = res.get(key)
                # c17：键存在还不够，路径必须真实落盘 —— 否则「bridge 声称产出了、
                # 实际什么都没写」会被判成功（qgis 分支因 Path()/_render_png 会碰真实文件，
                # 天然安全；arcpy 分支全靠这里兜住）。
                if val and Path(val).is_file():
                    results[key] = val
                    results["artifacts"].append(val)
                    job.artifacts.append(val)
            if res.get("elements"):
                results["layout_elements"] = res["elements"]
            # bridge 侧矢量叠加明细（C8 W3：诊断与验收证据）
            if spec.overlays:
                results["arcpy_overlays"] = res.get("overlays") or []
                if res.get("overlay_errors"):
                    results["arcpy_overlay_errors"] = res["overlay_errors"]
        except Exception as e:
            results["arcpy_error"] = f"{type(e).__name__}: {e}"
            job.progress("ArcGIS Pro 出图失败", 62, str(e)[:80])
    else:
        # --- qgis 分支（现状）：.qgz —— 指向**显示用**栅格，不是浮点分析用栅格 ---
        job.progress("生成 QGIS 工程", 62, ".qgz")
        try:
            # overlays：同一 OverlaySpec 分发两个 bridge —— 样式参数同源（C8 W3）
            qgz_detail = _qb.write_qgz(
                spec, visual, grid, _output_path(spec, "deliver", ".qgz"),
                timeout=240, layout=spec.layout, overlays=spec.overlays,
            )
            qgz = Path(qgz_detail["path"])
            results["qgz"] = str(qgz)
            if qgz_detail.get("layout"):
                results["qgis_layout"] = qgz_detail["layout"]
            # c17：布局失败必须留痕（旧代码只读 layout 键，layout_error 被静默丢弃）
            if qgz_detail.get("layout_error"):
                results["layout_error"] = qgz_detail["layout_error"]
            # bridge 侧矢量叠加明细（C8 W3：诊断与验收证据）
            if spec.overlays:
                results["qgis_overlays"] = qgz_detail.get("overlays") or 0
                if qgz_detail.get("overlay_errors"):
                    results["qgis_overlay_errors"] = qgz_detail["overlay_errors"]
            results["artifacts"].append(str(qgz))
            job.artifacts.append(str(qgz))
        except Exception as e:
            results["qgz_error"] = f"{type(e).__name__}: {e}"
            job.progress("QGIS 工程生成失败，继续做预览图", 62, str(e)[:80])

        # --- 静态 PNG ---
        job.check_cancelled()
        job.progress("渲染预览图", 78, ".png")
        try:
            png = _render_png(spec, raster, grid, job)
            results["png"] = str(png)
            results["artifacts"].append(str(png))
            job.artifacts.append(str(png))
        except Exception as e:
            results["png_error"] = f"{type(e).__name__}: {e}"

    # --- 失败判定（c17 收紧）：预期产物缺一即失败 ---
    # 旧口径是「两者都失败才算失败」（qgis: qgz_error AND png_error），于是「.qgz 崩了但 .png
    # 成了」会被判成功，verify_all 的渲染项 PASS 因此不可信。现改为按**预期产物**逐项核验，
    # 且「预期」从 spec 的真实配置推导，不写死 —— layout.formats 允许只要单一格式
    # （如 ("pdf",)），layout 缺席（nolayout）则本就不导出 PDF/PNG。
    expected, problems = _expected_map_artifacts(spec, renderer)
    missing = [k for k in expected if not results.get(k)]
    if missing:
        problems.append(f"预期产物缺失：{missing}（已产出：{sorted(k for k in expected if results.get(k))}）")
    # 布局失败必须显式化：qgis_bridge 一直产出 layout_error，旧代码只读 layout 键，把错误丢了
    if results.get("layout_error"):
        problems.append(f"布局生成失败：{results['layout_error']}")
    if problems:
        raise RuntimeError(
            f"renderer={renderer!r} 出图失败（预期产物 {expected}）：\n  - "
            + "\n  - ".join(problems)
            + f"\n  错误记录：{ {k: v for k, v in results.items() if k.endswith('_error')} }"
        )

    job.progress("完成", 100, f"{len(results['artifacts'])} 个产物")
    _record_cache_current(job, spec)
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
        rgb8 = _bake_uint8(np.stack(channels, axis=-1) * 255.0)
    else:
        rgb8 = _bake_uint8(
            _single_band_rgb(da.isel(band=(picks[0] if picks else 0)).values, render) * 255.0
        )
    # 烘焙完立即释放底层 rasterio/GDAL 数据集：留到 GC 或解释器退出期再析构，GDAL 在
    # finalization 阶段会抛异常，表现为「跑成功但 stderr 打出 Error in sys.excepthook」
    da.close()

    _write_geopng(out, rgb8, grid, spec)
    job.progress("渲染预览图", 92, f"{out.name} ({out.stat().st_size/1024:.0f} KB)")
    return out


def _bake_uint8(rgb: "np.ndarray") -> "np.ndarray":
    """
    显示用 8bit 转换：非有限值（掩膜/NaN）显式归零后取整。

    `astype("uint8")` 对 NaN 的结果是未定义的，且每次都会打
    "RuntimeWarning: invalid value encountered in cast"，污染成功路径的 stderr。
    显式归零后产物确定；源数据侧仍保留 NaN，掩膜语义不变。
    """
    import numpy as np

    return np.where(np.isfinite(rgb), rgb, 0.0).astype("uint8")


def _write_geopng(path: Path, rgb8: "np.ndarray", grid: Grid, spec: ArtifactSpec) -> None:
    """用 GDAL 写 PNG，并把 geotransform + CRS 嵌进去。"""
    from osgeo import gdal, osr

    # 显式声明沿用 GDAL 的「返回码/None」语义：GDAL 4.0 默认改为抛异常，不声明既会
    # 改变既有错误分支行为，也会在首次调用时打 FutureWarning 污染成功路径的 stderr
    gdal.DontUseExceptions()

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
    png = None  # noqa: F841 — 释放 GDAL dataset 引用，触发落盘
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
    # nodata（masked=True 的 NaN）必须先归零 —— 否则 np.clip 透传 NaN，
    # floor().astype(int) 下溢成 int64 最小值，索引直接 IndexError（C2 实测）。
    idx = np.nan_to_num(np.clip(data, 0, 1), nan=0.0) * (len(stops) - 1)
    lo = np.floor(idx).astype(int)
    hi = np.clip(lo + 1, 0, len(stops) - 1)
    t = (idx - lo)[..., None]
    return stops[lo] * (1 - t) + stops[hi] * t


def _hex_to_rgb01(hexcol: str) -> list:
    """'006400' / '#006400' → [0.0, 0.392, 0.0]（0-1 浮点）。"""
    c = str(hexcol).lstrip("#")
    if len(c) != 6:
        raise ValueError(f"颜色值 {hexcol!r} 不是 6 位十六进制。")
    return [int(c[i:i + 2], 16) / 255.0 for i in (0, 2, 4)]


def _apply_class_palette(data, render) -> "np.ndarray":
    """
    分类栅格：类值 → 颜色**精确映射**（不拉伸、不插值）。

    与 _apply_colormap 的分工：那条固定 viridis 色带把数据当连续量，分类栅格的类码
    （WorldCover 的 10/20/…/100）在色带上插值出来的颜色既不是标准配色，也没法和图例
    对齐。这里用数据源自带的类色表逐类取色，未列出的值（含 nodata）落到底色。
    """
    import numpy as np

    values = np.asarray(render.class_values, dtype="float64")
    cols = np.array([_hex_to_rgb01(c) for c in (render.palette or ())], dtype="float32")
    d = np.asarray(data, dtype="float64")

    base = _hex_to_rgb01(render.nodata_color) if render.nodata_color else [0.0, 0.0, 0.0]
    out = np.empty(d.shape + (3,), dtype="float32")
    out[...] = base

    filled = np.zeros(d.shape, dtype=bool)
    for v, col in zip(values, cols, strict=True):
        # 类码是整数；0.5 的容差吸掉浮点噪声，又远小于最小类间距（WorldCover 为 5）
        m = np.isclose(d, v, atol=0.5) & ~filled
        out[m] = col
        filled |= m
    return out


def _single_band_rgb(data, render) -> "np.ndarray":
    """单波段 → RGB（0-1）。分类栅格精确取色；其余走「拉伸 + 固定色带」。"""
    if render is not None and render.class_values and render.palette:
        return _apply_class_palette(data, render)
    return _apply_colormap(_stretch(data, render))


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

    src = rioxarray.open_rasterio(raster, masked=True)
    render = spec.render
    want = list(render.bands) if render and render.bands else []

    names = list(spec.bands) or [f"b{i}" for i in range(1, src.sizes["band"] + 1)]
    pos = {n: i for i, n in enumerate(names)}
    picks = [pos[b] for b in want if b in pos][:3]

    if len(picks) >= 3:
        ch = [_stretch(src.isel(band=i).values, render) for i in picks]
        rgb8 = _bake_uint8(np.stack(ch, axis=-1) * 255.0)
    else:
        rgb8 = _bake_uint8(
            _single_band_rgb(src.isel(band=(picks[0] if picks else 0)).values, render) * 255.0
        )
    # 烘焙完立即释放底层数据集（同上：退出期析构会在 GDAL 侧抛异常）
    src.close()

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
