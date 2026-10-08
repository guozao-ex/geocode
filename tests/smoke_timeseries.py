"""
C3 时序立方体验收脚本（A1–A4）—— tests/smoke_timeseries.py

⚠️ 需要网络（GEE 拉取共 8 次，已在验收项标注）：
    立方体 emit_array 1 + 立方体 emit_file 1 + 单期对照 emit_array 3 + 单期对照 emit_file 3
    A4 的 CRF 转换本身离线（依赖 A1 的 .nc 产物）。
样本：P0 参数（S2 北京，EPSG:32650 @10m，B4/B3/B2，median）+ time_step="month"
    → 2024-06/07/08 三期月度堆叠。

运行（geo env，仓库根）：
    C:/ProgramData/miniforge3/envs/geo/python.exe tests/smoke_timeseries.py
不依赖 daemon：直接构造 Job 调 emit.dispatch（与 jobs 执行器同路径）。
退出码 0 = 全部达标；1 = 有失败项。
"""

import io
import json
import sys
from pathlib import Path

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

# 仓库根入 path（脚本自带，不依赖运行方注入 PYTHONPATH）——C10 A3：
# 共享构造改走包路径 tests.unit._helpers，不再把 tests/unit 目录直插 sys.path。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tests.unit._helpers import P0_SPEC_DICT  # noqa: E402  （复用 P0 参数，含金指纹 AOI）

from gis.crf_bridge import write_crf  # noqa: E402
from gis.emit import ALIGN_TOLERANCE, dispatch  # noqa: E402
from gis.grid import compute_grid  # noqa: E402
from gis.jobs import Job, bind_progress  # noqa: E402
from gis.spec import ArtifactSpec, time_periods  # noqa: E402

CUBE_SPEC_DICT = {**P0_SPEC_DICT, "time_step": "month"}


def run_exit(spec: ArtifactSpec, exit_name: str, tag: str) -> dict:
    job = Job(id=f"smoke_ts_{tag}", kind="emit", spec=spec, exit=exit_name)
    bind_progress(job, lambda name, payload: None)
    result = dispatch(job)
    result["job_elapsed"] = round(job.elapsed, 1)
    return result


