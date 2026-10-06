"""ArtifactSpec / RenderSpec 校验与基础行为。

对应 brief 交付内容 1（validate 出口必填项）与 2（基础行为）。
"""

import unittest

from _helpers import BEIJING_AOI, make_spec

from gis.spec import (
    EXITS,
    ArtifactSpec,
    RenderSpec,
    SpecError,
    aoi_bbox,
    bbox_to_geojson,
)


class ValidateExitTest(unittest.TestCase):
    """validate(exit=...) 按出口必填项（交付内容 1）。"""

    def test_array_file_require_crs_scale_aoi(self):
        for exit in ("array", "file"):
            for missing in ("crs", "scale", "aoi"):
                with self.subTest(exit=exit, missing=missing):
                    s = make_spec(**{missing: None})
                    with self.assertRaises(SpecError) as cm:
                        s.validate(exit=exit)
                    self.assertIn(missing, str(cm.exception))

    def test_map_requires_only_aoi(self):
        make_spec(crs=None, scale=None).validate(exit="map")  # 不抛即通过
        s = make_spec(aoi=None)
        with self.assertRaises(SpecError) as cm:
            s.validate(exit="map")
        self.assertIn("aoi", str(cm.exception))

    def test_error_message_carries_fix_hint(self):
        with self.assertRaises(SpecError) as cm:
            make_spec(crs=None).validate(exit="file")
        self.assertIn("spec.defaults", str(cm.exception))

    def test_invalid_exit_rejected(self):
        with self.assertRaises(SpecError):
            make_spec().validate(exit="vector")

    def test_valid_spec_passes_all_exits(self):
        s = make_spec()
        for exit in EXITS:
            s.validate(exit=exit)


class ValidateBasicsTest(unittest.TestCase):
    def test_empty_id_rejected(self):
        for bad in ("", "   "):
            with self.subTest(bad=bad):
                with self.assertRaises(SpecError):
                    make_spec(id=bad).validate()

    def test_bad_dtype_rejected(self):
        with self.assertRaises(SpecError) as cm:
            make_spec(dtype="float16").validate()
        self.assertIn("float16", str(cm.exception))

    def test_nonpositive_scale_rejected(self):
        for bad in (0, -5.0):
            with self.subTest(bad=bad):
                with self.assertRaises(SpecError):
                    make_spec(scale=bad).validate()

    def test_time_range_checks(self):
        with self.assertRaises(SpecError):
            make_spec(time_range=("2024-01-01",)).validate()
        with self.assertRaises(SpecError) as cm:
            make_spec(time_range=("2024-12-31", "2024-01-01")).validate()
        self.assertIn("晚于", str(cm.exception))

    def test_unknown_reducer_rejected(self):
        with self.assertRaises(SpecError) as cm:
            make_spec(reducer="fancy").validate()
        self.assertIn("fancy", str(cm.exception))

    def test_aoi_must_be_geojson_dict(self):
        with self.assertRaises(SpecError):
            make_spec(aoi="POLYGON((0 0, 1 0, 1 1, 0 0))").validate()
        with self.assertRaises(SpecError):
            make_spec(aoi={"coordinates": []}).validate()


class SpecBasicsTest(unittest.TestCase):
    """with_ / JSON 往返 / slug / is_collection（交付内容 2）。"""

    def test_with_returns_new_and_keeps_original(self):
        s = make_spec()
        s2 = s.with_(scale=20.0)
        self.assertEqual(s2.scale, 20.0)
        self.assertEqual(s.scale, 10.0)  # 原 spec 不变
        self.assertIsNot(s, s2)

    def test_json_round_trip(self):
        s = make_spec()
        s2 = ArtifactSpec.from_json(s.to_json())
        self.assertEqual(s2, s)  # frozen dataclass 逐字段相等

    def test_from_dict_defaults_meta(self):
        d = make_spec().to_dict(include_meta=False)
        self.assertNotIn("note", d)
        s2 = ArtifactSpec.from_dict(d)
        self.assertEqual(s2.note, "")
        self.assertEqual(s2.tags, ())

    def test_slug_sanitizes(self):
        self.assertEqual(make_spec(id="s2 beijing/test").slug, "s2-beijing-test")
        self.assertEqual(make_spec(id="###").slug, "unnamed")

    def test_is_collection(self):
        self.assertTrue(make_spec().is_collection)              # 有 reducer
        self.assertTrue(make_spec(reducer=None).is_collection)  # 有 time_range
        self.assertFalse(
            make_spec(reducer=None, time_range=None).is_collection
        )


class RenderSpecTest(unittest.TestCase):
    def test_defaults(self):
        r = RenderSpec()
        self.assertEqual(r.stretch, "stddev")
        self.assertEqual(r.percentile, (2.0, 98.0))
        self.assertIsNone(r.bands)

    def test_dict_round_trip(self):
        r = RenderSpec(
            bands=("B4", "B3", "B2"), stretch="percentile", percentile=(5.0, 95.0)
        )
        self.assertEqual(RenderSpec.from_dict(r.to_dict()), r)
        self.assertIsNone(RenderSpec.from_dict(None))


class GeojsonHelperTest(unittest.TestCase):
    def test_bbox_to_geojson_closed_ring(self):
        g = bbox_to_geojson(116.0, 39.0, 117.0, 40.0)
        self.assertEqual(g["type"], "Polygon")
        ring = g["coordinates"][0]
        self.assertEqual(ring[0], ring[-1])  # 闭合环

    def test_aoi_bbox(self):
        self.assertEqual(aoi_bbox(BEIJING_AOI), (116.30, 39.90, 116.50, 40.10))
        self.assertIsNone(aoi_bbox(None))
        self.assertIsNone(aoi_bbox({}))


if __name__ == "__main__":
    unittest.main()
