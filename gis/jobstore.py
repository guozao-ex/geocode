"""
export 任务的最小持久化（brief D7，docs/README.md §9.2 决定 4）。

范围：**仅 kind="export"** —— describe / defaults / emit 是本地瞬时计算，
重启丢失属预期；GEE 服务端任务才需要跨 daemon 重启存活。

文件：`.cache/jobs.json`（与 daemon.json 同目录同风格）。写盘时机由 daemon
的事件监听驱动：提交后（job.created）、每次状态变化（job.updated）、终态
（job.finished）—— daemon 重启后的恢复轮询也走同一套事件，所以
"每次状态变化写盘"不需要每个调用点手动记。

格式：`{job_id: record}`，record = job.to_dict(include_result=True)。
加载用 restore() 重建 Job（不带线程），daemon 启动后由后台轮询用
task id 直连 GEE（ee.batch.Task(id)）重查推进 —— 不做列表扫描（D7）。
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from . import geoenv
from .jobs import KIND_EXPORT, Job
from .spec import ArtifactSpec

DEFAULT_PATH = geoenv.CACHE_DIR / "jobs.json"


def save(records: dict[str, dict], path: Path | None = None) -> None:
    """
    原子写盘：临时文件放**目标同目录**再 replace —— 同卷 rename 原子
    （跨盘 os.replace 会 WinError 17，踩坑 #11），下游只看到完整文件。
    """
    path = Path(path or DEFAULT_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".part")
    try:
        tmp.write_text(
            json.dumps(records, ensure_ascii=False, indent=2, default=str),
            encoding="utf-8",
        )
        tmp.replace(path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def load(path: Path | None = None) -> dict[str, dict]:
    """
    读持久化记录。文件缺失 / 损坏返回空 —— 状态文件坏了不该挡住 daemon
    启动；损坏的原文件留在磁盘上（save 只在下次事件时覆盖），供人工排查。
    """
    path = Path(path or DEFAULT_PATH)
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def snapshot(jobs_registry) -> dict[str, dict]:
    """从 Jobs 注册表导出全部 export 任务的记录（含终态，便于审计）。"""
    out: dict[str, dict] = {}
    for j in jobs_registry.list(limit=1000):
        if j.kind == KIND_EXPORT:
            out[j.id] = j.to_dict(include_result=True)
    return out


def save_from(jobs_registry, path: Path | None = None) -> None:
    save(snapshot(jobs_registry), path)


def restore(record: dict) -> Job:
    """
    持久化记录 → Job（无线程）。状态照存档呈现，交给 daemon 轮询用
    task id 向 GEE 重查推进；task id 缺失的记录原样恢复、如实可见。
    """
    job = Job(
        id=record.get("id") or f"j_{int(time.time() * 1000):x}",
        kind=KIND_EXPORT,
        spec=ArtifactSpec.from_dict(record["spec"]) if record.get("spec") else None,
        task_id=record.get("task_id"),
        status=record.get("status") or "queued",
        phase=record.get("phase", ""),
        pct=float(record.get("pct") or 0.0),
        message=record.get("message", ""),
        error=record.get("error", ""),
        warning=record.get("warning", ""),
        created_at=float(record.get("created_at") or time.time()),
        started_at=record.get("started_at"),
        finished_at=record.get("finished_at"),
    )
    job.result = record.get("result")
    return job
