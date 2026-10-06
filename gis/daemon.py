"""
守护进程：一个 HTTP 服务，两组路由。

    POST /mcp   → MCP 协议      （给 agent）
    POST /rpc   → JSON-RPC      （给 ArcGIS Pro 的 C# add-in）

外加一组给人和 TUI 用的只读/控制路由（/status /spec /job /events）。

为什么用标准库 http.server 而不是 uvicorn/fastapi：
  依赖面越小越不容易坏，而这里的并发量是"一个人 + 一个 agent"的量级，
  不需要 ASGI、不需要异步框架、不需要额外的包版本管理。

进程形态：独立守护进程，不注册开机自启、不注册 Windows 服务。
启动：python -m gis.daemon [--port 6531] [--foreground]
"""

from __future__ import annotations

import argparse
import json
import queue
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from . import geoenv, preflight
from .jobs import (
    KIND_DEFAULTS,
    KIND_DESCRIBE,
    KIND_EMIT,
    Jobs,
    run_defaults,
    run_describe,
    run_emit,
)
from .spec import EXITS, ArtifactSpec, SpecError

SERVER_NAME = "geocode-daemon"
SERVER_VERSION = "0.1.0"
MCP_PROTOCOL_FALLBACK = "2025-06-18"

STARTED_AT = time.time()

# 守护进程级的共享状态
JOBS = Jobs()
STATE_LOCK = threading.RLock()
CURRENT_SPEC: ArtifactSpec | None = None
SSE_CLIENTS: set[queue.Queue] = set()


# ---------------------------------------------------------------------------
# 事件广播
# ---------------------------------------------------------------------------

def _broadcast(event: str, payload: dict) -> None:
    """任务事件 → 所有 SSE 订阅者。TUI 和 dockpane 都靠这个免轮询。"""
    frame = {"event": event, "ts": time.time(), "data": payload}
    with STATE_LOCK:
        clients = list(SSE_CLIENTS)
    for q in clients:
        try:
            q.put_nowait(frame)
        except queue.Full:
            pass


JOBS.subscribe(_broadcast)


# ---------------------------------------------------------------------------
# 业务动作（HTTP 与 MCP 共用同一套）
# ---------------------------------------------------------------------------

def act_status(*, network: bool = False) -> dict:
    from . import source
    return {
        "server": {
            "name": SERVER_NAME,
            "version": SERVER_VERSION,
            "uptime_s": round(time.time() - STARTED_AT, 1),
            "pid": _pid(),
            "port": _PORT,
        },
        "env": preflight.probe_env(),
        "gee_local": preflight.check_gee_local().as_dict(),
        "gee_network": preflight.check_gee_network().as_dict() if network else None,
        "jobs": JOBS.summary(),
        "spec": CURRENT_SPEC.to_dict() if CURRENT_SPEC else None,
        "assets_known": list(source.DEFAULT_ASSETS.keys()),
    }


def _pid() -> int:
    import os
    return os.getpid()


def act_spec_get() -> dict:
    return {"spec": CURRENT_SPEC.to_dict() if CURRENT_SPEC else None}


def act_spec_set(patch: dict) -> dict:
    """局部更新当前 spec。未知键忽略并在警告里列出。"""
    global CURRENT_SPEC
    with STATE_LOCK:
        base = CURRENT_SPEC.to_dict(include_meta=False) if CURRENT_SPEC else {"id": "unnamed"}
        known = set(ArtifactSpec.__dataclass_fields__.keys())
        unknown = [k for k in patch if k not in known]
        merged = {k: v for k, v in patch.items() if k in known}
        base.update(merged)
        for key in ("bands", "tags"):
            if isinstance(base.get(key), list):
                base[key] = tuple(base[key])
        for key in ("time_range", "time_ranges"):
            if isinstance(base.get(key), list):
                base[key] = tuple(base[key])
        spec = ArtifactSpec.from_dict(base)
        spec.validate(None)          # 只校验通用字段；出口要求留到提交时
        CURRENT_SPEC = spec
    return {"spec": spec.to_dict(), "unknown_keys": unknown}


