"""
GEE 服务端批处理导出（kind="export"）—— 大范围导出的服务端路径。

背景（docs/README.md §9.2 C5 / §4）：getDownloadURL 直下单次上限约 64M 像素
（emit.MAX_DIRECT_PIXELS 的报错分支）；更大范围走 GEE 服务端批处理任务 ——
提交后任务在 GEE 服务端跑，本地进程退出也不影响，重启恢复靠持久化的
task id（jobstore.py）。

目的地（brief D10，2026-10-06 用户裁决）：`ee.batch.Export.image.toDrive`，
产物落用户自己的 Google Drive（免费配额，无支付依赖）。台账原文
toCloudStorage 因 GCS 建桶需绑信用卡而不可用；GEE 导出写入由 Google 服务端
执行、只能写真正的 GCS 桶，自建 S3 兼容存储不能作目的地——toDrive 与它
任务模型完全同构（六态 / task id / 恢复 / 取消），故改判。

设计要点（brief D3–D8, D10–D11）：
1. **仍是既有计算图上的新去向** —— ee 对象只来自 source.build_image()，
   网格只来自 compute_grid()（红线 1/2）。本模块只做"提交 / 查状态 / 取消"。
2. **状态映射（D4）** —— GEE 六态 → jobs 五态：UNSUBMITTED/READY→queued、
   RUNNING→running、COMPLETED→done（本地 DONE 的唯一依据）、FAILED→failed、
   CANCELLED→cancelled；未知状态保持现状 + warning，不猜。
3. **参数走 job 提交（D3/D11）** —— folder / file_prefix / file_format /
   shard_size / file_dimensions / max_pixels 由提交参数给，不进 ArtifactSpec
   （指纹零触碰，红线 8），也不进 geocode.json（目的地与部署环境无关）。
4. **ee 延迟导入** —— 与 source.py 同模式：本模块顶层不 import ee，
   离线单测可以安全导入全部纯逻辑（tests/unit/test_export_jobstore.py）。

不做：toCloudStorage / GCS 目的地（D10）、分片产物本地拼接（D6）。
"""

from __future__ import annotations

import json
import time
from typing import Any

from . import geoenv
from .jobs import CANCELLED, DONE, FAILED, KIND_EXPORT, QUEUED, RUNNING, Job, JobCancelled
from .spec import ArtifactSpec, SpecError

# GEE 状态轮询间隔（秒）。红线 6：批任务占 GEE 配额，只串行试点；
# 轮询是只读查询，但也不必密集 —— 15s 对分钟级的服务端任务绰绰有余。
POLL_INTERVAL = 15.0

# GEE task.state 全部取值 → jobs 五态
TASK_STATE_MAP = {
    "UNSUBMITTED": QUEUED,
    "READY": QUEUED,
    "RUNNING": RUNNING,
    "COMPLETED": DONE,
    "FAILED": FAILED,
    "CANCELLED": CANCELLED,
}

# file_format 合法值（GEE Export 支持面）
FILE_FORMATS = ("GeoTIFF", "TFRecord")

# Drive 目的地文件夹默认名（D11）
DEFAULT_FOLDER = "gexports"


# ---------------------------------------------------------------------------
# 纯逻辑（离线单测覆盖，验收 A5）
# ---------------------------------------------------------------------------

def map_task_state(gee_state: str | None) -> str | None:
    """GEE task.state → jobs 五态；未知/空返回 None（调用方保持现状 + warning）。"""
    if gee_state is None:
        return None
    return TASK_STATE_MAP.get(str(gee_state).strip().upper())


def require_folder(body: dict) -> str:
    """从提交 body 读 Drive 目的地文件夹（D11），空缺用默认。保留独立函数供离线断言。"""
    folder = str(body.get("folder") or "").strip()
    return folder or DEFAULT_FOLDER


