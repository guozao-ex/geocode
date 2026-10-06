"""C5 批处理导出的纯逻辑离线单测（验收 A5）。

覆盖 brief 验收项 A5：GEE 六态 → jobs 五态映射、jobs.json 保存/加载/恢复
往返、取消联动判定、导出参数校验的报错路径。
不导入 ee、不联网 —— export.py 顶层无 ee（延迟导入，同 source.py 模式），
jobstore.py 只依赖 stdlib + spec/jobs。
"""

import tempfile
import unittest
from pathlib import Path

from _helpers import make_spec
from gis import export, jobstore
from gis.jobs import CANCELLED, DONE, FAILED, KIND_EXPORT, QUEUED, RUNNING, Job, Jobs
from gis.spec import SpecError


class TaskStateMapTest(unittest.TestCase):
    """GEE 六态 → jobs 五态（brief D4）。"""

    def test_six_states_map_to_five(self):
        cases = {
            "UNSUBMITTED": QUEUED,
            "READY": QUEUED,
            "RUNNING": RUNNING,
            "COMPLETED": DONE,
            "FAILED": FAILED,
            "CANCELLED": CANCELLED,
        }
        for gee_state, want in cases.items():
            self.assertEqual(export.map_task_state(gee_state), want, gee_state)

    def test_case_and_whitespace_tolerant(self):
        self.assertEqual(export.map_task_state("running"), RUNNING)
        self.assertEqual(export.map_task_state("  COMPLETED "), DONE)

    def test_unknown_state_returns_none(self):
        """未知状态不猜 —— 返回 None，调用方保持现状 + warning。"""
        self.assertIsNone(export.map_task_state("SOMETHING_NEW"))
        self.assertIsNone(export.map_task_state(None))
        self.assertIsNone(export.map_task_state(""))


class ExportParamsTest(unittest.TestCase):
    """导出参数校验（brief D3/D11）：folder 默认与透传、file_format/分片参数。"""

    def test_folder_default(self):
        """folder 空缺/空白 → 默认 gexports（D11）。"""
        self.assertEqual(export.submit_params({})["folder"], "gexports")
        self.assertEqual(export.submit_params({"folder": "   "})["folder"], "gexports")

    def test_folder_passthrough_and_trim(self):
        self.assertEqual(export.require_folder({"folder": " my-exports "}), "my-exports")
        self.assertEqual(export.submit_params({"folder": "custom"})["folder"], "custom")

    def test_default_file_format(self):
        self.assertEqual(export.submit_params({})["file_format"], "GeoTIFF")

    def test_bad_file_format_rejected(self):
        with self.assertRaises(SpecError):
            export.submit_params({"file_format": "PNG"})

    def test_bad_shard_size_rejected(self):
        with self.assertRaises(SpecError):
            export.submit_params({"shard_size": 0})

    def test_bad_max_pixels_rejected(self):
        with self.assertRaises(SpecError):
            export.submit_params({"max_pixels": 0})

    def test_max_pixels_passthrough(self):
        self.assertEqual(export.submit_params({"max_pixels": 12345})["max_pixels"], 12345)

    def test_file_dimensions_list_validated(self):
        self.assertEqual(export.submit_params({"file_dimensions": [512, 512]})["file_dimensions"], [512, 512])
        with self.assertRaises(SpecError):
            export.submit_params({"file_dimensions": [512, 0]})


class ValidateExportSpecTest(unittest.TestCase):
    """export 的 spec 必填项与 file 出口相同（asset/crs/scale/aoi）。"""

    def test_requires_file_level_fields(self):
        spec = make_spec(crs=None, scale=None)
        with self.assertRaises(SpecError) as cm:
            export.validate_export_spec(spec)
        msg = str(cm.exception)
        self.assertIn("crs", msg)
        self.assertIn("scale", msg)

    def test_complete_spec_passes(self):
        export.validate_export_spec(make_spec())


class CancelCouplingTest(unittest.TestCase):
    """取消联动判定（brief D5）：只有未终态、有 task id 的 export 才碰 GEE。"""

    def _job(self, **over):
        kw = dict(id="j_test", kind=KIND_EXPORT, spec=make_spec(), task_id="TASK123")
        kw.update(over)
        return Job(**kw)

    def test_export_with_task_id_cancels_gee(self):
        self.assertTrue(export.should_cancel_gee(self._job()))

    def test_terminal_job_does_not_touch_gee(self):
        for status in (DONE, FAILED, CANCELLED):
            self.assertFalse(export.should_cancel_gee(self._job(status=status)), status)

    def test_other_kinds_or_missing_task_id_do_not_touch_gee(self):
        self.assertFalse(export.should_cancel_gee(self._job(kind="emit")))
        self.assertFalse(export.should_cancel_gee(self._job(task_id=None)))