def act_job_submit(body: dict) -> dict:
    global CURRENT_SPEC
    kind = body.get("kind") or KIND_EMIT
    exit_ = body.get("exit")

    raw_spec = body.get("spec")
    try:
        spec = ArtifactSpec.from_dict(raw_spec) if raw_spec else CURRENT_SPEC
    except Exception as e:
        raise SpecError(f"spec 解析失败：{e}")

    if spec is None:
        raise SpecError(
            "没有可用的 spec。先 POST /spec 设一份，或在提交时带上 spec 字段。"
        )

    if kind == KIND_EMIT:
        if exit_ not in EXITS:
            raise SpecError(
                f"emit 任务必须指定 exit，可选：{', '.join(EXITS)}。收到 {exit_!r}"
            )
        spec.validate(exit_)
    elif kind in (KIND_DESCRIBE, KIND_DEFAULTS):
        if not spec.asset:
            raise SpecError(f"{kind} 任务需要 spec.asset。")
    else:
        raise SpecError(f"未知任务类型 {kind!r}。可选：{KIND_EMIT}, {KIND_DESCRIBE}, {KIND_DEFAULTS}")

    with STATE_LOCK:
        CURRENT_SPEC = spec

    fn = {KIND_EMIT: run_emit, KIND_DESCRIBE: run_describe, KIND_DEFAULTS: run_defaults}[kind]
    renderer = body.get("renderer")
    if renderer is not None and kind == KIND_EMIT and exit_ == "map":
        if renderer not in ("qgis", "arcpy"):
            raise SpecError(
                f"renderer={renderer!r} 不认识。可选：'qgis'（默认，.qgz+PNG）或 'arcpy'（.aprx+PDF/PNG 出版级）。"
            )
    job = JOBS.submit(kind, fn, spec=spec, exit=exit_, renderer=renderer)
    return {"job_id": job.id, "job": job.to_dict()}


def act_job_list(limit: int = 50) -> dict:
    return {"jobs": [j.to_dict() for j in JOBS.list(limit=limit, active_first=True)],
            "summary": JOBS.summary()}


def act_job_get(job_id: str) -> dict:
    j = JOBS.get(job_id)
    if not j:
        raise KeyError(f"没有这个任务：{job_id}")
    return {"job": j.to_dict(include_result=True)}


def act_job_cancel(job_id: str) -> dict:
    ok = JOBS.cancel(job_id)
    if not ok:
        raise KeyError(f"任务不存在或已结束：{job_id}")
    return {"cancelled": job_id}


def act_gee_describe(asset: str) -> dict:
    from . import source
    return source.describe_asset(asset)


def act_gee_defaults(asset: str, aoi: dict | None = None) -> dict:
    from . import source
    return source.defaults_for(asset, aoi)


# ---------------------------------------------------------------------------
# MCP 工具表（单一来源 —— 给 daemon 用；导出成 JSON 后 C# add-in 复用同一份）
# ---------------------------------------------------------------------------

