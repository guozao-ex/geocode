"""LayoutSpec 制图契约（C2 交付 1/3：构造、校验、序列化往返）。"""

import unittest

from tests.unit._helpers import make_spec

from gis.spec import LayoutSpec, SpecError


class LayoutDefaultsTest(unittest.TestCase):
    def test_defaults_five_elements_on(self):
        """四要素默认开启（图廓/比例尺/指北针/图例），经纬网默认关。"""
        lay = LayoutSpec()
        self.assertTrue(lay.frame)
        self.assertTrue(lay.scalebar)
        self.assertTrue(lay.north_arrow)
        self.assertTrue(lay.legend)
        self.assertFalse(lay.graticule)
        self.assertEqual(lay.dpi, 300)
        self.assertEqual(lay.page_size, "A4")
        self.assertEqual(lay.orientation, "landscape")
        self.assertEqual(lay.formats, ("pdf", "png"))
        self.assertIsNone(lay.title)
        self.assertEqual(lay.scalebar_length_cm, 4.0)

    def test_invalid_values_rejected(self):
        for kw in (
            {"page_size": "B5"},
            {"orientation": "diagonal"},
            {"dpi": 0},
            {"dpi": 9999},
            {"formats": ("svg",)},
            {"scalebar_length_cm": 0},
            {"scalebar_length_cm": -2.0},
            {"scalebar_length_cm": 99.0},
        ):
            with self.subTest(kw=kw):
                with self.assertRaises(SpecError):
                    LayoutSpec(**kw)


class LayoutRoundTripTest(unittest.TestCase):
    def test_dict_round_trip(self):
        lay = LayoutSpec(title="论文图 1", graticule=True, dpi=200,
                         scalebar_length_cm=6.0, formats=("pdf",))
        lay2 = LayoutSpec.from_dict(lay.to_dict())
        self.assertEqual(lay2, lay)

    def test_from_dict_none_and_empty(self):
        self.assertIsNone(LayoutSpec.from_dict(None))
        self.assertIsNone(LayoutSpec.from_dict({}))

    def test_from_dict_partial(self):
        lay = LayoutSpec.from_dict({"title": "T", "dpi": 150})
        self.assertEqual(lay.title, "T")
        self.assertEqual(lay.dpi, 150)
        self.assertTrue(lay.legend)      # 未指定 → 默认开
        self.assertEqual(lay.formats, ("pdf", "png"))
        self.assertEqual(lay.scalebar_length_cm, 4.0)  # 未指定 → 默认条长


class SpecLayoutFieldTest(unittest.TestCase):
    def test_spec_json_round_trip_keeps_layout(self):
        s = make_spec(layout=LayoutSpec(title="T"))
        s2 = type(s).from_json(s.to_json())
        self.assertEqual(s2.layout, s.layout)
        self.assertIsNotNone(s2.layout)
        self.assertEqual(s2.layout.title, "T")

    def test_to_dict_includes_layout(self):
        d = make_spec(layout=LayoutSpec()).to_dict()
        self.assertIn("layout", d)
        self.assertIsInstance(d["layout"], dict)

    def test_layout_absent_is_none(self):
        self.assertIsNone(make_spec().layout)
        self.assertIsNone(make_spec().to_dict()["layout"])


if __name__ == "__main__":
    unittest.main()
