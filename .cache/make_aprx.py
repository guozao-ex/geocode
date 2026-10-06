# -*- coding: utf-8 -*-
"""由 GeoCode 调用：在 arcgispro-py3 里生成 .aprx + 出版级布局导出。argv[1]=JSON。"""
import json
import os
import shutil
import sys
import tempfile
import traceback


def emit(payload):
    print(json.dumps(payload, ensure_ascii=False))


def fail(code, message, **extra):
    emit({"ok": False, "code": code, "message": message, **extra})
    sys.exit(1)


def _style_line(el, rgb, width_pt):
    """线 graphic 定制样式（CIM 路径实测：graphic.symbol.symbol.symbolLayers）。"""
    cim = el.getDefinition("V3")
    sl = cim.graphic.symbol.symbol.symbolLayers[0]
    sl.width = width_pt
    sl.color.values = [rgb[0], rgb[1], rgb[2], 100]
    el.setDefinition(cim)


def _style_text(el, rgb):
    """文本字形填色（CIMTextSymbol.symbol 为字形填充多边形符号）。"""
    cim = el.getDefinition("V3")
    gsl = cim.graphic.symbol.symbol.symbol.symbolLayers[0]
    gsl.color.values = [rgb[0], rgb[1], rgb[2], 100]
    el.setDefinition(cim)


