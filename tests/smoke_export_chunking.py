"""
C15 分块下载在线冒烟（A1–A6 的实测证据入口）。

    python tests/smoke_export_chunking.py --stage a2      # 小 AOI 强制分块 vs 直写逐像元
    python tests/smoke_export_chunking.py --stage a3      # 注入断连的失败路径
    python tests/smoke_export_chunking.py --stage a4      # GeoTIFF/NetCDF 的 nodata 一致
    python tests/smoke_export_chunking.py --stage a5      # paths.data_dir 落盘
    python tests/smoke_export_chunking.py --stage a6      # 缓存清单（真实产物根，只读）
    python tests/smoke_export_chunking.py --stage a1      # 真实 adcode 370900 三出口（长任务）
    python tests/smoke_export_chunking.py --stage quick   # a2+a3+a4+a5+a6

每个 stage 落一份 `logs/c15_<stage>.json` 证据（含关键观察值与耗时），stdout 打印
`SMOKE-RESULT` 摘要行。需要真实 GEE（42/47）。

纪纪律：
- a2/a3/a4/a5 全部在**临时产物根**里跑（mock `geoenv.data_root`），不污染 data/；
- a1 是验收要求的真实尺度实测，产物落真实产物根（可复用缓存）；
- 只在 a1/a6 触碰真实 data/，a6 只读。
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
import tempfile
import time
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from gis import emit as emit_mod                     # noqa: E402
from gis import export_chunks as xc                  # noqa: E402
from gis import geoenv                               # noqa: E402
from gis.aoi import admin_aoi                      # noqa: E402
from gis.grid import compute_grid                    # noqa: E402
from gis.jobs import Job, bind_progress, run_emit    # noqa: E402
from gis.spec import (                               # noqa: E402
    ArtifactSpec, LayoutSpec, RenderSpec, bbox_to_geojson,
)

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOGS = ROOT / "logs"
P0_AOI = {
    "type": "Polygon",
    "coordinates": [[[116.30, 39.95], [116.40, 39.95],
                     [116.40, 40.02], [116.30, 40.02], [116.30, 39.95]]],
}
AOI_CITY = admin_aoi("370900")        # 泰安市
AOI_MOUNT = bbox_to_geojson(117.05, 36.15, 117.15, 36.25)   # 泰山附近小框


def p0_spec() -> ArtifactSpec:
    """P0 金指纹样本（指纹 b91c09c9c6451c16）—— A2 的对照基准。"""
    return ArtifactSpec(
        id="s2_beijing_test", asset="COPERNICUS/S2_SR_HARMONIZED",
        bands=("B4", "B3", "B2"), scale=10, crs="EPSG:32650", dtype="uint16",
        time_range=("2024-06-01", "2024-08-31"), reducer="median", aoi=P0_AOI,
    )


def dem_small_spec() -> ArtifactSpec:
    """小 DEM（新指纹，非缓存）—— A4 的同一 spec 两出口对照。"""
    return ArtifactSpec(
        id="c15_dem_small", asset="COPERNICUS/DEM/GLO30", bands=("DEM",),
        scale=30, crs="EPSG:32650", dtype="float32", aoi=AOI_MOUNT,
    )


def dem_county_spec() -> ArtifactSpec:
    """既有缓存产物（tif 的 nodata 是 -inf）—— A4 的缓存命中归一证据。"""
    return ArtifactSpec(
        id="taian_dem_county", asset="COPERNICUS/DEM/GLO30", bands=("DEM",),
        scale=30, crs="EPSG:32650", dtype="float32", aoi=admin_aoi("370902"),
    )


def truecolor_10m_spec() -> ArtifactSpec:
    """A1：泰安市 S2 真彩色 10m（165.4M 像素，估请求侧 ≈2.5 GB）。"""
    return ArtifactSpec(
        id="taian_s2_truecolor_10m", asset="COPERNICUS/S2_SR_HARMONIZED",
        bands=("B4", "B3", "B2"), scale=10, crs="EPSG:32650", dtype="uint16",
        time_range=("2025-06-01", "2025-08-31"), reducer="median", aoi=AOI_CITY,
        note="C15 A1：真实尺度三出口（10m 真彩色）",
        render=RenderSpec(bands=("B4", "B3", "B2")),
        layout=LayoutSpec(title="泰安市 Sentinel-2 真彩色 10m（2025 夏季中值合成）"),
    )


def run_spec(spec: ArtifactSpec, exit_: str, *, renderer=None, data_root=None,
             patches=(), quiet=False):
    """跑一次 emit，返回 (result, job, progress_lines)。可注入产物根与任意 patch。"""
    job = Job(id=f"{spec.id}_{exit_}_{renderer or ''}", kind="emit",
              spec=spec, exit=exit_, renderer=renderer)
    lines: list[tuple] = []
    bind_progress(job, lambda ev, p: lines.append(
        (ev, p.get("pct"), p.get("phase"), p.get("message"))))
    t0 = time.time()
    with contextlib.ExitStack() as stack:
        if data_root is not None:
            stack.enter_context(mock.patch.object(
                emit_mod.geoenv, "data_root", return_value=Path(data_root)))
        for target, attr, value in patches:
            stack.enter_context(mock.patch.object(target, attr, value))
        try:
            result = run_emit(job)
            err = None
        except BaseException as e:          # noqa: BLE001 — 证据要连错误一起留
            result, err = None, e
    dt = time.time() - t0
    if not quiet:
        for _ev, pct, phase, msg in lines[-28:]:
            print(f"    [{pct if pct is not None else '--':>5}] {phase:<14} {str(msg)[:88]}")
    if err is not None and not quiet:
        print(f"    ❌ {type(err).__name__}: {str(err)[:400]}")
    return result, job, err, dt, lines


def write_report(stage: str, payload: dict) -> Path:
    LOGS.mkdir(parents=True, exist_ok=True)
    p = LOGS / f"c15_{stage}.json"
    p.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n",
                 encoding="utf-8")
    return p


def raster_diff(path_a: Path, path_b: Path) -> dict:
    """逐像元比对两张栅格（掩膜 + 数值），返回证据字典。"""
    import numpy as np
    import rasterio

    with rasterio.open(path_a) as a, rasterio.open(path_b) as b:
        info = {
            "shape": [a.width, a.height, b.width, b.height],
            "count": [a.count, b.count],
            "dtype": [a.dtypes[0], b.dtypes[0]],
            "nodata": [str(a.nodata), str(b.nodata)],
            "crs": [str(a.crs), str(b.crs)],
            "transform_equal": tuple(a.transform)[:6] == tuple(b.transform)[:6],
        }
        if (a.count, a.width, a.height) != (b.count, b.width, b.height):
            info["match"] = False
            info["reason"] = "形状/波段数不一致"
            return info
        worst = 0.0
        mask_ok = True
        nan_ok = True
        for i in range(1, a.count + 1):
            av = a.read(i, masked=True)
            bv = b.read(i, masked=True)
            mask_ok &= bool((np.ma.getmaskarray(av) == np.ma.getmaskarray(bv)).all())
            x = np.ma.filled(av.astype("float64"), np.nan)
            y = np.ma.filled(bv.astype("float64"), np.nan)
            both_nan = np.isnan(x) & np.isnan(y)
            nan_ok &= bool(both_nan.sum() == np.isnan(x).sum() == np.isnan(y).sum())
            valid = ~np.isnan(x) & ~np.isnan(y)
            if valid.any():
                worst = max(worst, float(np.abs(x[valid] - y[valid]).max()))
        info.update({"mask_equal": mask_ok, "nan_positions_equal": nan_ok,
                     "max_abs_diff": worst, "match": bool(mask_ok and nan_ok and worst == 0.0)})
    return info


# ---------------------------------------------------------------------------
# stages
# ---------------------------------------------------------------------------

def stage_a2(args) -> dict:
    """A2：小 AOI 强制分块 vs 直写，逐像元完全一致（max|diff| = 0）。"""
    spec = p0_spec()
    grid = compute_grid(spec)
    print(f"[A2] P0 样本 {grid.width}×{grid.height} @ {grid.scale}m 指纹 {spec.fingerprint()[:8]}")
    with tempfile.TemporaryDirectory(prefix="c15a2_") as tmp:
        direct_root = Path(tmp) / "direct"
        chunk_root = Path(tmp) / "chunked"
        limit = 3_000_000     # 10.1 MB 的请求 → 切 4 片
        print(f"[A2] 直写（缺省上限）→ {direct_root}")
        r_direct, _j, e_direct, dt_direct, _l = run_spec(spec, "file", data_root=direct_root)
        if e_direct:
            raise RuntimeError(f"直写路径失败：{e_direct}")
        print(f"[A2] 分块（MAX_DOWNLOAD_BYTES={limit:,}）→ {chunk_root}")
        r_chunk, _j2, e_chunk, dt_chunk, lines = run_spec(
            spec, "file", data_root=chunk_root,
            patches=[(emit_mod, "MAX_DOWNLOAD_BYTES", limit)],
        )
        if e_chunk:
            raise RuntimeError(f"分块路径失败：{e_chunk}")
        chunk_msgs = [m for _e, _p, ph, m in lines if ph == "分块下载"]
        n_chunks = max((int(str(m).split("片 ")[1].split("/")[0])
                        for m in chunk_msgs if "片 " in str(m)), default=0)
        diff = raster_diff(Path(r_direct["path"]), Path(r_chunk["path"]))
        parts = list(Path(chunk_root).rglob("*.part*"))
        payload = {
            "stage": "a2", "grid": [grid.width, grid.height], "scale": grid.scale,
            "fingerprint": spec.fingerprint(),
            "limit_bytes": limit, "n_chunks": n_chunks,
            "direct": {"path": r_direct["path"], "size_mb": r_direct["size_mb"],
                       "seconds": round(dt_direct, 1)},
            "chunked": {"path": r_chunk["path"], "size_mb": r_chunk["size_mb"],
                        "seconds": round(dt_chunk, 1)},
            "per_pixel": diff,
            "leftover_parts": [str(p) for p in parts],
            "ok": bool(diff.get("match") and n_chunks > 1 and not parts),
        }
    print(f"[A2] {payload['n_chunks']} 片；逐像元：{json.dumps(diff, ensure_ascii=False)}")
    print(f"[A2] {'✅ PASS' if payload['ok'] else '❌ FAIL'} 残留 .part={len(parts)}")
    return payload


def _inject_disconnect(dest) -> bool:
    """第 2 片注入瞬时断连（A3 要求真实失败路径，不是纯单测）。"""
    return ".c0002." in str(dest)


def stage_a3(args) -> dict:
    """A3：单片连续失败 → 错误文案含片号/片数/体积/上限/重试次数/四条出路，且无残留。"""
    spec = p0_spec()
    limit = 3_000_000
    real_download = emit_mod._download
    calls = {"real": 0, "injected": 0}

    class RemoteDisconnected(OSError):
        pass

    def flaky(url, dest, job, **kw):
        if _inject_disconnect(dest):
            calls["injected"] += 1
            raise RemoteDisconnected("注入的瞬时断连（A3 实测）")
        calls["real"] += 1
        return real_download(url, dest, job, **kw)

    with tempfile.TemporaryDirectory(prefix="c15a3_") as tmp:
        root = Path(tmp) / "out"
        with mock.patch.object(emit_mod, "_download", flaky), \
                mock.patch.object(emit_mod, "DOWNLOAD_BACKOFF_SECONDS", (0.05, 0.05)), \
                mock.patch.object(emit_mod, "DOWNLOAD_ATTEMPTS", 3), \
                mock.patch.object(emit_mod, "CHUNK_ATTEMPTS", 1):
            _r, _j, err, dt, lines = run_spec(
                spec, "file", data_root=root,
                patches=[(emit_mod, "MAX_DOWNLOAD_BYTES", limit)],
            )
        msg = str(err) if err else ""
        leftovers = [str(p) for p in Path(root).rglob("*")
                     if p.is_file() and ".part" in p.name]
        finals = [str(p) for p in Path(root).rglob("*.tif")]
        checks = {
            "raised": err is not None,
            "is_runtime_error": isinstance(err, RuntimeError),
            "has_chunk_index": "第 2/" in msg,
            "has_estimate": "单片估算" in msg,
            "has_limit": "单请求上限" in msg,
            "has_retries": "已重试 2 次" in msg,
            "has_exits": "放大 scale" in msg and "改用 array" in msg,
            "no_part_left": not leftovers,
            "no_half_product": not finals,
            "real_chunks_downloaded": calls["real"] >= 1,
            "injected_attempts": calls["injected"] == 3,
        }
        retry_lines = [m for _e, _p, ph, m in lines if ph == "重试"]
        payload = {
            "stage": "a3", "seconds": round(dt, 1), "error": msg,
            "checks": checks, "calls": calls,
            "retry_log_lines": [str(m)[:120] for m in retry_lines],
            "leftover_parts": leftovers, "final_products": finals,
            "ok": all(checks.values()),
        }
    print(f"[A3] 注入断连 → {type(err).__name__}")
    for line in msg.splitlines()[:12]:
        print("    " + line)
    for k, v in checks.items():
        print(f"    [{'✓' if v else '✗'}] {k}")
    print(f"[A3] {'✅ PASS' if payload['ok'] else '❌ FAIL'}")
    return payload


def stage_a3b(args) -> dict:
    """A3 补充：一次性瞬时错误 → 重试后**真的恢复**（重试日志 + 产物落地）。"""
    spec = p0_spec()
    limit = 3_000_000
    real_download = emit_mod._download
    state = {"injected": 0}

    class RemoteDisconnected(OSError):
        pass

    def flaky(url, dest, job, **kw):
        if ".c0003." in str(dest) and state["injected"] == 0:
            state["injected"] += 1
            raise RemoteDisconnected("注入一次瞬时断连（A3 补充：重试后恢复）")
        return real_download(url, dest, job, **kw)

    with tempfile.TemporaryDirectory(prefix="c15a3b_") as tmp:
        root = Path(tmp) / "out"
        with mock.patch.object(emit_mod, "_download", flaky), \
                mock.patch.object(emit_mod, "DOWNLOAD_BACKOFF_SECONDS", (0.2, 0.2)):
            r, _j, err, dt, lines = run_spec(
                spec, "file", data_root=root,
                patches=[(emit_mod, "MAX_DOWNLOAD_BYTES", limit)],
            )
        retry_lines = [str(m) for _e, _p, ph, m in lines if ph == "重试"]
        final_parts = [str(p) for p in Path(root).rglob("*.part*")]
        payload = {
            "stage": "a3b", "seconds": round(dt, 1),
            "injected": state["injected"],
            "error": str(err)[:300] if err else None,
            "retry_log_lines": [x[:120] for x in retry_lines],
            "product": (r or {}).get("path"),
            "leftover_parts": final_parts,
            "ok": bool(err is None and r and state["injected"] == 1
                       and retry_lines and not final_parts),
        }
    print(f"[A3b] 注入 1 次瞬时断连 → {'成功恢复' if payload['ok'] else '未恢复'}"
          f"（重试日志 {len(retry_lines)} 条）")
    for line in payload["retry_log_lines"][:3]:
        print("    " + line)
    print(f"[A3b] {'✅ PASS' if payload['ok'] else '❌ FAIL'}")
    return payload


def stage_a4(args) -> dict:
    """A4：GeoTIFF 与 NetCDF 的 nodata 语义一致（NaN），含缓存命中归一。"""
    import numpy as np
    import rasterio
    import xarray as xr

    out: dict = {"stage": "a4", "fresh": {}, "cached": {}}
    with tempfile.TemporaryDirectory(prefix="c15a4_") as tmp:
        root = Path(tmp)
        spec = dem_small_spec()
        r_tif, _j, e1, dt1, _l = run_spec(spec, "file", data_root=root)
        if e1:
            raise RuntimeError(f"file 出口失败：{e1}")
        r_nc, _j, e2, dt2, _l = run_spec(spec, "array", data_root=root)
        if e2:
            raise RuntimeError(f"array 出口失败：{e2}")
        with rasterio.open(r_tif["path"]) as ds:
            tif_info = {
                "dtype": ds.dtypes[0], "nodata": str(ds.nodata),
                "nodata_is_nan": bool(ds.nodata is not None and np.isnan(ds.nodata)),
                "n_nan": int(np.isnan(ds.read(1)).sum()),
                "n_neg_inf": int(np.isneginf(ds.read(1)).sum()),
                "shape": [ds.width, ds.height],
            }
        with xr.open_dataset(r_nc["path"]) as ds:
            var = list(ds.data_vars)[0]
            fill = ds[var].encoding.get("_FillValue", ds[var].attrs.get("_FillValue"))
            nc_info = {
                "var": var, "dtype": str(ds[var].dtype),
                "fill_value": str(fill),
                "fill_is_nan": bool(fill is not None and np.isnan(fill)),
                "n_nan": int(np.isnan(ds[var].values).sum()),
            }
        # masked read 一致性
        with rasterio.open(r_tif["path"]) as ds:
            tif_masked = ds.read(1, masked=True)
        with xr.open_dataset(r_nc["path"]) as ds:
            nc_vals = ds[list(ds.data_vars)[0]].values
        mask_equal = bool(
            (np.ma.getmaskarray(tif_masked).sum() == np.isnan(nc_vals).sum())
        )
        out["fresh"] = {
            "tif": tif_info, "nc": nc_info, "mask_count_equal": mask_equal,
            "seconds": [round(dt1, 1), round(dt2, 1)],
            "ok": bool(tif_info["nodata_is_nan"] and nc_info["fill_is_nan"]
                       and tif_info["n_neg_inf"] == 0 and mask_equal),
        }

    # 既有缓存产物（旧 nodata = -inf / 0）：emit_file 命中缓存时就地归一
    spec = dem_county_spec()
    with rasterio.open(geoenv.data_path("derived", f"{spec.slug}.{spec.fingerprint()[:8]}.tif")) as ds:
        before = {"nodata": str(ds.nodata), "dtype": ds.dtypes[0]}
    r_cached, _j, e3, _dt3, lines = run_spec(spec, "file", quiet=True)
    if e3:
        raise RuntimeError(f"缓存命中路径失败：{e3}")
    with rasterio.open(r_cached["path"]) as ds:
        after = {"nodata": str(ds.nodata), "dtype": ds.dtypes[0],
                 "nodata_is_nan": bool(ds.nodata is not None and np.isnan(ds.nodata)),
                 "n_neg_inf": int(np.isneginf(ds.read(1)).sum())}
    norm_lines = [str(m) for _e, _p, ph, m in lines if ph == "既有产物 nodata 归一"]
    out["cached"] = {"path": r_cached["path"], "before": before, "after": after,
                     "normalize_log": norm_lines,
                     "ok": bool(after["nodata_is_nan"] and after["n_neg_inf"] == 0)}
    out["ok"] = bool(out["fresh"]["ok"] and out["cached"]["ok"])
    print(f"[A4] 新产物 tif={out['fresh']['tif']}")
    print(f"[A4] 新产物 nc ={out['fresh']['nc']}")
    print(f"[A4] 缓存归一  {before} → {after}")
    print(f"[A4] {'✅ PASS' if out['ok'] else '❌ FAIL'}")
    return out


def stage_a5(args) -> dict:
    """A5：geocode.json 设 paths.data_dir → 产物落该目录且三子目录自动创建。"""
    spec = dem_small_spec()
    with tempfile.TemporaryDirectory(prefix="c15a5_") as tmp:
        target = Path(tmp) / "research_out"
        cfg = json.loads(geoenv.CONFIG_PATH.read_text(encoding="utf-8"))
        cfg.setdefault("paths", {})["data_dir"] = str(target)
        cfg_path = Path(tmp) / "geocode.json"
        cfg_path.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
        with mock.patch.object(geoenv, "CONFIG_PATH", cfg_path):
            root = geoenv.data_root()
            dirs = {k: geoenv.data_path(k) for k in geoenv.DATA_KINDS}
            r, _j, err, dt, _l = run_spec(spec, "file", quiet=True)
        payload = {
            "stage": "a5", "configured": str(target), "data_root": str(root),
            "subdirs": {k: [str(v), v.is_dir()] for k, v in dirs.items()},
            "product": (r or {}).get("path"),
            "product_under_target": bool(r and str(r["path"]).startswith(str(target))),
            "error": str(err) if err else None,
            "seconds": round(dt, 1),
        }
        payload["ok"] = bool(
            payload["data_root"] == str(target)
            and payload["product_under_target"]
            and all(v[1] for v in payload["subdirs"].values())
            and err is None
        )
    print(f"[A5] data_root={payload['data_root']}")
    print(f"[A5] 产物={payload['product']}")
    print(f"[A5] {'✅ PASS' if payload['ok'] else '❌ FAIL'}")
    return payload


def stage_a6(args) -> dict:
    """A6：真实产物根的缓存清单 + 显式清理守卫（只读 + dry-run，不真删）。

    「当代指纹」用 mark-current 的典型用法登记：索引建立**之前**就存在的
    存量产物，其当代指纹必须由人/文档指定：
      - P0 样本：取 `tests/unit/_helpers` 的金指纹单一事实源（PV 时代自动跟随）；
      - c8_mini_dongcheng：README §9 记录的 mini-three-exits 指纹。
    """
    from gis import cache_manage as cm
    from tests.unit._helpers import P0_SPEC_DICT, expected_p0_fingerprint

    root = geoenv.data_path("derived")
    p0_slug = P0_SPEC_DICT["id"]
    known_current = {
        p0_slug: expected_p0_fingerprint(),
        "c8_mini_dongcheng": "2ba8b78c",
    }
    # 只登记产物根里**真实存在**的 slug（避免索引无意义膨胀）
    existing_slugs = {e.slug for e in cm.scan(root)}
    seeded = {k: v for k, v in known_current.items() if k in existing_slugs}
    for slug, fp in seeded.items():
        cm.record_current(root, slug, fp)

    current = cm.load_index(root)
    entries = cm.classify(cm.scan(root), current)
    summary = cm.summarize(entries)
    plan_history = cm.plan_prune(entries)
    plan_all = cm.plan_prune(entries, include_unknown=True)
    current_names = {e.path.name for e in entries if e.status == cm.STATUS_CURRENT}
    current_in_all_plan = [e.path.name for e in plan_all
                           if e.status == cm.STATUS_CURRENT]

    # dry-run：未确认必须拒绝（不删任何文件）
    refused_without_confirm = False
    try:
        cm.run_prune(plan_history, confirm=False)
    except RuntimeError:
        refused_without_confirm = True
    still_there = all((root / n).exists() for n in current_names)

    payload = {
        "stage": "a6", "root": str(root), "index": str(cm.index_path(root)),
        "seeded_slugs": seeded,
        "current_fingerprints": current,
        "summary": summary,
        "historical": [e.to_dict() for e in entries if e.status == cm.STATUS_HISTORICAL],
        "plan_history_count": len(plan_history),
        "plan_history_bytes": sum(e.size_bytes for e in plan_history),
        "plan_include_unknown_bytes": sum(e.size_bytes for e in plan_all),
        "current_in_any_plan": current_in_all_plan,
        "refused_without_confirm": refused_without_confirm,
        "current_artifacts_intact": still_there,
        "ok": bool(refused_without_confirm and still_there
                   and not current_in_all_plan),   # 当代产物永不可删
    }
    print(f"[A6] {root}")
    print(f"[A6] 当代 {summary['count'][cm.STATUS_CURRENT]} 项 / "
          f"历史 {summary['count'][cm.STATUS_HISTORICAL]} 项 / "
          f"未登记 {summary['count'][cm.STATUS_UNKNOWN]} 项；"
          f"合计 {cm.human_size(summary['total_bytes'])}")
    print(f"[A6] 历史指纹可清理 {len(plan_history)} 项"
          f"（{cm.human_size(payload['plan_history_bytes'])}）；"
          f"连未登记一起 {payload['plan_include_unknown_bytes']/2**30:.2f} GB")
    print(f"[A6] 未确认时拒绝执行：{refused_without_confirm}；"
          f"当代产物进清理计划：{current_in_all_plan}")
    print(f"[A6] {'✅ PASS' if payload['ok'] else '❌ FAIL'}")
    return payload


def stage_a1(args) -> dict:
    """A1：真实 adcode 370900、10m 真彩色，三出口全成功 + file↔array 逐像元一致。"""
    spec = truecolor_10m_spec()
    grid = compute_grid(spec)
    n_bands = len(spec.bands)
    px = grid.width * grid.height
    est5 = px * n_bands * xc.BYTES_PER_PIXEL_BAND          # float32 口径（旧）
    est9 = px * n_bands * xc.bytes_per_pixel_band("double")  # S2 真彩色实际是 double
    print(f"[A1] 网格 {grid.width}×{grid.height} = {px/1e6:.1f}M 像素；请求侧估算 "
          f"{est5/2**30:.2f}–{est9/2**30:.2f} GiB（5–9 B/像素/波段），"
          f"上限 {xc.MAX_DOWNLOAD_BYTES/2**20:.0f} MiB")
    results = {}
    for exit_, renderer in (("file", None), ("array", None), ("map", "qgis")):
        print(f"[A1] ▶ {exit_}{'/' + renderer if renderer else ''} ...", flush=True)
        r, _j, err, dt, _l = run_spec(spec, exit_, renderer=renderer)
        results[exit_] = {"ok": err is None and r is not None,
                          "seconds": round(dt, 1),
                          "error": str(err)[:600] if err else None,
                          "path": (r or {}).get("path"),
                          "artifacts": (r or {}).get("artifacts")}
        print(f"[A1] {'✅' if results[exit_]['ok'] else '❌'} {exit_} "
              f"({dt:.0f}s) {results[exit_]['path']}", flush=True)
        if err:
            print(f"     {str(err)[:500]}")
            break
    compare = None
    if results["file"]["ok"] and results["array"]["ok"]:
        print("[A1] ▶ file ↔ array 逐像元比对 ...", flush=True)
        t0 = time.time()
        compare = emit_mod.compare_exits(spec)
        compare["seconds"] = round(time.time() - t0, 1)
        print(f"[A1] max|diff|={compare.get('max_abs_diff')} "
              f"mask_match={compare.get('mask_match')} ok={compare.get('ok')}")
    payload = {
        "stage": "a1", "grid": [grid.width, grid.height], "scale": grid.scale,
        "pixels": px, "est_bytes_float32": est5, "est_bytes_double": est9,
        "fingerprint": spec.fingerprint(),
        "exits": results, "compare": compare,
        "ok": bool(all(v["ok"] for v in results.values())
                   and compare and compare.get("ok")),
    }
    return payload


STAGES = {"a1": stage_a1, "a2": stage_a2, "a3": stage_a3, "a3b": stage_a3b,
          "a4": stage_a4, "a5": stage_a5, "a6": stage_a6}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", required=True,
                    choices=[*STAGES, "quick"])
    args = ap.parse_args()
    names = ["a2", "a3", "a3b", "a4", "a5", "a6"] if args.stage == "quick" else [args.stage]
    all_ok = True
    for name in names:
        payload = STAGES[name](args)
        path = write_report(name, payload)
        all_ok &= bool(payload.get("ok"))
        print(f"SMOKE-RESULT {name}: {'PASS' if payload.get('ok') else 'FAIL'} → {path}\n")
    return 0 if all_ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
