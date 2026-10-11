"""
C15 A6：产物缓存清单 / 显式清理的 CLI 入口。

用法（geo 环境，仓库根）：

    python scripts/prune_cache.py list [--json]
    python scripts/prune_cache.py prune --confirm [--include-unknown] [--slug S]
    python scripts/prune_cache.py mark-current SLUG=FINGERPRINT

缺省作用在 `geoenv.data_path("derived")`（即 `geocode.json: paths.data_dir` 的
derived 子目录）；测试 / 研究项目可用 `--data-dir DIR` 直接指一个目录。

判定口径见 `gis/cache_manage.py`：
  - 当代指纹 = 产物根 `.cache-index.json` 里登记的该 slug 指纹；
  - 历史指纹 = 同 slug 的其它指纹；
  - 未登记   = 索引里没有这个 slug（默认保护，只有 `--include-unknown` 才删）。
无论什么参数组合，**当代指纹产物都不会被删**；`prune` 必须带 `--confirm`。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from gis import cache_manage as cm      # noqa: E402
from gis import geoenv                  # noqa: E402


def _resolve_root(args) -> Path:
    if args.data_dir:
        p = Path(args.data_dir)
        return p / "derived" if (p / "derived").is_dir() else p
    return geoenv.data_path("derived")


def _entries(root: Path, *, slug: str | None):
    current = cm.load_index(root)
    entries = cm.classify(cm.scan(root), current)
    if slug:
        entries = [e for e in entries if e.slug == slug]
    return current, entries


def cmd_list(args) -> int:
    root = _resolve_root(args)
    current, entries = _entries(root, slug=args.slug)
    summary = cm.summarize(entries)
    if args.json:
        print(json.dumps({
            "root": str(root),
            "index": str(cm.index_path(root)),
            "current_fingerprints": current,
            "summary": summary,
            "entries": [e.to_dict() for e in entries],
        }, ensure_ascii=False, indent=2))
        return 0
    print(f"产物根：{root}")
    print(f"索引  ：{cm.index_path(root)}"
          f"{'（不存在 → 全部按未登记保护）' if not current else ''}")
    for status, label in ((cm.STATUS_CURRENT, "当代指纹"),
                          (cm.STATUS_HISTORICAL, "历史指纹"),
                          (cm.STATUS_UNKNOWN, "未登记（默认保护）")):
        print(f"  {label:<12} {summary['count'][status]:>4} 项  "
              f"{cm.human_size(summary['bytes'][status])}")
    print(f"  合计{'':<10} {summary['total_count']:>4} 项  "
          f"{cm.human_size(summary['total_bytes'])}")
    print()
    for e in entries:
        mark = {cm.STATUS_CURRENT: "当代", cm.STATUS_HISTORICAL: "历史",
                cm.STATUS_UNKNOWN: "未登记"}[e.status]
        print(f"  [{mark:<3}] {e.fingerprint}  {cm.human_size(e.size_bytes):>10}  {e.path.name}")
    if not entries:
        print("  （没有指纹命名的产物）")
    return 0


def cmd_prune(args) -> int:
    root = _resolve_root(args)
    current, entries = _entries(root, slug=args.slug)
    plan = cm.plan_prune(entries, include_unknown=args.include_unknown)
    summary = cm.summarize(entries)
    if not plan:
        print(f"没有可删条目（当代 {summary['count'][cm.STATUS_CURRENT]} 项 / "
              f"未登记 {summary['count'][cm.STATUS_UNKNOWN]} 项受保护）。")
        return 0
    print(f"将删除 {len(plan)} 项历史指纹产物，释放约 "
          f"{cm.human_size(sum(e.size_bytes for e in plan))}：")
    for e in plan:
        print(f"  {e.fingerprint}  {cm.human_size(e.size_bytes):>10}  {e.path.name}")
    if not args.confirm:
        print("\n未删除任何文件。确认无误后加 --confirm 重跑。")
        return 2
    result = cm.run_prune(plan, confirm=True)
    print(f"\n已删除 {len(result['deleted'])} 个路径，释放 {cm.human_size(result['freed_bytes'])}。")
    if result["errors"]:
        print("以下路径删除失败：")
        for err in result["errors"]:
            print(f"  {err['path']}: {err['error']}")
        return 1
    return 0


def cmd_mark_current(args) -> int:
    root = _resolve_root(args)
    for item in args.pairs:
        if "=" not in item:
            print(f"格式应为 SLUG=FINGERPRINT，收到 {item!r}", file=sys.stderr)
            return 2
        slug, fp = item.split("=", 1)
        cm.record_current(root, slug.strip(), fp.strip())
    print(f"已登记当代指纹 → {cm.index_path(root)}")
    for slug, fp in sorted(cm.load_index(root).items()):
        print(f"  {slug} = {fp}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="prune_cache.py",
        description="产物缓存清单 / 显式清理（只删历史指纹，当代指纹永不可删）",
    )
    parser.add_argument("--data-dir", default=None,
                        help="产物目录或产物根（缺省 geoenv.data_path('derived')）")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_list = sub.add_parser("list", help="列出当代 / 历史 / 未登记指纹的占用")
    p_list.add_argument("--json", action="store_true")
    p_list.add_argument("--slug", default=None, help="只看某个 slug")
    p_list.set_defaults(func=cmd_list)

    p_prune = sub.add_parser("prune", help="删除历史指纹产物（必须 --confirm）")
    p_prune.add_argument("--confirm", action="store_true")
    p_prune.add_argument("--include-unknown", action="store_true",
                         help="连索引里没有的 slug 一起删（默认保护）")
    p_prune.add_argument("--slug", default=None, help="只清某个 slug")
    p_prune.set_defaults(func=cmd_prune)

    p_mark = sub.add_parser("mark-current", help="登记 slug 的当代指纹（可多组）")
    p_mark.add_argument("pairs", nargs="+", metavar="SLUG=FINGERPRINT")
    p_mark.set_defaults(func=cmd_mark_current)

    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