MCP_TOOLS: list[dict] = [
    {
        "name": "gee_status",
        "description": "报告运行环境状态：Python 包、GDAL、GEE 认证/项目、任务队列。"
                       "network=true 时额外做联网探测（较慢）。",
        "inputSchema": {
            "type": "object",
            "properties": {"network": {"type": "boolean", "default": False}},
            "required": [],
        },
    },
    {
        "name": "gee_describe",
        "description": "探测一个 GEE 资产：类型、波段、时间范围、属性、原生分辨率。"
                       "默认不做全量扫描（全量 size/时间范围实测 >90s）。",
        "inputSchema": {
            "type": "object",
            "properties": {"asset": {"type": "string", "description": "GEE 资产 ID，如 COPERNICUS/S2_SR_HARMONIZED"}},
            "required": ["asset"],
        },
    },
    {
        "name": "spec_defaults",
        "description": "从资产 ID 推导 ArtifactSpec 的合理默认值（尺度/波段/CRS/渲染）。"
                       "已知数据集走内置预设（零网络）。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "asset": {"type": "string"},
                "aoi": {"type": "object", "description": "GeoJSON geometry，用于推荐投影坐标系"},
            },
            "required": ["asset"],
        },
    },
    {
        "name": "spec_get",
        "description": "读取守护进程当前的 ArtifactSpec。",
        "inputSchema": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "spec_set",
        "description": "局部更新当前 ArtifactSpec（只覆盖传入的字段）。",
        "inputSchema": {
            "type": "object",
            "properties": {"patch": {"type": "object", "description": "要更新的字段"}},
            "required": ["patch"],
        },
    },
    {
        "name": "job_submit",
        "description": "提交任务。kind=emit 时物化产物（exit: array|file|map）；"
                       "kind=describe 探测资产；kind=defaults 推导默认值。",
        "inputSchema": {
            "type": "object",
            "properties": {
                "kind": {"type": "string", "enum": ["emit", "describe", "defaults"], "default": "emit"},
                "exit": {"type": "string", "enum": list(EXITS)},
                "renderer": {"type": "string", "enum": ["qgis", "arcpy"],
                             "description": "仅 exit=map 有效：qgis（默认，.qgz+PNG）/ arcpy（.aprx+PDF/PNG 出版级）"},
                "spec": {"type": "object", "description": "不传则用当前 spec"},
            },
            "required": [],
        },
    },
    {
        "name": "job_list",
        "description": "列出任务（活跃优先）。",
        "inputSchema": {
            "type": "object",
            "properties": {"limit": {"type": "integer", "default": 50}},
            "required": [],
        },
    },
    {
        "name": "job_get",
        "description": "取单个任务的完整状态与结果（含产物路径）。",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
    {
        "name": "job_cancel",
        "description": "请求取消任务（协作式，任务在下一个检查点停下）。",
        "inputSchema": {
            "type": "object",
            "properties": {"job_id": {"type": "string"}},
            "required": ["job_id"],
        },
    },
]


def mcp_call(name: str, args: dict) -> Any:
    if name == "gee_status":
        return act_status(network=bool(args.get("network")))
    if name == "gee_describe":
        return act_gee_describe(args["asset"])
    if name == "spec_defaults":
        return act_gee_defaults(args["asset"], args.get("aoi"))
    if name == "spec_get":
        return act_spec_get()
    if name == "spec_set":
        return act_spec_set(args.get("patch") or {})
    if name == "job_submit":
        return act_job_submit(args)
    if name == "job_list":
        return act_job_list(int(args.get("limit", 50)))
    if name == "job_get":
        return act_job_get(args["job_id"])
    if name == "job_cancel":
        return act_job_cancel(args["job_id"])
    raise KeyError(f"未知工具：{name}")


def mcp_handle(msg: dict) -> dict | None:
    """极简 MCP。返回 None 表示这是通知，不需要响应。"""
    mid = msg.get("id")
    method = msg.get("method", "")
    params = msg.get("params") or {}

    def ok(result: Any) -> dict:
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    if method in ("notifications/initialized", "notifications/cancelled"):
        return None

    if method == "initialize":
        return ok({
            "protocolVersion": params.get("protocolVersion") or MCP_PROTOCOL_FALLBACK,
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": SERVER_NAME, "version": SERVER_VERSION},
        })

    if method == "ping":
        return ok({})

    if method == "tools/list":
        return ok({"tools": MCP_TOOLS})

    if method == "tools/call":
        name = params.get("name")
        args = params.get("arguments") or {}
        try:
            result = mcp_call(name, args)
            return ok({
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2, default=str)}],
                "isError": False,
            })
        except Exception as e:
            return ok({
                "content": [{"type": "text", "text": f"{type(e).__name__}: {e}"}],
                "isError": True,
            })

    if mid is None:
        return None
    return {"jsonrpc": "2.0", "id": mid,
            "error": {"code": -32601, "message": f"未实现的方法：{method}"}}


