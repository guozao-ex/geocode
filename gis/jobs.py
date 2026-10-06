"""
任务模型与执行器。

设计要点：
1. **任务在独立线程跑，状态在共享 registry 里** —— 这样 HTTP 请求立刻返回 job_id，
   进度通过订阅者回调推给 SSE / TUI / dockpane。
2. **取消是协作式的** —— 任务在自己的检查点查 cancel event。
   不强行杀线程（Python 没这能力，硬杀会留下坏状态）。
3. **进度回调是统一的** —— 无论谁执行任务，都调 progress(phase, pct, msg)，
   于是 TUI / 日志 / MCP 三处显示一致。
"""

from __future__ import annotations

import threading
import time
import traceback
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from .spec import ArtifactSpec, Exit

# ---------------------------------------------------------------------------
# 状态常量
# ---------------------------------------------------------------------------

QUEUED = "queued"
RUNNING = "running"
DONE = "done"
FAILED = "failed"
CANCELLED = "cancelled"

TERMINAL = {DONE, FAILED, CANCELLED}

# 任务类型
KIND_DESCRIBE = "describe"     # 探测 GEE 资产
KIND_DEFAULTS = "defaults"     # 推导 spec 默认值
KIND_EMIT = "emit"             # 物化（三出口）
KIND_EXPORT = "export"         # GEE 服务端批处理导出（C5，状态由 GEE task 驱动）


# ---------------------------------------------------------------------------
# Job
# ---------------------------------------------------------------------------

def _noop(*_args: Any, **_kwargs: Any) -> None:
    """progress 的占位实现：绑定 bind_progress() 之前调用它不会炸。"""


@dataclass
class Job:
    id: str
    kind: str
    status: str = QUEUED
    spec: ArtifactSpec | None = None
    exit: Exit | None = None
    renderer: str | None = None     # map 出口专用：qgis（默认）/ arcpy
    task_id: str | None = None      # export 专用：GEE 服务端 task id（重启恢复的锚点）

    phase: str = ""
    pct: float = 0.0
    message: str = ""

    artifacts: list[str] = field(default_factory=list)
    result: dict[str, Any] | None = None
    error: str = ""
    warning: str = ""

    created_at: float = field(default_factory=time.time)
    started_at: float | None = None
    finished_at: float | None = None

    # 运行时（不进 JSON）
    _cancel: threading.Event = field(default_factory=threading.Event, repr=False)
    _thread: threading.Thread | None = field(default=None, repr=False)
    # 由 bind_progress() 在运行时替换；此处给个空实现兜底
    progress: Callable[..., None] = field(default=_noop, repr=False, compare=False)

    @property
    def elapsed(self) -> float:
        end = self.finished_at or time.time()
        return end - (self.started_at or self.created_at)

    @property
    def is_terminal(self) -> bool:
        return self.status in TERMINAL

    @property
    def cancel_requested(self) -> bool:
        return self._cancel.is_set()

    @property
    def thread_alive(self) -> bool:
        """执行线程还活着吗。export 的恢复路径用它判断状态由谁驱动。"""
        return self._thread is not None and self._thread.is_alive()

    def request_cancel(self) -> bool:
        if self.is_terminal:
            return False
        self._cancel.set()
        return True

    def check_cancelled(self) -> None:
        """任务在自己的检查点调这个。抛 JobCancelled 由执行器接住。"""
        if self._cancel.is_set():
            raise JobCancelled()

    def to_dict(self, *, include_result: bool = False) -> dict:
        d = {
            "id": self.id,
            "kind": self.kind,
            "status": self.status,
            "exit": self.exit,
            "renderer": self.renderer,
            "task_id": self.task_id,
            "phase": self.phase,
            "pct": round(self.pct, 1),
            "message": self.message,
            "artifacts": list(self.artifacts),
            "error": self.error,
            "warning": self.warning,
            "created_at": self.created_at,
            "started_at": self.started_at,
            "finished_at": self.finished_at,
            "elapsed": round(self.elapsed, 2),
            "spec_id": self.spec.id if self.spec else None,
            "spec_fingerprint": self.spec.fingerprint() if self.spec else None,
        }
        if include_result:
            d["result"] = self.result
            d["spec"] = self.spec.to_dict() if self.spec else None
        return d


