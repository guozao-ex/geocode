"""
C15 A6：产物缓存的**清单与显式清理**。

研究产物不能静默丢弃 —— 这里只做两件事：

1. 按「当代指纹 / 历史指纹 / 未登记」分类列出产物根（缺省 `data/derived`）的占用；
2. 只删除**历史指纹**的产物，且必须显式确认。

「当代指纹」的判定依据是产物根里的缓存索引 `<root>/.cache-index.json`
（`slug → 8 位指纹`）：emit 每成功产出一个产物就记一笔（`record_current`）。
索引里没有的 slug → 归为「未登记」，默认**不删**（宁可留着，不可错删）；
确要清掉索引建立之前的存量，用 `include_unknown=True`（CLI 的 `--include-unknown`）。

判定逻辑是纯函数 + 小文件 IO，离线用例覆盖
（含「当代指纹产物不得被删」的守卫用例）。
"""

from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import dataclass, replace
from pathlib import Path

# 缓存索引文件名（放产物根内，跟随 paths.data_dir 一起搬家）
INDEX_NAME = ".cache-index.json"
INDEX_SCHEMA = "geocode.cache-index.v1"

# 参与清单的产物后缀（derived 里实际会出现的是 nc / tif / crf）
ARTIFACT_EXTENSIONS = (
    "nc", "tif", "tiff", "cog", "crf", "gpkg", "csv", "json", "lax", "png", "qgz",
)

# 产物文件名约定：<slug>.<8 位十六进制指纹>.<ext>
_FP_RE = re.compile(r"^[0-9a-f]{8}$")

STATUS_CURRENT = "current"        # 当代指纹：索引登记的当前指纹
STATUS_HISTORICAL = "historical"  # 历史指纹：同一 slug 的旧指纹
STATUS_UNKNOWN = "unknown"        # 未登记：索引里没有这个 slug


@dataclass(frozen=True)
class ArtifactEntry:
    """一个缓存产物（文件或目录，如 arcpy 的 .crf 目录）。"""

    path: Path
    slug: str
    fingerprint: str
    ext: str
    size_bytes: int
    is_dir: bool = False
    status: str = STATUS_UNKNOWN

    def to_dict(self) -> dict:
        return {
            "path": str(self.path),
            "name": self.path.name,
            "slug": self.slug,
            "fingerprint": self.fingerprint,
            "ext": self.ext,
            "size_bytes": int(self.size_bytes),
            "size": human_size(self.size_bytes),
            "is_dir": bool(self.is_dir),
            "status": self.status,
        }


def human_size(n: int) -> str:
    v = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if v < 1024 or unit == "TB":
            return f"{v:.0f} {unit}" if unit == "B" else f"{v:.1f} {unit}"
        v /= 1024
    return f"{v:.1f} TB"              # pragma: no cover


def parse_artifact_name(name: str) -> tuple[str, str, str] | None:
    """
    `<slug>.<8 位十六进制指纹>.<ext>` → `(slug, 指纹, 后缀)`；不匹配返回 `None`。

    取**最后**一个 8 位十六进制段作为指纹（slug 自身允许带点，如 `c8_mini_dongcheng`）。
    """
    stem, dot, ext = str(name).rpartition(".")
    if not dot or not stem:
        return None
    slug, dot2, fp = stem.rpartition(".")
    if not dot2 or not slug or not _FP_RE.match(fp):
        return None
    if ext.lower() not in ARTIFACT_EXTENSIONS:
        return None
    return slug, fp, ext.lower()


def _dir_size(p: Path) -> int:
    total = 0
    for f in p.rglob("*"):
        try:
            if f.is_file():
                total += f.stat().st_size
        except OSError:
            continue
    return total


def scan(root: Path) -> list[ArtifactEntry]:
    """扫描产物根，返回指纹命名的产物条目（不含 .part / 索引等隐藏件）。"""
    root = Path(root)
    if not root.is_dir():
        return []
    out: list[ArtifactEntry] = []
    for child in sorted(root.iterdir()):
        if child.name.startswith("."):
            continue
        parsed = parse_artifact_name(child.name)
        if parsed is None:
            continue
        slug, fp, ext = parsed
        try:
            size = _dir_size(child) if child.is_dir() else child.stat().st_size
        except OSError:
            continue
        out.append(ArtifactEntry(child, slug, fp, ext, size, child.is_dir()))
    return out


# ---------------------------------------------------------------------------
# 缓存索引（slug → 当代指纹）
# ---------------------------------------------------------------------------

