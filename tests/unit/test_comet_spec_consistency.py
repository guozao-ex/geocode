"""C13 结构不变量守卫：`docs/comet` 的发布面 specs 与归档面必须自洽（离线、只读文件）。

四条不变量（C13 修订后确立的发布面规则）：

1. 每个 `docs/comet/specs/<cap>/spec.md` 的 H1 形如 `# Capability：<cap> —— …`，且 `<cap>`
   恰为发布面目录名（capability 名 = 目录名）；
2. 每个发布面 spec 在 `docs/comet/archive/*/specs/<cap>/spec.md` 有**逐字节相同**的归档副本；
3. 每个 `### Scenario:` 标题都带 `（验收：A…）` 引用（编号写在标题内；不接受标题外的独立引用行）；
4. 每个归档 change 目录含 `brief.md`、`comet-state.yaml`、`verification.md` 与 `specs/*/spec.md`。

来源：2026-10-08 对 C1–C12 的跨 change 审阅发现 8 条矛盾/不一致，其中四类可由静态断言机械检出
（见 `docs/comet/changes/c13-spec-consistency/spec-revision-list.md`）。本守卫把这四类固化，避免复发。
语义级取代关系（哪条条款被哪个 change 取代）无法自动化，靠 `docs/comet/specs/README.md` 的人工索引。

离线纪律：只读文件，不导入 socket/http/urllib 等（见 `test_offline_guard.py` 的 BANNED 名单）。
"""

import io
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PUBLISHED = os.path.join(ROOT, "docs", "comet", "specs")
ARCHIVE = os.path.join(ROOT, "docs", "comet", "archive")

REQUIRED_ARCHIVE_FILES = ("brief.md", "comet-state.yaml", "verification.md")


def _read(path: str) -> str:
    return io.open(path, encoding="utf-8").read()


def _published_specs() -> dict:
    """capability -> 发布面 spec 路径。"""
    out = {}
    if not os.path.isdir(PUBLISHED):
        return out
    for cap in sorted(os.listdir(PUBLISHED)):
        p = os.path.join(PUBLISHED, cap, "spec.md")
        if os.path.exists(p):
            out[cap] = p
    return out


def _archived_specs() -> dict:
    """capability -> [归档面 spec 路径, ...]（同一 capability 可能被多个 change 归档过）。"""
    out = {}
    if not os.path.isdir(ARCHIVE):
        return out
    for change_dir in sorted(os.listdir(ARCHIVE)):
        specs = os.path.join(ARCHIVE, change_dir, "specs")
        if not os.path.isdir(specs):
            continue
        for cap in sorted(os.listdir(specs)):
            p = os.path.join(specs, cap, "spec.md")
            if os.path.exists(p):
                out.setdefault(cap, []).append(p)
    return out


class PublishedSpecSurfaceTest(unittest.TestCase):
    """不变量 1：capability 名 = 发布面目录名，且 H1 前缀统一。"""

    def test_published_specs_exist(self):
        """发布面必须存在且有内容（删空或移走会让本守卫直接失败）。"""
        specs = _published_specs()
        self.assertTrue(specs, f"{PUBLISHED} 下没有 spec.md —— 发布面缺失")
        self.assertGreaterEqual(len(specs), 12, f"发布面 spec 数异常：{len(specs)}")

    def test_h1_declares_capability_name_matching_directory(self):
        """H1 必须是 `# Capability：<目录名> —— …`（C13 对齐 F5：曾有三处不符）。"""
        offenders = []
        for cap, path in _published_specs().items():
            h1 = _read(path).split("\n", 1)[0].strip()
            if not h1.startswith(f"# Capability：{cap} —— "):
                offenders.append(f"{cap}: {h1[:80]}")
        self.assertFalse(offenders, "H1 未声明 capability 名或与目录名不符：" + "; ".join(offenders))

    def test_placeholder_h1_absent(self):
        """H1 不得是裸标题（缺 `Capability：` 前缀）——F5 的两种历史形态。"""
        bad = [cap for cap, path in _published_specs().items()
               if not _read(path).startswith("# Capability：")]
        self.assertFalse(bad, f"缺 `# Capability：` 前缀的 spec：{bad}")


class PublishedArchivePairTest(unittest.TestCase):
    """不变量 2：发布面 spec 必须在归档面有逐字节相同的副本。"""

    def test_every_published_spec_has_identical_archive_twin(self):
        published, archived = _published_specs(), _archived_specs()
        self.assertTrue(archived, f"{ARCHIVE} 下没有归档 spec —— 归档面缺失")
        problems = []
        for cap, path in published.items():
            twins = archived.get(cap)
            if not twins:
                problems.append(f"{cap}: 归档面无副本")
                continue
            data = io.open(path, "rb").read()
            if not any(io.open(t, "rb").read() == data for t in twins):
                problems.append(f"{cap}: 与归档副本内容不一致（{len(twins)} 个副本均不逐字节相同）")
        self.assertFalse(problems, "发布面/归档面不一致：" + "; ".join(problems))

    def test_no_orphan_archived_spec(self):
        """归档面不得有发布面缺失的 capability（孤儿）。"""
        published, archived = _published_specs(), _archived_specs()
        orphans = sorted(set(archived) - set(published))
        self.assertFalse(orphans, f"归档面存在发布面缺失的 capability：{orphans}")


class ScenarioAcceptanceReferenceTest(unittest.TestCase):
    """不变量 3：每个 Scenario 必带验收引用，且不存在标题外的独立引用行。"""

    def test_every_scenario_carries_acceptance_reference(self):
        missing = {}
        for cap, path in _published_specs().items():
            lines = _read(path).split("\n")
            heads = [l for l in lines if l.startswith("### Scenario: ")]
            bad = [l for l in heads if "（验收：" not in l]
            if bad:
                missing[cap] = len(bad)
            if not heads:
                missing[cap] = "无 Scenario"
        self.assertFalse(missing, f"缺 `（验收：…）` 引用的 spec：{missing}")

    def test_no_standalone_acceptance_reference_line(self):
        """引用必须写在标题内：单独的 `（验收：…）` 行属历史异类形态（C13 已统一）。"""
        offenders = []
        for cap, path in _published_specs().items():
            for ln in _read(path).split("\n"):
                if ln.startswith("（验收："):
                    offenders.append(cap)
                    break
        self.assertFalse(offenders, f"存在标题外独立验收引用行：{offenders}")


class ArchiveCompletenessTest(unittest.TestCase):
    """不变量 4：归档 change 目录的必备产物齐备。"""

    def test_archive_dirs_have_required_artifacts(self):
        self.assertTrue(os.path.isdir(ARCHIVE), f"{ARCHIVE} 不存在")
        problems = []
        for change_dir in sorted(os.listdir(ARCHIVE)):
            p = os.path.join(ARCHIVE, change_dir)
            if not os.path.isdir(p):
                continue
            missing = [n for n in REQUIRED_ARCHIVE_FILES if not os.path.exists(os.path.join(p, n))]
            specs_dir = os.path.join(p, "specs")
            has_spec = os.path.isdir(specs_dir) and any(
                f == "spec.md" for _, _, fs in os.walk(specs_dir) for f in fs)
            if missing or not has_spec:
                problems.append(f"{change_dir}: 缺 {missing or ''}{' 无 specs/*/spec.md' if not has_spec else ''}")
        self.assertFalse(problems, "归档产物不完整：" + "; ".join(problems))


if __name__ == "__main__":
    unittest.main()
