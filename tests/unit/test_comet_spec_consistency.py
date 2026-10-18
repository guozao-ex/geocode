"""C13 结构不变量守卫：`docs/comet` 的发布面 specs 与归档面必须自洽（离线、只读文件）。

四条不变量（C13 修订后确立的发布面规则）：

1. 每个 `docs/comet/specs/<cap>/spec.md` 的 H1 形如 `# Capability：<cap> —— …`，且 `<cap>`
   恰为发布面目录名（capability 名 = 目录名）；
2. 每个发布面 spec 在 `docs/comet/archive/*/specs/<cap>/spec.md` 有**逐字节相同**的归档副本；
3. 每个 `### Scenario:` 标题都带 `（验收：A…）` 引用（编号写在标题内；不接受标题外的独立引用行）；
4. 每个归档 change 目录含 `brief.md`、`comet-state.yaml`、`verification.md` 与 `specs/*/spec.md`；
   **例外（c20 修订）**：`brief.md` 声明了合规（非占位）的「不改变产品行为」豁免时，允许没有 `specs/`
   —— 判据镜像 Comet Runtime 的 `hasExplicitSpecExemption` / `isPlaceholderExemptionReason`。

来源：2026-10-08 对 C1–C12 的跨 change 审阅发现 8 条矛盾/不一致，其中四类可由静态断言机械检出
（见 `docs/comet/changes/c13-spec-consistency/spec-revision-list.md`）。本守卫把这四类固化，避免复发。
语义级取代关系（哪条条款被哪个 change 取代）无法自动化，靠 `docs/comet/specs/README.md` 的人工索引。

c20 修订（2026-10-18）：不变量 4 原先要求**每个**归档 change 目录都含 `specs/*/spec.md`，与 Comet
Runtime 的「不改变产品行为」豁免（change 的 `brief.md` 写一行合规声明即可免写目标 Spec）相矛盾。
c19-verify-report-drift 走豁免归档后，其归档目录本来就没有 `specs/`，导致本守卫在 main 上长期转红
（全量单测 393 例 1 失败）。现按「有合规豁免声明才放行、其余必备件仍强制」判定。

离线纪律：只读文件，不导入 socket/http/urllib 等（见 `test_offline_guard.py` 的 BANNED 名单）。
"""

import os
import re
import pathlib
import re
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
PUBLISHED = os.path.join(ROOT, "docs", "comet", "specs")
ARCHIVE = os.path.join(ROOT, "docs", "comet", "archive")

REQUIRED_ARCHIVE_FILES = ("brief.md", "comet-state.yaml", "verification.md")


def _read(path: str) -> str:
    return pathlib.Path(path).read_text(encoding="utf-8")


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
            data = pathlib.Path(path).read_bytes()
            if not any(pathlib.Path(t).read_bytes() == data for t in twins):
                problems.append(f"{cap}: 与归档副本内容不一致（{len(twins)} 个副本均不逐字节相同）")
        self.assertFalse(problems, "发布面/归档面不一致：" + "; ".join(problems))

    def test_no_orphan_archived_spec(self):
        """归档面不得有发布面缺失的 capability（孤儿）。"""
        published, archived = _published_specs(), _archived_specs()
        orphans = sorted(set(archived) - set(published))
        self.assertFalse(orphans, f"归档面存在发布面缺失的 capability：{orphans}")


# 验收引用的承载形态（c18 起两种都接受，语义等价）：
#   1. 标题内 `### Scenario: <标题>（验收：A<n>）` —— C13 发布面规范 2 的历史形态；
#   2. Scenario 正文独占一行 `Acceptance: A<n>` / `（验：A<n>` —— Comet Runtime 的引用契约
#      （native-acceptance.js 只在**正文行**上匹配 Acceptance / （验，据此把场景挂到 brief 的验收 ID，
#       不再另发一条重复验收项）。spec 的 Scenario 编号与 brief 验收 ID **互不重叠**（c18：brief A1–A10 / spec A11–A20）。
REF_RE = re.compile(r"^(?:Acceptance|验收)\s*[:：]\s*A[1-9]\d*$", re.IGNORECASE | re.UNICODE)
HEAD_REF = "（验收：A"


def _is_scenario_head(line: str) -> bool:
    return line.startswith("### Scenario: ")


def _scenario_reference(lines: list[str], head_index: int) -> str | None:
    """该 Scenario 的验收引用文本；标题内与正文独占行两种形态都算。"""
    head = lines[head_index]
    if HEAD_REF in head:
        return head[head.index(HEAD_REF):]
    for ln in lines[head_index + 1:]:
        if _is_scenario_head(ln) or ln.lstrip().startswith("#"):
            break
        if REF_RE.match(ln.strip()):
            return ln.strip()
    return None