def validate_export_spec(spec: ArtifactSpec) -> None:
    """
    export 的 spec 必填项与 file 出口相同（asset / crs / scale / aoi）。

    不走 spec.validate(exit=...) —— 那是 spec.py 的出口概念，本 change 不动
    spec.py；这里只做同等要求的手工检查，报错风格保持一致。
    """
    missing = [f for f in ("asset", "crs", "scale", "aoi") if getattr(spec, f) in (None, "")]
    if missing:
        raise SpecError(
            f"批处理导出（kind=export）的 spec 缺少必填字段：{', '.join(missing)}\n"
            f"  要求与 exit='file' 相同：asset / crs / scale / aoi。\n"
            f"  提示：可以用 spec.defaults(asset) 推导默认值。"
        )
    spec.validate(None)


def submit_params(body: dict) -> dict:
    """从提交 body 抽取导出参数（D3/D11），带可读校验。"""
    p: dict[str, Any] = {
        "folder": require_folder(body),
    }
    if body.get("file_prefix"):
        p["file_prefix"] = str(body["file_prefix"])
    ff = body.get("file_format") or "GeoTIFF"
    if ff not in FILE_FORMATS:
        raise SpecError(f"file_format={ff!r} 不支持。可选：{', '.join(FILE_FORMATS)}")
    p["file_format"] = ff
    for key in ("shard_size", "max_pixels"):
        if body.get(key) is not None:
            v = int(body[key])
            if v <= 0:
                raise SpecError(f"{key} 必须是正整数，收到 {body[key]!r}。")
            p[key] = v
    fd = body.get("file_dimensions")
    if fd is not None:
        if isinstance(fd, list):
            if not fd or not all(isinstance(x, int) and x > 0 for x in fd):
                raise SpecError("file_dimensions 必须是正整数或正整数列表。")
            p["file_dimensions"] = [int(x) for x in fd]
        else:
            v = int(fd)
            if v <= 0:
                raise SpecError(f"file_dimensions 必须是正整数或正整数列表，收到 {fd!r}。")
            p["file_dimensions"] = v
    return p


def should_cancel_gee(job: Job) -> bool:
    """取消联动判定（D5）：只有未终态、有 task id 的 export 任务才碰 GEE。"""
    return job.kind == KIND_EXPORT and bool(job.task_id) and not job.is_terminal


# ---------------------------------------------------------------------------
# 提交（job 线程体）
# ---------------------------------------------------------------------------

