# -*- coding: utf-8 -*-
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