def main() -> int:
    failures: list[str] = []
    report: dict = {"tolerance": ALIGN_TOLERANCE, "steps": {}}

    cube = ArtifactSpec.from_dict(CUBE_SPEC_DICT)
    cube.validate(exit="array")
    grid = compute_grid(cube)
    gw, gh = grid.width, grid.height
    periods = time_periods(cube)
    bands = list(cube.bands)
    n, b = len(periods), len(bands)
    print(f"立方体 spec：{n} 期 × {b} 波段，指纹 {cube.fingerprint()}，网格 {gw}×{gh}")
    print(f"期窗口：{[list(p) for p in periods]}")

    # --- A1：立方体 emit_array → .nc ---------------------------------------
    print("\n[A1] 立方体 emit_array（网络）...")
    arr_cube = run_exit(cube, "array", "cube_array")
    report["steps"]["A1_cube_array"] = {
        k: arr_cube.get(k) for k in ("path", "size_mb", "dims", "vars", "timeseries")
    }
    nc_cube = arr_cube.get("path")
    if not nc_cube:
        failures.append("A1: emit_array 未返回产物路径")
    else:
        import numpy as np
        import xarray as xr

        ds = xr.open_dataset(nc_cube)
        dims = {k: int(v) for k, v in ds.sizes.items()}
        ok_dims = dims.get("time") == n and dims.get("y") == gh and dims.get("x") == gw
        # time 坐标 = 各期窗口起点（datetime 语义）
        want_times = [str(np.datetime64(p[0], "ns")) for p in periods]
        got_times = [str(t) for t in ds["time"].values]
        ok_times = got_times == want_times
        ts = arr_cube.get("timeseries") or {}
        ok_meta = ts.get("n_periods") == n and len(ts.get("periods") or []) == n
        ok_vars = all(v in ds for v in bands)
        if not (ok_dims and ok_meta and ok_vars and ok_times):
            failures.append(
                f"A1: 立方体结构不符 dims={dims} timeseries={ts} vars_ok={ok_vars} "
                f"time_coords={got_times}（期望 {want_times}）"
            )
        report["steps"]["A1_cube_array"]["nc_dims"] = dims
        report["steps"]["A1_cube_array"]["time_coords"] = got_times
        ds.close()
    print(f"    dims/期数/变量：{'OK' if not failures else failures[-1]}")

    # --- A3 前半：立方体 emit_file → 堆叠 .tif ------------------------------
    print("[A3] 立方体 emit_file → 期×波段堆叠 GeoTIFF（网络）...")
    file_cube = run_exit(cube, "file", "cube_file")
    report["steps"]["A3_cube_file"] = {
        k: file_cube.get(k) for k in ("path", "size_mb", "grid_aligned", "grid_problems", "timeseries")
    }
    tif_cube = file_cube.get("path")
    if not tif_cube or not file_cube.get("grid_aligned"):
        failures.append(f"A3: 立方体 GeoTIFF 网格未对齐 {file_cube.get('grid_problems')}")
    else:
        import rasterio

        with rasterio.open(tif_cube) as r:
            names = list(r.descriptions or ())
            if r.count != n * b:
                failures.append(f"A3: 堆叠波段数 {r.count} != {n}×{b}")
            expect = [f"{p[0].replace('-', '')}_{bd}" for p in periods for bd in bands]
            if names != expect:
                failures.append(f"A3: 波段名 {names[:4]}... != 期前缀约定 {expect[:4]}...")
            report["steps"]["A3_cube_file"]["band_names"] = names
    print(f"    波段数/命名/网格：{'OK' if not failures else failures[-1]}")

    # --- 单期对照（A2/A3 的比较基准，网络 6 次）-----------------------------
    print("\n[对照] 逐期单期 emit_array + emit_file（网络 3×2 次）...")
    singles = []
    for i, (ps, pe) in enumerate(periods):
        spec_i = ArtifactSpec.from_dict({**P0_SPEC_DICT, "time_range": [ps, pe]})
        a = run_exit(spec_i, "array", f"single_array_{i}")
        f = run_exit(spec_i, "file", f"single_file_{i}")
        if not a.get("path") or not f.get("path"):
            failures.append(f"第 {i} 期单期产物缺失：array={a.get('path')} file={f.get('path')}")
        singles.append({"period": [ps, pe], "array": a, "file": f})
        print(f"    期 {i} [{ps} ~ {pe}) 完成：{a['job_elapsed']}s / {f['job_elapsed']}s")
    report["steps"]["singles"] = [
        {"period": s["period"], "array_path": s["array"].get("path"),
         "file_path": s["file"].get("path")} for s in singles
    ]

    # --- A2：立方体逐期切片 vs 单期 .nc --------------------------------------
    print("\n[A2] 逐期对齐比对（array）...")
    a2 = []
    if nc_cube and all(s["array"].get("path") for s in singles):
        import numpy as np
        import xarray as xr

        cube_ds = xr.open_dataset(nc_cube)
        for i, s in enumerate(singles):
            single_ds = xr.open_dataset(s["array"]["path"])
            per = {}
            for bd in bands:
                a = np.asarray(cube_ds[bd].isel(time=i).values, dtype="float64")
                # 单期 .nc 也带 time=1 维（xee 对单 Image 同样给时间维）——先对齐形状
                v = single_ds[bd]
                if "time" in v.dims and v.sizes.get("time", 1) == 1:
                    v = v.isel(time=0)
                c = np.asarray(v.values, dtype="float64")
                if a.shape != c.shape:
                    per[bd] = {"shape_mismatch": [list(a.shape), list(c.shape)],
                               "mask_match": False, "max_abs_diff": None}
                    continue
                ma, mc = np.isfinite(a), np.isfinite(c)
                d = np.abs(a[ma & mc] - c[ma & mc]) if (ma & mc).any() else np.array([0.0])
                per[bd] = {
                    "mask_match": bool((ma == mc).all()),
                    "n_valid": int((ma & mc).sum()),
                    "max_abs_diff": float(d.max()) if d.size else 0.0,
                }
            mask_ok = all(v.get("mask_match") for v in per.values())
            worst = max((v.get("max_abs_diff") or 0.0 for v in per.values()), default=0.0)
            ok = mask_ok and worst <= ALIGN_TOLERANCE
            if not ok:
                failures.append(f"A2: 第 {i} 期对齐失败 mask_ok={mask_ok} max_diff={worst} "
                                f"bands={json.dumps(per, ensure_ascii=False)[:240]}")
            a2.append({"period": i, "ok": ok, "mask_ok": mask_ok,
                       "max_abs_diff": worst, "bands": per})
            print(f"    期 {i}: {'OK' if ok else 'FAIL'} (max|diff|={worst})")
            single_ds.close()
        cube_ds.close()
    report["steps"]["A2_period_align_array"] = a2

    # --- A3 后半：堆叠 .tif 第 i 期波段 vs 单期 .tif ------------------------
    print("[A3] 逐期对齐比对（file）...")
    a3 = []
    if tif_cube and all(s["file"].get("path") for s in singles):
        import numpy as np
        import rasterio

        with rasterio.open(tif_cube) as rc:
            for i, s in enumerate(singles):
                with rasterio.open(s["file"]["path"]) as rs:
                    per = {}
                    for j, bd in enumerate(bands):
                        a = rc.read(i * b + j + 1).astype("float64")
                        c = rs.read(j + 1).astype("float64")
                        na, nc_ = rc.nodata, rs.nodata
                        mask_a = (a != na) if na is not None else np.ones_like(a, bool)
                        mask_c = (c != nc_) if nc_ is not None else np.ones_like(c, bool)
                        valid = mask_a & mask_c
                        d = np.abs(a[valid] - c[valid]) if valid.any() else np.array([0.0])
                        per[bd] = {
                            "mask_match": bool((mask_a == mask_c).all()),
                            "n_valid": int(valid.sum()),
                            "max_abs_diff": float(d.max()) if d.size else 0.0,
                        }
                mask_ok = all(v.get("mask_match") for v in per.values())
                worst = max(v.get("max_abs_diff", 0.0) for v in per.values())
                ok = mask_ok and worst <= ALIGN_TOLERANCE
                if not ok:
                    failures.append(f"A3: 第 {i} 期 file 对齐失败 mask_ok={mask_ok} max_diff={worst}")
                a3.append({"period": i, "ok": ok, "mask_ok": mask_ok,
                           "max_abs_diff": worst, "bands": per})
                print(f"    期 {i}: {'OK' if ok else 'FAIL'} (max|diff|={worst})")
    report["steps"]["A3_period_align_file"] = a3

    # --- A4：.nc → .crf（arcpy 桥，转换离线）--------------------------------
    print("\n[A4] CRF 转换（arcgispro-py3，离线）...")
    if nc_cube:
        try:
            crf = write_crf(cube, nc_cube if isinstance(nc_cube, str) else str(nc_cube))
            vs = crf.get("variables") or {}
            crf_ok = (
                crf.get("is_multidimensional") is True
                and len(vs) == b
                and all(v.get("sizes", {}).get("StdTime") == n for v in vs.values())
            )
            if not crf_ok:
                failures.append(f"A4: CRF 读回证据不符 {json.dumps(crf, ensure_ascii=False)[:300]}")
            report["steps"]["A4_crf"] = {k: crf.get(k) for k in
                                         ("crf", "is_multidimensional", "band_count", "variables")}
            print(f"    {'OK' if crf_ok else 'FAIL'}：{crf.get('crf')}")
        except Exception as e:
            failures.append(f"A4: CRF 转换异常 {type(e).__name__}: {e}")
            print(f"    FAIL：{e}")
    else:
        failures.append("A4: 缺少 A1 的 .nc，无法转 CRF")

    # --- 汇总 ---------------------------------------------------------------
    report["ok"] = not failures
    report["failures"] = failures
    print("\n" + "=" * 72)
    if failures:
        print("❌ 未达标：")
        for f in failures:
            print("   -", f)
    else:
        print("✅ A1–A4 全部达标"
              f"（{n} 期 × {b} 波段，容差 {ALIGN_TOLERANCE}，逐期最大差见报告）")
    print(json.dumps({k: v for k, v in report.items() if k != "steps"}, ensure_ascii=False))
    return 0 if not failures else 1


if __name__ == "__main__":
    sys.exit(main())