def run_export(
    job: Job,
    *,
    folder: str = DEFAULT_FOLDER,
    file_prefix: str | None = None,
    file_format: str = "GeoTIFF",
    shard_size: int | None = None,
    file_dimensions: int | list[int] | None = None,
    max_pixels: int | None = None,
) -> dict:
    """
    kind="export" 的任务体：提交 + 轮询到终态。

    线程路径：executor 起 job 线程跑本函数 —— 返回即本地 done（仅当 GEE
    COMPLETED），抛异常即 failed / cancelled。daemon 重启后线程消失，由
    daemon 的后台轮询用 task id 直连接管（jobstore.restore 的产物）。
    """
    from . import source
    from .grid import compute_grid

    spec = job.spec
    assert spec is not None

    validate_export_spec(spec)

    job.progress("构建计算图", 5, f"{spec.asset} → ee.Image")
    img = source.build_image(spec)
    grid = compute_grid(spec)
    job.check_cancelled()

    prefix = file_prefix or f"{spec.slug}.{spec.fingerprint()[:8]}"
    est = grid.width * grid.height
    mp = int(max_pixels) if max_pixels else int(est * 1.2) + 1000

    job.progress(
        "提交 GEE 批处理任务", 15,
        f"{grid.width}×{grid.height} @ {grid.scale}m → Drive/{folder}/{prefix}*",
    )
    ee, _ = geoenv.init_ee()  # 内部已 ee.Initialize(project=pid)
    # ⚠️ 不要在这里补一刀裸 ee.Initialize()：它会把 _cloud_api_user_project
    #   清成 None，之后的 ee.data.getTaskStatus/cancelTask 会报
    #   "Caller does not have required permission to use project ..."（试点实测）。

    # region 直接用 spec.aoi 的 ee.Geometry（source.to_ee_geometry，不自行建对象）。
    # Export 有独立的 crs/scale 参数；getDownloadURL 的 region EPSG:4326 约束
    # 是否外推以实测为准（brief D8，试点时核实）。
    region = source.to_ee_geometry(spec.aoi)
    params: dict[str, Any] = {
        "image": img,
        "description": f"geocode-{job.id}",
        "folder": folder,
        "fileNamePrefix": prefix,
        "region": region,
        "scale": grid.scale,
        "crs": grid.crs,
        "fileFormat": file_format,
        "maxPixels": mp,
    }
    if shard_size:
        params["shardSize"] = int(shard_size)
    if file_dimensions:
        params["fileDimensions"] = file_dimensions
    job.check_cancelled()

    task = ee.batch.Export.image.toDrive(**params)
    task.start()
    job.task_id = getattr(task, "id", None) or (task.status() or {}).get("id")
    if not job.task_id:
        raise RuntimeError("GEE 未返回 task id，无法追踪该导出任务。")

    # 提交信息先落 job.result：轮询/恢复路径据此组装产物定位（Drive folder + 前缀）。
    job.result = {
        "task_id": job.task_id,
        "description": f"geocode-{job.id}",
        "folder": folder,
        "file_prefix": prefix,
        "destination": f"Drive/{folder}/{prefix}*",
        "max_pixels": mp,
        "file_format": file_format,
    }
    job.progress(
        "已提交", 20,
        f"task {job.task_id}（GEE 服务端执行中，本地每 {POLL_INTERVAL:.0f}s 查一次）",
    )

    while True:
        job.check_cancelled()
        _sleep(POLL_INTERVAL, job)
        try:
            r = query_task(job)
        except Exception as e:
            # 网络抖动不该把服务端任务标成本地失败 —— 如实记录（带连续计数），下轮再查
            note_poll_failure(job, e)
            continue
        reset_poll_failure(job)
        apply_progress(job, r)
        if r["terminal"]:
            if r["mapped"] == DONE:
                return r["result"]
            if r["mapped"] == FAILED:
                raise RuntimeError(r["error"] or "GEE task FAILED")
            raise JobCancelled()        # CANCELLED


def _sleep(seconds: float, job: Job) -> None:
    """分片睡眠，取消请求最迟 ~0.5s 内被看到。"""
    end = time.time() + seconds
    while time.time() < end:
        job.check_cancelled()
        time.sleep(min(0.5, max(0.0, end - time.time())))


# ---------------------------------------------------------------------------
# 查询与状态推进
# ---------------------------------------------------------------------------

def query_task(job: Job) -> dict:
    """
    查一次 GEE task 状态并解读。不改 job 的终态 —— 终态收敛由调用方决定：
    线程路径经 executor（返回/抛异常），恢复路径由 daemon 轮询直接写。
    """
    status = _gee_task_status(job.task_id)
    gee_state = status.get("state")
    mapped = map_task_state(gee_state)
    out: dict[str, Any] = {
        "gee_state": gee_state,
        "mapped": mapped,
        "terminal": mapped in (DONE, FAILED, CANCELLED),
        "detail": status,
        "error": None,
        "result": None,
    }
    if mapped == FAILED:
        out["error"] = _format_gee_error(status)
    if mapped == DONE:
        out["result"] = _export_result(job, status)
    return out


def apply_progress(job: Job, r: dict) -> None:
    """把 query_task 的解读落到 job 的非终态字段（状态 / phase / message）。"""
    mapped = r["mapped"]
    if mapped is None:
        job.warning = f"未知 GEE 状态 {r['gee_state']!r}，保持本地现状"
        return
    if mapped in (QUEUED, RUNNING):
        job.status = mapped
        job.phase = "GEE 排队" if mapped == QUEUED else "GEE 计算中"
        msg = f"GEE {r['gee_state']} · task {job.task_id}"
        if job.message != msg:
            job.message = msg