class JobCancelled(Exception):
    pass


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------

Subscriber = Callable[[str, dict], None]   # (event_name, payload)


class Jobs:
    """任务注册表 + 执行器。线程安全。"""

    _lock: threading.RLock
    _max_history: int

    def __init__(self, max_history: int = 200) -> None:
        self._lock = threading.RLock()
        self._jobs: dict[str, Job] = {}
        self._order: list[str] = []
        self._subs: list[Subscriber] = []
        self._max_history = max_history

    # --- 订阅（SSE / TUI 用）--------------------------------------------

    def subscribe(self, cb: Subscriber) -> Callable[[], None]:
        with self._lock:
            self._subs.append(cb)

        def unsub() -> None:
            with self._lock:
                if cb in self._subs:
                    self._subs.remove(cb)

        return unsub

    def _emit(self, event: str, payload: dict) -> None:
        with self._lock:
            subs = list(self._subs)
        for cb in subs:
            try:
                cb(event, payload)
            except Exception:
                # 订阅者坏掉不能影响任务执行
                pass

    # --- 查询 -------------------------------------------------------------

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 50, *, active_first: bool = False) -> list[Job]:
        with self._lock:
            jobs = [self._jobs[i] for i in self._order if i in self._jobs]
        if active_first:
            jobs.sort(key=lambda j: (j.is_terminal, -j.created_at))
        else:
            jobs.sort(key=lambda j: -j.created_at)
        return jobs[:limit]

    def summary(self) -> dict:
        with self._lock:
            jobs = list(self._jobs.values())
        by = {}
        for j in jobs:
            by[j.status] = by.get(j.status, 0) + 1
        active = [j.id for j in jobs if not j.is_terminal]
        return {"total": len(jobs), "by_status": by, "active": active}

    # --- 提交 -------------------------------------------------------------

    def submit(
        self,
        kind: str,
        fn: Callable[[Job], Any],
        *,
        spec: ArtifactSpec | None = None,
        exit: Exit | None = None,
        renderer: str | None = None,
        job_id: str | None = None,
    ) -> Job:
        """
        fn 接收 Job 对象，用 job.progress(...) 推进度，返回值存进 job.result。
        进度辅助：见下面的 _Progress 绑定。
        """
        jid = job_id or f"j_{uuid.uuid4().hex[:8]}"
        job = Job(id=jid, kind=kind, spec=spec, exit=exit, renderer=renderer)
        with self._lock:
            self._jobs[jid] = job
            self._order.append(jid)
            self._trim()
        self._emit("job.created", job.to_dict())
        self._start(job, fn)
        return job

    def _trim(self) -> None:
        """只裁终态任务，保留 max_history 条。"""
        if len(self._order) <= self._max_history:
            return
        for jid in list(self._order):
            if len(self._order) <= self._max_history:
                break
            j = self._jobs.get(jid)
            if j and j.is_terminal:
                self._order.remove(jid)
                self._jobs.pop(jid, None)

    def _start(self, job: Job, fn: Callable[[Job], Any]) -> None:
        def runner() -> None:
            job.status = RUNNING
            job.started_at = time.time()
            bind_progress(job, self._emit)
            self._emit("job.updated", job.to_dict())
            try:
                result = fn(job)
                if job.cancel_requested:
                    raise JobCancelled()
                job.result = result if isinstance(result, dict) else {"value": result}
                job.status = DONE
                job.pct = 100.0
                job.phase = "完成"
            except JobCancelled:
                job.status = CANCELLED
                job.phase = "已取消"
                job.message = job.message or "用户取消"
            except Exception as e:
                job.status = FAILED
                job.phase = "失败"
                job.error = _format_exc(e)
            finally:
                job.finished_at = time.time()
                self._emit("job.finished", job.to_dict(include_result=True))

        t = threading.Thread(target=runner, name=f"job-{job.id}", daemon=True)
        job._thread = t
        t.start()

    def cancel(self, job_id: str) -> bool:
        job = self.get(job_id)
        if not job:
            return False
        ok = job.request_cancel()
        if ok:
            job.message = "取消请求已发出（任务会在下一个检查点停下）"
            self._emit("job.updated", job.to_dict())
        return ok

    def cancel_all(self) -> int:
        n = 0
        for j in self.list(limit=1000):
            if not j.is_terminal and j.request_cancel():
                n += 1
        return n

    # --- 等待（CLI / 测试用）--------------------------------------------

    def wait(self, job_id: str, timeout: float | None = None, poll: float = 0.15) -> Job | None:
        deadline = None if timeout is None else time.time() + timeout
        while True:
            job = self.get(job_id)
            if job is None or job.is_terminal:
                return job
            if deadline is not None and time.time() > deadline:
                return job
            time.sleep(poll)

    # --- 恢复与外部驱动（export 持久化用，C5）--------------------------

    def adopt(self, job: Job) -> None:
        """把恢复出来的历史任务直接登记进注册表（不启动线程）。"""
        with self._lock:
            self._jobs[job.id] = job
            self._order.append(job.id)
            self._trim()
        self._emit("job.created", job.to_dict())

    def emit(self, event: str, payload: dict) -> None:
        """外部驱动者（daemon 的 export 轮询）推状态变化用的事件出口。"""
        self._emit(event, payload)


