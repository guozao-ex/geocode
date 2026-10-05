"""
CRS 纪律 —— 从 GeoCode 的 run-processing.txt 提炼，并补上中国制图场景。

核心规则（GeoCode 原文，值得原样遵守）：

    距离 / 面积 / 缓冲区 / 密度 / 坡度 这类"消费或产出线性单位"的算法，
    必须在投影坐标系（PCS）上跑。地理坐标系（GCS）会给无意义的结果 ——
    例如 500 米的缓冲区会变成 500 度。

QGIS 和 ArcGIS 的算法都**不会**替你校验输入 CRS。所以这一层必须前置。

本模块只做"该不该、建议用什么"，不替调用方重投影 —— 重投影是出口层的事。
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

# ---------------------------------------------------------------------------
# 运算分类：按"单位敏感性"分三档
# ---------------------------------------------------------------------------

# 需要线性单位（米）。在 GCS 上跑会得到无意义甚至荒唐的结果。
LINEAR_UNIT_OPS = frozenset({
    "buffer",          # 缓冲区
    "distance",        # 距离计算 / 近邻
    "area",            # 面积计算
    "length",          # 长度计算
    "density",         # 密度分析
    "slope",           # 坡度
    "aspect",          # 坡度变率亦按线性处理
    "hillshade",       # 山体阴影依赖真实距离
    "viewshed",        # 可视域
    "watershed",       # 水文
    "reproject_keep_length",  # 任意保长变换
    "interpolation",   # 插值
    "kriging",
    "idw",
    "cluster_distance",
    "spatial_join_distance",
    "near",
    "service_area",
})

# 与 CRS 无关，或者自身会做正确的事（数据驱动）
CRS_AGNOSTIC_OPS = frozenset({
    "dissolve",
    "clip",
    "select",
    "filter",
    "attribute_join",
    "merge",
    "export",
    "raster_math",
    "band_arithmetic",
    "ndvi",
    "ndwi",
    "nbr",
    "composite",
    "mosaic",
    "classify",
    "mask",
})

OpKind = Literal["linear", "agnostic"]

Issue_Level = Literal["error", "warning", "info"]


@dataclass(frozen=True)
class Issue:
    level: Issue_Level
    code: str
    message: str

    def as_dict(self) -> dict:
        return {"level": self.level, "code": self.code, "message": self.message}


# ---------------------------------------------------------------------------
# CRS 查询（懒加载 pyproj —— 没装的路径不该因此失败）
# ---------------------------------------------------------------------------

@lru_cache(maxsize=256)
def resolve(crs: str | int):
    """字符串 / EPSG 码 -> pyproj.CRS。无法解析时抛 ValueError。"""
    from pyproj import CRS
    from pyproj.exceptions import CRSError

    try:
        return CRS.from_user_input(crs)
    except CRSError as e:
        raise ValueError(
            f"无法解析 CRS {crs!r}：{e}\n"
            "  用标准写法：'EPSG:4326' / 'EPSG:32650'，或完整 PROJ/WKT 字符串。"
        ) from e


def is_projected(crs: str | int) -> bool:
    return bool(resolve(crs).is_projected)


def unit_of(crs: str | int) -> str:
    """返回轴向单位名，如 'metre' / 'degree'。"""
    ax = resolve(crs).axis_info
    return ax[0].unit_name if ax else "unknown"


def is_metric(crs: str | int) -> bool:
    u = unit_of(crs).lower()
    return u in ("metre", "meter", "m")


# ---------------------------------------------------------------------------
# 推荐 CRS
# ---------------------------------------------------------------------------

def utm_epsg(lon: float, lat: float) -> int:
    """WGS84 UTM 带号 -> EPSG。南北半球分别落在 326xx / 327xx。"""
    lon = max(-180.0, min(180.0, float(lon)))
    lat = max(-80.0, min(84.0, float(lat)))
    zone = int(math.floor((lon + 180.0) / 6.0)) + 1
    zone = max(1, min(60, zone))
    return (32600 if lat >= 0 else 32700) + zone


@lru_cache(maxsize=1)
def _cgcs2000_3deg_table() -> dict[int, int]:
    """
    CGCS2000 3 度带（中央经线变体）的 EPSG 表：{中央经线度数: EPSG}。

    不硬编码 —— 从 pyproj 的数据库里现查，查不到就返回空表。
    这样表随 PROJ 版本自动更新，也不会因为我记错编号而骗人。
    """
    out: dict[int, int] = {}
    try:
        from pyproj.database import query_crs_info
    except Exception:
        return out
    try:
        infos = query_crs_info(
            auth_name="EPSG",
            pj_types=None,
            area_of_interest=None,
        )
    except Exception:
        return out
    for info in infos:
        name = (info.name or "").lower()
        if "cgcs2000" not in name:
            continue
        if "3-degree" not in name and "3 degree" not in name:
            continue
        # 只收 "CM 117E" 这种，跳过带带号前缀的（假东偏 500000 才是我们要的）
        if "cm" not in name:
            continue
        import re
        m = re.search(r"cm\s+(\d{2,3})e", name)
        if not m:
            continue
        cm = int(m.group(1))
        try:
            code = int(info.code)
        except (TypeError, ValueError):
            continue
        out.setdefault(cm, code)
    return out


def cgcs2000_3deg_epsg(lon: float) -> int | None:
    """给定经度，返回对应的 CGCS2000 3 度带 EPSG；查不到返回 None。"""
    table = _cgcs2000_3deg_table()
    if not table:
        return None
    lon = float(lon)
    # 3 度带：中央经线 = 3 * round(lon / 3)，中国范围大致 75E–135E
    cm = int(round(lon / 3.0) * 3)
    if cm in table:
        return table[cm]
    # 容错：找最近的
    nearest = min(table, key=lambda k: abs(k - cm))
    return table[nearest] if abs(nearest - cm) <= 3 else None


def suggest_crs(
    aoi: dict | None = None,
    *,
    prefer: Literal["utm", "cgcs2000"] = "utm",
    fallback: str = "EPSG:4326",
) -> str:
    """
    按 AOI 质心推荐投影坐标系。

    中国项目建议 prefer='cgcs2000'；国际项目用 'utm'。
    AOI 为空或质心取不到时退回 fallback（并保留 GCS —— 调用方应据此提示用户）。
    """
    from .spec import aoi_bbox

    box = aoi_bbox(aoi) if aoi else None
    if not box:
        return fallback
    west, south, east, north = box
    lon = (west + east) / 2.0
    lat = (south + north) / 2.0

    if prefer == "cgcs2000":
        code = cgcs2000_3deg_epsg(lon)
        if code:
            return f"EPSG:{code}"
    return f"EPSG:{utm_epsg(lon, lat)}"


def describe(crs: str | int) -> dict:
    """给 UI / 日志用的一份 CRS 说明。"""
    c = resolve(crs)
    ax = c.axis_info[0] if c.axis_info else None
    return {
        "input": str(crs),
        "name": c.name,
        "authority": f"{c.to_epsg()}" if c.to_epsg() else None,
        "epsg": c.to_epsg(),
        "is_projected": c.is_projected,
        "is_geographic": c.is_geographic,
        "unit": ax.unit_name if ax else None,
        "metric": is_metric(crs),
    }


# ---------------------------------------------------------------------------
# 检查
# ---------------------------------------------------------------------------

def classify(op: str) -> OpKind:
    """把运算名归到 'linear' 或 'agnostic'。未知运算按 agnostic（不误伤）。"""
    key = op.strip().lower().replace(" ", "_").replace("-", "_")
    if key in LINEAR_UNIT_OPS:
        return "linear"
    if key in CRS_AGNOSTIC_OPS:
        return "agnostic"
    # 子串兜底：native:buffer / gdal:slope …
    short = key.split(":")[-1]
    if any(tok in short for tok in ("buffer", "distance", "slope", "area", "density", "viewshed")):
        return "linear"
    return "agnostic"


def check(op: str, crs: str | int | None) -> list[Issue]:
    """
    检查某运算在某 CRS 下是否成立。

    返回 Issue 列表；空列表表示没问题。
    crs 为 None 时不报错（上层自己决定默认值），只给 info。
    """
    issues: list[Issue] = []
    kind = classify(op)

    if crs is None:
        if kind == "linear":
            issues.append(Issue(
                "info", "crs-unspecified-linear",
                f"运算 {op!r} 消费/产出线性单位，但 CRS 未指定。"
                "建议用 crs_rules.suggest_crs(aoi) 推导，或显式给一个投影坐标系。",
            ))
        return issues

    try:
        proj = is_projected(crs)
        metric = is_metric(crs)
        unit = unit_of(crs)
    except ValueError as e:
        return [Issue("error", "crs-unresolvable", str(e))]

    if kind == "linear":
        if not proj:
            issues.append(Issue(
                "error", "linear-op-on-geographic",
                f"运算 {op!r} 需要投影坐标系，但 {crs} 是地理坐标系（单位 {unit}）。\n"
                f"  后果：线性参数会被当作『度』解释 —— 例如 500 米的缓冲区变成 500 度。\n"
                f"  修法：先重投影到 PCS（native:reprojectlayer / gdal:warpreproject），"
                f"或用 crs_rules.suggest_crs(aoi) 取一个。",
            ))
        elif not metric:
            issues.append(Issue(
                "warning", "linear-op-on-non-metric",
                f"运算 {op!r} 需要线性单位，但 {crs} 的轴向单位是 {unit}（非米）。\n"
                "  如果该单位是英尺等长度单位且你已按该单位给参数，可忽略。",
            ))
    return issues


def preflight_report(spec, op: str) -> dict:
    """把 spec + 运算名合成一份可直接塞进 UI / 日志的检查报告。"""
    issues = check(op, getattr(spec, "crs", None))
    ok = not any(i.level == "error" for i in issues)
    return {
        "op": op,
        "kind": classify(op),
        "crs": getattr(spec, "crs", None),
        "ok": ok,
        "issues": [i.as_dict() for i in issues],
    }


def self_test() -> list[str]:
    """自检：不依赖网络，验证基本判断正确。返回问题列表（空 = 全通过）。"""
    problems: list[str] = []

    if not is_projected("EPSG:32650"):
        problems.append("EPSG:32650 应被判为投影坐标系")
    if is_projected("EPSG:4326"):
        problems.append("EPSG:4326 应被判为地理坐标系")
    if not is_metric("EPSG:32650"):
        problems.append("EPSG:32650 单位应为米")

    # 北京附近 → UTM 50N
    got = utm_epsg(116.4, 39.9)
    if got != 32650:
        problems.append(f"北京应落在 EPSG:32650，实得 {got}")

    # 线性运算 + GCS 必须报 error
    errs = [i for i in check("buffer", "EPSG:4326") if i.level == "error"]
    if not errs:
        problems.append("buffer 在 EPSG:4326 上应报 error")

    # 线性运算 + PCS 必须干净
    if check("buffer", "EPSG:32650"):
        problems.append("buffer 在 EPSG:32650 上不应有问题")

    # 非单位敏感运算不该报错
    if [i for i in check("dissolve", "EPSG:4326") if i.level == "error"]:
        problems.append("dissolve 在 GCS 上不应报 error")

    # 未知运算不该误伤
    if [i for i in check("some_unknown_algo_xyz", "EPSG:4326") if i.level == "error"]:
        problems.append("未知运算不应报 error")

    return problems


if __name__ == "__main__":
    import json
    problems = self_test()
    print("self_test:", "全部通过" if not problems else problems)

    aoi = {"type": "Polygon", "coordinates": [[
        [116.0, 39.5], [117.0, 39.5], [117.0, 40.2], [116.0, 40.2], [116.0, 39.5],
    ]]}
    print("suggest(utm):     ", suggest_crs(aoi))
    print("suggest(cgcs2000):", suggest_crs(aoi, prefer="cgcs2000"))
    print("describe(32650):  ", json.dumps(describe("EPSG:32650"), ensure_ascii=False))
    print("cgcs2000 表大小:  ", len(_cgcs2000_3deg_table()))
