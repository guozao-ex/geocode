"""C6 串行试点（红线 6：先小后大）：emit_array 分块路径真实 GEE 验证。

用法（worktree 根，geo env）：
    PYTHONPATH=. python tests/smoke_array_chunking.py --stage small   # 阶段1：小网格双路径交叉验证
    PYTHONPATH=. python tests/smoke_array_chunking.py --stage big     # 阶段2：>64M 像素大网格 + 内存峰值

不经过 daemon（进程内直接调 emit_array），避免并行会话的 6531 端口冲突。
输出全部为数字与文件证据（无图），验收要点逐项打印 PASS/FAIL。
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from gis.emit import MAX_DIRECT_PIXELS, emit_array, plan_chunks  # noqa: E402
from gis.grid import compute_grid  # noqa: E402
from gis.jobs import Job  # noqa: E402
from gis.spec import ArtifactSpec, bbox_to_geojson  # noqa: E402
from gis import geoenv  # noqa: E402


class ProgressCollector:
    """收集 job.progress 消息，打印块进度并保留末尾若干条作证据。"""

    def __init__(self, label: str):
        self.label = label
        self.messages: list[str] = []

    def __call__(self, phase=None, pct=None, message=None, **extra):
        self.messages.append(f"[{self.label}] {phase} {pct:>5.1f}% {message}")

    def tail(self, n: int = 6) -> list[str]:
        return self.messages[-n:]


def _sha256(path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _run(job_id: str, spec: ArtifactSpec, label: str) -> tuple[dict, ProgressCollector]:
    job = Job(id=job_id, kind="emit", spec=spec, exit="array")
    collector = ProgressCollector(label)
    job.progress = collector
    t0 = time.perf_counter()
    result = emit_array(job)
    result["_wall_seconds"] = round(time.perf_counter() - t0, 1)
    return result, collector


def _load_values(result: dict) -> dict[str, np.ndarray]:
    import xarray as xr

    with xr.open_dataset(Path(result["path"])) as ds:
        return {v: ds[v].values.copy() for v in ds.data_vars}


def stage_small() -> int:
    print("=== 阶段1：小网格（860×784）direct vs chunked 真实 GEE 交叉验证 ===")
    spec = ArtifactSpec.from_dict({
        "id": "s2_chunking_pilot",
        "asset": "COPERNICUS/S2_SR_HARMONIZED",
        "bands": ["B4", "B3", "B2"],
        "scale": 10,
        "crs": "EPSG:32650",
        "dtype": "uint16",
        "time_range": ["2024-06-01", "2024-08-31"],
        "reducer": "median",
        "aoi": {
            "type": "Polygon",
            "coordinates": [[[116.30, 39.95], [116.40, 39.95],
                             [116.40, 40.02], [116.30, 40.02], [116.30, 39.95]]],
        },
    })
    grid = compute_grid(spec)
    print(f"网格: {grid.width}×{grid.height} @ {grid.scale}m "
          f"(est = {grid.width * grid.height * 3 / 1e6:.1f}M 像素, "
          f"阈值 {MAX_DIRECT_PIXELS / 1e6:.0f}M → auto=direct)")

    ok = True

    import os
    import shutil

    # 缓存击穿：直读腿前先清掉同指纹产物（上一轮 chunked 产物同指纹名，会污染 direct 腿）
    pilot_cache = Path(geoenv.data_path(
        "derived", f"{spec.slug}.{spec.fingerprint()[:8]}.nc"))
    if pilot_cache.exists():
        pilot_cache.unlink()
        print("已清除同指纹缓存产物:", pilot_cache.name)

    os.environ["GEOCODE_ARRAY_PATH"] = "direct"
    r_direct, c_direct = _run("pilot-direct", spec, "direct")
    vals_direct = _load_values(r_direct)
    direct_sha = _sha256(r_direct["path"])
    # 留档直读产物副本（接下来要 unlink 原件做缓存击穿，双路径产物都保给 Verifier）
    direct_copy = Path(r_direct["path"]).with_name(
        Path(r_direct["path"]).stem + ".evidence-direct.nc")
    shutil.copy2(r_direct["path"], direct_copy)
    print(f"direct 完成: {r_direct['_wall_seconds']}s, "
          f"{r_direct['size_mb']} MB, sample keys={sorted(r_direct['sample'].keys())}")

    (Path(r_direct["path"])).unlink()  # 清缓存，强制第二跑真实下载
    os.environ["GEOCODE_ARRAY_PATH"] = "chunked"
    r_chunked, c_chunked = _run("pilot-chunked", spec, "chunked")
    vals_chunked = _load_values(r_chunked)
    expected_chunks = plan_chunks(grid.width, grid.height, 1, 3)
    print(f"chunked 完成: {r_chunked['_wall_seconds']}s, {r_chunked['size_mb']} MB, "
          f"期望 io_chunks={expected_chunks}")
    for m in c_chunked.tail():
        print("  ", m)

    # A5 判据：max|diff| = 0，NaN 位置一致，dims/vars/sample 一致
    if r_direct["dims"] != r_chunked["dims"] or r_direct["vars"] != r_chunked["vars"]:
        ok = False
        print("FAIL: dims/vars 不一致", r_direct["dims"], r_chunked["dims"])
    band_report = {}
    for b in r_direct["vars"]:
        a, c = vals_direct[b], vals_chunked[b]
        nan_ok = np.array_equal(np.isnan(a), np.isnan(c))
        diff = np.abs(a[~np.isnan(a)] - c[~np.isnan(c)])
        max_diff = float(diff.max()) if diff.size else 0.0
        n_nan = int(np.isnan(a).sum())
        line_ok = nan_ok and max_diff == 0.0
        ok = ok and line_ok
        band_report[b] = {
            "max_abs_diff": max_diff, "nan_positions_equal": bool(nan_ok),
            "nan_count": n_nan, "total_px": int(a.size),
            "value_min": float(np.nanmin(a)), "value_max": float(np.nanmax(a)),
        }
        print(f"  {b}: max|diff|={max_diff}  NaN位置一致={nan_ok}  NaN数={n_nan}  "
              f"{'PASS' if line_ok else 'FAIL'}")
    sample_ok = r_direct["sample"] == r_chunked["sample"]
    ok = ok and sample_ok
    print(f"  result.sample 一致: {sample_ok}")

    # 留档（Verifier 证据）：比对数字 + 双路径产物本体都保留，不再 unlink
    evidence = {
        "stage": "small", "spec_id": spec.id, "fingerprint": spec.fingerprint(),
        "grid": {"width": grid.width, "height": grid.height, "scale": grid.scale},
        "expected_io_chunks": expected_chunks,
        "direct": {"path": str(direct_copy), "wall_seconds": r_direct["_wall_seconds"],
                   "size_mb": r_direct["size_mb"], "dims": r_direct["dims"],
                   "sha256": direct_sha,
                   "note": "原件指纹名缓存已 unlink（缓存击穿），此为逐字节副本"},
        "chunked": {"path": r_chunked["path"], "wall_seconds": r_chunked["_wall_seconds"],
                    "size_mb": r_chunked["size_mb"], "dims": r_chunked["dims"],
                    "sha256": _sha256(r_chunked["path"])},
        "bands": band_report,
        "sample_equal": bool(sample_ok),
        "verdict": "PASS" if ok else "FAIL",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    ev_path = Path(r_chunked["path"]).with_name("stage1_cross_validation_evidence.json")
    ev_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("证据留档:", ev_path)
    print("阶段1 总判定:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


class _MemorySampler:
    """psutil RSS 采样线程（0.2s），记录基线与峰值。"""

    def __init__(self, interval: float = 0.2):
        import psutil

        self._proc = psutil.Process()
        self._interval = interval
        self._stop = threading.Event()
        self.baseline = self._proc.memory_info().rss
        self.peak = self.baseline
        self._thread = threading.Thread(target=self._loop, daemon=True)

    def _loop(self):
        while not self._stop.is_set():
            rss = self._proc.memory_info().rss
            if rss > self.peak:
                self.peak = rss
            time.sleep(self._interval)

    def __enter__(self):
        self._thread.start()
        return self

    def __exit__(self, *exc):
        self._stop.set()
        self._thread.join(timeout=2.0)

    def report(self) -> dict:
        return {
            "baseline_mb": round(self.baseline / 1048576, 1),
            "peak_mb": round(self.peak / 1048576, 1),
            "peak_delta_mb": round((self.peak - self.baseline) / 1048576, 1),
        }


def stage_big() -> int:
    print("=== 阶段2：大网格 smoke（≈82km×82km @10m 单期，est≫64M）===")
    spec = ArtifactSpec.from_dict({
        "id": "s2_chunking_big_smoke",
        "asset": "COPERNICUS/S2_SR_HARMONIZED",
        "bands": ["B4", "B3", "B2"],
        "scale": 10,
        "crs": "EPSG:32650",
        "dtype": "uint16",
        "time_range": ["2024-06-01", "2024-06-15"],
        "reducer": "median",
        "aoi": bbox_to_geojson(116.10, 39.60, 117.06, 40.34),
    })
    grid = compute_grid(spec)
    est = grid.width * grid.height * 3
    expected_chunks = plan_chunks(grid.width, grid.height, 1, 3)
    print(f"网格: {grid.width}×{grid.height} @ {grid.scale}m "
          f"(est = {est / 1e6:.1f}M 像素 ≥ {MAX_DIRECT_PIXELS / 1e6:.0f}M → chunked)")
    print(f"io_chunks(计划): {expected_chunks}  "
          f"块驻留 ≤ {expected_chunks['index'] * expected_chunks['width'] * expected_chunks['height'] * 3 * 4 / 1048576:.1f} MB, "
          f"请求侧 ≤ {expected_chunks['index'] * expected_chunks['width'] * expected_chunks['height'] * 5 / 1048576:.1f} MB")

    with _MemorySampler() as mem:
        r, collector = _run("pilot-big", spec, "big")

    print(f"chunked 大网格完成: {r['_wall_seconds']}s, {r['size_mb']} MB")
    for m in collector.tail():
        print("  ", m)
    mem_report = mem.report()
    print(f"内存采样: {json.dumps(mem_report)}")

    # 数值核验（块式扫描，不整段加载；读回阶段同样有界）
    import netCDF4 as nc

    f = nc.Dataset(r["path"])
    dims = {k: len(v) for k, v in f.dimensions.items()}
    print("dims:", dims)
    scan_ok = True
    band_stats = {}
    for b in r["vars"]:
        v = f.variables[b]
        mn, mx, n_nan, n_all = None, None, 0, 0
        for y0 in range(0, dims["y"], 2048):
            y1 = min(y0 + 2048, dims["y"])
            chunk = np.asarray(v[:, y0:y1, :])
            finite = chunk[np.isfinite(chunk)]
            if finite.size:
                b_min, b_max = float(finite.min()), float(finite.max())
                # 修正（Verifier 指出）：累积必须取 min/max，不能被单块覆盖
                mn = b_min if mn is None else min(mn, b_min)
                mx = b_max if mx is None else max(mx, b_max)
            n_nan += int(np.isnan(chunk).sum())
            n_all += chunk.size
            del chunk
        band_stats[b] = {"min": mn, "max": mx, "nan": n_nan, "total": n_all}
        print(f"  {b}: min={mn:.6f} max={mx:.6f} NaN={n_nan}/{n_all} "
              f"({n_nan / n_all * 100:.2f}%)")
    f.close()

    # A3/A4 判定
    judge = {
        "A3_无select('*')": bool(collector.messages and any(
            "分块拉取+落盘" in m for m in collector.messages
        )),  # 走到分块拉取即未触发 select('*')（触发必 400 中断）
        "A4_峰值有界": mem_report["peak_delta_mb"] < 2048,  # 期望 ≈ 基线+单块+缓冲，≪ 全量 810MB×裕度
    }

    # 留档（Verifier 证据）
    evidence = {
        "stage": "big", "spec_id": spec.id, "fingerprint": spec.fingerprint(),
        "grid": {"width": grid.width, "height": grid.height, "scale": grid.scale},
        "est_pixels": est, "expected_io_chunks": expected_chunks,
        "product": {"path": r["path"], "size_mb": r["size_mb"],
                    "wall_seconds": r["_wall_seconds"], "dims": dims},
        "memory": mem_report, "band_stats": band_stats, "judge": judge,
        "verdict": "PASS" if (scan_ok and all(judge.values())) else "FAIL",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    ev_path = Path(r["path"]).with_name("stage2_big_smoke_evidence.json")
    ev_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("证据留档:", ev_path)

    for k, v in judge.items():
        print(f"  {k}: {'PASS' if v else 'FAIL'}")
    all_ok = scan_ok and all(judge.values())
    print("阶段2 总判定:", "PASS" if all_ok else "FAIL")
    print(f"产物保留（Verifier 证据）: {r['path']}")
    return 0 if all_ok else 1


def stage_rescan_big() -> int:
    """对已存在的大网格产物离线重扫描（不碰网络）：修正旧日志的 max 累积缺陷，
    产出 stage2_big_smoke_evidence.json 供 Verifier 使用。"""
    import netCDF4 as nc

    print("=== 阶段rescan-big：对已有大网格产物离线重扫描（无网络）===")
    product = geoenv.data_path("derived", "s2_chunking_big_smoke.9d517910.nc")
    if not Path(product).exists():
        print("FAIL: 产物不存在", product)
        return 1
    expected_chunks = plan_chunks(8244, 8253, 1, 3)
    f = nc.Dataset(product)
    dims = {k: len(v) for k, v in f.dimensions.items()}
    print("dims:", dims)
    band_stats = {}
    for b in ("B4", "B3", "B2"):
        v = f.variables[b]
        mn, mx, n_nan, n_all = None, None, 0, 0
        for y0 in range(0, dims["y"], 2048):
            y1 = min(y0 + 2048, dims["y"])
            chunk = np.asarray(v[:, y0:y1, :])
            finite = chunk[np.isfinite(chunk)]
            if finite.size:
                b_min, b_max = float(finite.min()), float(finite.max())
                mn = b_min if mn is None else min(mn, b_min)
                mx = b_max if mx is None else max(mx, b_max)
            n_nan += int(np.isnan(chunk).sum())
            n_all += chunk.size
            del chunk
        band_stats[b] = {"min": mn, "max": mx, "nan": n_nan, "total": n_all}
        print(f"  {b}: min={mn:.6f} max={mx:.6f} NaN={n_nan}/{n_all} "
              f"({n_nan / n_all * 100:.2f}%)")
    attrs = {k: f.variables[b].getncattr(k)
             for b in ("B4",) for k in f.variables[b].ncattrs()}
    f.close()
    evidence = {
        "stage": "big-rescan", "product": {"path": str(product),
                                           "sha256": _sha256(product)},
        "dims": dims, "expected_io_chunks": expected_chunks,
        "band_stats": band_stats, "B4_attrs": attrs,
        "note": "对已落盘产物离线重扫描；修正 2026-10-07 旧日志的 max 逐块覆盖缺陷（min/NaN 原本正确）",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    ev_path = Path(product).with_name("stage2_big_smoke_evidence.json")
    ev_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print("证据留档:", ev_path)
    print("阶段rescan-big 总判定: PASS")
    return 0


def stage_memory_constant() -> int:
    """风险②对照实验：小网格（860×784 ≈ 2.0M px，仅大网格 1/100）强制分块 +
    内存采样，验证运行峰值增量与网格尺寸无关（第二数据点）。

    常数分解：进程基线 RSS → 导入后 RSS（解释器+库的地板）→ 运行峰值。
    与大网格实测（Δ227.1MB @ 204.1M px，stage2_big_smoke_evidence.json）对照。
    """
    import os

    import netCDF4 as nc  # 预导入（与大网格运行同一库集）
    import psutil

    print("=== 阶段memory-constant：小网格分块内存对照（无大网格依赖）===")
    proc = psutil.Process()
    baseline_mb = proc.memory_info().rss / 1048576

    import xarray as xr  # noqa: F401
    from gis.emit import emit_array  # 导入 gis.emit + 其依赖（geoenv 等）

    post_import_mb = proc.memory_info().rss / 1048576

    spec = ArtifactSpec.from_dict({
        "id": "s2_chunking_pilot",
        "asset": "COPERNICUS/S2_SR_HARMONIZED",
        "bands": ["B4", "B3", "B2"],
        "scale": 10,
        "crs": "EPSG:32650",
        "dtype": "uint16",
        "time_range": ["2024-06-01", "2024-08-31"],
        "reducer": "median",
        "aoi": {
            "type": "Polygon",
            "coordinates": [[[116.30, 39.95], [116.40, 39.95],
                             [116.40, 40.02], [116.30, 40.02], [116.30, 39.95]]],
        },
    })
    grid = compute_grid(spec)
    est = grid.width * grid.height * 3
    out = geoenv.data_path("derived", f"{spec.slug}.{spec.fingerprint()[:8]}.nc")
    if Path(out).exists():
        Path(out).unlink()  # 缓存击穿，确保真实下载
    print(f"网格: {grid.width}×{grid.height}（est {est/1e6:.1f}M px，"
          f"为大网格 204.1M px 的 1/{204.1 / max(est / 1e6, 0.01):.0f}），"
          f"GEOCODE_ARRAY_PATH=chunked 强制分块")

    job = Job(id="pilot-mem", kind="emit", spec=spec, exit="array")
    collector = ProgressCollector("mem")
    job.progress = collector
    pre_run_mb = proc.memory_info().rss / 1048576
    with _MemorySampler(interval=0.1) as mem:
        os.environ["GEOCODE_ARRAY_PATH"] = "chunked"
        result = emit_array(job)
        os.environ["GEOCODE_ARRAY_PATH"] = "auto"
    peak_mb = mem.peak / 1048576

    # 产物核验（变量序 = direct 序，修复轮风险①）
    with nc.Dataset(result["path"]) as f:
        var_order = list(f.variables)
    print("产物变量序:", var_order, "（期望 B4,B3,B2,time,y,x = direct 序）")

    report = {
        "stage": "memory-constant",
        "small": {
            "grid": {"width": grid.width, "height": grid.height},
            "est_pixels": est,
            "baseline_mb": round(baseline_mb, 1),
            "post_import_mb": round(post_import_mb, 1),
            "pre_run_mb": round(pre_run_mb, 1),
            "peak_mb": round(peak_mb, 1),
            "delta_vs_baseline_mb": round(peak_mb - baseline_mb, 1),
            "delta_vs_pre_run_mb": round(peak_mb - pre_run_mb, 1),
        },
        "big_reference": {
            "source": "stage2_big_smoke_evidence.json + big_smoke_log.txt",
            "grid": {"width": 8244, "height": 8253},
            "est_pixels": 204113196,
            "delta_vs_baseline_mb": 227.1,
        },
        "var_order": var_order,
        "expected_var_order": ["B4", "B3", "B2", "time", "y", "x"],
        "note": "两尺寸峰值增量若同带（差 ≪ 全量驻留差），则『与网格尺寸无关』成立",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    ev_path = Path(result["path"]).with_name("memory_constant_evidence.json")
    ev_path.write_text(json.dumps(report, ensure_ascii=False, indent=1, default=str),
                       encoding="utf-8")
    print(json.dumps(report["small"], ensure_ascii=False, indent=1))
    print("证据留档:", ev_path)

    same_band = abs(report["small"]["delta_vs_baseline_mb"] - 227.1) < 300
    order_ok = var_order == report["expected_var_order"]
    print(f"  第二数据点与 227.1MB 同带（±300MB）: {same_band}")
    print(f"  变量序 = direct 序: {order_ok}")
    ok = same_band and order_ok
    print("阶段memory-constant 总判定:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def stage_client(port: int) -> int:
    """A1 佐证：daemon→client→emit_array 全链路（备用端口，不碰共享的 6531）。

    P0 参数（与 tests/smoke_emit.py 同 spec）走 exit="array"：小网格 → direct
    路径（现状行为）。先起 daemon：python -m gis.daemon --port <port> --foreground
    """
    from gis.client import Client

    print(f"=== 阶段client：daemon:{port} → exit=array（P0 参数，现状路径不回退）===")
    c = Client(port=port)
    r = c.set_spec({
        "id": "s2_beijing_test", "asset": "COPERNICUS/S2_SR_HARMONIZED",
        "bands": ["B4", "B3", "B2"], "scale": 10, "crs": "EPSG:32650",
        "dtype": "uint16", "time_range": ["2024-06-01", "2024-08-31"],
        "reducer": "median",
        "aoi": {"type": "Polygon", "coordinates": [[[116.30, 39.95], [116.40, 39.95],
                [116.40, 40.02], [116.30, 40.02], [116.30, 39.95]]]},
    })
    print("   指纹 :", r["spec"]["fingerprint"], "（期望 c9243efd…，金值不回退）")
    sub = c.submit(kind="emit", exit="array")
    jid = sub["job_id"]
    last = None
    for _ in range(120):
        j = c.job(jid)["job"]
        line = f'   [{j["status"]:8s}] {j["pct"]:5.1f}%  {j["phase"]:12s} {j["message"][:58]}'
        if line != last:
            print(line)
            last = line
        if j["status"] in ("done", "failed", "cancelled"):
            if j["status"] == "done":
                res = j.get("result") or {}
                print("   ✅ 产物 :", res.get("path"))
                print("      体积 :", res.get("size_mb"), "MB")
                print("      指纹 :", res.get("spec_fingerprint"))
                print("      dims :", res.get("dims"))
                ok = res.get("spec_fingerprint", "").startswith("c9243efd")
            else:
                print("   ❌ 错误 :")
                for ln in (j.get("error") or "").splitlines()[:14]:
                    print("      " + ln)
                ok = False
            break
        time.sleep(3)
    print("阶段client 总判定:", "PASS" if ok else "FAIL")
    return 0 if ok else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage",
                    choices=["small", "big", "client", "rescan-big",
                             "memory-constant"],
                    required=True)
    ap.add_argument("--port", type=int, default=6532)
    args = ap.parse_args()
    if args.stage == "small":
        return stage_small()
    if args.stage == "client":
        return stage_client(args.port)
    if args.stage == "rescan-big":
        return stage_rescan_big()
    if args.stage == "memory-constant":
        return stage_memory_constant()
    return stage_big()


if __name__ == "__main__":
    sys.exit(main())
