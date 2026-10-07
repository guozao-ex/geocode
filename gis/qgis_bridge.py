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
import sys
from pathlib import Path

from . import geoenv
from .grid import Grid
from .spec import ArtifactSpec, LayoutSpec

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
    layout: LayoutSpec | None = None,
    overlays: tuple = (),
) -> dict:
    """
    调 QGIS 生成 .qgz。失败抛 RuntimeError，消息里带 QGIS 的原始输出。

    参数 out 由调用方决定，本函数只负责"生成成功或抛出带原因的异常"。
    layout 非 None 时在工程内嵌一个打印布局（图廓/比例尺/指北针/图例/标题/
    经纬网）—— 消费 LayoutSpec 契约，不私造布局参数。
    overlays 非 () 时叠加矢量图层 —— 消费 OverlaySpec 契约（与 arcpy bridge
    同源样式，不私造矢量参数）。
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
        "title": (layout.title if layout and layout.title else spec.id),
        "layer_name": spec.slug,
        # LayoutSpec 契约透传给 QGIS 侧脚本（呈现层，不私造参数）
        "layout": layout.to_dict() if layout else None,
        # OverlaySpec 契约透传（C8 W3；呈现层，不私造矢量样式参数）
        "overlays": [
            o.to_dict() if hasattr(o, "to_dict") else dict(o) for o in overlays
        ] if overlays else None,
        "color": {
            "bands": list(render.bands) if render and render.bands else None,
            "band_index": band_index,
            "palette": list(render.palette) if render and render.palette else None,
            # 分类栅格：与 palette 配对的精确类值（QGIS 侧按 Exact 色带渲染）
            "class_values": list(render.class_values) if render and render.class_values else None,
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
    # 子进程 stderr 里是布局/经纬网等的 WARN 与 traceback —— 带回给调用方
    warn_lines = [l for l in (proc.stderr or "").strip().splitlines() if l.strip()]
    if warn_lines:
        detail["stderr_tail"] = warn_lines[-12:]

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
        class_values = color.get("class_values") or []
        stretch = (color.get("stretch") or "stddev").lower()
        stats = color.get("stats") or {}
        dp = layer.dataProvider()
        nbands = layer.bandCount()
        is_byte_rgb = nbands == 3 and dp.dataType(1) == Qgis.DataType.Byte
        mode = "default"

        def rng_for(band_no):
            return stats.get(str(band_no))

        if is_byte_rgb:
            # ★ 已烘焙的 8 位显示栅格：颜色就是像素本身 —— 一律多波段 + 零拉伸。
            # 这一支必须排在 palette 之前：分类栅格（palette 非空）否则会被单波段
            # 伪彩分支**再着色一次**，变成双层配色。
            nums = [idx.get(b, i + 1) for i, b in enumerate(bands[:3])] or [1, 2, 3]
            r = QgsMultiBandColorRenderer(dp, nums[0], nums[1], nums[2])
            r.setMinMaxOrigin(QgsRasterMinMaxOrigin())
            layer.setRenderer(r)
            mode = "multiband:" + ",".join(str(n) for n in nums) + "+noenhancement(已烘焙)"

        elif len(bands) >= 3 and nbands >= 3:
            nums = [idx.get(b, i + 1) for i, b in enumerate(bands[:3])]
            r = QgsMultiBandColorRenderer(dp, nums[0], nums[1], nums[2])
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

        elif class_values and palette and nbands <= 2:
            # 分类栅格源：类值 → 颜色**精确**取色（Exact），不做 min/max 插值 ——
            # 插值会把 10/20/…/100 这类离散类码渲染成连续色带，与图例对不上。
            fn = QgsColorRampShader()
            fn.setColorRampType(QgsColorRampShader.Exact)
            items = []
            for v, hexcol in zip(class_values, palette):
                col = str(hexcol).lstrip("#")
                if len(col) == 6:
                    items.append(QgsColorRampShader.ColorRampItem(float(v), QColor("#" + col)))
            fn.setColorRampItemList(items)
            shader = QgsRasterShader()
            shader.setRasterShaderFunction(fn)
            layer.setRenderer(QgsSingleBandPseudoColorRenderer(dp, 1, shader))
            mode = "classes:%d" % len(items)

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

        # --- 矢量叠加（OverlaySpec 契约，C8 W3）---
        vlayers, overlay_errors = add_overlays(proj, cfg.get("overlays") or [])

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

        # --- 打印布局（LayoutSpec 契约，C2）---
        layout_name = None
        layout_error = None
        lay_cfg = cfg.get("layout")
        if lay_cfg:
            try:
                layout_name = build_layout(proj, layer, lay_cfg, vlayers)
            except Exception as exc:
                import traceback as _tb
                layout_error = type(exc).__name__ + ": " + str(exc)
                print("WARN: 打印布局生成失败: " + layout_error, file=sys.stderr)
                print(_tb.format_exc(limit=6), file=sys.stderr)
                layout_name = None

        wrote = bool(proj.write(cfg["out"]))
        ext = layer.extent()
        print(json.dumps({
            "wrote": wrote,
            "renderer": mode,
            "crs": proj.crs().authid(),
            "bands": nbands,
            "layer_valid": layer.isValid(),
            "view_extent_set": view_ok,
            "layout": layout_name,
            "layout_error": layout_error,
            "overlays": len(vlayers),
            "overlay_errors": overlay_errors,
            "extent": [ext.xMinimum(), ext.yMinimum(), ext.xMaximum(), ext.yMaximum()],
        }, ensure_ascii=False))
        return 0 if wrote else 3
    finally:
        qgs.exitQgis()


def add_overlays(proj, ovs):
    """
    按 OverlaySpec 契约加载矢量叠加图层（样式参数同源于 OverlaySpec，
    不私造）。单个图层失败只 WARN 留痕，不中断整张工程。
    返回 (图层列表, 错误列表)。
    """
    import os as _os

    from qgis.core import QgsSingleSymbolRenderer, QgsVectorLayer
    from qgis.PyQt.QtGui import QColor

    made, errors = [], []
    for i, ov in enumerate(ovs):
        try:
            src = str(ov.get("source") or "")
            if not src:
                raise ValueError("overlay source 为空")
            name = _os.path.splitext(_os.path.basename(src))[0][:60] or f"overlay{i}"
            v = QgsVectorLayer(src, name, "ogr")
            if not v.isValid():
                raise ValueError("图层无效: " + src)
            color = QColor(ov.get("color") or "#3388ff")
            width = float(ov.get("width") or 2.0)
            fill = ov.get("fill_color")
            try:
                from qgis.core import (
                    QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol,
                )
                gtype = v.geometryType()  # 0=点 1=线 2=面
                if gtype == 2:
                    props = {
                        "outline_color": color.name(),
                        "outline_width": width,
                        "outline_width_unit": "Pixel",
                        "style": "no" if not fill else "solid",
                    }
                    if fill:
                        props["color"] = QColor(fill).name()
                    sym = QgsFillSymbol.createSimple(props)
                elif gtype == 1:
                    sym = QgsLineSymbol.createSimple({
                        "line_color": color.name(),
                        "line_width": width,
                        "line_width_unit": "Pixel",
                    })
                else:
                    sym = QgsMarkerSymbol.createSimple({
                        "color": color.name(),
                        "outline_color": color.name(),
                        "name": "circle",
                        "size": max(2.0, width),
                        "size_unit": "Pixel",
                    })
                v.setRenderer(QgsSingleSymbolRenderer(sym))
            except Exception as exc:
                errors.append({"index": i, "error": "symbology: " + str(exc)})
            try:
                v.setOpacity(float(ov.get("opacity", 1.0)))
            except Exception:
                pass
            label_field = ov.get("label_field")
            if label_field:
                try:
                    from qgis.core import (
                        QgsPalLayerSettings, QgsTextFormat,
                        QgsVectorLayerSimpleLabeling,
                    )
                    st = QgsPalLayerSettings()
                    st.fieldName = str(label_field)
                    st.setFormat(QgsTextFormat())
                    v.setLabeling(QgsVectorLayerSimpleLabeling(st))
                    v.setLabelsEnabled(True)
                except Exception as exc:
                    errors.append({"index": i, "error": "label: " + str(exc)})
            proj.addMapLayer(v)
            made.append(v)
        except Exception as exc:
            errors.append({"index": i, "error": str(exc)})
    return made, errors


def build_layout(proj, layer, lay_cfg, vlayers=None):
    """
    内嵌打印布局：消费 LayoutSpec（图廓/比例尺/指北针/图例/标题）。
    经纬网（graticule）用 QgsLayoutItemMapGrid 实现（CRS=4326 度间隔，退化时投影网格）。
    """
    import os
    import sys
    import tempfile
    from qgis.core import (
        QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItemLabel,
        QgsLayoutItemLegend, QgsLayoutItemScaleBar,
        QgsLayoutPoint, QgsLayoutSize, QgsUnitTypes, QgsLayoutItemPage,
    )
    from qgis.PyQt.QtGui import QFont

    # QGIS 4 把枚举从 QgsUnitTypes 迁到了 Qgis —— 双写兼容
    try:
        mm = QgsUnitTypes.LayoutMillimeters
    except AttributeError:
        mm = Qgis.LayoutUnit.Millimeters
    try:
        Orient = QgsLayoutItemPage.Orientation
    except AttributeError:
        Orient = Qgis.LayoutOrientation

    lyt = QgsPrintLayout(proj)
    lyt.initializeDefaults()
    name = (lay_cfg.get("title") or "geocode-layout")[:60]
    lyt.setName(name)

    page = lyt.pageCollection().page(0)
    orient = (Orient.Portrait if lay_cfg.get("orientation") == "portrait"
              else Orient.Landscape)
    page.setPageSize(lay_cfg.get("page_size") or "A4", orient)

    mm = QgsUnitTypes.LayoutMillimeters
    pw, ph = page.pageSize().width(), page.pageSize().height()
    margin = 10

    # 地图主体 + 图廓（矢量叠加层与栅格一起进布局 —— 消费同一 OverlaySpec）
    map_item = QgsLayoutItemMap(lyt)
    map_item.setRect(0, 0, 100, 100)
    map_item.setLayers([layer] + list(vlayers or []))
    try:
        map_item.setCrs(layer.crs())   # 不设 CRS 会让经纬网度变换退化为空变换
    except Exception:
        pass
    map_item.setFrameEnabled(bool(lay_cfg.get("frame", True)))
    lyt.addLayoutItem(map_item)
    map_item.attemptMove(QgsLayoutPoint(margin, margin + 14, mm))
    map_item.attemptResize(QgsLayoutSize(pw - 2 * margin, ph - 2 * margin - 22, mm))
    map_item.setExtent(layer.extent())

    # 标题
    if lay_cfg.get("title"):
        lbl = QgsLayoutItemLabel(lyt)
        lbl.setText(lay_cfg["title"])
        f = QFont()
        f.setPointSize(16)
        f.setBold(True)
        lbl.setFont(f)
        lyt.addLayoutItem(lbl)
        lbl.attemptMove(QgsLayoutPoint(margin, margin, mm))
        lbl.attemptResize(QgsLayoutSize(pw - 2 * margin, 12, mm))

    # 图例
    if lay_cfg.get("legend", True):
        leg = QgsLayoutItemLegend(lyt)
        leg.setLinkedMap(map_item)
        lyt.addLayoutItem(leg)
        leg.attemptMove(QgsLayoutPoint(margin + 2, ph - margin - 48, mm))

    # 比例尺
    if lay_cfg.get("scalebar", True):
        sb = QgsLayoutItemScaleBar(lyt)
        sb.setLinkedMap(map_item)
        sb.applyDefaultSize()
        lyt.addLayoutItem(sb)
        sb.attemptMove(QgsLayoutPoint(margin + 2, ph - margin - 14, mm))

    # 指北针：QGIS 4 移除了 QgsLayoutItemNorthArrow —— 用内置 SVG 的 Picture 兜底
    if lay_cfg.get("north_arrow", True):
        try:
            from qgis.core import QgsLayoutItemNorthArrow
            na = QgsLayoutItemNorthArrow(lyt)
            na.setLinkedMap(map_item)
        except ImportError:
            from qgis.core import QgsLayoutItemPicture
            svg_path = os.path.join(tempfile.gettempdir(), "geocode_north_arrow.svg")
            with open(svg_path, "w", encoding="utf-8") as f:
                f.write(
                    '<svg xmlns="http://www.w3.org/2000/svg" width="60" height="72" '
                    'viewBox="0 0 60 72">'
                    '<polygon points="30,4 40,48 30,40 20,48" fill="#1a1a1a"/>'
                    '<text x="30" y="66" font-size="14" text-anchor="middle" '
                    'font-family="Arial" fill="#1a1a1a">N</text></svg>'
                )
            na = QgsLayoutItemPicture(lyt)
            na.setPicturePath(svg_path)
            na.setLinkedMap(map_item)
        lyt.addLayoutItem(na)
        na.attemptMove(QgsLayoutPoint(pw - margin - 20, ph - margin - 34, mm))

    # 经纬网（graticule）：QgsLayoutItemMapGrid，CRS=4326，间隔按范围取 1/2/5 整值
    if lay_cfg.get("graticule"):
        import math as _math
        try:
            from qgis.core import QgsLayoutItemMapGrid, QgsCoordinateTransform
            g = QgsLayoutItemMapGrid("geocode-graticule", map_item)
            g.setCrs(QgsCoordinateReferenceSystem("EPSG:4326"))
            try:
                xform = QgsCoordinateTransform(
                    map_item.crs(), QgsCoordinateReferenceSystem("EPSG:4326"),
                    proj.transformContext())
                ext4326 = xform.transformBoundingBox(map_item.extent())
                span = max(ext4326.xMaximum() - ext4326.xMinimum(),
                           ext4326.yMaximum() - ext4326.yMinimum())
                mag = 10 ** int(_math.floor(_math.log10(span / 5)))
                step = mag
                for mult in (5, 2, 1):
                    if span / 5 >= mult * mag:
                        step = mult * mag
                        break
                g.setIntervalX(step)
                g.setIntervalY(step)
            except Exception as exc:
                # 度变换失败 → 退化为投影坐标网格（CRS 同步改为地图 CRS，单位一致）
                print("WARN: 经纬网度间隔设置失败，退化为投影坐标网格: " + str(exc),
                      file=sys.stderr)
                g.setCrs(map_item.crs())
                ext_m = map_item.extent()
                span_m = max(ext_m.width(), ext_m.height())
                mag = 10 ** int(_math.floor(_math.log10(span_m / 5)))
                step = mag
                for mult in (5, 2, 1):
                    if span_m / 5 >= mult * mag:
                        step = mult * mag
                        break
                g.setIntervalX(step)
                g.setIntervalY(step)
            try:
                g.setStyle(QgsLayoutItemMapGrid.Line)
            except Exception:
                try:
                    g.setStyle(Qgis.LayoutGridStyle.Line)
                except Exception:
                    pass
            try:
                g.setGridLineWidth(0.2)
            except Exception:
                pass
            map_item.grids().addGrid(g)
            map_item.updateBoundingRect()
            map_item.update()
        except Exception as exc:
            import traceback as _tb
            print("WARN: 经纬网生成失败: " + repr(exc), file=sys.stderr)
            print(_tb.format_exc(limit=6), file=sys.stderr)

    proj.layoutManager().addLayout(lyt)
    return lyt.name()


if __name__ == "__main__":
    sys.exit(main(json.loads(sys.argv[1])))
'''
