"""
守护进程客户端。

TUI、CLI、测试都用这一个 —— 只有一处知道怎么跟 daemon 说话。

两种协议：
    MCP  : connect_mcp()  —— 给 agent / MCP 客户端
    直连  : Client        —— 给 TUI / CLI（更直接，少一层 JSON-RPC 包装）
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any


class DaemonError(RuntimeError):
    pass


class Client:
    """直连 REST 路由的客户端。TUI / CLI 用这个。"""

    base: str
    timeout: float
    _opener: urllib.request.OpenerDirector

    def __init__(self, host: str = "127.0.0.1", port: int = 6531, timeout: float = 30.0) -> None:
        self.base = f"http://{host}:{port}"
        self.timeout = timeout
        # 守护进程在 loopback 上，永远不该走代理
        self._opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
        )

    # --- 底层 -------------------------------------------------------------

    def _req(self, method: str, path: str, body: dict | None = None,
             timeout: float | None = None) -> Any:
        url = self.base + path
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(url, data=data, method=method)
        if data:
            req.add_header("Content-Type", "application/json")
        try:
            with self._opener.open(req, timeout=timeout or self.timeout) as r:
                raw = r.read()
        except urllib.error.HTTPError as e:
            detail = e.read().decode("utf-8", "replace")
            try:
                detail = json.loads(detail).get("error", detail)
            except Exception:
                pass
            raise DaemonError(f"HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            raise DaemonError(
                f"连不上守护进程 {self.base} —— {e.reason}\n"
                f"  启动：python -m gis.daemon"
            ) from None
        if not raw:
            return None
        return json.loads(raw.decode("utf-8"))

    # --- 只读 -------------------------------------------------------------

    def alive(self) -> bool:
        try:
            self._req("GET", "/", timeout=2.0)
            return True
        except Exception:
            return False

    def status(self, *, network: bool = False) -> dict:
        return self._req("GET", "/status" + ("?network=1" if network else ""))

    def spec(self) -> dict:
        return self._req("GET", "/spec")

    def jobs(self, limit: int = 50) -> dict:
        return self._req("GET", "/job")

    def job(self, job_id: str) -> dict:
        return self._req("GET", f"/job/{job_id}")

    # --- 写 ---------------------------------------------------------------

    def set_spec(self, patch: dict) -> dict:
        return self._req("POST", "/spec", patch)

    def submit(self, kind: str = "emit", exit: str | None = None,
               spec: dict | None = None) -> dict:
        body: dict[str, Any] = {"kind": kind}
        if exit:
            body["exit"] = exit
        if spec:
            body["spec"] = spec
        return self._req("POST", "/job", body)

    def cancel(self, job_id: str) -> dict:
        return self._req("POST", f"/job/{job_id}/cancel")

    def cancel_all(self) -> dict:
        return self._req("POST", "/job/cancel")

    def describe_asset(self, asset: str) -> dict:
        return self._req("POST", "/rpc", {"id": 1, "method": "gee.describe",
                                          "params": {"asset": asset}})["result"]

    def defaults_for(self, asset: str, aoi: dict | None = None) -> dict:
        return self._req("POST", "/rpc", {"id": 1, "method": "spec.defaults",
                                          "params": {"asset": asset, "aoi": aoi}})["result"]


# ---------------------------------------------------------------------------
# MCP 客户端（给 agent / 测试用）
# ---------------------------------------------------------------------------

class McpClient:
    """极简 MCP 客户端。用来验证 MCP 端点，也方便脚本化调用。"""

    url: str
    timeout: float
    _id: int
    _opener: urllib.request.OpenerDirector

    def __init__(self, host: str = "127.0.0.1", port: int = 6531, timeout: float = 60.0) -> None:
        self.url = f"http://{host}:{port}/mcp"
        self.timeout = timeout
        self._id = 0
        self._opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self._id += 1
        body = {"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}
        req = urllib.request.Request(
            self.url, data=json.dumps(body).encode("utf-8"), method="POST",
            headers={"Content-Type": "application/json"},
        )
        with self._opener.open(req, timeout=self.timeout) as r:
            out = json.loads(r.read().decode("utf-8"))
        if "error" in out:
            raise DaemonError(f"MCP 错误：{out['error']}")
        return out["result"]

    def initialize(self) -> dict:
        return self.rpc("initialize", {"protocolVersion": "2025-06-18"})

    def tools(self) -> list[dict]:
        return self.rpc("tools/list")["tools"]

    def call(self, name: str, arguments: dict | None = None) -> Any:
        res = self.rpc("tools/call", {"name": name, "arguments": arguments or {}})
        text = res["content"][0]["text"]
        if res.get("isError"):
            raise DaemonError(text)
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            return text


if __name__ == "__main__":

    c = Client()
    if not c.alive():
        print("守护进程未运行。启动：python -m gis.daemon")
        raise SystemExit(1)
    print(json.dumps(c.status(), indent=2, ensure_ascii=False)[:1500])
