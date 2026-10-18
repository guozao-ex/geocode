"""C15：下载完整性守卫（Content-Length 截断检测）的离线用例。

背景（A1 第 71/98 片实测）：连接提前关闭时 `HTTPResponse.read(amt)` 会**静默返回空**
（不抛 IncompleteRead），截断的 GeoTIFF 落到磁盘，直到 GDAL 读它才报 “Read failed”，
而回读重试对截断文件永远无效。`_download` 现在核对 Content-Length，不符按
`IncompleteRead` 抛出（可重试 → 网络重试会重下）。

不发网络：替换的是 `gis.emit.urllib.request.urlopen` 这个模块属性（不是导入网络库，
见 test_offline_guard.py 的 AST 禁网名单）。
"""

from __future__ import annotations

import io
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from gis import emit as emit_mod
from gis.emit import _download
from gis.export_chunks import is_retryable_error
from gis.jobs import Job


class _FakeResponse(io.BytesIO):
    """urllib 响应的最小替身（上下文管理器 + Content-Length 头）。"""

    def __init__(self, body: bytes, content_length: int | None = None):
        super().__init__(body)
        self.headers = {} if content_length is None else {"Content-Length": str(content_length)}

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class DownloadLengthGuardTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.dest = Path(self._tmp.name) / "probe.bin"
        self.job = Job(id="t-download-guard", kind="emit")

    def _run(self, resp) -> None:
        with mock.patch.object(emit_mod.urllib.request, "urlopen", return_value=resp):
            _download("https://example.test/x", self.dest, self.job)

    def test_truncated_body_raises_retryable_error(self):
        """响应体 40 B 但 Content-Length 100 B → 截断，必须抛可重试错误。"""
        with self.assertRaises(Exception) as ctx:
            self._run(_FakeResponse(b"x" * 40, content_length=100))
        self.assertEqual(type(ctx.exception).__name__, "IncompleteRead")
        self.assertTrue(is_retryable_error(ctx.exception), "截断必须可重试（重下）")

    def test_complete_body_passes(self):
        self._run(_FakeResponse(b"y" * 9000, content_length=9000))
        self.assertEqual(self.dest.stat().st_size, 9000)

    def test_no_content_length_is_not_treated_as_truncated(self):
        self._run(_FakeResponse(b"z" * 9000, content_length=None))
        self.assertEqual(self.dest.stat().st_size, 9000)

    def test_small_json_error_body_still_reported_as_error(self):
        body = b'{"error": "Image has no band named B4"}'
        with self.assertRaises(RuntimeError) as ctx:
            self._run(_FakeResponse(body, content_length=len(body)))
        self.assertIn("GEE 返回的不是影像", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