def main(cfg):
    import arcpy

    lay = cfg.get("layout") or None
    has_layout = bool(lay)
    lay = lay or {}
    title = cfg.get("title") or "geocode"

    # 1. 临时目录建工程（Pro 会生成 .gdb/.atbx 伴生文件 → 不污染 deliver/）
    workdir = tempfile.mkdtemp(prefix="geocode_aprx_")
    try:
        try:
            aprx = arcpy.mp.CreateArcGISProject(workdir, "geocode", False)
        except TypeError:
            aprx = arcpy.mp.CreateArcGISProject(workdir, "geocode")
        aprx_path = os.path.join(workdir, "geocode.aprx")

        # 2. 地图 + 图层（只吃现成 GeoTIFF —— 红线 7）
        #    实测 CreateArcGISProject/createMap 出来的工程会带 Esri basemap
        #    服务图层 —— 出图前全部移除，只渲染我们自己的数据。
        m = aprx.createMap("geocode")
        for l in list(m.listLayers()):
            try:
                if l.isBasemapLayer:
                    m.removeLayer(l)
            except Exception:
                pass
        layer = m.addDataFromPath(cfg["raster"])
        if layer is None:
            layer = m.listLayers()[-1]
        try:
            layer.name = cfg["layer_name"]   # 图例里显示短名，不显示文件全名
        except Exception:
            pass

        # 3. 布局（layout 缺席 = nolayout：只出 map-only aprx，无布局无导出）
        lyt = None
        exports = {}
        created = []
        if has_layout:
            formats = [f.lower() for f in (lay.get("formats") or ["pdf", "png"])]
            dpi = int(lay.get("dpi") or 300)
            page_size = (lay.get("page_size") or "A4").upper()
            orientation = (lay.get("orientation") or "landscape").lower()
            # 经纬网由自绘实现（见下方 graticule 块）；surround 只做图例/指北针
            graticule_on = bool(lay.get("graticule"))

            PAGE_CM = {"A4": (29.7, 21.0), "A3": (42.0, 29.7), "A2": (59.4, 42.0),
                       "A1": (84.1, 59.4), "LETTER": (27.9, 21.6), "TABLOID": (43.2, 27.9)}
            if page_size not in PAGE_CM:
                fail("page-size", "page_size=%r 不在已知纸型表 %s" % (page_size, sorted(PAGE_CM)))
            w, h = PAGE_CM[page_size]
            if orientation == "portrait":
                w, h = h, w

            # 布局 + 地图框（地图框自带边框 = 图廓）；右侧留图例栏
            lyt = aprx.createLayout(w, h, "CENTIMETER", (lay.get("title") or title)[:40])
            inset = 1.0
            bottom_band = 3.4
            title_h = 1.8 if lay.get("title") else 0.0
            col = 6.0   # 右侧图例栏宽（cm）

            mf = lyt.createMapFrame(arcpy.Point(inset, inset + bottom_band), m, "geocode-mapframe")
            mf.elementPositionX = inset
            mf.elementPositionY = inset + bottom_band
            mf.elementWidth = w - 2 * inset - col - 0.4
            mf.elementHeight = h - 2 * inset - title_h - bottom_band
            try:
                ext = mf.getLayerExtent(layer, False, True)
            except Exception:
                ext = arcpy.Describe(cfg["raster"]).extent
            try:
                mf.camera.setExtent(ext)
                mf.camera.scale = mf.camera.scale * 1.02   # 四周留一点缓冲
            except Exception as exc:
                print("WARN: 设置地图框范围失败: " + str(exc), file=sys.stderr)

            # 图廓边框：frame=False 时用 CIM 把边框线宽归零
            # （实测 graphicFrame.borderSymbol.symbol.symbolLayers[*].width 可持久化；
            #   borderSymbol=None 写回不持久 —— 见 change 卷宗探针）
            if not lay.get("frame", True):
                try:
                    cim_mf = mf.getDefinition("V3")
                    for sl in cim_mf.graphicFrame.borderSymbol.symbol.symbolLayers:
                        if hasattr(sl, "width"):
                            sl.width = 0.0
                    mf.setDefinition(cim_mf)
                except Exception as exc:
                    print("WARN: 关闭图廓边框失败: " + str(exc), file=sys.stderr)

            # 标题（文本元素，页面原点在左下角、Y 向上）
            if lay.get("title"):
                aprx.createTextElement(lyt, arcpy.Point(inset, h - inset - 1.4),
                                       "POINT", str(lay["title"]),
                                       text_size=16, font_family_name="Arial")
                created.append("title")

            # 图例 / 指北针 / 经纬网（surround 元素，挂地图框）
            surround = []
            if lay.get("legend", True):
                surround.append((w - inset - col, h - inset - title_h - 0.2, "LEGEND", "legend"))
            if lay.get("north_arrow", True):
                surround.append((w - inset - col + 2.2, inset + bottom_band + 4.5, "NORTH_ARROW", "north_arrow"))
            surround_doc = None
            for x, y, stype, key in surround:
                try:
                    el = lyt.createMapSurroundElement(arcpy.Point(x, y), stype, mf)
                    created.append(key)
                    if key == "legend" and el is not None:
                        try:
                            el.elementWidth = col   # 图例宽度约束在栏内，不溢出页边
                        except Exception:
                            pass
                except Exception as exc:
                    if surround_doc is None:
                        fn = getattr(type(lyt), "createMapSurroundElement", None)
                        surround_doc = (fn.__doc__ or "")[:1500] if fn else None
                    fail("surround-element",
                         "createMapSurroundElement(%s) 失败：%s: %s" % (stype, type(exc).__name__, str(exc)[:300]),
                         key=key, doc=surround_doc)

            # 比例尺：自绘细分格条（线 + 刻度 + 文字）。
            #   Pro 的 SCALE_BAR surround 在 CENTIMETER/INCH 页面单位下 division
            #   都按 `barWidth_pt × scale / divisions` 误算（实测 probe 见卷宗），
            #   且 CIM 写回被 setDefinition 重算覆盖 —— 只能绕开：按 camera.scale
            #   自绘。半格距取 1/2/5 整值（就近 G0/4），格数 n=round(G0/半格距)
            #   截断 2-10 → 总长偏差收窄到半格级（约 ±10% 内），全部标注仍为
            #   1/2/5 整值，由构造保证正确。目标条长 = LayoutSpec.scalebar_length_cm。
            if lay.get("scalebar", True):
                import math as _math

                S = mf.camera.scale                    # 1:S（无单位）
                L0 = float(lay.get("scalebar_length_cm") or 4.0)
                G0 = L0 * S / 100.0                    # 目标总长对应实地距离（米）
                mag = 10 ** int(_math.floor(_math.log10(G0 / 4)))
                cands = [m * mag for m in (1, 2, 5)] + [m * mag * 10 for m in (1, 2, 5)]
                half = min(cands, key=lambda c: abs(c - G0 / 4))   # 半格距（米）
                n = max(2, min(10, int(round(G0 / half))))          # 半格数
                D = half * n                           # 实际总距离（米）
                L = D * 100.0 / S                      # 实际条长（cm）
                max_L = w - 3 * inset - col
                if L > max_L:                          # 页面放不下 → 减格数
                    n = max(2, int(max_L * S / 100.0 / half))
                    D = half * n
                    L = D * 100.0 / S
                x0, y0, hbar = inset + 0.4, inset + 0.55, 0.22
                half_cm = half * 100.0 / S

                def _bar_line(xa, ya, xb, yb):
                    # createGraphicElement 挂在 ArcGISProject 上（container=layout）
                    _style_line(aprx.createGraphicElement(lyt, arcpy.Polyline(
                        arcpy.Array([arcpy.Point(xa, ya), arcpy.Point(xb, yb)]))),
                        (0, 0, 0), 1.2)

                _bar_line(x0, y0, x0 + L, y0)                   # 主线
                for k in range(n + 1):                          # 逐半格刻度
                    _bar_line(x0 + k * half_cm, y0 - hbar,
                              x0 + k * half_cm, y0 + hbar)
                label_positions = [(x0 - 0.25, "0")]
                for k in range(2, n + 1, 2):                    # 逐整格标注
                    label_positions.append((x0 + k * half_cm - 0.25, "%g" % (k * half)))
                # 端点标签自带单位（避免独立的"m"与端点数字重叠）
                if n % 2 == 1:                                  # 奇数格：端点未标 → 补
                    label_positions.append((x0 + L - 0.25, "%g m" % D))
                else:                                           # 偶数格：末格即端点 → 附单位
                    label_positions[-1] = (x0 + L - 0.25, "%g m" % D)
                for xx, txt in label_positions:
                    aprx.createTextElement(lyt, arcpy.Point(xx, y0 + 0.18), "POINT",
                                           txt, text_size=8, font_family_name="Arial")
                created.append("scalebar")

            # 经纬网：自绘（经纬线按 1/2/5 度间隔，projectAs 投到地图 CRS）。
            #   Pro 3.7 的 GRID surround doc 列了该类型，运行时却抛 ValueError
            #   （实测 probe 见卷宗）—— 只能绕开。两点直连投影在小范围内
            #   弯曲可忽略。线为白色（深色影像上可读），度标注：经线在框底
            #   （白底黑字）、纬线在框左内沿（影像上白字）。
            if graticule_on:
                import math as _math

                sr_map = arcpy.Describe(cfg["raster"]).spatialReference
                sr_wgs = arcpy.SpatialReference(4326)
                ext_mf = mf.camera.getExtent()
                corners = [arcpy.PointGeometry(arcpy.Point(ext_mf.XMin, ext_mf.YMin), sr_map),
                           arcpy.PointGeometry(arcpy.Point(ext_mf.XMax, ext_mf.YMax), sr_map)]
                lons, lats = [], []
                for c in corners:
                    g4326 = c.projectAs(sr_wgs)
                    lons.append(g4326.firstPoint.X)
                    lats.append(g4326.firstPoint.Y)
                lon0, lon1 = min(lons), max(lons)
                lat0, lat1 = min(lats), max(lats)

                def _nice(span):
                    mag = 10 ** int(_math.floor(_math.log10(span / 5)))
                    step = mag
                    for mult in (5, 2, 1):
                        if span / 5 >= mult * mag:
                            step = mult * mag
                            break
                    return step

                dstep = _nice(max(lon1 - lon0, lat1 - lat0))

                # 页面坐标线性映射（camera extent ↔ 地图框矩形）
                fx0, fy0 = mf.elementPositionX, mf.elementPositionY
                fw, fh = mf.elementWidth, mf.elementHeight
                sx = fw / (ext_mf.XMax - ext_mf.XMin)
                sy = fh / (ext_mf.YMax - ext_mf.YMin)

                def _fmt(v, is_lon):
                    hemi = ("E" if v >= 0 else "W") if is_lon else ("N" if v >= 0 else "S")
                    return ("%g°%s" % (abs(v), hemi))

                # 经线 + 底部度标注（框底下沿的空白带，白底黑字）
                y_bot = fy0
                lon = _math.ceil(lon0 / dstep) * dstep
                while lon <= lon1 + 1e-9:
                    line = arcpy.Polyline(arcpy.Array([arcpy.Point(lon, lat0),
                                                        arcpy.Point(lon, lat1)]), sr_wgs)
                    _style_line(aprx.createGraphicElement(lyt, line.projectAs(sr_map)),
                                (255, 255, 255), 0.8)
                    p = arcpy.PointGeometry(arcpy.Point(lon, (lat0 + lat1) / 2), sr_wgs).projectAs(sr_map)
                    x_page = fx0 + (p.firstPoint.X - ext_mf.XMin) * sx
                    aprx.createTextElement(lyt, arcpy.Point(x_page - 0.35, y_bot - 0.34),
                                           "POINT", _fmt(lon, True),
                                           text_size=7, font_family_name="Arial")
                    lon += dstep
                # 纬线 + 左侧度标注（框左内沿，影像上白字）
                lat = _math.ceil(lat0 / dstep) * dstep
                while lat <= lat1 + 1e-9:
                    line = arcpy.Polyline(arcpy.Array([arcpy.Point(lon0, lat),
                                                        arcpy.Point(lon1, lat)]), sr_wgs)
                    _style_line(aprx.createGraphicElement(lyt, line.projectAs(sr_map)),
                                (255, 255, 255), 0.8)
                    p = arcpy.PointGeometry(arcpy.Point((lon0 + lon1) / 2, lat), sr_wgs).projectAs(sr_map)
                    y_page = fy0 + (p.firstPoint.Y - ext_mf.YMin) * sy
                    lbl = aprx.createTextElement(lyt, arcpy.Point(fx0 + 0.06, y_page - 0.12),
                                                 "POINT", _fmt(lat, False),
                                                 text_size=7, font_family_name="Arial")
                    _style_text(lbl, (255, 255, 255))
                    lat += dstep
                created.append("graticule")

            # 导出 PDF / PNG（LayoutSpec.formats + dpi）
            # 文件名带 .layout. 中缀 —— 不与 qgis 路径的 {stem}.png 预览图相撞
            for f in formats:
                outp = os.path.join(cfg["out_dir"], cfg["stem"] + ".layout." + f)
                if f == "pdf":
                    lyt.exportToPDF(outp, resolution=dpi)
                elif f == "png":
                    lyt.exportToPNG(outp, resolution=dpi)
                elif f == "jpg":
                    lyt.exportToJPEG(outp, resolution=dpi)
                else:
                    fail("format", "导出格式 %r 暂不支持（pdf/png/jpg）" % f)
                exports[f] = outp.replace("\\", "/")

        aprx.save()
        # 只把 .aprx 拷到 deliver（.gdb/.atbx 伴生文件留在临时目录）
        shutil.copyfile(aprx_path, cfg["aprx"])

        elements = [e.name for e in lyt.listElements()] if lyt is not None else []
        emit({
            "ok": True,
            "exports": exports,
            "elements": elements,
            "created": created,
            "has_layout": has_layout,
        })
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


if __name__ == "__main__":
    try:
        main(json.loads(sys.argv[1]))
    except SystemExit:
        raise
    except Exception as e:
        fail("exception", type(e).__name__ + ": " + str(e)[:500], tb=traceback.format_exc(limit=6))
