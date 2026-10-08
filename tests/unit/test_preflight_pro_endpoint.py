"""C12 离线单测：Pro add-in **端点级**探测（A1–A6 / A12 / A16）。

被测行为（`gis/preflight.py`）：
- `_mcp_endpoint_alive(port)`：`GET http://127.0.0.1:<port>/` 须 200 + 合法 JSON + `name == "geocode-pro"`；
- `check_pro_addin()`：`ok` 以**端点**为准（`listening` 降为诊断字段），端口被别的进程占用时
  报独立的占用类失败码而不是「就绪」。

离线纪律（测试自身的约束，见 `test_offline_guard.py`）：本文件**不得导入** socket/http/urllib 等
网络库。因此假服务器与假监听者一律用**子进程**承载（`subprocess` + `sys.executable -c`），
只绑定 `127.0.0.1`、端口由内核分配（不占用固定 6530/6531），用例结束即终止子进程释放监听。
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from gis import preflight

# 子进程假服务器：绑定 127.0.0.1:0（内核分配端口），把端口写进 portfile，然后按 mode 应答。
# mode: raw（只 listen 不应答）/ blackhole（accept 后不回）/ garbage（回非 HTTP 字节）
#       / good（回本 add-in 的 GET / 形状）/ wrongname（回合法 JSON 但 name 不匹配）
_CHILD = r'''
import json, socket, sys, time

mode, portfile = sys.argv[1], sys.argv[2]
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 0))
srv.listen(8)
with open(portfile, "w", encoding="utf-8") as fh:
    fh.write(str(srv.getsockname()[1]))

if mode == "raw":
    time.sleep(60)                      # 只 listen：握手靠 backlog 完成，但永不应答
elif mode == "blackhole":
    conns = []
    while True:                         # accept 后挂住连接，永不响应
        c, _ = srv.accept()
        conns.append(c)
elif mode == "garbage":
    while True:
        c, _ = srv.accept()
        try:
            c.sendall(b"not-http\r\n\r\n")
        finally:
            c.close()
else:                                   # good / wrongname
    payload = {
        "name": "geocode-pro" if mode == "good" else "someone-else",
        "version": "0.0.0-test",
        "routes": ["/mcp"],
        "hint": "MCP 客户端连 /mcp",
    }
    body = json.dumps(payload).encode("utf-8")
    head = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
            b"Content-Length: " + str(len(body)).encode() + b"\r\nConnection: close\r\n\r\n")
    while True:
        c, _ = srv.accept()
        try:
            c.recv(65536)
            c.sendall(head + body)
        finally:
            c.close()
'''


class _FakeServer:
    """子进程假服务器/假监听者（上下文管理器，退出即终止）。"""

    def __init__(self, mode: str):
        self.mode = mode
        self._tmp = tempfile.TemporaryDirectory()
        self.portfile = Path(self._tmp.name) / "port.txt"
        self.proc = subprocess.Popen(
            [sys.executable, "-c", _CHILD, mode, str(self.portfile)],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )

    def __enter__(self) -> "_FakeServer":
        deadline = time.time() + 20.0
        while time.time() < deadline:
            if self.portfile.exists():
                text = self.portfile.read_text(encoding="utf-8").strip()
                if text:
                    self.port = int(text)
                    return self
            if self.proc.poll() is not None:
                raise AssertionError(f"假服务器({self.mode})提前退出，退出码 {self.proc.returncode}")
            time.sleep(0.05)
        raise AssertionError(f"假服务器({self.mode})未在 20s 内就绪")

    def __exit__(self, *exc) -> None:
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=10)
            except subprocess.TimeoutExpired:      # pragma: no cover - 兜底
                self.proc.kill()
                self.proc.wait(timeout=10)
        self._tmp.cleanup()


def _mock_addin_dir() -> tempfile.TemporaryDirectory:
    """造一个含 *.esriAddInX 的临时 add-in 目录（deployed=True）。"""
    td = tempfile.TemporaryDirectory()
    (Path(td.name) / "fake.esriAddInX").write_bytes(b"zip")
    return td


class EndpointProbeTest(unittest.TestCase):
    """A1–A6 / A12：`_mcp_endpoint_alive` 的端点判定语义（真打真连，端口由内核分配）。"""

    def test_A4_endpoint_identity_matches_addin_shape(self):
        """A4/A11：模拟本 add-in 的 GET / → 判定为本端点（name=geocode-pro）。"""
        with _FakeServer("good") as srv:
            alive, name, err = preflight._mcp_endpoint_alive(srv.port, timeout=1.0)
        self.assertTrue(alive, f"应判为本端点，实际 error={err}")
        self.assertEqual(name, preflight.PRO_ENDPOINT_NAME)
        self.assertIsNone(err)

    def test_A3_http_json_with_other_identity_is_not_our_endpoint(self):
        """A3：200 + 合法 JSON 但 name 不是 geocode-pro → 不是本端点。"""
        with _FakeServer("wrongname") as srv:
            alive, name, err = preflight._mcp_endpoint_alive(srv.port, timeout=1.0)
        self.assertFalse(alive)
        self.assertEqual(name, "someone-else")
        self.assertIn("someone-else", err or "")

    def test_A2_non_http_responder_is_not_our_endpoint(self):
        """A2 变体：非 HTTP 应答 → 不是本端点（不得抛异常）。"""
        with _FakeServer("garbage") as srv:
            alive, name, err = preflight._mcp_endpoint_alive(srv.port, timeout=1.0)
        self.assertFalse(alive)
        self.assertIsNone(name)
        self.assertTrue(err, "必须给出失败原因，供占用态 reason 展示")

    def test_A5_raw_listener_times_out_within_budget(self):
        """A5/A12：只 listen 不应答（半开）→ 有界时延内返回 False，不挂死。"""
        with _FakeServer("raw") as srv:
            t0 = time.monotonic()
            alive, _name, err = preflight._mcp_endpoint_alive(srv.port, timeout=0.6)
            elapsed = time.monotonic() - t0
        self.assertFalse(alive)
        self.assertTrue(err)
        self.assertLess(elapsed, 6.0, f"探测必须在有界时延内返回（实测 {elapsed:.2f}s）")

    def test_A5_blackhole_listener_times_out_within_budget(self):
        """A5/A12：accept 后永不响应 → 同样有界返回 False。"""
        with _FakeServer("blackhole") as srv:
            t0 = time.monotonic()
            alive, _name, err = preflight._mcp_endpoint_alive(srv.port, timeout=0.6)
            elapsed = time.monotonic() - t0
        self.assertFalse(alive)
        self.assertTrue(err)
        self.assertLess(elapsed, 6.0, f"探测必须在有界时延内返回（实测 {elapsed:.2f}s）")


class CheckProAddinWiringTest(unittest.TestCase):
    """A1/A2/A6/A8：`check_pro_addin` 的判定接线（失败码 / ok / value 字段 / 端口覆盖）。"""

    def test_A1_not_listening_reports_baseline_code(self):
        """A1：端口无人监听 → 既有失败码不变，端点字段为 False。"""
        with _mock_addin_dir() as td:
            with mock.patch.object(preflight, "_port_listening", return_value=False), \
                 mock.patch.object(preflight, "_mcp_endpoint_alive") as probe:
                r = preflight.check_pro_addin(addin_dir=Path(td), port=6530)
        probe.assert_not_called()          # 端口没人接就不发 HTTP
        self.assertFalse(r.ok)
        self.assertFalse(r.value["listening"])
        self.assertFalse(r.value["endpoint_alive"])
        if r.value["installed"] and r.value["deployed"]:
            self.assertEqual(r.code, "pro-mcp-not-listening")

    def test_A2_occupied_but_not_our_endpoint_gets_distinct_code(self):
        """A2：有监听但不是本端点 → 独立占用类失败码 + 可执行 reason（含 netstat）。"""
        with _mock_addin_dir() as td:
            with mock.patch.object(preflight, "_port_listening", return_value=True), \
                 mock.patch.object(preflight, "_mcp_endpoint_alive",
                                   return_value=(False, None, "TimeoutError: timed out")):
                r = preflight.check_pro_addin(addin_dir=Path(td), port=6530)
        self.assertFalse(r.ok, "端口被别的进程占用时不得报就绪")
        self.assertTrue(r.value["listening"], "listening 保留为诊断字段")
        self.assertFalse(r.value["endpoint_alive"])
        self.assertEqual(r.value["endpoint_error"], "TimeoutError: timed out")
        if r.value["installed"] and r.value["deployed"]:
            self.assertEqual(r.code, "pro-port-occupied-by-other")
            self.assertNotEqual(r.code, "pro-mcp-not-listening", "占用与未监听必须可区分")
            self.assertIn("netstat", r.reason)
            self.assertTrue(r.reason.startswith("症状："))

    def test_A4_ready_requires_our_endpoint(self):
        """A4：installed+deployed+端点为本 add-in → ok=True、无失败码。"""
        with _mock_addin_dir() as td:
            with mock.patch.object(preflight, "_port_listening", return_value=True), \
                 mock.patch.object(preflight, "_mcp_endpoint_alive",
                                   return_value=(True, "geocode-pro", None)):
                r = preflight.check_pro_addin(addin_dir=Path(td), port=6530)
        self.assertTrue(r.value["endpoint_alive"])
        if r.value["installed"] and r.value["deployed"]:
            self.assertTrue(r.ok)
            self.assertEqual(r.code, "")

    def test_A6_port_override_applies_to_endpoint_probe(self):
        """A6：GEOCODE_PRO_PORT 覆盖时，端点探测打在同一端口。"""
        with _mock_addin_dir() as td:
            with mock.patch.dict(os.environ, {"GEOCODE_PRO_PORT": "6999"}), \
                 mock.patch.object(preflight, "_port_listening", return_value=True), \
                 mock.patch.object(preflight, "_mcp_endpoint_alive",
                                   return_value=(True, "geocode-pro", None)) as probe:
                r = preflight.check_pro_addin(addin_dir=Path(td), port=None)
        self.assertEqual(r.value["port"], 6999)
        self.assertEqual(probe.call_args[0][0], 6999)

    def test_A4_end_to_end_with_real_fake_endpoint(self):
        """A4/E2E：真子进程假端点 + 真 `_port_listening` → endpoint_alive=True。"""
        with _FakeServer("good") as srv, _mock_addin_dir() as td:
            r = preflight.check_pro_addin(addin_dir=Path(td), port=srv.port)
        self.assertTrue(r.value["listening"])
        self.assertTrue(r.value["endpoint_alive"], f"错误：{r.value['endpoint_error']}")
        if r.value["installed"] and r.value["deployed"]:
            self.assertTrue(r.ok)
            self.assertEqual(r.code, "")

    def test_A2_end_to_end_with_real_raw_listener(self):
        """A2/E2E：真原始监听者占端口（非本端点）→ 不得报就绪。"""
        with _FakeServer("raw") as srv, _mock_addin_dir() as td:
            r = preflight.check_pro_addin(addin_dir=Path(td), port=srv.port)
        self.assertTrue(r.value["listening"])
        self.assertFalse(r.value["endpoint_alive"])
        self.assertFalse(r.ok)
        if r.value["installed"] and r.value["deployed"]:
            self.assertEqual(r.code, "pro-port-occupied-by-other")

    def test_A8_value_keys_and_probe_all_shape(self):
        """A8：value 增字段不删旧字段；probe_all 键面不变；summarize 不崩。"""
        v = preflight.check_pro_addin(addin_dir=Path(tempfile.gettempdir()), port=6530).value
        for key in ("pro_bin", "installed", "addin_dir", "addin_files", "addin_zips",
                    "deployed", "port", "listening",
                    "endpoint_alive", "endpoint_name", "endpoint_error"):
            self.assertIn(key, v, f"value 缺少字段 {key}")
        res = preflight.probe_all()          # 默认零网络
        self.assertIn("pro_addin", res)
        self.assertIn("endpoint_alive", res["pro_addin"]["value"])
        self.assertIsInstance(preflight.summarize(res), str)


if __name__ == "__main__":
    unittest.main()
