"""
统一环境入口：路径、解释器、GDAL、GEE 认证、代理。

所有其他模块都从这里取环境事实，不各自探测。
"""

from __future__ import annotations

import os
import sys
import json
import shutil
import socket
from dataclasses import dataclass
from pathlib import Path

# ---------------------------------------------------------------------------
# 路径
# ---------------------------------------------------------------------------

# gis/geoenv.py -> gis/ -> 项目根
ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
RAW_DIR = DATA_DIR / "raw"          # 原始下载，不手改
DERIVED_DIR = DATA_DIR / "derived"  # 中间产物
DELIVER_DIR = DATA_DIR / "deliver"  # 交付件：GPKG / COG / CSV
PROJECTS_DIR = ROOT / "projects"    # 生成的 .qgz / .aprx
CACHE_DIR = ROOT / ".cache"         # 缓存与运行态
LOG_DIR = ROOT / "logs"

CONFIG_PATH = ROOT / "geocode.json"

for _d in (DATA_DIR, RAW_DIR, DERIVED_DIR, DELIVER_DIR, PROJECTS_DIR, CACHE_DIR, LOG_DIR):
    _d.mkdir(parents=True, exist_ok=True)

# 分类子目录：raw/s2、derived/s2、deliver/... 由调用方自行 mkdir
DATA_KINDS = ("raw", "derived", "deliver")


def data_path(kind: str, *parts: str) -> Path:
    """data_path('deliver', 'aoi_ndvi.gpkg') -> 落在交付目录，并建好父目录。"""
    if kind not in DATA_KINDS:
        raise ValueError(f"kind 必须是 {DATA_KINDS} 之一，收到 {kind!r}")
    p = {"raw": RAW_DIR, "derived": DERIVED_DIR, "deliver": DELIVER_DIR}[kind]
    for part in parts[:-1]:
        p = p / part
    p.mkdir(parents=True, exist_ok=True)
    return p / parts[-1] if parts else p


# ---------------------------------------------------------------------------
# GDAL / PROJ
# ---------------------------------------------------------------------------

def fix_gdal_env() -> dict[str, str]:
    """
    conda 环境下 GDAL_DATA / PROJ_LIB 常常没导出，导致：
      - "Cannot find gdalvrt.xsd (GDAL_DATA is not defined)"
      - CRS 解析降级 / 坐标转换失败

    从当前解释器所在前缀里定位数据目录并写回 os.environ。
    幂等：已有且存在就不动。
    """
    prefix = Path(sys.prefix)
    candidates = {
        "GDAL_DATA": [prefix / "Library" / "share" / "gdal", prefix / "share" / "gdal"],
        "PROJ_LIB": [prefix / "Library" / "share" / "proj", prefix / "share" / "proj"],
        "PROJ_DATA": [prefix / "Library" / "share" / "proj", prefix / "share" / "proj"],
    }
    applied: dict[str, str] = {}
    for var, paths in candidates.items():
        cur = os.environ.get(var)
        if cur and Path(cur).is_dir():
            applied[var] = cur
            continue
        for p in paths:
            if p.is_dir():
                os.environ[var] = str(p)
                applied[var] = str(p)
                break
    return applied


GDAL_ENV = fix_gdal_env()


def disable_pam() -> None:
    """
    关掉 GDAL 的 PAM 旁挂文件（.aux.xml）。

    rioxarray 用 masked=True 打开栅格时，GDAL 会写一个 <name>.aux.xml 缓存
    直方图和统计量 —— 实测 3.4 MB 的 tif 配了 48 KB 的 aux，纯冗余。

    我们的产物 CRS/变换都直接写在文件里，不依赖 PAM；关掉它，
    交付目录就只剩真正的产物。
    """
    os.environ["GDAL_PAM_ENABLED"] = "NO"


disable_pam()


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------

DEFAULT_CONFIG = {
    "gee": {
        "project": "",
        "credentials": "",      # 留空 = 用默认 ~/.config/earthengine/credentials
        "proxy": "http://127.0.0.1:7897",
        "use_proxy": True,
    },
    "gdal": {
        "bin_dir": "",          # GDAL CLI 目录（可选；留空则用 conda 自带的）
    },
    "server": {
        "host": "127.0.0.1",
        "port": 6531,
    },
}


def load_config() -> dict:
    """读 geocode.json，与 DEFAULT_CONFIG 深合并。文件不存在则返回默认值。"""
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))  # deep copy
    if CONFIG_PATH.exists():
        raw = CONFIG_PATH.read_text(encoding="utf-8-sig")  # 容忍 BOM
        try:
            user = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"{CONFIG_PATH} 不是合法 JSON：{e}") from e
        _deep_merge(cfg, user)
    return cfg


def _deep_merge(base: dict, over: dict) -> None:
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(base.get(k), dict):
            _deep_merge(base[k], v)
        else:
            base[k] = v


