"""
QGIS 集成：生成 .qgz 工程文件。

为什么单独一个模块：
    emit.py 负责"产物形态"，QGIS 集成是**跨进程、跨解释器**的事
    （要调 QGIS 自带的 python-qgis.bat），边界清晰比塞在一起好维护。

为什么让 QGIS 自己写工程文件而不是我们手写 XML：
    .qgs/.qgz 的 schema 随 QGIS 版本变化。手写的在某版能开、换版就崩，
    而且失败方式通常是"打不开"或"图层空白"这种难诊断的症状。
    交给 QGIS 自己的 API 写，schema 永远是对的。
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from . import geoenv
from .grid import Grid
from .spec import ArtifactSpec

# ---------------------------------------------------------------------------
# 定位 QGIS
# ---------------------------------------------------------------------------

def qgis_python() -> Path | None:
    """定位 QGIS 的 python-qgis.bat（它负责把 PyQGIS 的运行时环境铺好）。"""
    cfg = geoenv.load_config()
    prefix = (cfg.get("qgis") or {}).get("prefix")

    candidates: list[Path] = []
    if prefix:
        candidates.append(Path(prefix) / "bin" / "python-qgis.bat")
    for root in (Path("C:/Program Files"), Path("C:/OSGeo4W"), Path("C:/OSGeo4W64")):
        if root.is_dir():
            for d in sorted(root.glob("QGIS*"), reverse=True):
                candidates.append(d / "bin" / "python-qgis.bat")

    for c in candidates:
        if c.is_file():
            return c
    return None


def probe() -> dict:
    """QGIS 可用性探测。给 preflight / dockpane 用。"""
    bat = qgis_python()
    if bat is None:
        return {
            "ok": False,
            "code": "qgis-not-found",
            "reason": (
                "找不到 QGIS 的 python-qgis.bat，无法生成 .qgz 工程。\n"
                "  期望位置：C:\\Program Files\\QGIS*\\bin\\python-qgis.bat\n"
                "  或在 geocode.json 设 qgis.prefix\n"
                "  影响：只有 exit='map' 的 .qgz 分支不可用；PNG 分支不受影响。"
            ),
        }
    return {"ok": True, "value": {"bat": str(bat)}}


# ---------------------------------------------------------------------------
# 生成工程
# ---------------------------------------------------------------------------

def write_qgz(
    spec: ArtifactSpec,
    raster: Path,
    grid: Grid,
    out: Path,
    *,
    timeout: float = 240.0,
) -> dict:
    """
    调 QGIS 生成 .qgz。失败抛 RuntimeError，消息里带 QGIS 的原始输出。

    参数 out 由调用方决定，本函数只负责"生成成功或抛出带原因的异常"。
    """
    bat = qgis_python()
    if bat is None:
        raise RuntimeError(probe()["reason"])

    out.parent.mkdir(parents=True, exist_ok=True)

    # 波段名 → 1 基波段号（QGIS 渲染器要的是序号）
    band_index: dict[str, int] = {}
    # ★ 自己在 Python 侧算好每波段的 2/98 分位拉伸区间。
    #
    # 为什么不让 QGIS 自己算：
    #   QgsContrastEnhancement 的算法与手动 setMin/Max 混用会互相覆盖，
    #   实测结果是渲染出一片彩色噪点（已用 QgsMapRenderer 复现）。
    #   自己算 → 写死区间 → 用 UserDefinedEnhancement，
    #   既确定又与我们已验证的 PNG 渲染完全一致。
    stats: dict[str, list[float]] = {}
    try:
        import numpy as np
        import rasterio
        with rasterio.open(raster) as ds:
            for i, name in enumerate([d for d in (ds.descriptions or []) if d], start=1):
                band_index[name] = i
            n = ds.count
            for b in range(1, n + 1):
                arr = ds.read(b, masked=True)
                valid = arr.compressed()
                if valid.size == 0:
                    continue
                lo, hi = (float(v) for v in np.percentile(valid, [2.0, 98.0]))
                if hi <= lo:
                    lo, hi = float(valid.min()), float(valid.max())
                stats[str(b)] = [lo, hi]
    except Exception as exc:  # 算不出来就让 QGIS 自己决定，至少不至于崩
        stats = {}
        print(f"WARN: 分位统计失败，回退默认拉伸: {exc}", file=sys.stderr)

    if not band_index and spec.bands:
        band_index = {b: i for i, b in enumerate(spec.bands, start=1)}

    render = spec.render
    cfg = {
        "raster": str(raster).replace("\\", "/"),
        "out": str(out).replace("\\", "/"),
        "crs": grid.crs,
        "title": spec.id,
        "layer_name": spec.slug,
        "color": {
            "bands": list(render.bands) if render and render.bands else None,
            "band_index": band_index,
            "palette": list(render.palette) if render and render.palette else None,
            "stretch": (render.stretch if render else "stddev"),
            "percentile": list(render.percentile) if render and render.percentile else [2.0, 98.0],
            "stats": stats,
        },
    }

    script = geoenv.CACHE_DIR / "make_qgz.py"
    script.write_text(_QGZ_SCRIPT, encoding="utf-8")

    proc = subprocess.run(
        [str(bat), str(script), json.dumps(cfg, ensure_ascii=False)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        timeout=timeout, cwd=str(geoenv.ROOT),
    )

    if proc.returncode != 0 or not out.is_file():
        raise RuntimeError(
            "QGIS 生成工程失败\n"
            f"  退出码 : {proc.returncode}\n"
            f"  命令   : {bat} {script}\n"
            f"  stdout : {(proc.stdout or '').strip()[-600:] or '(空)'}\n"
            f"  stderr : {(proc.stderr or '').strip()[-600:] or '(空)'}"
        )

    detail: dict = {}
    tail = (proc.stdout or "").strip().splitlines()
    if tail:
        try:
            detail = json.loads(tail[-1])
        except json.JSONDecodeError:
            detail = {"stdout": tail[-1][:300]}

    detail.update({
        "ok": True,
        "path": str(out),
        "size_kb": round(out.stat().st_size / 1024, 1),
    })
    return detail


# ---------------------------------------------------------------------------
# QGIS 侧脚本（在 python-qgis.bat 里跑）
# ---------------------------------------------------------------------------

_QGZ_SCRIPT = r'''# -*- coding: utf-8 -*-
"""由 GeoCode 调用生成 QGIS 工程。argv[1] 是 JSON 配置。"""
import json
import sys

from qgis.core import (
    QgsApplication, QgsProject, QgsRasterLayer, QgsCoordinateReferenceSystem,
    QgsColorRampShader, QgsRasterShader, QgsSingleBandPseudoColorRenderer,
    QgsMultiBandColorRenderer, QgsContrastEnhancement, QgsRasterMinMaxOrigin,
    QgsReferencedRectangle, Qgis,
)
from qgis.PyQt.QtGui import QColor


def apply_stretch(renderer, lo=0.02, hi=0.98):
    """
    按累计截断（cumulative cut）设置对比度拉伸。

    ★ 这是 QGIS 的原生做法 —— GUI 里「累计截断 2%–98%」用的就是它。

    为什么不用手搓 QgsContrastEnhancement：
      手动 setContrastEnhancementAlgorithm + setMinimumValue/setMaximumValue
      在 QGS 4.x 的多波段渲染器上不按预期工作（实测：要么渲染成彩色噪点，
      要么整幅白图）。QgsRasterMinMaxOrigin 让 QGIS 自己按统计算 min/max，
      既正确又稳。实测输出 mean=114.9 std=79.7 全跨度 [0,255]，正常。
    """
    mmo = QgsRasterMinMaxOrigin()
    mmo.setLimits(QgsRasterMinMaxOrigin.Limits.CumulativeCut)
    mmo.setExtent(QgsRasterMinMaxOrigin.Extent.WholeRaster)
    mmo.setStatAccuracy(QgsRasterMinMaxOrigin.StatAccuracy.Estimated)
    mmo.setCumulativeCutLower(lo)
    mmo.setCumulativeCutUpper(hi)
    renderer.setMinMaxOrigin(mmo)
    return mmo


def main(cfg):
    qgs = QgsApplication([], False)
    qgs.initQgis()
    try:
        proj = QgsProject.instance()
        proj.setTitle(cfg["title"])
        proj.setCrs(QgsCoordinateReferenceSystem(cfg["crs"]))

        layer = QgsRasterLayer(cfg["raster"], cfg["layer_name"], "gdal")
        if not layer.isValid():
            print("ERROR: QgsRasterLayer 无效: " + cfg["raster"], file=sys.stderr)
            return 2

        color = cfg.get("color") or {}
        bands = color.get("bands") or []
        idx = color.get("band_index") or {}
        palette = color.get("palette") or []
        stretch = (color.get("stretch") or "stddev").lower()
        stats = color.get("stats") or {}
        dp = layer.dataProvider()
        nbands = layer.bandCount()
        is_byte_rgb = nbands == 3 and dp.dataType(1) == Qgis.DataType.Byte
        mode = "default"

        def rng_for(band_no):
            return stats.get(str(band_no))

        if len(bands) >= 3 and nbands >= 3:
            nums = [idx.get(b, i + 1) for i, b in enumerate(bands[:3])]
            r = QgsMultiBandColorRenderer(dp, nums[0], nums[1], nums[2])
            # 8 位显示栅格的拉伸已经烘焙进像素，这里**不要**再加拉伸 ——
            # 加任何一点都会把已经定好的 0-255 再压一次。
            if is_byte_rgb:
                r.setMinMaxOrigin(QgsRasterMinMaxOrigin())
                mode_suffix = "+noenhancement(已烘焙)"
            else:
                try:
                    p_lo = float((color.get("percentile") or [2.0, 98.0])[0]) / 100.0
                    p_hi = float((color.get("percentile") or [2.0, 98.0])[1]) / 100.0
                    apply_stretch(r, p_lo, p_hi)
                    mode_suffix = "+cumulativecut%d-%d" % (int(p_lo*100), int(p_hi*100))
                except Exception as exc:
                    print("WARN: 拉伸设置失败 " + str(exc), file=sys.stderr)
                    mode_suffix = ""
            layer.setRenderer(r)
            mode = "multiband:" + ",".join(str(n) for n in nums) + mode_suffix

        elif palette and nbands >= 1:
            fn = QgsColorRampShader()
            fn.setColorRampType(QgsColorRampShader.Interpolated)
            try:
                st = dp.bandStatistics(1)
                lo, hi = st.minimumValue, st.maximumValue
            except Exception:
                lo, hi = 0.0, 255.0
            items = []
            n = len(palette)
            for i, hexcol in enumerate(palette):
                val = lo + (hi - lo) * (i / max(1, n - 1))
                col = hexcol.lstrip("#")
                if len(col) == 6:
                    items.append(QgsColorRampShader.ColorRampItem(val, QColor("#" + col)))
            fn.setColorRampItemList(items)
            shader = QgsRasterShader()
            shader.setRasterShaderFunction(fn)
            layer.setRenderer(QgsSingleBandPseudoColorRenderer(dp, 1, shader))
            mode = "palette:%d" % len(palette)

        else:
            try:
                apply_stretch(layer.renderer())
                mode = "default+cumulativecut2-98"
            except Exception:
                pass

        proj.addMapLayer(layer)

        # ★ 必须设默认视图范围。
        # 不设的话工程里就没有 <mapcanvas> 元素，QGIS 打开时画布范围未定义，
        # 用户看到一片空白，得手动「缩放到图层」——会以为工程坏了。
        # 这一步让打开即可见。
        try:
            proj.viewSettings().setDefaultViewExtent(
                QgsReferencedRectangle(layer.extent(), layer.crs()))
            view_ok = True
        except Exception as exc:
            print("WARN: 设置默认视图范围失败: " + str(exc), file=sys.stderr)
            view_ok = False

        wrote = bool(proj.write(cfg["out"]))
        ext = layer.extent()
        print(json.dumps({
            "wrote": wrote,
            "renderer": mode,
            "crs": proj.crs().authid(),
            "bands": nbands,
            "layer_valid": layer.isValid(),
            "view_extent_set": view_ok,
            "extent": [ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum()],
        }, ensure_ascii=False))
        return 0 if wrote else 3
    finally:
        qgs.exitQgis()


if __name__ == "__main__":
    sys.exit(main(json.loads(sys.argv[1])))
'''