def index_path(root: Path) -> Path:
    return Path(root) / INDEX_NAME


def load_index(root: Path) -> dict[str, str]:
    """读缓存索引；缺失 / 损坏一律当空表（索引坏了不该挡住产物使用）。"""
    p = index_path(root)
    if not p.is_file():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return {}
    current = data.get("current") if isinstance(data, dict) else None
    if not isinstance(current, dict):
        return {}
    return {str(k): str(v).lower() for k, v in current.items() if isinstance(v, str)}


def save_index(root: Path, current: dict[str, str]) -> Path:
    """原子写索引（同目录 .part + rename）：下游只会看到完整文件。"""
    p = index_path(root)
    p.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema": INDEX_SCHEMA,
        "generated": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "current": dict(sorted((str(k), str(v).lower()) for k, v in current.items())),
    }
    tmp = p.with_name(p.name + ".part")
    try:
        tmp.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8",
        )
        tmp.replace(p)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
    return p


def record_current(root: Path, slug: str, fingerprint: str) -> dict[str, str]:
    """记一笔「这个 slug 的当代指纹」——emit 成功产出产物后调用。"""
    fp8 = str(fingerprint)[:8].lower()
    current = load_index(root)
    if current.get(str(slug)) != fp8:
        current[str(slug)] = fp8
        save_index(root, current)
    return current


# ---------------------------------------------------------------------------
# 分类 / 清理
# ---------------------------------------------------------------------------

def classify(entries: list[ArtifactEntry], current: dict[str, str]) -> list[ArtifactEntry]:
    """按当代指纹表给条目定状态：current / historical / unknown。"""
    out: list[ArtifactEntry] = []
    for e in entries:
        want = current.get(e.slug)
        if want is None:
            status = STATUS_UNKNOWN
        elif want == e.fingerprint:
            status = STATUS_CURRENT
        else:
            status = STATUS_HISTORICAL
        out.append(replace(e, status=status))
    return out


def summarize(entries: list[ArtifactEntry]) -> dict:
    """各状态的条目数与占用（A6 的「能列出当代与历史指纹各自的占用」）。"""
    bytes_by = {STATUS_CURRENT: 0, STATUS_HISTORICAL: 0, STATUS_UNKNOWN: 0}
    count_by = {STATUS_CURRENT: 0, STATUS_HISTORICAL: 0, STATUS_UNKNOWN: 0}
    for e in entries:
        bytes_by[e.status] = bytes_by.get(e.status, 0) + e.size_bytes
        count_by[e.status] = count_by.get(e.status, 0) + 1
    return {
        "count": count_by,
        "bytes": bytes_by,
        "total_count": len(entries),
        "total_bytes": sum(bytes_by.values()),
    }


def plan_prune(
    entries: list[ArtifactEntry], *, include_unknown: bool = False,
) -> list[ArtifactEntry]:
    """
    选出可删条目：**只有历史指纹**（`include_unknown=True` 时额外包含未登记条目）。

    当代指纹条目在任何参数组合下都不会出现在结果里 —— 这是 A6 的硬守卫。
    """
    allowed = {STATUS_HISTORICAL}
    if include_unknown:
        allowed.add(STATUS_UNKNOWN)
    return [e for e in entries if e.status in allowed]


def run_prune(plan: list[ArtifactEntry], *, confirm: bool = False) -> dict:
    """执行清理。未显式确认（`confirm=False`）且有可删条目时拒绝执行。"""
    if plan and not confirm:
        raise RuntimeError(
            f"拒绝执行：{len(plan)} 个历史指纹产物需要显式确认（--confirm）。\n"
            f"  先跑 `list` 看清占用，再带 --confirm 重跑。当前未删除任何文件。"
        )
    deleted: list[str] = []
    errors: list[dict] = []
    freed = 0
    for e in plan:
        targets = [e.path]
        if not e.is_dir:
            targets.append(e.path.with_name(e.path.name + ".aux.xml"))  # PAM 旁挂
        ok = True
        for t in targets:
            try:
                if t.is_dir():
                    shutil.rmtree(t)
                elif t.is_file():
                    t.unlink()
                else:
                    continue
            except OSError as ex:
                errors.append({"path": str(t), "error": f"{type(ex).__name__}: {ex}"})
                ok = False
                continue
            deleted.append(str(t))
        if ok:
            freed += e.size_bytes
    return {"deleted": deleted, "freed_bytes": freed, "errors": errors}
