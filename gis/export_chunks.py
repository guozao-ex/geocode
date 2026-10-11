"""
C15：`emit_file` 的**分块下载计划**与本地拼接。

为什么需要：GEE 的 `getDownloadURL` 对**单次请求**有 50,331,648 B（48 MiB）硬上限，
按「像素 × 波段 × (输出 dtype 字节 + 1 B mask)」计费（float32 即 5 B/像素/波段，
double 是 9 B）—— 直写路径上限约 **1000 万像素/波段**（float32）；
泰安市 30m DEM 只有 18.4M 像素就撞顶（实测 91,916,930 B 与 GEE 报数逐字节吻合）。
超过这个规模的 AOI 必须切块请求、本地拼接。

本模块分两层：

- **纯函数层**（`plan_download_chunks` / `chunk_request_bytes` / `window_bounds` /
  `locate_actual_window` / `coerce_nan` / `is_retryable_error`）：
  无 IO、无网络、无全局态，同输入同输出 —— `tests/unit` 的 AST 禁网守卫要求切块
  计划可以离线直测；
- **IO 层**（`write_chunk_array` / `normalize_nodata_to_nan`）：
  rasterio 本地读写，不依赖网络。

★ 红线（C15 brief）：分块**不得另建网格**。所有窗口都以 `grid.compute_grid()`
  的结果为唯一坐标系；拼接输出严格等于目标网格 —— 不重采样、不吸附、不猜测。
★ 边界处理：请求的 4326 region 会带 1 像素余量（吸收 GEE 边界吸附的 ±1 像素），
  拼接时按**实际返回的 transform** 定位并裁掉余量，而不是假设尺寸。
"""

from __future__ import annotations

import math
from pathlib import Path

# GEE 单次下载字节上限（实测报错原文：
#   "Total request size (91916930 bytes) must be less than or equal to 50331648 bytes"）
MAX_DOWNLOAD_BYTES = 50_331_648          # 48 MiB

# ⚠️ 每像素每波段的计费字节**取决于输出 dtype**：`dtype 字节 + 1 B（mask）`。
# 实测（2026-10-11，C15 真数据）：
#   - float32 单波段 DEM：5 B/px（18,383,386 px → 91,916,930 B，逐字节吻合）
#   - double  单波段 NDVI：8.996 B/px（8,019,744 px → 72,145,242 B）
#   - double  三波段 S2 真彩色：26.98 B/px（2,006,048 px → 54,133,272 B）
# 即：**不能按 spec.dtype 猜**（spec 写 uint16，GEE 实际输出 double）——
# 必须问 `img.bandTypes()`，见 emit._image_bytes_per_band()。
BYTES_PER_PIXEL_BAND = 5                 # float32 基准（历史口径）：4 B + 1 B mask
BYTES_PER_PIXEL_BAND_UNKNOWN = 9         # 未知精度：按最坏（double 8 B + 1 B）算

# EE PixelType.precision → (数据字节 + mask 1B)
PRECISION_BYTES = {
    "int8": 1, "uint8": 1, "byte": 1,
    "int16": 2, "uint16": 2, "ushort": 2,
    "int32": 4, "uint32": 4, "float": 4, "float32": 4,
    "int64": 8, "uint64": 8, "double": 8, "float64": 8,
}


def bytes_per_pixel_band(precision: str | None) -> int:
    """GEE 单请求计费：输出精度数据字节 + 1 B mask。未知 / 空精度按最坏（double）算。"""
    if not precision:
        return BYTES_PER_PIXEL_BAND_UNKNOWN
    data = PRECISION_BYTES.get(str(precision).strip().lower())
    return data + 1 if data is not None else BYTES_PER_PIXEL_BAND_UNKNOWN

# 每片额外多请的像素余量（单边）：region 外扩 1 px + GEE 把 region 边界向外
# 吸附到 scale 整数倍时最多再多 1 px。两者都只影响请求体积，不进入产物。
CHUNK_MARGIN_PIXELS = 1      # region 外扩（覆盖保险）
CHUNK_SNAP_PIXELS = 1        # GEE 向外吸附（SnapOut）最多 1 px

# 预算安全系数：实测多边形 region 下 GEE 网格 = 窗口 + 2×(margin+snap)，
# 留 2% 余量应对边界取整差异（分片偏小只会多几次请求，不会失败）。
CHUNK_SAFETY_FACTOR = 1.02

# 判定"实际栅格与目标网格像素对齐"的容差（单位：像素）
_ALIGN_TOL_PIXELS = 1e-3


