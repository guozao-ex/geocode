"""
行政区 AOI 供给（C8 W2）—— 中国边界合规纪律（D2）的唯一消费点。

- 中国行政区划边界的**唯一**合规来源是本地 `_ref/contributions/
  china-admin-boundaries/skill/data/`（省 34 / 市 375 / 县 2891，
  EPSG:4326 GeoJSON，含 adcode 字段），按 **adcode 唯一键**取几何；
  OSM / Natural Earth / GADM 一律不得用于中国行政区划边界（知识库
  china-admin-boundaries 行明文）。`_ref/` 缺失时报错指向
  docs/knowledge/README.md「出处」节的重新抓取程序。
- `osm_boundary_aoi` 提供同形态的 Overpass 边界查询，**仅限非中国
  研究区**：country 指向中国即拒绝（ComplianceError）。
- 两者产物一律是**物化后的 GeoJSON geometry dict**，由调用方写进
  spec.aoi —— spec 永不持有活引用（D4）；OSM 数据的 osm3s.timestamp
  由调用方记录到 spec.note / sidecar（osm_boundary_aoi 的 meta 返回值
  提供），绝不嵌进 aoi 几何 dict（否则指纹被数据时戳污染）。

依赖纪律：geopandas 懒加载，模块顶层只有标准库与 gis 内部模块。
"""

from __future__ import annotations

import json
from pathlib import Path

from . import geoenv

# 本地合规边界数据默认目录（geocode.json 的 aoi.admin_data_dir 可覆盖）。
_DEFAULT_ADMIN_DIR = (
    geoenv.ROOT / "_ref" / "contributions" / "china-admin-boundaries" / "skill" / "data"
)

# 唯一键查找顺序：县 → 市 → 省（adcode 6 位，级别按前两位/文件天然互斥）。
_ADMIN_FILES = ("china_county.geojson", "china_city.geojson", "china_province.geojson")

# country 参数的中国标识（D2 守卫）：命中即拒绝 OSM 边界查询。
_CN_MARKERS = {"cn", "chn", "156", "中国", "中华人民共和国"}


class ComplianceError(ValueError):
    """合规边界被触碰（D2）。消息说明合法路径。"""


def admin_data_dir() -> Path:
    """合规边界数据目录：geocode.json aoi.admin_data_dir > 默认 _ref 路径。"""
    override = (geoenv.load_config().get("aoi") or {}).get("admin_data_dir")
    return Path(override) if override else _DEFAULT_ADMIN_DIR


def _read_admin_file(path: Path):
    import geopandas as gpd

    gdf = gpd.read_file(path)
    if "adcode" not in gdf.columns:
        raise RuntimeError(
            f"合规边界数据缺 adcode 字段：{path}\n"
            "  该文件应来自 china-admin-boundaries 收录（见 docs/knowledge/README.md）；\n"
            "  请按「出处」节的程序重新抓取，不要手工替换为其他来源。"
        )
    return gdf


def admin_aoi(adcode: str | int, *, data_dir: str | Path | None = None) -> dict:
    """
    adcode → GeoJSON geometry dict（EPSG:4326，物化结果，可直接进 spec.aoi）。

    adcode 唯一键纪律：三份文件中恰好命中一条；0 条或多于 1 条都报可读错误。
    data_dir 缺省走 admin_data_dir()（geocode.json 可覆盖；单测注入 fixture 用）。
    """
    d = Path(data_dir) if data_dir else admin_data_dir()
    if not d.is_dir():
        raise FileNotFoundError(
            f"中国行政区划边界数据目录缺失：{d}\n"
            "  这是本项目中国边界（AOI）的唯一合规来源（D2 硬约束）。\n"
            "  恢复程序：读 docs/knowledge/README.md「出处」节 —— 按上游\n"
            "  GeoCode-Release 的 commit 重新 sparse-checkout 抓取到 _ref/，\n"
            "  或在 geocode.json 的 aoi.admin_data_dir 指向既有数据目录。\n"
            "  禁止改用 OSM / Natural Earth / GADM 等来源。"
        )
    code = str(adcode).strip()
    if not (code.isdigit() and len(code) == 6):
        raise ValueError(
            f"adcode 应为 6 位数字字符串，收到 {adcode!r}。\n"
            "  例：110000（北京）、110100（城区）、110101（东城区）。"
        )
    for fname in _ADMIN_FILES:
        path = d / fname
        if not path.is_file():
            raise FileNotFoundError(
                f"合规边界数据文件缺失：{path}\n"
                "  恢复程序见 docs/knowledge/README.md「出处」节。"
            )
        gdf = _read_admin_file(path)
        hits = gdf[gdf["adcode"].astype(str) == code]
        if len(hits) > 1:
            raise RuntimeError(
                f"adcode 唯一键被破坏：{code} 在 {fname} 中命中 {len(hits)} 条。\n"
                "  数据源应保证 adcode 唯一；请按「出处」节程序重新抓取。"
            )
        if len(hits) == 1:
            return hits.geometry.iloc[0].__geo_interface__
    raise ValueError(
        f"adcode {code} 未在合规边界数据中找到（查过：{', '.join(_ADMIN_FILES)}，目录 {d}）。\n"
        "  检查：级别（省 110000 / 市 110100 / 县 110101）与数字是否正确。\n"
        "  数据范围见 docs/knowledge/README.md china-admin-boundaries 条目。"
    )


