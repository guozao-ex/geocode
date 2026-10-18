"""C18：产物**容器 dtype 契约**与实施工具。

为什么需要：产物的容器 dtype 在 c18 之前不由 `ArtifactSpec` 决定，而由 GEE 导出路径决定 ——
声明 `uint16` 的 S2 样本实落 GeoTIFF `float64`，声明 `uint8` 的 WorldCover 实落 `float32`；
NetCDF 侧统一 float32。同一份数据两出口字节占用差 2–3 倍，声明值与实际值不符。
本模块把"落盘容器"从副产物提升为显式契约（`spec.container_dtype`，默认 float32）。

语义分工（见 brief D1）：
    `spec.dtype`            = 数据语义提示（当前不影响落盘，进指纹）
    `spec.container_dtype`  = 落盘容器契约（不进指纹、不 bump PROCESSING_VERSION）

本模块三组能力：

1. **契约解析**：`resolve_container()` —— 取 spec 的容器契约并做可用性守卫
   （整数容器与 `nodata=NaN` 语义互斥，一律拒绝；见 c15 的 collapse_mask_bands 缺口）；
2. **量纲守卫**：`guard_container_capacity()` —— 写盘**之前**用有界采样自证
   "目标容器装得下这份数据"，把"0–1 小数被量化成 0"这类静默损坏变成可读报错；
3. **容器实施**：`cast_to_container()`（内存数组）/ `rewrite_geotiff_container()`（原地改容器）/
   `read_bounded_sample()` / `assert_product_container()`（产物核验）。

红线：本模块**不改像素值语义**（不 cast 数值、不缩放），只决定"用哪个容器装"；
GEE 侧计算图仍只在 `gis/source.py` 构建。
"""

from __future__ import annotations

from pathlib import Path

from .spec import DEFAULT_CONTAINER_DTYPE, INTEGER_CONTAINER_DTYPES, SpecError


# ---------------------------------------------------------------------------
# 1. 契约解析
# ---------------------------------------------------------------------------

def resolve_container(spec) -> str:
    """
    取 spec 的容器契约；整数容器一律拒绝（c18 口径，见 brief D7/D9）。

    为什么整数容器被拒：C15 起 GeoTIFF/NetCDF 的无数据语义统一为 **NaN**
    （`normalize_nodata_to_nan` / `collapse_mask_bands`）。整数容器装不下 NaN ——
    rasterio 直接抛 "nodata value, nan, is beyond the valid range of its data type"。
    要么补齐整数 $\to$ 浮点提升、要么拒绝，本 change 选**拒绝**：显式声明的容器契约
    不允许被出口层悄悄改写（否则"声明可控"这条 capability 目标当场失效）。
    完整整数容器支持（整数 nodata 哨兵 + 无量纲数据）是独立 change。
    """
    dtype = str(getattr(spec, "container_dtype", DEFAULT_CONTAINER_DTYPE) or DEFAULT_CONTAINER_DTYPE)
    if dtype in INTEGER_CONTAINER_DTYPES:
        raise SpecError(
            f"container_dtype={dtype!r} 暂不支持（c18 口径）：\n"
            f"  产物无数据语义统一为 NaN（C15 起），整数容器装不下 NaN —— rasterio 会直接报"
            f" \"nodata value, nan, is beyond the valid range of its data type\"。\n"
            f"  改法：container_dtype 用 'float32'（默认）或 'float64'。\n"
            f"  若确实需要整数容器（例如无量纲分类栅格），那是独立 change 的话题。"
        )
    return dtype


# ---------------------------------------------------------------------------
# 2. 量纲守卫
# ---------------------------------------------------------------------------

def guard_container_capacity(values, container: str, context: str = "") -> None:
    """
    写盘**之前**自证：目标容器装得下这份数据。

    判据（有界采样的**实测证据**，不是只看声明）：
      - 数据是浮点、含小数部分，而容器是整数 ⇒ 小数会被截断（S2 反射率 0.0695 → 0）；
      - 数据含 NaN/Inf，而容器是整数 ⇒ 掩膜语义丢失；
      - 概览会报出**第一个**越界样值、它在采样块内的位置与目标容器，便于定位。

    容器可装（浮点容器、或整数数据配整数容器）则静默返回。
    """
    import numpy as np

    src = np.asarray(values)
    if not np.issubdtype(src.dtype, np.integer) and not np.issubdtype(src.dtype, np.floating):
        src = src.astype("float64")
    if np.issubdtype(src.dtype, np.integer):
        return                       # 整数数据 + 任何容器都不会丢小数（浮点容器自然装得下）
    if container not in INTEGER_CONTAINER_DTYPES:
        return                       # 浮点容器：NaN / 小数都能装

    bad_frac = np.isfinite(src) & (src != np.floor(src))
    bad_nan = ~np.isfinite(src)
    bad = bad_frac | bad_nan
    if not bad.any():
        return

    frac_only = bad_frac & ~bad_nan
    loc = np.argwhere(frac_only) if frac_only.any() else np.argwhere(bad)
    idx = tuple(int(i) for i in loc[0])
    sample = float(src[idx])
    where = f"{context} " if context else ""
    raise SpecError(
        f"{where}目标容器 {container!r} 装不下这份数据：采样块内有 {int(bad.sum())} 个像元会被"
        f"截断或丢失（小数 {int(bad_frac.sum())} / 非有限 {int(bad_nan.sum())}）。\n"
        f"  首个越界样值 = {sample!r}（位置 {idx}）—— 整数容器会把它变成 "
        f"{int(sample) if sample == sample else '未定义值'}，属**静默数据损坏**。\n"
        f"  改法二选一：container_dtype 改成 'float32'（默认）/'float64'；"
        f"或先把数据归一到整数量纲（方案见 docs/README 的容器契约节）。"
    )


