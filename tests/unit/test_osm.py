"""OSM / Overpass 矢量源（C8 A1/A2/A3/A7）。

全部离线：transport 注入假实现（不发真实请求）、fixture 为真实录制响应
（北京非边界水系，≤200 要素 <500KB，D2 合规）。覆盖：
- 查询构造纯函数确定性（A1）
- 解析装配：way→面/线、带洞 relation、skipped 留痕、osm id 排序、CRS=4326（A2）
- 429/504 指数退避、endpoint 镜像、GEOCODE_OSM_REFRESH 强刷（A2/D6/D5）
- GPKG 交付：读回一致、sidecar、hash8 确定、幂等复用（A3/D5）
- 合规守卫：osm 模块无中国边界查询路径；fixture 无行政边界要素（A7/D2）
"""

import ast
import json
import pathlib
import unittest
from unittest import mock

from gis import osm as osm_mod
from gis.osm import (
    MAX_RETRIES, REFRESH_ENV, VECTOR_VERSION, build_query, cache_digest,
    deliver_hash, fetch_osm, parse_overpass_response, query_osm,
)

ROOT = pathlib.Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "tests" / "unit" / "fixtures" / "osm_water_recorded.json"

BBOX = (116.30, 39.90, 116.35, 39.95)  # (west, south, east, north)


def _recorded() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _fake_transport(payload, statuses=(200,)):
    """假 transport：按序列吐状态码，最后返回 payload。记录调用。"""
    seq = list(statuses)
    calls = []

    def tr(endpoint, ql, timeout):
        calls.append({"endpoint": endpoint, "ql": ql})
        if len(seq) > 1:
            return seq.pop(0), ""
        return seq[0], payload if isinstance(payload, str) else json.dumps(payload)

    tr.calls = calls
    return tr


class QueryBuildTest(unittest.TestCase):
    """A1：查询构造纯函数，同参同串（字节级）。"""

    def test_deterministic_bytes(self):
        q1 = build_query(("way", "relation"), {"natural": "water"}, BBOX, timeout=60)
        q2 = build_query(("way", "relation"), {"natural": "water"}, BBOX, timeout=60)
        self.assertEqual(q1, q2)
        self.assertTrue(q1.startswith("[out:json][timeout:60];"))
        self.assertTrue(q1.endswith(";out geom;"))

    def test_tag_order_canonicalized(self):
        # dict 键插入顺序不同 → 同一规范串（归一化查询的前提）
        q1 = build_query(("way",), {"leisure": "park", "natural": "water"}, None)
        q2 = build_query(("way",), {"natural": "water", "leisure": "park"}, None)
        self.assertEqual(q1, q2)
        self.assertIn('["leisure"="park"]', q1)
        self.assertIn('["natural"="water"]', q1)
        self.assertLess(q1.index("leisure"), q1.index("natural"))

    def test_multivalue_regex_sorted(self):
        q1 = build_query(("node",), {"leisure": ["park", "garden"]}, None)
        q2 = build_query(("node",), {"leisure": ["garden", "park"]}, None)
        self.assertEqual(q1, q2)
        self.assertIn('["leisure"~"^(garden|park)$"]', q1)

    def test_bbox_order_and_validation(self):
        q = build_query(("way",), None, BBOX)
        # Overpass QL 的 bbox 顺序是 (south, west, north, east)
        self.assertIn("(39.900000,116.300000,39.950000,116.350000)", q)
        with self.assertRaises(ValueError):
            build_query(("way",), None, (116.50, 39.90, 116.30, 39.95))  # 西>东
        with self.assertRaises(ValueError):
            build_query(("way",), None, (116.30, 39.95, 116.35, 39.90))  # 南>北

    def test_selector_validation_and_nwr(self):
        with self.assertRaises(ValueError):
            build_query(("area",), None, None)
        with self.assertRaises(ValueError):
            build_query((), None, None)
        q = build_query("nwr", {"natural": "water"}, None)
        for w in ("node", "way", "relation"):
            self.assertIn(f'{w}["natural"="water"]', q)