def finalize(job: Job, r: dict) -> None:
    """恢复路径（daemon 轮询）的终态收敛；线程路径走 executor，不经这里。"""
    mapped = r["mapped"]
    job.status = mapped
    job.finished_at = time.time()
    if mapped == DONE:
        job.pct = 100.0
        job.phase = "完成"
        job.result = r["result"]
    elif mapped == FAILED:
        job.phase = "失败"
        job.error = r["error"] or "GEE task FAILED"
    else:
        job.phase = "已取消"
        job.message = job.message or "GEE 侧任务已取消"


def note_poll_failure(job: Job, err: BaseException) -> int:
    """
    记录连续查询失败次数并如实更新 message。

    spec：「轮询失败不误标终态，连续失败在 job.message 中如实报错」——
    报错带连续计数，权限传播这类分钟级窗口内，用户能看到"还在重试、
    第几次"而不是一条冻结的旧消息。返回当前连续失败数。
    """
    n = int(getattr(job, "_poll_fail_streak", 0)) + 1
    job._poll_fail_streak = n
    job.message = f"GEE 查询失败（连续第 {n} 次，下轮重试）：{type(err).__name__}: {err}"
    return n


def reset_poll_failure(job: Job) -> None:
    """查询成功即清零连续失败计数（下一次失败从 1 起算）。"""
    job._poll_fail_streak = 0


def cancel_gee_task(task_id: str) -> bool:
    """
    调 GEE task.cancel()（D5）。ee 1.7.46 按 id 取消走 `ee.data.cancelTask`。
    失败不抛 —— 本地取消照常推进，调用方把失败记进 job.warning
    （服务端任务可能仍在跑，需人工核对）。
    """
    try:
        ee, _ = geoenv.init_ee()  # 内部已 ee.Initialize(project=pid)；勿再裸 Initialize（见 run_export 注）
        ee.data.cancelTask(task_id)
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# 内部
# ---------------------------------------------------------------------------

def _gee_task_status(task_id: str | None) -> dict:
    """
    按 task id 直连 GEE 查询，不做列表扫描（D7）。

    ⚠️ ee 1.7.46 实测：`ee.batch.Task(task_id)` 构造器要求 task_type/state
    等必填参数，无法按 id 重建 Task 对象（试点实测的 TypeError）。等价且
    更直接的按 id 接口是 `ee.data.getTaskStatus`；取消同理用 cancelTask。
    查无此 id 时返回 state=None（调用方按"未知状态"处理，不猜）。
    """
    if not task_id:
        return {"state": None, "error_message": "本地没有 task id（提交可能未完成）"}
    ee, _ = geoenv.init_ee()  # 内部已 ee.Initialize(project=pid)；勿再裸 Initialize（见 run_export 注）
    statuses = ee.data.getTaskStatus(task_id)
    if not statuses:
        return {"state": None, "error_message": f"GEE 查无此 task：{task_id}"}
    return dict(statuses[0] or {})


def _format_gee_error(status: dict) -> str:
    """getTaskStatus 的失败任务给 'error_message'（字符串）；兼容嵌套 dict 形态。"""
    err = status.get("error_message") or status.get("error")
    if isinstance(err, dict):
        msg = err.get("message") or json.dumps(err, ensure_ascii=False, default=str)
        return f"GEE task FAILED：{msg}"
    return f"GEE task FAILED：{err or '（GEE 未给错误详情）'}"


def _export_result(job: Job, status: dict) -> dict:
    """终态 result：以提交时落在 job.result 里的定位信息为底，补 GEE 侧结论。"""
    base = dict(job.result or {})
    base["gee_state"] = status.get("state")
    # getTaskStatus 会带回产物目的地（toDrive 是 Drive 文件夹链接）——最有力的落盘证据
    if status.get("destination_uris"):
        base["destination_uris"] = list(status["destination_uris"])
    return base
