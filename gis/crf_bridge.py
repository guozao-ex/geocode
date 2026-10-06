"""
CRF 桥 —— 多维 NetCDF → ArcGIS Pro 原生 CRF 多维栅格。

为什么必须有这一步（2026-10-06 实测）：
    geo env 的 GDAL 3.13.3 与 rasterio 内置 GDAL 都**没有 CRF 驱动**
    （gdal.GetDriverByName('CRF') → None），CRF 写出唯一可行端是
    arcgispro-py3（Esri 自家的格式）。

边界纪律（红线 7，与 arcpy_bridge 一致）：
    arcgispro-py3 里不装任何 GEE / geo 栈。本模块把**已落盘的多维 .nc**
    交给 Pro 自己的 python，两侧只做文件交换；转换离线，无网络。

用法：
    from gis.crf_bridge import write_crf
    res = write_crf(spec, nc_path)     # → {"crf": path, "md_info": {...}}
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

from . import geoenv
from .spec import ArtifactSpec

_DEFAULT_PRO_PYTHON = Path(r"C:\Program Files\ArcGIS\Pro\bin\Python\envs\arcgispro-py3\python.exe")

# 子进程脚本：.nc 直接 CopyRaster → .crf（Pro 识别多维 NetCDF，全变量 +
# StdTime 维保留 —— 已实测；MakeMultidimensionalRasterLayer 默认只取
# 第一个变量，不能做主路径）。读回证据用 Raster 的多维 API：
# isMultidimensional + 逐变量 getDimensionNames/getDimensionValues
# （Pro 3.7 无 GetMultidimensionalInfo 工具，Describe().multidimensionalInfo
#  对 CRF 也不填充 —— 已实测；Raster 方法是可靠的证据面）。
_CRF_SCRIPT = r'''
import json, sys, traceback
import arcpy

def main(nc_path, out_path, variables):
    arcpy.env.overwriteOutput = True
    res = {"ok": False, "crf": out_path}
    try:
        # ① 转换：扩展名 .crf 触发 CRF 驱动。
        try:
            arcpy.management.CopyRaster(nc_path, out_path)
        except Exception:
            # 备选：显式全变量 md 图层中转（直接拷失败时兜底）
            layer = arcpy.md.MakeMultidimensionalRasterLayer(nc_path, "md_tmp", ";".join(variables))
            arcpy.management.CopyRaster(layer.getOutput(0), out_path)

        # ② 读回证据：逐变量读维度名与取值个数（期数 = StdTime 维长度）
        r = arcpy.Raster(out_path)
        res["is_multidimensional"] = bool(r.isMultidimensional)
        res["band_count"] = int(r.bandCount)
        per_var = {}
        for var in variables:
            try:
                dims = [str(d) for d in (r.getDimensionNames(var) or [])]
                sizes = {}
                for d in dims:
                    try:
                        sizes[d] = len(r.getDimensionValues(var, d) or [])
                    except Exception:
                        sizes[d] = None
                per_var[var] = {"dimensions": dims, "sizes": sizes}
            except Exception as e:
                per_var[var] = {"error": f"{type(e).__name__}: {e}"}
        res["variables"] = per_var
        res["ok"] = True
    except Exception:
        res["error"] = traceback.format_exc(limit=6)
    print("@@JSON@@" + json.dumps(res, ensure_ascii=False))

if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2], json.loads(sys.argv[3]))
'''


def pro_python() -> Path | None:
    """定位 arcgispro-py3 解释器。geocode.json 可用 arcgis.prefix 覆盖。"""
    cfg = geoenv.load_config()
    prefix = (cfg.get("arcgis") or {}).get("prefix")
    candidates = []
    if prefix:
        candidates.append(Path(prefix))
    candidates.append(_DEFAULT_PRO_PYTHON)
    for c in candidates:
        if c.is_file():
            return c
    return None


def write_crf(spec: ArtifactSpec, nc_path: Path) -> dict:
    """
    多维 .nc → {slug}.{指纹8位}.crf（多维栅格，CRF 是文件夹形态）。

    读回证据（来自 arcgispro-py3 侧 Raster 多维 API）：
      is_multidimensional / band_count / variables[变量] = {dimensions, sizes}
    调用方据此核对期数（StdTime 维长度）与 .nc 一致。

    返回 {"crf": path, ...证据...}；失败抛 RuntimeError。
    """
    pro = pro_python()
    if pro is None:
        raise RuntimeError(
            "找不到 arcgispro-py3 解释器，无法转出 CRF。\n"
            f"  期望位置：{_DEFAULT_PRO_PYTHON}\n"
            "  或在 geocode.json 设 arcgis.prefix。"
        )
    nc_path = Path(nc_path)
    if not nc_path.is_file():
        raise RuntimeError(f"输入 .nc 不存在：{nc_path}")

    # geo env 侧读出期望清单（离线，xarray），传给 Pro 侧逐变量核对
    expected = _nc_variable_dims(nc_path)

    out = nc_path.with_suffix(".crf")
    if out.exists():
        shutil.rmtree(out, ignore_errors=True)   # CRF 是文件夹，先清场

    import tempfile
    with tempfile.TemporaryDirectory(prefix="geocode_crf_") as td:
        script = Path(td) / "nc2crf.py"
        script.write_text(_CRF_SCRIPT, encoding="utf-8")
        proc = subprocess.run(
            [str(pro), str(script), str(nc_path), str(out), json.dumps(expected["variables"])],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=900,
        )
    payload = _extract_json(proc.stdout)
    if payload is None or not payload.get("ok"):
        err = (payload or {}).get("error") or proc.stdout[-1200:] or proc.stderr[-1200:]
        raise RuntimeError(
            f"CRF 转换失败（arcgispro-py3）。\n  {err}"
        )
    if not Path(out).exists():
        raise RuntimeError(f"arcgispro-py3 报告成功但产物缺失：{out}")

    return {
        "crf": str(out),
        "is_multidimensional": payload.get("is_multidimensional"),
        "band_count": payload.get("band_count"),
        "variables": payload.get("variables"),
        "expected": expected,
    }


def _nc_variable_dims(nc_path: Path) -> dict:
    """geo env 侧读 .nc 的变量与维度尺寸（离线），作为读回核对的期望值。"""
    import xarray as xr
    ds = xr.open_dataset(nc_path)
    try:
        variables = sorted(str(v) for v in ds.data_vars)
        sizes = {
            str(v): {str(d): int(n) for d, n in ds[v].sizes.items()}
            for v in variables
        }
        return {"variables": variables, "sizes": sizes}
    finally:
        ds.close()


def _extract_json(stdout: str) -> dict | None:
    """子进程 stdout 里抠 @@JSON@@ 标记后面的负载。"""
    marker = "@@JSON@@"
    idx = stdout.rfind(marker)
    if idx < 0:
        return None
    try:
        return json.loads(stdout[idx + len(marker):].strip())
    except Exception:
        return None