class ParseAssembleTest(unittest.TestCase):
    """A2：真实 fixture 的装配 + 内联畸形要素的 skipped 留痕。"""

    def test_recorded_fixture_way_polygon_sort_crs(self):
        parsed = parse_overpass_response(_recorded())
        gdf = parsed["gdf"]
        self.assertEqual(gdf.crs.to_epsg(), 4326)
        self.assertEqual(parsed["element_count"], len(_recorded()["elements"]))
        self.assertGreater(len(gdf), 0)
        # osm id 确定性排序：同类型按 id 升序，类型序 node < way < relation
        keys = [(osm_mod._TYPE_RANK[t], i) for t, i in
                zip(gdf["osm_type"], gdf["osm_id"])]
        self.assertEqual(keys, sorted(keys))
        # 北京水系：闭合 way → Polygon
        ways = gdf[gdf["osm_type"] == "way"]
        self.assertTrue((ways.geometry.geom_type == "Polygon").all())
        # 真实 relation（multipolygon）→ Polygon/MultiPolygon
        rels = gdf[gdf["osm_type"] == "relation"]
        self.assertTrue(len(rels) > 0)
        self.assertTrue((rels.geometry.geom_type.isin(["Polygon", "MultiPolygon"])).all())

    def test_open_way_becomes_linestring(self):
        raw = {"osm3s": {"timestamp_osm_base": "2026-10-07T00:00:00Z"}, "elements": [
            {"type": "way", "id": 11, "geometry": [
                {"lat": 39.93, "lon": 116.31}, {"lat": 39.94, "lon": 116.33}],
             "tags": {"waterway": "stream"}},
        ]}
        gdf = parse_overpass_response(raw)["gdf"]
        self.assertEqual(gdf.iloc[0].geometry.geom_type, "LineString")

    def test_relation_with_hole(self):
        raw = {"osm3s": {"timestamp_osm_base": "2026-10-07T00:00:00Z"}, "elements": [
            {"type": "relation", "id": 30, "members": [
                {"type": "way", "ref": 101, "role": "outer", "geometry": [
                    {"lat": 40.00, "lon": 116.40}, {"lat": 40.02, "lon": 116.40},
                    {"lat": 40.02, "lon": 116.44}, {"lat": 40.00, "lon": 116.40}]},
                {"type": "way", "ref": 102, "role": "inner", "geometry": [
                    {"lat": 40.01, "lon": 116.41}, {"lat": 40.015, "lon": 116.41},
                    {"lat": 40.015, "lon": 116.43}, {"lat": 40.01, "lon": 116.41}]}],
             "tags": {"natural": "water"}},
        ]}
        gdf = parse_overpass_response(raw)["gdf"]
        geom = gdf.iloc[0].geometry
        self.assertEqual(geom.geom_type, "Polygon")
        self.assertEqual(len(geom.interiors), 1, "inner 环应成洞")

    def test_skipped_counted_not_silent(self):
        raw = {"osm3s": {"timestamp_osm_base": "2026-10-07T00:00:00Z"}, "elements": [
            {"type": "way", "id": 20, "tags": {"natural": "water"}},   # 无 geometry
            {"type": "relation", "id": 31, "members": [
                {"type": "way", "ref": 103, "role": "inner", "geometry": [
                    {"lat": 39.5, "lon": 116.1}, {"lat": 39.5, "lon": 116.2}]}],
             "tags": {"type": "multipolygon"}},                        # 无 outer
            {"type": "relation", "id": 32, "members": [
                {"type": "way", "ref": 104, "role": "outer", "geometry": [
                    {"lat": 39.6, "lon": 116.1}, {"lat": 39.6, "lon": 116.2}]}],
             "tags": {"natural": "water"}},                            # outer 拼不闭合
        ]}
        parsed = parse_overpass_response(raw)
        reasons = [s["reason"] for s in parsed["skipped"]]
        self.assertEqual(len(parsed["skipped"]), 3)
        self.assertIn("way_without_geometry", reasons)
        self.assertIn("relation_without_outer", reasons)
        self.assertIn("relation_unclosed_outer", reasons)
        self.assertEqual(len(parsed["gdf"]), 0)   # 全被跳过，不静默丢弃

    def test_inner_not_contained_skips(self):
        raw = {"osm3s": {"timestamp_osm_base": "2026-10-07T00:00:00Z"}, "elements": [
            {"type": "relation", "id": 33, "members": [
                {"type": "way", "ref": 201, "role": "outer", "geometry": [
                    {"lat": 40.00, "lon": 116.40}, {"lat": 40.02, "lon": 116.40},
                    {"lat": 40.02, "lon": 116.44}, {"lat": 40.00, "lon": 116.40}]},
                {"type": "way", "ref": 202, "role": "inner", "geometry": [
                    {"lat": 41.00, "lon": 117.40}, {"lat": 41.01, "lon": 117.40},
                    {"lat": 41.01, "lon": 117.44}, {"lat": 41.00, "lon": 117.40}]}],
             "tags": {"natural": "water"}},
        ]}
        parsed = parse_overpass_response(raw)
        self.assertEqual([s["reason"] for s in parsed["skipped"]],
                         ["inner_not_contained"])