# ---------------------------------------------------------------------------
# HTTP
# ---------------------------------------------------------------------------

_PORT = 6531


class Handler(BaseHTTPRequestHandler):
    server_version: str = f"{SERVER_NAME}/{SERVER_VERSION}"
    protocol_version: str = "HTTP/1.1"

    # --- 工具 ------------------------------------------------------------

    def _send(self, code: int, body: bytes, ctype: str = "application/json; charset=utf-8",
              extra: dict | None = None) -> None:
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, obj: Any, code: int = 200) -> None:
        self._send(code, json.dumps(obj, ensure_ascii=False, default=str).encode("utf-8"))

    def _error(self, code: int, msg: str) -> None:
        self._json({"ok": False, "error": msg}, code)

    def _read_json(self) -> dict:
        n = int(self.headers.get("Content-Length") or 0)
        if n <= 0:
            return {}
        raw = self.rfile.read(n)
        try:
            return json.loads(raw.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise ValueError(f"请求体不是合法 JSON：{e}") from e

    def log_message(self, fmt, *args):  # 保持安静，日志走我们自己的
        pass

    # --- 路由 ------------------------------------------------------------

    def do_OPTIONS(self) -> None:
        self.send_response(204)
        self.send_header("Allow", "GET, POST, OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/":
                return self._json({
                    "name": SERVER_NAME, "version": SERVER_VERSION,
                    "routes": ["/status", "/spec", "/job", "/events (SSE)", "/mcp", "/rpc"],
                    "hint": "MCP 客户端连 http://127.0.0.1:%d/mcp" % _PORT,
                })
            if path == "/status":
                q = urlparse(self.path).query
                return self._json(act_status(network="network=1" in q or "network=true" in q))
            if path == "/spec":
                return self._json(act_spec_get())
            if path == "/job":
                return self._json(act_job_list())
            if path.startswith("/job/"):
                return self._json(act_job_get(path.split("/", 2)[2]))
            if path == "/events":
                return self._sse()
            if path == "/mcp":
                # 某些客户端会先 GET 探测
                return self._json({"error": "MCP 用 POST"}, 405)
            return self._error(404, f"没有这个路由：{path}")
        except Exception as e:
            return self._error(500, f"{type(e).__name__}: {e}")

    def do_POST(self) -> None:
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            body = self._read_json()
        except ValueError as e:
            return self._error(400, str(e))

        try:
            if path == "/mcp":
                resp = mcp_handle(body)
                if resp is None:
                    return self._send(202, b"", "application/json")
                return self._json(resp)
            if path == "/rpc":
                return self._json(self._rpc(body))
            if path == "/spec":
                return self._json(act_spec_set(body if "patch" not in body else body["patch"]))
            if path == "/job":
                return self._json(act_job_submit(body))
            if path.startswith("/job/") and path.endswith("/cancel"):
                return self._json(act_job_cancel(path.split("/")[2]))
            if path == "/job/cancel":
                return self._json({"cancelled": JOBS.cancel_all()})
            return self._error(404, f"没有这个路由：{path}")
        except SpecError as e:
            return self._error(422, str(e))
        except KeyError as e:
            return self._error(404, str(e))
        except Exception as e:
            return self._error(500, f"{type(e).__name__}: {e}\n{traceback.format_exc(limit=4)}")

    def _rpc(self, body: dict) -> dict:
        """给 C# add-in 的简单 JSON-RPC。与 MCP 共用 act_* 实现。"""
        method = body.get("method")
        params = body.get("params") or {}
        rid = body.get("id")
        try:
            if method == "status":
                return {"id": rid, "ok": True, "result": act_status(network=bool(params.get("network")))}
            if method == "spec.get":
                return {"id": rid, "ok": True, "result": act_spec_get()}
            if method == "spec.set":
                return {"id": rid, "ok": True, "result": act_spec_set(params.get("patch") or params)}
            if method == "spec.defaults":
                return {"id": rid, "ok": True, "result": act_gee_defaults(params["asset"], params.get("aoi"))}
            if method == "gee.describe":
                return {"id": rid, "ok": True, "result": act_gee_describe(params["asset"])}
            if method == "job.submit":
                return {"id": rid, "ok": True, "result": act_job_submit(params)}
            if method == "job.list":
                return {"id": rid, "ok": True, "result": act_job_list(int(params.get("limit", 50)))}
            if method == "job.get":
                return {"id": rid, "ok": True, "result": act_job_get(params["job_id"])}
            if method == "job.cancel":
                return {"id": rid, "ok": True, "result": act_job_cancel(params["job_id"])}
            return {"id": rid, "ok": False, "error": f"未知方法：{method}"}
        except Exception as e:
            return {"id": rid, "ok": False, "error": f"{type(e).__name__}: {e}"}

    # --- SSE --------------------------------------------------------------

    def _sse(self) -> None:
        q: queue.Queue = queue.Queue(maxsize=512)
        with STATE_LOCK:
            SSE_CLIENTS.add(q)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()
        try:
            self._sse_write("hello", {"server": SERVER_NAME, "version": SERVER_VERSION,
                                      "jobs": [j.to_dict() for j in JOBS.list(limit=30)]})
            while True:
                try:
                    fr = q.get(timeout=15.0)
                except queue.Empty:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    continue
                self._sse_write(fr["event"], fr["data"])
        except (BrokenPipeError, ConnectionResetError, OSError):
            pass
        finally:
            with STATE_LOCK:
                SSE_CLIENTS.discard(q)

    def _sse_write(self, event: str, data: Any) -> None:
        payload = json.dumps(data, ensure_ascii=False, default=str)
        self.wfile.write(f"event: {event}\ndata: {payload}\n\n".encode("utf-8"))
        self.wfile.flush()


# ---------------------------------------------------------------------------
# 进程管理
# ---------------------------------------------------------------------------

def port_in_use(host: str, port: int) -> bool:
    return geoenv.port_open(host, port)


def serve(host: str, port: int) -> ThreadingHTTPServer:
    httpd = ThreadingHTTPServer((host, port), Handler)
    httpd.daemon_threads = True
    return httpd


def daemonize_file() -> None:
    """把 PID / 端口写进 .cache，供 CLI 判断存活。"""
    from . import geoenv
    (geoenv.CACHE_DIR / "daemon.json").write_text(
        json.dumps({"pid": _pid(), "port": _PORT, "started_at": STARTED_AT}),
        encoding="utf-8",
    )


def main(argv: list[str] | None = None) -> int:
    global _PORT
    ap = argparse.ArgumentParser(prog="gis.daemon", description="GeoCode 守护进程")
    ap.add_argument("--host", default=None)
    ap.add_argument("--port", type=int, default=None)
    ap.add_argument("--status", action="store_true", help="打印一次状态后退出")
    a = ap.parse_args(argv)

    cfg = geoenv.load_config()["server"]
    host = a.host or cfg["host"]
    port = a.port or int(cfg["port"])
    _PORT = port

    if a.status:
        if port_in_use(host, port):
            import urllib.request
            with urllib.request.urlopen(f"http://{host}:{port}/status", timeout=10) as r:
                print(json.dumps(json.loads(r.read()), indent=2, ensure_ascii=False, default=str))
            return 0
        print(json.dumps({"running": False, "host": host, "port": port}, ensure_ascii=False))
        return 1

    if port_in_use(host, port):
        print(f"端口 {port} 已被占用 —— 守护进程大概已经在跑了。")
        print("  查看状态: python -m gis.cli status")
        return 2

    httpd = serve(host, port)
    daemonize_file()
    print(f"{SERVER_NAME} {SERVER_VERSION} 监听 http://{host}:{port}")
    print(f"  MCP : http://{host}:{port}/mcp")
    print(f"  SSE : http://{host}:{port}/events")
    print("  Ctrl-C 停止")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\n停止中…")
    finally:
        httpd.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