def save_config(cfg: dict) -> None:
    CONFIG_PATH.write_text(
        json.dumps(cfg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )


def ensure_config_template() -> bool:
    """首次运行时写一份带默认值的配置。已存在则不覆盖。返回是否新建。"""
    if CONFIG_PATH.exists():
        return False
    save_config(DEFAULT_CONFIG)
    return True


# ---------------------------------------------------------------------------
# GEE
# ---------------------------------------------------------------------------

def gee_project() -> str:
    """GEE 项目 ID。优先级：环境变量 > geocode.json。"""
    return (os.environ.get("GEE_PROJECT") or load_config()["gee"]["project"] or "").strip()


def gee_credentials_path() -> Path:
    """
    GEE 凭据路径。

    注意：earthengine-api 在**所有平台**（含 Windows）都用
    `~/.config/earthengine/credentials`，不是 `%APPDATA%`。
    所以这里不猜路径 —— 直接问库；问不到才按约定拼。
    这样库改了实现我们也不会跟着错。
    """
    cfg = load_config()["gee"]
    if cfg.get("credentials"):
        return Path(cfg["credentials"]).expanduser()
    try:
        from ee import oauth
        return Path(oauth.get_credentials_path())
    except Exception:
        return Path.home() / ".config" / "earthengine" / "credentials"


def gee_credentials_present() -> bool:
    return gee_credentials_path().is_file()


def apply_proxy_env() -> str | None:
    """
    按配置注入 HTTPS_PROXY / HTTP_PROXY 并返回生效的代理地址。
    已在环境里设过的代理优先（用户显式设的说了算）。
    """
    cfg = load_config()["gee"]
    existing = os.environ.get("HTTPS_PROXY") or os.environ.get("https_proxy")
    if existing:
        return existing
    if not cfg.get("use_proxy"):
        return None
    proxy = (cfg.get("proxy") or "").strip()
    if not proxy:
        return None
    for var in ("HTTP_PROXY", "HTTPS_PROXY"):
        os.environ[var] = proxy
    os.environ.setdefault("NO_PROXY", "127.0.0.1,localhost,::1")
    os.environ.setdefault("no_proxy", "127.0.0.1,localhost,::1")
    return proxy


def init_ee(project: str | None = None, quiet: bool = True):
    """
    初始化 earthengine-api。返回 (ee 模块, 项目 ID)。
    不做浏览器 OAuth —— 认证必须先在终端跑 `earthengine authenticate`。
    """
    import ee  # 延迟导入：没装 ee 的代码路径不该因此失败

    apply_proxy_env()
    from . import geoenv as _self  # noqa  (保持模块自引用的一致性)

    pid = (project or _self.gee_project()).strip()
    if not pid:
        raise RuntimeError(
            "GEE 项目 ID 未配置。两种设法二选一：\n"
            f"  1. 写进 {CONFIG_PATH} 的 gee.project\n"
            "  2. 设环境变量 GEE_PROJECT\n"
            "项目 ID 在 https://code.earthengine.google.com 页面顶部可以看到。"
        )
    if not gee_credentials_present():
        raise RuntimeError(
            "GEE 凭据缺失。先在终端跑一次：\n"
            "  earthengine authenticate\n"
            f"（凭据默认落在 {gee_credentials_path()}）"
        )
    ee.Initialize(project=pid)
    return ee, pid


# ---------------------------------------------------------------------------
# 运行时信息
# ---------------------------------------------------------------------------

def python_exe() -> Path:
    return Path(sys.executable)


def env_name() -> str:
    return Path(sys.prefix).name


def port_open(host: str, port: int, timeout: float = 0.4) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        return s.connect_ex((host, port)) == 0


def gdal_bin() -> Path | None:
    """定位 GDAL CLI 目录。优先 conda 前缀，其次配置里的覆盖。"""
    override = load_config()["gdal"].get("bin_dir")
    if override and Path(override).is_dir():
        return Path(override)
    cand = Path(sys.prefix) / "Library" / "bin"
    if (cand / "gdalinfo.exe").exists() or (cand / "gdalinfo").exists():
        return cand
    which = shutil.which("gdalinfo")
    return Path(which).parent if which else None


def describe() -> dict:
    """给 UI / CLI 用的一份环境快照。"""
    return {
        "root": str(ROOT),
        "python": str(python_exe()),
        "env": env_name(),
        "gdal_env": GDAL_ENV,
        "gdal_bin": str(gdal_bin()) if gdal_bin() else None,
        "gee_project": gee_project() or None,
        "gee_credentials": str(gee_credentials_path()),
        "gee_credentials_present": gee_credentials_present(),
        "config": str(CONFIG_PATH),
        "config_exists": CONFIG_PATH.exists(),
    }


if __name__ == "__main__":
    print(json.dumps(describe(), indent=2, ensure_ascii=False))