def admin_counts(*, data_dir: str | Path | None = None) -> dict[str, int]:
    """三份边界文件的要素数（自检用：省 34 / 市 375 / 县 2891）。"""
    d = Path(data_dir) if data_dir else admin_data_dir()
    out: dict[str, int] = {}
    for fname in _ADMIN_FILES:
        out[fname] = int(len(_read_admin_file(d / fname)))
    return out


# ---------------------------------------------------------------------------
# Overpass 边界查询（仅限非中国研究区，D2）
# ---------------------------------------------------------------------------

def osm_boundary_aoi(
    name: str,
    *,
    admin_level: int | None = None,
    country: str | None = None,
    timeout: int = 90,
    transport=None,
    return_meta: bool = False,
):
    """
    按 OSM administrative boundary 名称取**非中国**研究区的边界几何。

    返回物化 GeoJSON geometry dict（可直接进 spec.aoi）；return_meta=True 时
    返回 (geometry, meta)，meta 含 osm3s_timestamp / osm_id —— 记到 spec.note
    或 sidecar（D4），不要塞进 aoi 几何 dict。

    country 守卫（D2 硬约束）：指向中国即抛 ComplianceError —— 中国行政区
    边界一律走 admin_aoi（本地合规数据）。
    """
    marker = (country or "").strip().lower()
    if marker in _CN_MARKERS:
        raise ComplianceError(
            f"osm_boundary_aoi 拒绝中国边界查询（country={country!r}）—— D2 合规硬约束。\n"
            "  中国行政区划边界只允许从本地合规数据取：gis.aoi.admin_aoi(adcode)。\n"
            "  本地数据缺失时的恢复程序见 docs/knowledge/README.md「出处」节。"
        )

    from . import osm as _osm

    tags: dict = {"boundary": "administrative", "name": name}
    if admin_level is not None:
        tags["admin_level"] = str(admin_level)
    ql = _osm.build_query(("relation",), tags, None, timeout=timeout)
    raw = _osm.query_osm(ql, timeout=float(timeout), transport=transport)
    ts = (raw.get("osm3s") or {}).get("timestamp_osm_base") or ""

    hits = [el for el in (raw.get("elements") or [])
            if el.get("type") == "relation" and (el.get("tags") or {}).get("name") == name]
    if not hits:
        raise ValueError(
            f"OSM 中未找到名为 {name!r} 的行政边界 relation"
            + (f"（admin_level={admin_level}）" if admin_level else "")
            + "。\n  检查名称拼写（OSM name 为当地官方名称）；"
              "或改用 admin_aoi(adcode)（仅限中国）。"
        )
    el = min(hits, key=lambda e: int(e.get("id") or 0))  # 重名取最小 id，确定性

    geom, reason = _osm._assemble_relation(el)
    if geom is None:
        raise ValueError(
            f"OSM 边界 {name!r}（relation {el.get('id')}）装配失败：{reason}。\n"
            "  该边界的 outer 环无法闭合为多边形；换更高层级的边界或用 bbox 圈定研究区。"
        )
    geometry = geom.__geo_interface__
    if return_meta:
        return geometry, {"osm3s_timestamp": ts, "osm_id": el.get("id"),
                          "osm_type": "relation", "name": name}
    return geometry


def save_aoi_note(geometry: dict, meta: dict) -> str:
    """把 OSM 边界的元信息拼成 spec.note 片段（D4：时戳进 note，不进 aoi）。"""
    return json.dumps({"osm3s_timestamp": meta.get("osm3s_timestamp", ""),
                       "osm_id": meta.get("osm_id"), "osm_type": "relation"},
                      ensure_ascii=False, sort_keys=True)