class ScenarioAcceptanceReferenceTest(unittest.TestCase):
    """不变量 3：每个 Scenario 必带验收引用；承载形态见本类上方注释。"""

    def test_every_scenario_carries_acceptance_reference(self):
        missing = {}
        for cap, path in _published_specs().items():
            lines = _read(path).split("\n")
            heads = [i for i, l in enumerate(lines) if _is_scenario_head(l)]
            bad = [lines[i] for i in heads if _scenario_reference(lines, i) is None]
            if bad:
                missing[cap] = len(bad)
            if not heads:
                missing[cap] = "无 Scenario"
        self.assertFalse(missing, f"缺验收引用的 spec：{missing}")

    def test_no_legacy_bare_reference_line(self):
        """历史异类形态（C13 已统一）不得复活：正文独占一行的 `（验收：…）` 属旧形态。"""
        offenders = []
        for cap, path in _published_specs().items():
            for ln in _read(path).split("\n"):
                if ln.startswith("（验收："):
                    offenders.append(cap)
                    break
        self.assertFalse(offenders, f"存在历史形态的独立验收引用行：{offenders}")


# ---------------------------------------------------------------------------
# 不变量 4：归档产物完备性（c20 起识别 Runtime 的「不改变产品行为」豁免）
# ---------------------------------------------------------------------------

SPEC_EXEMPTION_RE = re.compile(
    r"(?:no\s+product\s+behavior\s+change|documentation[- ]only|不改变产品行为|不涉及产品行为|仅文档)"
    r"\s*[:：]\s*(.*)$",
    re.IGNORECASE | re.UNICODE,
)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_FENCE_RE = re.compile(r"^\s*(?:```|~~~)")
_HEADING_RE = re.compile(r"^\s*#{1,6}\s+")
_PLACEHOLDER_SHAPE_RE = re.compile(r"^(?:<[^>\r\n]+>|\{\{[^}\r\n]+\}\})[.!：: -]*$", re.IGNORECASE)
_PLACEHOLDER_WORD_RE = re.compile(
    r"^(?:(?:todo|tbd|fixme)\b|fill(?:\s+this\s+in)?\b|placeholder\b|documentation[- ]only\b"
    r"|no\s+product\s+behavior\s+change\b|待填写|待补充|仅文档|不改变产品行为|不涉及产品行为)"
    r"[.!。；;：:，,、 -]*$",
    re.IGNORECASE,
)


def _strip_html_comments(text: str) -> str:
    return _HTML_COMMENT_RE.sub("", text)


def _visible_lines(text: str) -> list:
    """与 Runtime 同口径的可见行：排除围栏内代码与标题行。"""
    lines = []
    in_fence = False
    for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        if not in_fence and not _HEADING_RE.match(line):
            lines.append(line)
    return lines


def _is_placeholder_reason(reason: str) -> bool:
    """占位理由不算豁免（镜像 Runtime 的 isPlaceholderExemptionReason）。"""
    normalized = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)]\s+)", "", reason)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    if not normalized:
        return True
    if _PLACEHOLDER_SHAPE_RE.match(normalized):
        return True
    decorated = re.sub(r"[*_`>#\[\]()]", " ", normalized)
    decorated = re.sub(r"\s+", " ", decorated).strip()
    if re.match(r"^(?:todo|tbd|fixme)(?:\s*[:：-]|\s*$)", decorated, re.IGNORECASE):
        return True
    if re.match(r"^(?:fill(?:\s+this\s+in)?|placeholder)\b", decorated, re.IGNORECASE):
        return True
    if re.match(r"^(?:待填写|待补充)", decorated):
        return True
    return _PLACEHOLDER_WORD_RE.match(decorated) is not None


def spec_exemption_reason(brief_text: str) -> str:
    """brief.md 里合规的「不改变产品行为」豁免理由；没有则返回空串。"""
    for line in _visible_lines(_strip_html_comments(brief_text)):
        found = SPEC_EXEMPTION_RE.search(line)
        if found:
            reason = found.group(1) or ""
            if not _is_placeholder_reason(reason):
                return reason.strip()
    return ""


def archive_completeness_problems(archive_root) -> list:
    """不变量 4：返回归档目录的完备性问题描述（空列表 = 全部通过）。"""
    if not os.path.isdir(archive_root):
        return [f"{archive_root} 不存在"]
    problems = []
    for change_dir in sorted(os.listdir(archive_root)):
        p = os.path.join(archive_root, change_dir)
        if not os.path.isdir(p):
            continue
        missing = [n for n in REQUIRED_ARCHIVE_FILES if not os.path.exists(os.path.join(p, n))]
        specs_dir = os.path.join(p, "specs")
        has_spec = os.path.isdir(specs_dir) and any(
            f == "spec.md" for _, _, fs in os.walk(specs_dir) for f in fs)
        exempt = False
        if not has_spec:
            brief_path = os.path.join(p, "brief.md")
            if os.path.exists(brief_path):
                exempt = bool(spec_exemption_reason(
                    pathlib.Path(brief_path).read_text(encoding="utf-8")))
        if missing or (not has_spec and not exempt):
            detail = f"缺 {missing or ''}"
            if not has_spec and not exempt:
                detail += (" 无 specs/*/spec.md 且 brief.md 未声明合规的「不改变产品行为」豁免"
                           if os.path.exists(os.path.join(p, "brief.md"))
                           else " 无 specs/*/spec.md")
            problems.append(f"{change_dir}: {detail}")
    return problems


