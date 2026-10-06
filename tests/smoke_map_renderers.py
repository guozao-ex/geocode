# -*- coding: utf-8 -*-
"""
C2 冒烟：emit_map 双 renderer。

用法：
    python tests/smoke_map_renderers.py qgis
    python tests/smoke_map_renderers.py arcpy
    python tests/smoke_map_renderers.py qgis nolayout    # 无 LayoutSpec（两 renderer 均不建布局）
    python tests/smoke_map_renderers.py qgis graticule   # 经纬网开
    python tests/smoke_map_renderers.py arcpy noframe    # 图廓边框关（arcpy CIM）

数据来源：同指纹（c9243efd）的 derived/*.tif 已在 P0 产出 —— layout/render
都不参与指纹，这里直接命中 `_ensure_raster` 缓存，**全程离线**。
"""
import json
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
sys.path.insert(0, ".")

from gis.jobs import Job, bind_progress, run_emit
from gis.spec import ArtifactSpec, LayoutSpec, RenderSpec

renderer = sys.argv[1] if len(sys.argv) > 1 else "qgis"
mode = sys.argv[2] if len(sys.argv) > 2 else ""

AOI = {"type": "Polygon", "coordinates": [[[116.30, 39.95], [116.40, 39.95],
                                           [116.40, 40.02], [116.30, 40.02], [116.30, 39.95]]]}
layout_kw = {"title": "北京 S2 真彩色（C2 验收）"}
if mode == "graticule":
    layout_kw["graticule"] = True
if mode == "noframe":
    layout_kw["frame"] = False

spec = ArtifactSpec(
    id="s2_beijing_test", asset="COPERNICUS/S2_SR_HARMONIZED",
    bands=("B4", "B3", "B2"), scale=10, crs="EPSG:32650",
    dtype="uint16", time_range=("2024-06-01", "2024-08-31"),
    reducer="median", aoi=AOI,
    render=RenderSpec(bands=("B4", "B3", "B2")),
    layout=None if mode == "nolayout" else LayoutSpec(**layout_kw),
)

print("fingerprint:", spec.fingerprint())
job = Job(id=f"smoke_{renderer}", kind="emit", spec=spec, exit="map", renderer=renderer)
bind_progress(job, lambda ev, p: print(f"  [{p.get('pct', 0):5.1f}%] {p.get('phase', '')} {p.get('message', '')[:70]}"))

t0 = time.time()
result = run_emit(job)
dt = time.time() - t0

if job.error:
    print("ERROR:")
    print(job.error[:2500])
    sys.exit(1)

slim = {k: v for k, v in (result or {}).items() if k not in ("grid", "source_raster", "visual_raster")}
print(json.dumps(slim, ensure_ascii=False, indent=1))
print(f"elapsed: {dt:.1f}s")
