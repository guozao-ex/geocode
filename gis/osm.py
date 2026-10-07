"""
OSM / Overpass 矢量源（C8 W1）。

链路：
    结构化参数 → 纯函数构造 Overpass QL → urllib 拉取（代理/镜像/429,504 退避）
    → 解析装配为 GeoDataFrame（EPSG:4326，osm id 确定性排序）
    → AOI/范围裁剪 → GPKG 交付（data/deliver/{id}.{hash8}.gpkg + sidecar）。

合规红线（任务书 D2）：本模块是**通用** Overpass 客户端，不内置任何
"中国行政区划边界"的查询路径或示例；中国行政区 AOI 一律走
gis.aoi.admin_aoi（本地合规数据，唯一键纪律）。OSM 边界查询仅限
非中国研究区（见 gis.aoi.osm_boundary_aoi 的 country 守卫）。

依赖纪律：geopandas / shapely 懒加载（函数内 import）——模块顶层只有
标准库与 gis 内部模块，`import gis` 的传递链不因此变重，
tests/unit 的离线守卫与秒级基线不受影响。

多边形装配能力边界（D7）：way（含闭合面）+ relation 的 outer/inner
两级标准装配（含洞）；超出能力的要素跳过并计数留痕（skipped 列表），
禁止静默丢弃。
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from . import geoenv
from .spec import aoi_bbox

# ★ 矢量解析装配逻辑版本。独立于 PROCESSING_VERSION（那个只管栅格像素），
#   只进矢量产物命名（hash8 输入）与 sidecar —— 改装配/解析行为时 +1。
VECTOR_VERSION = 1

# 默认 Overpass endpoint；geocode.json 的 osm.endpoints 列表可覆盖（可加镜像）。
DEFAULT_ENDPOINTS: tuple[str, ...] = ("https://overpass-api.de/api/interpreter",)

# 强制刷新钩子：设为非空且非 "0"/"false" 时绕过缓存重拉（C6 GEOCODE_ARRAY_PATH 先例）。
REFRESH_ENV = "GEOCODE_OSM_REFRESH"

# 429/504 指数退避重试上限（不含首次请求）。
MAX_RETRIES = 2
_RETRYABLE = {429, 504}
_BACKOFF_BASE = 2.0  # 秒；第 n 次重试前等 base**n

# Overpass QL 的 bbox 顺序是 (south, west, north, east)；本模块统一用
# spec.aoi_bbox 的 (west, south, east, north) 约定，构造时换序。

_SELECTOR_WORDS = ("node", "way", "relation")
_TYPE_RANK = {"node": 0, "way": 1, "relation": 2}

Transport = Callable[[str, str, float], tuple[int, str]]
"""transport(endpoint_url, ql_text, timeout) -> (http_status, body_text)。
可注入（tests/unit 用假 transport，不发真实请求）。"""


class OverpassError(RuntimeError):
    """Overpass 拉取失败。消息给人和 agent 看，含可执行出路。"""


# ---------------------------------------------------------------------------
# 查询构造（纯函数，字节级确定性）
# ---------------------------------------------------------------------------

def _quote(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace('"', '\\"')


def _tag_predicates(tags: dict | None) -> list[str]:
    """tag 过滤 dict → 排序后的 QL 谓词序列。list/tuple 值 → 多值正则。"""
    if not tags:
        return []
    preds: list[str] = []
    for key in sorted(tags):
        val = tags[key]
        if isinstance(val, (list, tuple)):
            if not val:
                continue
            alts = "|".join(_quote_re(v) for v in sorted(str(v) for v in val))
            preds.append(f'["{_quote(key)}"~"^({alts})$"]')
        else:
            preds.append(f'["{_quote(key)}"="{_quote(val)}"]')
    return preds


def _quote_re(s: str) -> str:
    return str(s).replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)") \
                 .replace("^", "\\^").replace("$", "\\$").replace("|", "\\|") \
                 .replace(".", "\\.").replace("+", "\\+").replace("?", "\\?") \
                 .replace("[", "\\[").replace("]", "\\]").replace("{", "\\{") \
                 .replace("}", "\\}").replace("*", "\\*")


def build_query(
    selectors: tuple[str, ...] | str,
    tags: dict[str, str | list[str]] | None,
    bbox: tuple[float, float, float, float] | None = None,
    *,
    timeout: int = 60,
) -> str:
    """
    结构化参数 → Overpass QL。**纯函数**：同参同串（字节级）。

    selectors: ("way", "relation") 等 _SELECTOR_WORDS 的非空子集，顺序保留、去重。
    tags:      {"natural": "water"} 精确匹配；{"leisure": ["park","garden"]} 多值。
    bbox:      (west, south, east, north) 经纬度；None = 全球范围。
    """
    if isinstance(selectors, str):
        selectors = (selectors,)
    sels: list[str] = []
    for s in selectors:
        w = str(s).strip().lower()
        if w == "nwr":
            w_list = ["node", "way", "relation"]
        elif w in _SELECTOR_WORDS:
            w_list = [w]
        else:
            raise ValueError(
                f"selectors 含未知要素选择器 {s!r}。可选：node / way / relation / nwr。"
            )
        for w2 in w_list:
            if w2 not in sels:
                sels.append(w2)
    if not sels:
        raise ValueError("selectors 不能为空。至少给一个 node / way / relation。")

    preds = _tag_predicates(tags)
    tail = f"[timeout:{int(timeout)}]" if timeout else ""

    if bbox is not None:
        west, south, east, north = (float(v) for v in bbox)
        if not (west < east and south < north):
            raise ValueError(
                f"bbox 非法：{bbox!r}。约定 (west, south, east, north)，且西<东、南<北。"
            )
        bb = f"({south:.6f},{west:.6f},{north:.6f},{east:.6f})"
    else:
        bb = ""

    body = ";".join(f'{s}{"".join(preds)}{bb}' for s in sels)
    return f"[out:json]{tail};({body};);out geom;"


# ---------------------------------------------------------------------------
# 拉取（urllib + 代理 + 镜像 + 退避）
# ---------------------------------------------------------------------------

def _endpoints() -> tuple[str, ...]:
    eps = (geoenv.load_config().get("osm") or {}).get("endpoints")
    if isinstance(eps, (list, tuple)) and eps:
        return tuple(str(e) for e in eps)
    return DEFAULT_ENDPOINTS


def _default_transport(endpoint: str, ql: str, timeout: float) -> tuple[int, str]:
    """stdlib urllib POST。代理由 apply_proxy_env() 写进环境后 urllib 自动生效。"""
    import urllib.error
    import urllib.request

    geoenv.apply_proxy_env()
    req = urllib.request.Request(
        endpoint, data=ql.encode("utf-8"),
        headers={"Content-Type": "text/plain; charset=utf-8",
                 "User-Agent": "geocode-osm/0.1"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return int(resp.getcode()), resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        body = ""
        try:
            body = e.read().decode("utf-8", "replace")
        except Exception:
            pass
        return int(e.code), body


def query_osm(
    ql: str,
    *,
    timeout: float = 90.0,
    transport: Transport | None = None,
    _sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """
    执行 Overpass 查询，返回解析后的 JSON dict。

    endpoint 列表逐个尝试；429/504 指数退避重试 ≤MAX_RETRIES 次；
    超限抛 OverpassError（消息含等 N 秒 / 换镜像 / 缩小查询 的可执行出路）。
    """
    tr = transport or _default_transport
    attempts: list[dict] = []
    retries = 0
    eps = _endpoints()
    for endpoint in eps:
        attempt = 0
        while True:
            try:
                status, body = tr(endpoint, ql, timeout)
            except Exception as exc:  # 网络异常按可重试处理（与 5xx 同权）
                status, body = 0, f"{type(exc).__name__}: {exc}"
            attempts.append({"endpoint": endpoint, "status": status, "attempt": attempt})
            if status == 200:
                try:
                    return json.loads(body)
                except json.JSONDecodeError as e:
                    raise OverpassError(
                        "Overpass 返回 200 但内容不是合法 JSON"
                        f"（endpoint={endpoint}）：{e}\n"
                        "  试试：换镜像（geocode.json osm.endpoints）或缩小查询。"
                    ) from e
            if status in _RETRYABLE and retries < MAX_RETRIES:
                retries += 1
                delay = _BACKOFF_BASE ** retries
                _sleep(delay)
                attempt += 1
                continue
            break  # 该 endpoint 放弃

    detail = "; ".join(f"{a['endpoint']}#{a['attempt']}={a['status']}" for a in attempts[-6:])
    tail = (body or "").strip().replace("\n", " ")[:200]
    raise OverpassError(
        f"Overpass 拉取失败（重试 {retries} 次后仍不成功）。最近尝试：{detail}\n"
        f"  最后响应片段：{tail or '(空)'}\n"
        "  可执行出路：\n"
        f"    1. 稍等 {_BACKOFF_BASE ** (MAX_RETRIES + 1):.0f} 秒以上再试（429 = 限流，504 = 网关超时）；\n"
        "    2. 在 geocode.json 的 osm.endpoints 加镜像并置于首位；\n"
        "    3. 缩小查询（更小 bbox / 更少 tag / 更长 timeout）。"
    )


# ---------------------------------------------------------------------------
# 解析与装配（EPSG:4326，osm id 确定性排序）
# ---------------------------------------------------------------------------

def _pt(lon, lat) -> tuple[float, float]:
    return (float(lon), float(lat))


def _stitch_rings(parts: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """
    共享端点的折线段 → 闭合环序列（确定性：按输入顺序拼接，端点按 1e-7 吸附）。
    拼不回的段留在返回值之外 —— 由调用方按 skipped 留痕。
    """
    def key(p):
        return (round(p[0], 7), round(p[1], 7))

    remaining = [list(seg) for seg in parts if len(seg) >= 2]
    rings: list[list[tuple[float, float]]] = []
    while remaining:
        ring = remaining.pop(0)
        extended = True
        while extended and key(ring[0]) != key(ring[-1]):
            extended = False
            end = key(ring[-1])
            for i, seg in enumerate(remaining):
                if key(seg[0]) == end:
                    ring.extend(seg[1:])
                    remaining.pop(i)
                    extended = True
                    break
                if key(seg[-1]) == end:
                    ring.extend(list(reversed(seg))[1:])
                    remaining.pop(i)
                    extended = True
                    break
        if key(ring[0]) == key(ring[-1]) and len(ring) >= 4:
            rings.append(ring)
    return rings


def _assemble_way(el: dict):
    """闭合 way → Polygon，开放 way → LineString。返回 (geom, skip_reason)。"""
    from shapely.geometry import LineString, Polygon

    geo = el.get("geometry") or []
    coords = [_pt(g["lon"], g["lat"]) for g in geo]
    if len(coords) < 2:
        return None, "way_without_geometry"
    if len(coords) >= 4 and coords[0] == coords[-1]:
        return Polygon(coords), None
    return LineString(coords), None


def _assemble_relation(el: dict):
    """relation 的 outer/inner 两级标准装配（含洞）。返回 (geom, skip_reason)。"""
    from shapely.geometry import MultiPolygon, Polygon
    from shapely.ops import polygonize

    members = el.get("members") or []
    def mcoords(m):
        return [_pt(g["lon"], g["lat"]) for g in (m.get("geometry") or [])]

    outer_segs = [c for m in members if m.get("role") == "outer" and len(c := mcoords(m)) >= 2]
    inner_segs = [c for m in members if m.get("role") == "inner" and len(c := mcoords(m)) >= 2]
    if not outer_segs:
        return None, "relation_without_outer"

    outer_rings = _stitch_rings(outer_segs)
    if not outer_rings:
        return None, "relation_unclosed_outer"

    outer_polys = list(polygonize([ring for ring in outer_rings]))
    if not outer_polys:
        return None, "relation_unclosed_outer"

    inner_polys = list(polygonize([ring for ring in _stitch_rings(inner_segs)])) \
        if inner_segs else []

    with_holes: list[Polygon] = list(outer_polys)
    for hole in inner_polys:
        pt = hole.representative_point()
        host = next((p for p in with_holes if p.covers(pt)), None)
        if host is None:
            return None, "inner_not_contained"
        with_holes = [p for p in with_holes if not p.equals(host)]
        with_holes.append(Polygon(host.exterior, list(host.interiors) + [hole.exterior]))

    if len(with_holes) == 1:
        return with_holes[0], None
    return MultiPolygon(with_holes), None


def parse_overpass_response(raw: dict) -> dict:
    """
    Overpass JSON → {"gdf": GeoDataFrame, "skipped": [...], "osm3s_timestamp": str,
    "element_count": int}。按 (类型序, osm id) 确定性排序；CRS = EPSG:4326。
    """
    import geopandas as gpd
    from shapely.geometry import LineString, Point, Polygon

    elements = raw.get("elements") or []
    ts = (raw.get("osm3s") or {}).get("timestamp_osm_base") or ""
    skipped: list[dict] = []
    rows: list[dict] = []

    for el in elements:
        etype = el.get("type")
        eid = el.get("id")
        tags = el.get("tags") or {}
        base = {"osm_id": eid, "osm_type": etype,
                "name": tags.get("name") or "", "tags": json.dumps(tags, ensure_ascii=False, sort_keys=True)}
        try:
            if etype == "node":
                if el.get("lon") is None or el.get("lat") is None:
                    raise ValueError("node_without_coordinates")
                geom = Point(_pt(el["lon"], el["lat"]))
            elif etype == "way":
                geom, reason = _assemble_way(el)
                if geom is None:
                    raise ValueError(reason or "way_skipped")
            elif etype == "relation":
                geom, reason = _assemble_relation(el)
                if geom is None:
                    raise ValueError(reason or "relation_skipped")
            else:
                raise ValueError(f"unsupported_type:{etype}")
        except Exception as exc:
            skipped.append({"osm_type": etype, "osm_id": eid, "reason": str(exc)})
            continue
        rows.append({**base, "geometry": geom})

    rows.sort(key=lambda r: (_TYPE_RANK.get(r["osm_type"], 9), r["osm_id"]))
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326") if rows \
        else gpd.GeoDataFrame(columns=["osm_id", "osm_type", "name", "tags", "geometry"],
                             geometry="geometry", crs="EPSG:4326")
    return {"gdf": gdf, "skipped": skipped, "osm3s_timestamp": ts,
            "element_count": len(elements)}


def clip_gdf(gdf, clip: dict | None) -> tuple[Any, int]:
    """AOI/范围裁剪：几何与 clip GeoJSON 求交，空结果丢弃。返回 (gdf, 丢弃数)。"""
    if not clip:
        return gdf, 0
    from shapely.geometry import shape

    clip_geom = shape(clip)
    keep, dropped = [], 0
    for _, row in gdf.iterrows():
        try:
            g2 = row.geometry.intersection(clip_geom)
        except Exception:
            dropped += 1
            continue
        if g2.is_empty:
            dropped += 1
            continue
        row = row.copy()
        row["geometry"] = g2
        keep.append(row)
    if not keep:
        return gdf.iloc[0:0], dropped
    import geopandas as gpd
    return gpd.GeoDataFrame(keep, geometry="geometry", crs=gdf.crs), dropped


# ---------------------------------------------------------------------------
# 命名与缓存（D5）
# ---------------------------------------------------------------------------

def aoi_digest(clip: dict | None) -> str:
    """AOI 摘要：clip GeoJSON 的规范 JSON sha256（无 clip 用固定占位）。"""
    if not clip:
        return hashlib.sha256(b"no-clip").hexdigest()
    blob = json.dumps(clip, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def deliver_hash(ql: str, clip: dict | None, osm_timestamp: str) -> str:
    """hash8 = sha256(归一化查询 + AOI 摘要 + osm3s.timestamp + VECTOR_VERSION)[:8]。"""
    payload = "\n".join([ql, aoi_digest(clip), osm_timestamp,
                         f"VECTOR_VERSION={VECTOR_VERSION}"])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


def cache_digest(ql: str, clip: dict | None) -> str:
    """缓存查找键：不含 osm3s.timestamp（命中即复用既有数据版本）。"""
    payload = "\n".join([ql, aoi_digest(clip), f"VECTOR_VERSION={VECTOR_VERSION}"])
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:8]


def _refresh_forced() -> bool:
    v = os.environ.get(REFRESH_ENV, "").strip().lower()
    return bool(v) and v not in ("0", "false")


def _layer_name(query_id: str) -> str:
    keep = [c if (c.isalnum() or c in "-_") else "-" for c in query_id]
    return ("".join(keep).strip("-") or "osm_layer")[:60]


def deliver_gpkg(gdf, *, query_id: str, hash8: str, sidecar: dict) -> tuple[Path, Path, bool]:
    """
    GPKG 落盘：data/deliver/{id}.{hash8}.gpkg + 同名 .json sidecar。
    已存在 → 幂等复用（返回 reused=True），不重写。
    """
    gpkg = geoenv.data_path("deliver", f"{query_id}.{hash8}.gpkg")
    side = gpkg.with_suffix(".json")
    if gpkg.is_file() and side.is_file():
        return gpkg, side, True
    gdf.to_file(gpkg, layer=_layer_name(query_id), driver="GPKG", engine="pyogrio")
    side.write_text(json.dumps(sidecar, ensure_ascii=False, indent=2) + "\n",
                    encoding="utf-8")
    return gpkg, side, False


def _find_cached(query_id: str, cdigest: str) -> Path | None:
    """按 sidecar 里的 cache_digest 找既有交付（同查询同 AOI → 复用）。"""
    deliver = geoenv.DELIVER_DIR
    for side in sorted(deliver.glob(f"{query_id}.*.json")):
        try:
            meta = json.loads(side.read_text(encoding="utf-8"))
        except Exception:
            continue
        if meta.get("cache_digest") == cdigest:
            gpkg = deliver / (side.stem + ".gpkg")
            if gpkg.is_file():
                return gpkg
    return None


# ---------------------------------------------------------------------------
# 一体化入口
# ---------------------------------------------------------------------------

def fetch_osm(
    *,
    selectors: tuple[str, ...] | str = ("way", "relation"),
    tags: dict[str, str | list[str]] | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    clip: dict | None = None,
    query_id: str = "osm_export",
    timeout: int = 60,
    transport: Transport | None = None,
) -> dict:
    """
    全链路：构造 QL → 拉取 → 解析装配 → 裁剪 → GPKG 交付。

    clip: 裁剪用 GeoJSON geometry；bbox 缺省时由 clip 推导外接框。
    返回 dict：query/gpkg/sidecar/hash8/feature_count/skipped/... （见键）。
    """
    if clip is not None and bbox is None:
        bbox = aoi_bbox(clip)
    ql = build_query(selectors, tags, bbox, timeout=timeout)
    cdigest = cache_digest(ql, clip)

    if not _refresh_forced():
        cached = _find_cached(query_id, cdigest)
        if cached is not None:
            side = cached.with_suffix(".json")
            meta = json.loads(side.read_text(encoding="utf-8"))
            meta.update({"query": ql, "reused": True,
                         "gpkg": str(cached), "sidecar": str(side),
                         "layer": _layer_name(query_id)})
            return meta

    raw = query_osm(ql, timeout=float(timeout), transport=transport)
    parsed = parse_overpass_response(raw)
    gdf, dropped = clip_gdf(parsed["gdf"], clip)
    ts = parsed["osm3s_timestamp"]
    hash8 = deliver_hash(ql, clip, ts)
    sidecar = {
        "hash8": hash8,
        "query": ql,
        "endpoint": _endpoints()[0],
        "osm3s_timestamp": ts,
        "feature_count": int(len(gdf)),
        "skipped": parsed["skipped"],
        "skipped_count": len(parsed["skipped"]),
        "element_count": parsed["element_count"],
        "clipped_away": dropped,
        "hash_input": {"aoi_digest": aoi_digest(clip), "vector_version": VECTOR_VERSION},
        "cache_digest": cdigest,
        "vector_version": VECTOR_VERSION,
        "reused": False,
    }
    gpkg, side, _ = deliver_gpkg(gdf, query_id=query_id, hash8=hash8, sidecar=sidecar)
    sidecar.update({"gpkg": str(gpkg), "sidecar": str(side),
                    "layer": _layer_name(query_id)})
    return sidecar