class FetchRetryTest(unittest.TestCase):
    """A2/D6：429/504 指数退避 ≤2、endpoint 镜像、GEOCODE_OSM_REFRESH。

    endpoint 列表 mock 成单一确定值 —— 单测不得依赖本地 geocode.json。
    """

    EP = "https://overpass.example.test/api/interpreter"

    def setUp(self):
        patcher = mock.patch.object(osm_mod, "_endpoints", lambda: (self.EP,))
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_retry_on_429_then_success(self):
        tr = _fake_transport(_recorded(), statuses=(429, 200))
        sleeps = []
        raw = query_osm("q", transport=tr, _sleep=sleeps.append)
        self.assertEqual(len(tr.calls), 2)
        self.assertEqual(tr.calls[0]["endpoint"], self.EP)
        self.assertEqual(sleeps, [osm_mod._BACKOFF_BASE ** 1])

    def test_retry_exhausted_raises_with_hints(self):
        tr = _fake_transport("", statuses=(429, 429, 429))
        with self.assertRaises(osm_mod.OverpassError) as ctx:
            query_osm("q", transport=tr, _sleep=lambda s: None)
        msg = str(ctx.exception)
        self.assertIn("镜像", msg)
        self.assertIn("缩小查询", msg)
        self.assertEqual(len(tr.calls), MAX_RETRIES + 1)

    def test_504_retryable_then_mirror_fallback(self):
        # 同端点先退避重试至多 MAX_RETRIES 次，仍失败才落镜像
        eps = [self.EP, "https://mirror.example.test/api/interpreter"]
        calls = []

        def tr(endpoint, ql, timeout):
            calls.append(endpoint)
            if endpoint == self.EP:
                return 504, ""
            return 200, json.dumps(_recorded())

        with mock.patch.object(osm_mod, "_endpoints", lambda: tuple(eps)):
            raw = query_osm("q", transport=tr, _sleep=lambda s: None)
        self.assertEqual(len(raw["elements"]), 25)
        self.assertEqual(calls, [self.EP] * (MAX_RETRIES + 1) + eps[1:],
                         "504 应先同端点退避重试，再落到镜像 endpoint")

    def test_400_not_retryable_reports_body(self):
        tr = _fake_transport("<html>parse error</html>", statuses=(400,))
        with self.assertRaises(osm_mod.OverpassError) as ctx:
            query_osm("q", transport=tr, _sleep=lambda s: None)
        self.assertIn("parse error", str(ctx.exception))
        self.assertEqual(len(tr.calls), 1)


