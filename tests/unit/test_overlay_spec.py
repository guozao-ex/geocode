"""OverlaySpec 矢量叠加契约（C8 A5/A6 离线侧）。

覆盖：构造校验与序列化往返、frozen 呈现层语义（指纹归属守卫在
test_spec_fingerprint.py，金指纹锚定）、两 bridge 样式参数同源守卫
（签名 + emit_map 分发点静态扫描，LayoutSpec 守卫同款）。
"""

import ast
import dataclasses
import inspect
import pathlib
import unittest

from gis import emit as emit_mod
from gis import arcpy_bridge, qgis_bridge
from gis.spec import OverlaySpec, SpecError

ROOT = pathlib.Path(__file__).resolve().parents[2]


class OverlaySpecContractTest(unittest.TestCase):
    def test_defaults(self):
        ov = OverlaySpec(source="data/deliver/x.gpkg")
        self.assertEqual(ov.color, "#3388ff")
        self.assertEqual(ov.width, 2.0)
        self.assertEqual(ov.opacity, 1.0)
        self.assertIsNone(ov.fill_color)
        self.assertIsNone(ov.label_field)

    def test_frozen_dataclass(self):
        ov = OverlaySpec(source="x.gpkg")
        self.assertTrue(dataclasses.is_dataclass(ov))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            ov.color = "#ff0000"

    def test_validation_rejects_bad_values(self):
        for kw in (
            {"width": 0},
            {"width": -1.0},
            {"opacity": 1.5},
            {"opacity": -0.1},
            {"color": ""},
            {"fill_color": "   "},
        ):
            with self.subTest(kw=kw):
                with self.assertRaises(SpecError):
                    OverlaySpec(source="x.gpkg", **kw)
        # source 校验单独覆盖
        for src in ("", "   ", None):
            with self.subTest(source=src):
                with self.assertRaises(SpecError):
                    OverlaySpec(source=src)

    def test_dict_round_trip_and_absent_keys(self):
        ov = OverlaySpec(source="data/deliver/x.gpkg", color="#ff0000",
                         width=3.5, opacity=0.8, fill_color="#00ff00",
                         label_field="name")
        self.assertEqual(OverlaySpec.from_dict(ov.to_dict()), ov)
        # 缺省可选键整个缺席（与指纹 payload 缺席语义同款纪律）
        d = OverlaySpec(source="x.gpkg").to_dict()
        self.assertNotIn("fill_color", d)
        self.assertNotIn("label_field", d)
        self.assertEqual(OverlaySpec.from_dict(d), OverlaySpec(source="x.gpkg"))

    def test_from_dict_rejects_missing_source(self):
        with self.assertRaises(SpecError):
            OverlaySpec.from_dict({"color": "#ff0000"})
        with self.assertRaises(SpecError):
            OverlaySpec.from_dict("not-a-dict")


class SpecOverlaysFieldTest(unittest.TestCase):
    def test_spec_json_round_trip_keeps_overlays(self):
        from tests.unit._helpers import make_spec
        s = make_spec(overlays=(OverlaySpec(source="data/deliver/x.gpkg",
                                            label_field="name"),))
        s2 = type(s).from_json(s.to_json())
        self.assertEqual(s2.overlays, s.overlays)
        self.assertEqual(s2.overlays[0].label_field, "name")

    def test_spec_to_dict_absent_overlays_is_none(self):
        from tests.unit._helpers import make_spec
        self.assertIsNone(make_spec().to_dict()["overlays"])
        self.assertEqual(make_spec().overlays, ())


class BridgeSameSourceGuardTest(unittest.TestCase):
    """A5（离线侧）：两 bridge 共同消费同一 OverlaySpec，禁止私有样式参数。"""

    def test_both_bridges_accept_overlays_param(self):
        for fn in (qgis_bridge.write_qgz, arcpy_bridge.write_aprx):
            with self.subTest(fn=fn.__name__):
                params = inspect.signature(fn).parameters
                self.assertIn("overlays", params)

    def test_emit_map_dispatches_same_spec_overlays(self):
        # emit_map 的两个分发点必须都用 spec.overlays（单一来源，静态扫描）
        src = inspect.getsource(emit_mod.emit_map)
        tree = ast.parse(src)
        calls = [n for n in ast.walk(tree) if isinstance(n, ast.Call)]
        dispatched = []
        for c in calls:
            fn = c.func
            name = getattr(fn, "attr", None) or getattr(fn, "id", "")
            if name in ("write_qgz", "write_aprx"):
                kw = {k.arg: k.value for k in c.keywords}
                self.assertIn("overlays", kw, f"{name} 未接收 overlays")
                self.assertIsInstance(kw["overlays"], ast.Attribute)
                self.assertEqual(kw["overlays"].attr, "overlays")
                dispatched.append(name)
        self.assertEqual(sorted(dispatched), ["write_aprx", "write_qgz"],
                         "emit_map 必须同时分发两个 bridge")


if __name__ == "__main__":
    unittest.main()