def bind_progress(job: Job, emit: Callable[[str, dict], None]) -> None:
    """给 job 挂上 progress() 方法。节流：同一百分比不重复推。"""

    def progress(phase: str | None = None, pct: float | None = None,
                 message: str | None = None, **extra: Any) -> None:
        changed = False
        if phase is not None and phase != job.phase:
            job.phase = phase
            changed = True
        if pct is not None:
            p = max(0.0, min(100.0, float(pct)))
            if abs(p - job.pct) >= 0.5:
                job.pct = p
                changed = True
        if message is not None and message != job.message:
            job.message = message
            changed = True
        if changed:
            payload = job.to_dict()
            if extra:
                payload["extra"] = extra
            emit("job.updated", payload)

    job.progress = progress


def _format_exc(e: BaseException) -> str:
    if isinstance(e, JobCancelled):
        return "已取消"
    tb = traceback.format_exc(limit=8)
    return f"{type(e).__name__}: {e}\n{tb}" if tb and tb.strip() != "NoneType: None" else f"{type(e).__name__}: {e}"


# ---------------------------------------------------------------------------
# 任务实现（P0 范围：探测 + 默认值；物化待三出口写完）
# ---------------------------------------------------------------------------

def run_describe(job: Job) -> dict:
    from . import source

    asset = (job.spec.asset if job.spec else None) or (job.result or {}).get("asset")
    if not asset:
        raise ValueError("describe 任务需要 spec.asset 或在提交时给 asset")
    job.progress("探测资产", 10, f"getAsset {asset}")
    d = source.describe_asset(asset, deep=False)
    job.progress("完成", 100, f"{d['type']}，{len(d.get('bands', []))} 个波段")
    return d


def run_defaults(job: Job) -> dict:
    from . import source

    if not job.spec or not job.spec.asset:
        raise ValueError("defaults 任务需要 spec.asset")
    job.progress("推导默认值", 30, job.spec.asset)
    d = source.defaults_for(job.spec.asset, job.spec.aoi)
    job.progress("完成", 100)
    return d


def run_emit(job: Job) -> dict:
    """三出口的统一入口。P0 阶段尚未实现，报明确的可执行错误。"""
    from . import emit

    return emit.dispatch(job)