class GpkgDeliverTest(unittest.TestCase):
    """A3/D5：GPKG 读回一致、sidecar 完整、hash8 确定、幂等复用、强刷。

    交付目录隔离到临时目录 —— 单测不读写真实 data/deliver，且
    多轮运行（幂等复用语义）不会互相污染。
    """

    def setUp(self):
        import tempfile

        tmp = tempfile.mkdtemp(prefix="geocode_ut_deliver_")
        self.deliver_dir = pathlib.Path(tmp)
        patcher = mock.patch.object(osm_mod.geoenv, "DELIVER_DIR", self.deliver_dir)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher2 = mock.patch.object(osm_mod, "_endpoints",
                                     lambda: ("https://overpass.example.test/api/interpreter",))
        patcher2.start()
        self.addCleanup(patcher2.stop)

    def test_full_chain_deliver_and_reuse(self):
        tr = _fake_transport(_recorded())
        r1 = fetch_osm(query_id="ut_osm_chain", tags={"natural": "water"},
                       bbox=BBOX, transport=tr)
        self.assertEqual(r1["reused"], False)
        self.assertEqual(r1["feature_count"], 25)
        self.assertEqual(r1["skipped_count"], 0)
        self.assertEqual(r1["osm3s_timestamp"],
                         _recorded()["osm3s"]["timestamp_osm_base"])
        # sidecar 文件键完整（D5：查询/endpoint/时戳/计数/hash 输入）
        side = json.loads(pathlib.Path(r1["sidecar"]).read_text(encoding="utf-8"))
        for key in ("query", "endpoint", "osm3s_timestamp", "feature_count",
                    "skipped", "hash8", "hash_input", "cache_digest",
                    "vector_version"):
            self.assertIn(key, side)
        self.assertEqual(side["vector_version"], VECTOR_VERSION)
        # GPKG 读回：要素数一致、CRS=4326
        import geopandas as gpd
        back = gpd.read_file(r1["gpkg"], layer=r1["layer"])
        self.assertEqual(len(back), 25)
        self.assertEqual(back.crs.to_epsg(), 4326)

        # 同输入重复导出：hash 相同、幂等复用、不再发请求
        r2 = fetch_osm(query_id="ut_osm_chain", tags={"natural": "water"},
                       bbox=BBOX, transport=tr)
        self.assertTrue(r2["reused"])
        self.assertEqual(r1["gpkg"], r2["gpkg"])
        self.assertEqual(len(tr.calls), 1)
        # 文件名 = {id}.{hash8}.gpkg
        self.assertTrue(pathlib.Path(r1["gpkg"]).name.startswith("ut_osm_chain."))

    def test_refresh_env_forces_refetch(self):
        tr = _fake_transport(_recorded())
        fetch_osm(query_id="ut_osm_refresh", tags={"natural": "water"},
                  bbox=BBOX, transport=tr)
        self.assertEqual(len(tr.calls), 1)
        with mock.patch.dict("os.environ", {REFRESH_ENV: "1"}):
            r = fetch_osm(query_id="ut_osm_refresh", tags={"natural": "water"},
                          bbox=BBOX, transport=tr)
        self.assertFalse(r["reused"])
        self.assertEqual(len(tr.calls), 2, "GEOCODE_OSM_REFRESH 应绕过缓存")

    def test_hash8_deterministic_components(self):
        q = build_query(("way",), {"natural": "water"}, BBOX)
        h1 = deliver_hash(q, None, "2026-10-07T00:00:00Z")
        h2 = deliver_hash(q, None, "2026-10-07T00:00:00Z")
        self.assertEqual(h1, h2)
        self.assertEqual(len(h1), 8)
        self.assertNotEqual(h1, deliver_hash(q, None, "2026-10-08T00:00:00Z"),
                            "数据时戳进 hash（数据更新 → 新交付文件）")
        self.assertNotEqual(deliver_hash(q, {"type": "Point"}, "t"),
                            deliver_hash(q, None, "t"), "AOI 摘要进 hash")
        self.assertNotEqual(h1, cache_digest(q, None),
                            "缓存键不含数据时戳（命中即复用既有版本）")


class ComplianceGuardTest(unittest.TestCase):
    """A7/D2：OSM 通用客户端不携带中国边界查询路径；fixture 无行政边界要素。"""

    def test_osm_module_has_no_china_boundary_path(self):
        # A7/D2：OSM 通用客户端不得携带中国边界**查询路径**的指示物
        # （adcode 纪律、本地合规数据路径、边界文件名）。中国边界的唯一
        # 合法消费点是 gis/aoi.py；gis/osm.py 里的"合规说明"文字本身不是
        # 查询路径，故不按字面禁词。
        src = (ROOT / "gis" / "osm.py").read_text(encoding="utf-8")
        low = src.lower()
        for token in ("adcode", "china-admin-boundaries", "china_county",
                      "china_city", "china_province"):
            self.assertNotIn(token, low,
                             f"gis/osm.py 不得出现 {token!r}（中国边界唯一合规来源是本地 _ref）")

    def test_admin_boundary_consumer_is_unique(self):
        # gis/ 下引用 china-admin-boundaries 数据的模块必须只有 gis/aoi.py
        offenders = []
        for p in sorted((ROOT / "gis").glob("*.py")):
            txt = p.read_text(encoding="utf-8")
            if "china-admin-boundaries" in txt and p.name != "aoi.py":
                offenders.append(p.name)
        self.assertEqual(offenders, [])

    def test_fixtures_contain_no_administrative_boundary(self):
        # fixture 只能是中国**非边界**要素（水系等）；出现 boundary=administrative 即违规
        data = json.loads(FIXTURE.read_text(encoding="utf-8"))
        tagged = [e for e in data["elements"]
                  if (e.get("tags") or {}).get("boundary") == "administrative"]
        self.assertEqual(tagged, [])


if __name__ == "__main__":
    unittest.main()