def plan_download_chunks(
    width: int,
    height: int,
    n_bands: int = 1,
    *,
    max_bytes: int | None = None,
    bytes_per_pixel_band: int = BYTES_PER_PIXEL_BAND,
    margin_pixels: int = CHUNK_MARGIN_PIXELS,
    snap_pixels: int = CHUNK_SNAP_PIXELS,
    safety_factor: float = CHUNK_SAFETY_FACTOR,
) -> list[dict[str, int]]:
    """
    把 `width×height` 网格切成若干矩形窗口（像素坐标，行优先）。

    预算账（与 GEE 对齐）：`(w + 2p)(h + 2p) × 波段 × B/像素 ≤ max_bytes / safety`，
    其中 `p = margin + snap` —— region 外扩 + GEE 向外吸附合计最多 2 px/边。
    返回 `[{"x","y","width","height"}, ...]`：

    - 覆盖恰好一次：所有窗口拼起来等于整幅网格，无重叠、无空洞；
    - 同输入同输出（纯函数，无 IO）；
    - **方形块**：region 只能是经纬度几何，横长矩形会被子午线收敛“鼓包”放大，
      所以不按整行切，而是取接近正方形的块。

    预算太小（连 1 像素 + 余量都装不下）时报 `ValueError`，不返回会永远失败的窗口。
    """
    w = int(width)
    h = int(height)
    if w <= 0 or h <= 0:
        raise ValueError(f"网格尺寸非法：{width}×{height}")
    bands = max(1, int(n_bands))
    bpp = int(bytes_per_pixel_band)
    if bpp <= 0:
        raise ValueError(f"bytes_per_pixel_band 必须为正整数，收到 {bytes_per_pixel_band!r}")
    budget = int(MAX_DOWNLOAD_BYTES if max_bytes is None else max_bytes)
    if budget <= 0:
        raise ValueError(f"max_bytes 必须为正整数，收到 {max_bytes!r}")
    m = max(0, int(margin_pixels)) + max(0, int(snap_pixels))
    safety = float(safety_factor) if safety_factor and safety_factor >= 1.0 else 1.0

    px_budget = int(budget // (bpp * bands) // safety)
    if (1 + 2 * m) * (1 + 2 * m) > px_budget:
        raise ValueError(
            f"单请求预算太小：{budget} B / {bands} 波段 / {bpp} B/像素 → "
            f"{px_budget} 像素，装不下 1 像素 + {m} 像素余量。"
        )

    def fits(w_: int, h_: int) -> bool:
        return (w_ + 2 * m) * (h_ + 2 * m) <= px_budget

    # ★ 方形块（C15 实测教训）：region 最后是 EPSG:4326 的曲边几何，
    #   而投影坐标下的横长矩形在 4326 里“鼓包”很大：整行切（17680×103 px，跨 2° 经度）
    #   实测 GEE 报 95,026,878 B，是估算（50 MB）的 1.9 倍，第一片就被拒。
    #   方形块跨度小（~14 km），鼓包降到亚米级。
    side = max(1, math.isqrt(px_budget) - 2 * m)
    step_w = min(w, side)
    while step_w > 1 and not fits(step_w, 1):
        step_w -= 1
    step_h = max(1, min(h, px_budget // (step_w + 2 * m) - 2 * m))
    while step_h > 1 and not fits(step_w, step_h):
        step_h -= 1

    windows: list[dict[str, int]] = []
    for y0 in range(0, h, step_h):
        bh = min(step_h, h - y0)
        for x0 in range(0, w, step_w):
            bw = min(step_w, w - x0)
            if not fits(bw, bh):   # 防御：预算或形状参数变化时不允许越限
                raise AssertionError(
                    f"分块越限：窗口 {bw}×{bh} + 余量 {m} > 预算 {px_budget} 像素"
                    f"（max_bytes={budget}, 波段={bands}）"
                )
            windows.append({"x": int(x0), "y": int(y0), "width": int(bw), "height": int(bh)})
    return windows


def chunk_request_bytes(
    window: dict[str, int],
    n_bands: int = 1,
    *,
    bytes_per_pixel_band: int = BYTES_PER_PIXEL_BAND,
    margin_pixels: int = CHUNK_MARGIN_PIXELS,
    snap_pixels: int = CHUNK_SNAP_PIXELS,
) -> int:
    """单片的请求体积估算（含 region 外扩与 GEE 吸附余量）—— 用于失败文案与守卫。"""
    m = max(0, int(margin_pixels)) + max(0, int(snap_pixels))
    return (
        (int(window["width"]) + 2 * m)
        * (int(window["height"]) + 2 * m)
        * max(1, int(n_bands))
        * int(bytes_per_pixel_band)
    )


def window_bounds(grid, window: dict[str, int]) -> tuple[float, float, float, float]:
    """
    像素窗口 → 投影坐标 `(xmin, ymin, xmax, ymax)`。

    严格落在网格上：边界 = `grid.xmin + 列号 × scale`，不吸附、不取整。
    `grid` 只需有 `xmin/ymax/scale` 三个属性（duck typing，便于离线直测）。
    """
    x0 = grid.xmin + int(window["x"]) * grid.scale
    y1 = grid.ymax - int(window["y"]) * grid.scale
    x1 = x0 + int(window["width"]) * grid.scale
    y0 = y1 - int(window["height"]) * grid.scale
    return (float(x0), float(y0), float(x1), float(y1))


def locate_actual_window(
    grid,
    window: dict[str, int],
    *,
    transform,
    size: tuple[int, int],
    tol_pixels: float = _ALIGN_TOL_PIXELS,
) -> tuple[int, int, int, int] | None:
    """
    算出**实际返回的栅格**里，与目标窗口对应的 `(col0, row0, width, height)`。

    实际栅格必须：与目标网格同 scale、无旋转、像素对齐（允许边界多出余量）。
    任何一项不满足（错位 / 覆盖不足 / 尺寸不符）都返回 `None` —— 由调用方
    报可读错误，绝不"凑合拼"。
    """
    a, b, c, d, e, f = (float(v) for v in tuple(transform)[:6])
    if abs(b) > 1e-9 or abs(d) > 1e-9:
        return None                                   # 有旋转 → 不是同一网格
    if not math.isclose(abs(a), grid.scale, rel_tol=1e-6) or not math.isclose(
        abs(e), grid.scale, rel_tol=1e-6
    ):
        return None                                   # 分辨率不同
    if a <= 0 or e >= 0:
        return None                                   # 方向不是北向上

    xmin_exp, _ymin, _xmax, ymax_exp = window_bounds(grid, window)
    col_f = (xmin_exp - c) / float(grid.scale)
    row_f = (f - ymax_exp) / float(grid.scale)
    col0 = int(round(col_f))
    row0 = int(round(row_f))
    if abs(col_f - col0) > tol_pixels or abs(row_f - row0) > tol_pixels:
        return None                                   # 像素错位（半格）
    if col0 < 0 or row0 < 0:
        return None                                   # 覆盖不足（左上出界）
    aw = int(size[0])
    ah = int(size[1])
    if col0 + int(window["width"]) > aw or row0 + int(window["height"]) > ah:
        return None                                   # 覆盖不足（右下出界）
    return (col0, row0, int(window["width"]), int(window["height"]))


def coerce_nan(arr, src_nodata=None):
    """
    把源 nodata 值与所有非有限值统一成 `NaN`（C15 A4）。

    - 浮点容器：保留 dtype，只替换"无效像素"；
    - 整数容器：提升为 float32（NaN 需要浮点容器）；
    - 不修改入参数组（有替换时返回副本）。

    `src_nodata` 为 ±inf / nan 时无需额外比较（非有限检查已覆盖）。
    """
    import numpy as np

    a = np.asarray(arr)
    if not np.issubdtype(a.dtype, np.floating):
        a = a.astype("float32")
    mask = ~np.isfinite(a)
    if src_nodata is not None:
        try:
            sd = float(src_nodata)
        except (TypeError, ValueError):
            sd = None
        if sd is not None and math.isfinite(sd):
            mask = mask | (a == sd)
    if mask.any():
        a = a.copy()
        a[mask] = np.nan
    return a


# ---------------------------------------------------------------------------
# 重试判定（纯函数：按异常类型名 / HTTP 状态码 / 报错文本分类，不导入网络库）
# ---------------------------------------------------------------------------

RETRYABLE_HTTP_CODES = frozenset({408, 425, 429, 500, 501, 502, 503, 504, 507, 509, 522, 524})
RETRYABLE_EXC_NAMES = frozenset({
    "RemoteDisconnected", "ConnectionResetError", "ConnectionAbortedError",
    "BrokenPipeError", "TimeoutError", "URLError", "IncompleteRead",
    "ProtocolError", "ChunkedEncodingError", "ReadTimeout", "ConnectTimeout",
    "SSLError", "ConnectionError",
})
# 服务端可重现的瞬时文本（GEE 侧 EEException 也走这条）
RETRYABLE_TEXT = (
    "internal error", "backend error", "deadline exceeded", "connection reset",
    "connection aborted", "timed out", "timeout", "temporarily unavailable",
    "service unavailable", "server unavailable", "try again", "rate limit",
    "http code: 429", "http code: 500", "http code: 502", "http code: 503",
    "http code: 504",
)
# 确定性错误：明确不重试（含 GEE 的体积上限报错与 band-not-found）
NON_RETRYABLE_TEXT = (
    "must be less than or equal to", "no band named", "not found",
    "expression contains", "invalid argument", "permission denied",
    "unauthorized", "forbidden",
)


def is_retryable_error(exc: BaseException | None) -> bool:
    """
    判断异常是否属于**瞬时**错误（值得重试）。

    只看类型名 / HTTP 状态码 / 文本，不导入 `http` / `urllib` / `socket` ——
    这样 `tests/unit` 可以直接构造同名异常离线验证分类逻辑。
    会沿 `__cause__` / `reason` 链向下看一层（`URLError(reason=ConnectionResetError)`）。
    """
    seen: set[int] = set()
    cur: BaseException | None = exc
    depth = 0
    while cur is not None and depth < 5 and id(cur) not in seen:
        seen.add(id(cur))
        depth += 1

        name = type(cur).__name__
        code = getattr(cur, "code", None)
        if code is None:
            code = getattr(cur, "status", None)
        if isinstance(code, int):
            if code in RETRYABLE_HTTP_CODES:
                return True
            if 400 <= code < 500:
                return False
            if 500 <= code < 600:
                return True
        if name in RETRYABLE_EXC_NAMES:
            return True

        msg = str(cur).lower()
        if any(tok in msg for tok in NON_RETRYABLE_TEXT):
            return False
        if any(tok in msg for tok in RETRYABLE_TEXT):
            return True

        nxt = getattr(cur, "__cause__", None) or getattr(cur, "reason", None)
        cur = nxt if isinstance(nxt, BaseException) else None
    return False


# ---------------------------------------------------------------------------
# IO 层
# ---------------------------------------------------------------------------

def write_chunk_array(dst, window: dict[str, int], arr) -> None:
    """把一片数组写进目标栅格的对应窗口（`dst` = rasterio 写句柄，窗口已是目标坐标）。"""
    from rasterio.windows import Window

    dst.write(
        arr, 1,
        window=Window(int(window["x"]), int(window["y"]),
                      int(window["width"]), int(window["height"])),
    )


def normalize_nodata_to_nan(path: Path, *, block_rows: int = 1024) -> dict:
    """
    GeoTIFF 的 nodata 语义统一为 `NaN`（C15 A4）：把"声明为 nodata 的像素"与
    所有非有限值全部改写成 `NaN`，并把 nodata 声明改成 `nan`。

    为什么必须改像素而不只是改声明：GEE 的 GEO_TIFF 把掩膜像素写成
    `-inf`（float32）/ `0`（float64）/ 整数哨兵，只改声明的话，`rasterio`
    `masked=True` 读回仍会看到 `-inf` 或 0，与 NetCDF 的 NaN 语义不一致。

    返回 `{"changed": bool, "nodata": 原始声明, "dtype": 原始 dtype, ...}`；
    已是 NaN 语义的产物直接短路（`changed=False`），不做无谓重写。
    重写走同目录 `.part` + 原子 rename，失败不留半截文件。
    """
    import numpy as np
    import rasterio
    from rasterio.windows import Window

    path = Path(path)
    with rasterio.open(path) as ds:
        src_nodata = ds.nodata
        src_dtype = ds.dtypes[0]
        if (
            np.issubdtype(np.dtype(src_dtype), np.floating)
            and src_nodata is not None
            and np.isnan(src_nodata)
            and len(set(ds.dtypes)) == 1
        ):
            return {"changed": False, "nodata": src_nodata, "dtype": src_dtype,
                    "reason": "已是 NaN 语义"}
        profile = ds.profile.copy()
        descriptions = list(ds.descriptions)
        tags = dict(ds.tags())
        count, width, height = ds.count, ds.width, ds.height
        transform, crs = ds.transform, ds.crs
        band_tags = [dict(ds.tags(i)) for i in range(1, count + 1)]

    # 整数容器装不下 NaN → 提升为 float32（GEE 只在这些容器里用整数哨兵）
    out_dtype = "float32" if not np.issubdtype(np.dtype(src_dtype), np.floating) else src_dtype
    profile.update(dtype=out_dtype, nodata=float("nan"))

    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    try:
        with rasterio.open(tmp, "w", **profile) as dst:
            with rasterio.open(path) as src:
                for i in range(1, count + 1):
                    for row0 in range(0, height, block_rows):
                        rows = min(block_rows, height - row0)
                        win = Window(0, row0, width, rows)
                        block = src.read(i, window=win)
                        dst.write(coerce_nan(block, src_nodata), i, window=win)
                    if i <= len(descriptions) and descriptions[i - 1]:
                        dst.set_band_description(i, descriptions[i - 1])
            for k, v in tags.items():
                dst.update_tags(**{k: v})
            for i, bt in enumerate(band_tags, start=1):
                if bt:
                    dst.update_tags(i, **bt)
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise

    # PAM 旁挂（.aux.xml）里可能缓存了旧的统计量/直方图，替换后作废
    aux = path.with_name(path.name + ".aux.xml")
    aux.unlink(missing_ok=True)
    return {
        "changed": True,
        "nodata": src_nodata,
        "dtype": src_dtype,
        "out_dtype": out_dtype,
        "shape": [width, height],
        "crs": str(crs),
        "transform": tuple(transform)[:6],
    }
