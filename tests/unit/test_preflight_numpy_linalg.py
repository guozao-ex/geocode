"""C16 离线单测：preflight 的 numpy 相关矩阵探测（A5）。

被测行为（`gis/preflight.py`）：
- `check_numpy_linalg()` 在**子进程**里探测 np.cov / np.corrcoef，父进程不得崩溃；
- 探测输入必须是**浮点数组** —— 本机崩溃只在该输入下复现，整数 / list 输入正常返回，
  用后两者探测会得到假阴性（这正是本 change 要防的"离线全绿、真跑必挂"同类问题）；
- 检查项**如实反映探测结果**（2026-10-18 用户决定 D7）：崩就报失败 + 规避写法，
  环境可用就报通过，不保留"即使可用也固定告警"的历史语义。

离线纪律（见 test_offline_guard.py）：本文件不得导入 socket / http / urllib 等网络库，
也不得导入 numpy 本身（父进程侧只做编排与判读，真跑在子进程里）。
"""

import subprocess
import sys
import unittest
from unittest import mock

from gis import preflight


class NumpyProbeSourceTest(unittest.TestCase):
    """探测脚本本身的约束（不需要真跑就能验的部分）。"""

    def test_probe_uses_float_array(self):
        """浮点数组是本机崩溃的必要条件 —— 改成整数/list 会让检查项假阴性。"""
        src = preflight._NUMPY_PROBE_SRC
        self.assertIn("np.cov(", src)
        self.assertIn("np.corrcoef(", src)
        self.assertIn("random", src, "探测输入必须来自浮点随机数组")
        # 明确**不要**出现整数构造（arange / randint / 整型 list）
        self.assertNotIn("arange", src)
        self.assertNotIn("randint", src)
        self.assertNotIn("integers", src)

    def test_native_crash_codes_cover_both_views(self):
        """同一崩溃在 Python 侧与 Git Bash 侧的可观察退出码不同，两种都要认。"""
        self.assertIn(3228369023, preflight.NUMPY_NATIVE_CRASH_CODES)   # 无符号 0xC06D007F
        self.assertIn(-1073741511, preflight.NUMPY_NATIVE_CRASH_CODES)  # 有符号同值
        self.assertIn(127, preflight.NUMPY_NATIVE_CRASH_CODES)          # MSYS 截断形态


class NumpyProbeBehaviorTest(unittest.TestCase):
    """用假子进程结果驱动判读分支（不依赖本机 numpy 是否真的坏）。"""

    def _run_with(self, returncode, stdout="", stderr=""):
        fake = subprocess.CompletedProcess(
            args=["python", "-c", "..."], returncode=returncode,
            stdout=stdout, stderr=stderr)
        with mock.patch.object(preflight.subprocess, "run", return_value=fake):
            return preflight.check_numpy_linalg()

    def test_ok_when_subprocess_reports_usable(self):
        c = self._run_with(0, stdout="numpy-linalg-ok 2.5.3")
        self.assertTrue(c.ok, c.reason)
        self.assertEqual(c.value.get("numpy_version"), "2.5.3")

    def test_fails_with_workaround_on_native_crash(self):
        """原生崩溃（无 traceback）必须报失败，并给出两条已验证的规避写法。"""
        c = self._run_with(3228369023, stderr="")
        self.assertFalse(c.ok)
        self.assertEqual(c.code, preflight.ENV_NUMPY_LINALG_BROKEN)
        self.assertIn("原生", c.reason)
        self.assertIn("3228369023", c.reason)
        # 规避写法两条都必须在（这是 A5 的验收点）
        self.assertIn("z-score", c.reason)
        self.assertIn("pearsonr", c.reason)
        # 影响说明必须写清"静默死"而不是"抛异常"
        self.assertIn("静默", c.reason)

    def test_native_crash_without_any_stderr_is_still_detected(self):
        """崩溃时 stdout/stderr 都可能是空的 —— 不能因此误判为"普通异常"。"""
        c = self._run_with(999, stderr="")
        self.assertFalse(c.ok)
        self.assertIn("原生", c.reason)

    def test_python_exception_is_reported_separately(self):
        """有 traceback 的失败是普通异常，走另一条文案（不冒充原生崩溃）。"""
        c = self._run_with(1, stderr="Traceback (most recent call last):\n  ...\nImportError: x")
        self.assertFalse(c.ok)
        self.assertNotIn("原生致命退出", c.reason)
        self.assertIn("scipy.stats.pearsonr", c.reason)

    def test_timeout_is_bounded_and_reported(self):
        with mock.patch.object(preflight.subprocess, "run",
                               side_effect=subprocess.TimeoutExpired(cmd="x", timeout=60)):
            c = preflight.check_numpy_linalg(timeout=60)
        self.assertFalse(c.ok)
        self.assertIn("超时", c.reason)

    def test_oserror_reports_interpreter_path(self):
        with mock.patch.object(preflight.subprocess, "run",
                               side_effect=OSError("no such file")):
            c = preflight.check_numpy_linalg()
        self.assertFalse(c.ok)
        self.assertIn("无法启动子进程", c.reason)


class NumpyProbeParentSafetyTest(unittest.TestCase):
    """A5 的硬要求：探测走子进程 ⇒ 父进程必须活着且拿得到结论。"""

    def test_parent_survives_and_returns_check(self):
        c = preflight.check_numpy_linalg()
        # 无论本机 numpy 好坏，父进程都必须正常返回一个 Check 对象
        self.assertIsInstance(c, preflight.Check)
        self.assertIsInstance(c.ok, bool)
        self.assertIsInstance(c.value, dict)

    def test_probe_is_wired_into_probe_env(self):
        env = preflight.probe_env()
        self.assertIn("numpy_linalg", env)
        self.assertIn("ok", env["numpy_linalg"])

    def test_probe_uses_sys_executable(self):
        """子进程必须用当前解释器 —— 否则可能探测到另一个环境的 numpy。"""
        captured = {}

        def fake_run(cmd, **kw):
            captured["cmd"] = cmd
            return subprocess.CompletedProcess(args=cmd, returncode=0,
                                               stdout="numpy-linalg-ok 9.9.9", stderr="")

        with mock.patch.object(preflight.subprocess, "run", side_effect=fake_run):
            preflight.check_numpy_linalg()
        self.assertEqual(captured["cmd"][0], sys.executable)


if __name__ == "__main__":
    unittest.main()
