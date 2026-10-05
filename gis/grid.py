"""
确定性的栅格网格。

★ 这是"三形态对齐"的地基。

问题：如果让 GEE（getDownloadURL）和 xee（open_dataset）各自算网格，
两者会用不同的对齐规则，导致像素**差半格**——数值看起来差不多，
但做算术就错位。这是最阴险的一类 bug。

解法：网格由我们自己算定，两个出口都喂同一份：
    emit_file  → region/scale/crs（并事后校验 GEE 是否照做）
    emit_array → crs + crs_transform + shape_2d
    emit_map   → extent

对齐规则（显式写死，不依赖任何库的默认行为）：
    1. AOI 外接框 → 重投影到目标 CRS
    2. 四个边**向外**吸附到 scale 的整数倍
    3. 原点是左上角，y 轴向下（transform 的 e 为负）
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .spec import ArtifactSpec, aoi_bbox


@dataclass(frozen=True)
class Grid:
    """一个像素网格的完整定义。三出口共享。"""

    crs: str
    scale: float
    width: int
    height: int
    # GDAL 六参数仿射变换：(a, b, c, d, e, f)
    #   x = a*col + b*row + c
    #   y = d*col + e*row + f
    # 北向上：a=scale, b=0, d=0, e=-scale
    transform: tuple[float, float, float, float, float, float]

    # --- 便利属性 ---------------------------------------------------------

    @property
    def xmin(self) -> float:
        return self.transform[2]

    @property
    def ymax(self) -> float:
        return self.transform[5]

    @property
    def xmax(self) -> float:
        return self.xmin + self.width * self.scale

    @property
    def ymin(self) -> float:
        return self.ymax - self.height * self.scale

    @property
    def bounds(self) -> tuple[float, float, float, float]:
        """(xmin, ymin, xmax, ymax) —— 与 rasterio 的 bounds 同序。"""
        return (self.xmin, self.ymin, self.xmax, self.ymax)

    @property
    def shape_2d(self) -> tuple[int, int]:
        """(height, width) —— numpy / xarray 顺序。"""
        return (self.height, self.width)

    @property
    def transform_gdal(self) -> tuple[float, float, float, float, float, float]:
        """rasterio / GDAL 的 Affine 参数顺序（与 transform 相同，留作语义区分）。"""
        return self.transform

    def to_dict(self) -> dict:
        return {
            "crs": self.crs,
            "scale": self.scale,
            "width": self.width,
            "height": self.height,
            "bounds": [round(v, 4) for v in self.bounds],
            "transform": [round(v, 6) for v in self.transform],
        }

    def matches(self, *, crs: str, bounds: tuple, shape: tuple,
                rtol: float = 1e-3) -> tuple[bool, list[str]]:
        """
        对比另一套网格参数，返回 (是否一致, 差异说明)。
        用于校验 GEE 是否照我们给的网格执行 —— 不对齐就报警，不装作没事。
        """
        problems: list[str] = []

        def close(a: float, b: float) -> bool:
            return math.isclose(a, b, rel_tol=rtol, abs_tol=max(rtol, self.scale * 0.01))

        if _norm_crs(crs) != _norm_crs(self.crs):
            problems.append(f"CRS 不同：{crs} vs {self.crs}")

        b = tuple(bounds)
        for i, name in enumerate(("xmin", "ymin", "xmax", "ymax")):
            if not close(b[i], self.bounds[i]):
                problems.append(f"{name} 偏差 {b[i] - self.bounds[i]:+.3f}（{b[i]} vs {self.bounds[i]}）")

        h, w = int(shape[0]), int(shape[1])
        if (w, h) != (self.width, self.height):
            problems.append(f"尺寸不同：{w}×{h} vs {self.width}×{self.height}")

        return (not problems, problems)


def _norm_crs(crs) -> str:
    """把各种 CRS 写法归一成 EPSG:NNNN 便于比较。"""
    if crs is None:
        return ""
    s = str(crs)
    if s.upper().startswith("EPSG:"):
        return s.upper()
    try:
        from pyproj import CRS
        code = CRS.from_user_input(crs).to_epsg()
        return f"EPSG:{code}" if code else s
    except Exception:
        return s


class GridError(ValueError):
    pass


def compute_grid(spec: ArtifactSpec, *, pad_pixels: int = 0) -> Grid:
    """
    从 spec 算出确定的网格。

    pad_pixels > 0 时在四周各留 n 个像素的余量 —— 邻域分析（坡度、卷积、
    边缘检测）需要，否则结果边缘会被裁掉。
    """
    if not spec.crs:
        raise GridError(
            "spec.crs 为空，无法定义网格。\n"
            "  用 crs_rules.suggest_crs(aoi) 推导，或显式给一个投影坐标系。"
        )
    if not spec.scale or spec.scale <= 0:
        raise GridError(f"spec.scale 必须是正数，收到 {spec.scale!r}")

    box = aoi_bbox(spec.aoi) if spec.aoi else None
    if not box:
        raise GridError(
            "spec.aoi 为空，无法定义网格。\n"
            "  网格必须有范围。在 ArcGIS Pro 里可以用「从当前视图取 AOI」按钮生成。"
        )

    west, south, east, north = box
    crs = _norm_crs(spec.crs)
    scale = float(spec.scale)

    # --- 1. 重投影外接框 ---
    from pyproj import CRS, Transformer
    src = CRS.from_epsg(4326)
    dst = CRS.from_user_input(crs)

    if dst.to_epsg() == 4326 or dst.is_geographic:
        # 地理坐标系下"米"没有意义 —— 明确拒绝而不是给个错的结果
        if dst.is_geographic:
            raise GridError(
                f"目标 CRS {crs} 是地理坐标系，不能用米作为 scale 定义网格。\n"
                "  这会导致『10 米』被解释成『10 度』。\n"
                "  改用投影坐标系：crs_rules.suggest_crs(aoi)"
            )
        px_xmin, px_ymin, px_xmax, px_ymax = west, south, east, north
    else:
        tr = Transformer.from_crs(src, dst, always_xy=True)
        # 只用两个对角点会把弧形边界算窄 —— 沿四边采样取极值
        xs, ys = [], []
        n = 32
        for i in range(n + 1):
            t = i / n
            lon = west + (east - west) * t
            lat = south + (north - south) * t
            x1, y1 = tr.transform(lon, south)
            x2, y2 = tr.transform(lon, north)
            x3, y3 = tr.transform(west, lat)
            x4, y4 = tr.transform(east, lat)
            xs += [x1, x2, x3, x4]
            ys += [y1, y2, y3, y4]
        px_xmin, px_xmax = min(xs), max(xs)
        px_ymin, px_ymax = min(ys), max(ys)

    # --- 2. 向外吸附到 scale 的整数倍 ---
    pad = pad_pixels * scale
    ox = math.floor((px_xmin - pad) / scale) * scale
    oy = math.ceil((px_ymax + pad) / scale) * scale
    xmax_snap = math.ceil((px_xmax + pad) / scale) * scale
    ymin_snap = math.floor((px_ymin - pad) / scale) * scale

    width = int(round((xmax_snap - ox) / scale))
    height = int(round((oy - ymin_snap) / scale))

    if width <= 0 or height <= 0:
        raise GridError(
            f"算出的网格尺寸非法：{width}×{height}。\n"
            f"  AOI 或 scale 可能有误。AOI bbox={box}, scale={scale}"
        )

    return Grid(
        crs=crs,
        scale=scale,
        width=width,
        height=height,
        transform=(scale, 0.0, ox, 0.0, -scale, oy),
    )


def grid_from_raster(path) -> Grid:
    """从已有栅格文件反推网格。用于校验和"从产物继续"的工作流。"""
    import rasterio
    with rasterio.open(path) as ds:
        t = ds.transform
        return Grid(
            crs=_norm_crs(ds.crs),
            scale=abs(float(t.a)),
            width=ds.width,
            height=ds.height,
            transform=(float(t.a), float(t.b), float(t.c), float(t.d), float(t.e), float(t.f)),
        )


def self_test() -> list[str]:
    """不依赖网络的网格算法自检。"""
    from .spec import ArtifactSpec

    problems: list[str] = []
    aoi = {"type": "Polygon", "coordinates": [[
        [116.30, 39.95], [116.40, 39.95], [116.40, 40.02], [116.30, 40.02], [116.30, 39.95],
    ]]}
    s = ArtifactSpec(id="t", crs="EPSG:32650", scale=10, aoi=aoi)
    g = compute_grid(s)

    # 原点必须落在 scale 整数倍上
    if abs(g.xmin / g.scale - round(g.xmin / g.scale)) > 1e-9:
        problems.append(f"xmin={g.xmin} 不是 {g.scale} 的整数倍")
    if abs(g.ymax / g.scale - round(g.ymax / g.scale)) > 1e-9:
        problems.append(f"ymax={g.ymax} 不是 {g.scale} 的整数倍")

    # 自洽性
    if abs(g.xmax - (g.xmin + g.width * g.scale)) > 1e-6:
        problems.append("xmax 与 width 不自洽")
    if abs(g.ymin - (g.ymax - g.height * g.scale)) > 1e-6:
        problems.append("ymin 与 height 不自洽")
    if g.transform[4] > 0:
        problems.append("e 应为负（北向上，y 轴向下）")

    # 地理坐标系必须被拒绝
    try:
        compute_grid(ArtifactSpec(id="t", crs="EPSG:4326", scale=10, aoi=aoi))
        problems.append("EPSG:4326 + scale=10 应该被拒绝，但没有")
    except GridError:
        pass

    # pad 应该让网格变大
    g2 = compute_grid(s, pad_pixels=2)
    if not (g2.width > g.width and g2.height > g.height):
        problems.append(f"pad_pixels=2 未扩大网格：{g.width}×{g.height} → {g2.width}×{g2.height}")

    return problems


if __name__ == "__main__":
    import json
    import sys

    problems = self_test()
    print("self_test:", "全部通过" if not problems else problems)

    if len(sys.argv) > 1:
        from . import grid_from_raster
        g = grid_from_raster(sys.argv[1])
        print(json.dumps(g.to_dict(), indent=2, ensure_ascii=False))