class JobstoreTest(unittest.TestCase):
    """jobs.json 保存 / 加载 / 恢复往返（brief D7）。"""

    def test_roundtrip_save_load_restore(self):
        job = Job(id="j_rt", kind=KIND_EXPORT, spec=make_spec(), task_id="T-1")
        job.result = {"folder": "gexports", "file_prefix": "p", "destination": "Drive/gexports/p*"}
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "jobs.json"
            jobstore.save({"j_rt": job.to_dict(include_result=True)}, path)
            loaded = jobstore.load(path)
            self.assertIn("j_rt", loaded)
            restored = jobstore.restore(loaded["j_rt"])
            self.assertEqual(restored.id, "j_rt")
            self.assertEqual(restored.kind, KIND_EXPORT)
            self.assertEqual(restored.task_id, "T-1")
            # spec 往返保真：指纹不变是恢复可用性的锚
            self.assertEqual(restored.spec.fingerprint(), make_spec().fingerprint())
            self.assertEqual(restored.result["destination"], "Drive/gexports/p*")

    def test_restore_preserves_status_and_timestamps(self):
        rec = {
            "id": "j_s", "kind": KIND_EXPORT, "status": RUNNING,
            "task_id": "T-2", "phase": "GEE 计算中", "pct": 42.0,
            "created_at": 1000.0, "started_at": 1001.0,
        }
        job = jobstore.restore(rec)
        self.assertEqual(job.status, RUNNING)
        self.assertEqual(job.task_id, "T-2")
        self.assertEqual(job.pct, 42.0)
        self.assertEqual(job.created_at, 1000.0)
        self.assertEqual(job.started_at, 1001.0)

    def test_restore_without_task_id_is_visible_not_fatal(self):
        """task id 缺失的记录原样恢复、如实可见（不伪造状态）。"""
        job = jobstore.restore({"id": "j_x", "kind": KIND_EXPORT, "status": "queued"})
        self.assertIsNone(job.task_id)
        self.assertEqual(job.status, "queued")

    def test_load_missing_file_returns_empty(self):
        self.assertEqual(jobstore.load(Path("Z:/definitely/not/there/jobs.json")), {})

    def test_load_corrupt_file_returns_empty(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "jobs.json"
            path.write_text("{not json", encoding="utf-8")
            self.assertEqual(jobstore.load(path), {})

    def test_save_is_atomic(self):
        """同目录 .part + replace，成功后无残留（踩坑 #11）。"""
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "jobs.json"
            jobstore.save({"a": {"id": "a"}}, path)
            self.assertTrue(path.is_file())
            self.assertFalse(path.with_suffix(path.suffix + ".part").exists())

    def test_snapshot_filters_export_only(self):
        """持久化范围仅 export（describe/defaults/emit 是本地瞬时计算）。"""
        jobs = Jobs()
        jobs.adopt(Job(id="j_ex", kind=KIND_EXPORT, spec=make_spec(), task_id="T"))
        jobs.adopt(Job(id="j_loc", kind="emit", spec=make_spec()))
        snap = jobstore.snapshot(jobs)
        self.assertIn("j_ex", snap)
        self.assertNotIn("j_loc", snap)


class FormatGeeErrorTest(unittest.TestCase):
    """getTaskStatus 的错误字段形态（字符串 error_message，兼容嵌套 dict）。"""

    def test_error_message_string(self):
        r = export._format_gee_error({"error_message": "Drive quota exceeded"})
        self.assertEqual(r, "GEE task FAILED：Drive quota exceeded")

    def test_nested_error_dict(self):
        r = export._format_gee_error({"error": {"message": "boom", "code": 3}})
        self.assertEqual(r, "GEE task FAILED：boom")

    def test_missing_error_details(self):
        r = export._format_gee_error({})
        self.assertIn("GEE 未给错误详情", r)


class PollFailureStreakTest(unittest.TestCase):
    """连续查询失败计数（风险②修复）：报错带次数、成功即清零。"""

    def test_streak_counts_up_and_message_includes_count(self):
        job = Job(id="j_f", kind=KIND_EXPORT, spec=make_spec(), task_id="T")
        n1 = export.note_poll_failure(job, RuntimeError("boom"))
        n2 = export.note_poll_failure(job, RuntimeError("again"))
        self.assertEqual((n1, n2), (1, 2))
        self.assertIn("连续第 2 次", job.message)
        self.assertIn("RuntimeError", job.message)

    def test_reset_clears_streak(self):
        job = Job(id="j_f2", kind=KIND_EXPORT, spec=make_spec(), task_id="T")
        export.note_poll_failure(job, RuntimeError("x"))
        export.reset_poll_failure(job)
        n = export.note_poll_failure(job, RuntimeError("z"))
        self.assertEqual(n, 1)


class JobsRegistryTest(unittest.TestCase):
    """C5 给 jobs.py 的最小扩展：task_id 字段、adopt、emit。"""

    def test_task_id_in_to_dict(self):
        job = Job(id="j1", kind=KIND_EXPORT, spec=make_spec(), task_id="T9")
        self.assertEqual(job.to_dict()["task_id"], "T9")

    def test_adopt_registers_without_thread(self):
        jobs = Jobs()
        job = Job(id="j_adopt", kind=KIND_EXPORT, spec=make_spec(), status=RUNNING, task_id="T")
        jobs.adopt(job)
        self.assertIs(jobs.get("j_adopt"), job)
        self.assertFalse(job.thread_alive)          # 恢复的任务无线程，由轮询驱动

    def test_adopt_emits_created_event(self):
        """adopt 也走事件流 —— 持久化监听与 SSE 都能感知恢复任务。"""
        jobs = Jobs()
        seen = []
        jobs.subscribe(lambda ev, payload: seen.append(ev))
        jobs.adopt(Job(id="j_e", kind=KIND_EXPORT, spec=make_spec()))
        self.assertIn("job.created", seen)


if __name__ == "__main__":
    unittest.main()