class ArchiveCompletenessTest(unittest.TestCase):
    """不变量 4：归档 change 目录的必备产物齐备（c20 起识别「不改变产品行为」豁免）。"""

    def test_archive_dirs_have_required_artifacts(self):
        problems = archive_completeness_problems(ARCHIVE)
        self.assertFalse(problems, "归档产物不完整：" + "; ".join(problems))



class ArchiveSpecExemptionTest(unittest.TestCase):
    """c20：不变量 4 的「不改变产品行为」豁免（判据与 Comet Runtime 同源）。

    由来：c19-verify-report-drift 走 Runtime 的豁免（brief 一行声明即可免写目标 Spec）归档后，
    其归档目录本来就没有 specs/，原判据让本守卫在 main 上长期转红（全量单测 393 例 1 失败）。
    放行必须挂在**合规**豁免声明上，不能变成「没有 specs/ 就一律放行」。
    """

    REQUIRED = ("brief.md", "comet-state.yaml", "verification.md")

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)

    def _archived_change(self, name, brief_text):
        change_dir = self.root / name
        change_dir.mkdir(parents=True, exist_ok=True)
        for filename in self.REQUIRED:
            (change_dir / filename).write_text("x\n", encoding="utf-8")
        (change_dir / "brief.md").write_text(brief_text, encoding="utf-8")
        return change_dir

    def test_exempt_change_without_spec_is_accepted(self):
        """合规豁免声明 -> 允许没有 specs/（A1）。"""
        self._archived_change(
            "sample-exempt",
            "# 目标\n\n- 不改变产品行为：仅新增两个只读开发者工具与离线用例，不接入任何产品路径。\n",
        )
        self.assertEqual(archive_completeness_problems(str(self.root)), [])

    def test_change_without_spec_and_without_exemption_is_rejected(self):
        """没有豁免声明就不放行，且点名该目录（A2）。"""
        self._archived_change("sample-changed", "# 目标\n\n本 change 改了 gis/spec.py 的行为。\n")
        problems = archive_completeness_problems(str(self.root))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("sample-changed", problems[0])
        self.assertIn("无 specs/*/spec.md", problems[0])

    def test_placeholder_exemption_reason_is_rejected(self):
        """破坏性自证：占位理由不算豁免（A3）。"""
        for index, reason in enumerate(("", "   ", "<TODO>", "{{reason}}", "待填写", "TODO")):
            with self.subTest(reason=reason):
                name = f"sample-placeholder-{index}"
                self._archived_change(name, "# 目标\n\n- 不改变产品行为：" + reason + "\n")
                problems = archive_completeness_problems(str(self.root))
                self.assertTrue(problems, f"占位理由 {reason!r} 未被判红")
                self.assertTrue(any(name in item for item in problems), problems)

    def test_exemption_must_be_a_visible_line(self):
        """标题行与围栏内的豁免声明不算数（与 Runtime 的可见行口径一致）。"""
        for index, brief in enumerate((
            "# 不改变产品行为：仅文档\n\n正文没有豁免声明。\n",
            "```\n不改变产品行为：仅文档\n```\n",
            "<!-- 不改变产品行为：仅文档 -->\n",
        )):
            with self.subTest(case=index):
                name = f"sample-invisible-{index}"
                self._archived_change(name, brief)
                problems = archive_completeness_problems(str(self.root))
                self.assertTrue(problems, f"第 {index} 种不可见形态未被判红")
                self.assertTrue(any(name in item for item in problems), problems)

    def test_missing_required_artifact_is_still_rejected(self):
        """破坏性自证：有合规豁免但缺其它必备件时仍必须转红（A3）。"""
        change_dir = self._archived_change(
            "sample-missing",
            "# 目标\n\n- 不改变产品行为：仅调整仓库内的开发期守卫判据。\n",
        )
        (change_dir / "verification.md").unlink()
        problems = archive_completeness_problems(str(self.root))
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("sample-missing", problems[0])
        self.assertIn("verification.md", problems[0])

    def test_archive_root_missing_is_reported(self):
        problems = archive_completeness_problems(str(self.root / "nope"))
        self.assertEqual(len(problems), 1)
        self.assertIn("不存在", problems[0])

if __name__ == "__main__":
    unittest.main()