def read_bounded_sample(path: Path, *, block_rows: int = 64):
    """
    读栅格的**有界采样窗口**（左上角起 block_rows 行），供写盘前/核验时做量纲自证。

    只读一窗口：1200 万×3 波段的真彩色也不会因守卫而整份入内存。
    """
    import rasterio
    from rasterio.windows import Window

    path = Path(path)
    with rasterio.open(path) as ds:
        rows = max(1, min(int(block_rows), ds.height))
        return ds.read(window=Window(0, 0, ds.width, rows))


def assert_product_container(path: Path, spec) -> list[str]:
    """
    核验产物容器是否等于契约；返回偏差列表（空列表 = 一致）。

    只做只读检查，不改文件 —— 供缓存命中判定与验收取证共用。
    """
    import rasterio

    want = resolve_container(spec)
    problems: list[str] = []
    path = Path(path)
    if path.suffix.lower() == ".nc":
        import xarray as xr

        with xr.open_dataset(path) as ds:
            for name, var in ds.data_vars.items():
                if str(var.dtype) != want:
                    problems.append(f"{path.name}:{name} {var.dtype} != 契约 {want}")
        return problems
    with rasterio.open(path) as ds:
        for i, got in enumerate(ds.dtypes, start=1):
            if got != want:
                problems.append(f"{path.name}:band{i} {got} != 契约 {want}")
    return problems


# ---------------------------------------------------------------------------
# 3. 容器实施
# ---------------------------------------------------------------------------

def default_container() -> str:
    return DEFAULT_CONTAINER_DTYPE


def cast_to_container(arr, container: str):
    """把数组装进目标容器（只 astype，不缩放值）。"""
    import numpy as np

    return np.asarray(arr).astype(np.dtype(container), copy=False)


def rewrite_geotiff_container(
    path: Path, container: str, *, block_rows: int = 1024, nodata: float | None = None,
) -> dict:
    """
    就地把 GeoTIFF 的容器改成 `container`（同目录 `.part` + 原子替换，失败不留半截文件）。

    用途：缓存命中时归一既有产物的容器（C15 先例的容器版）。只改容器类型，
    不碰像素值语义；nodata 声明默认沿用原文件，可用 `nodata` 覆盖（如 C15 的 NaN 归一）。

    返回 `{"changed": bool, "from": 原容器, "to": 目标容器, ...}`；容器已一致且 nodata 无需
    改写时直接短路（不重写文件 —— 避免无谓的字节变化）。
    """
    import numpy as np
    import rasterio
    from rasterio.windows import Window

    path = Path(path)
    with rasterio.open(path) as ds:
        src_dtype = ds.dtypes[0]
        src_nodata = ds.nodata
        want_nodata = src_nodata if nodata is None else nodata
        if (
            all(d == container for d in ds.dtypes)
            and _same_nodata(src_nodata, want_nodata)
        ):
            return {"changed": False, "from": src_dtype, "to": container,
                    "reason": "容器与 nodata 均已一致"}
        profile = ds.profile.copy()
        descriptions = list(ds.descriptions or ())
        tags = dict(ds.tags())
        band_tags = [dict(ds.tags(i)) for i in range(1, ds.count + 1)]
        count, width, height = ds.count, ds.width, ds.height
        rows_per_read = max(1, int(block_rows) // max(1, count))

    profile.update(dtype=container, nodata=want_nodata)
    tmp = path.with_suffix(path.suffix + ".part")
    try:
        with rasterio.open(tmp, "w", **profile) as dst:
            with rasterio.open(path) as src:
                for row0 in range(0, height, rows_per_read):
                    rows = min(rows_per_read, height - row0)
                    win = Window(0, row0, width, rows)
                    stack = src.read(window=win)
                    if np.issubdtype(np.dtype(container), np.integer):
                        guard_container_capacity(stack, container, context=f"{path.name}:")
                    dst.write(stack.astype(container, copy=False), window=win)
                for i, name in enumerate(descriptions, start=1):
                    if name:
                        dst.set_band_description(i, name)
            for k, v in tags.items():
                dst.update_tags(**{k: v})
            for i, bt in enumerate(band_tags, start=1):
                if bt:
                    dst.update_tags(i, **bt)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    # PAM 旁挂（.aux.xml）里可能缓存了旧 dtype 的统计量/直方图，替换后作废
    aux = path.with_name(path.name + ".aux.xml")
    aux.unlink(missing_ok=True)
    return {
        "changed": True, "from": src_dtype, "to": container,
        "nodata": src_nodata, "out_nodata": want_nodata,
        "shape": [width, height],
    }


def _same_nodata(a, b) -> bool:
    """nodata 声明等价判定（NaN 需要特判：NaN != NaN）。"""
    if a is None or b is None:
        return a is b or (a is None and b is None)
    try:
        import math

        fa, fb = float(a), float(b)
        if math.isnan(fa) or math.isnan(fb):
            return math.isnan(fa) and math.isnan(fb)
        return fa == fb
    except (TypeError, ValueError):
        return a == b
