"""
环境探测与失败分类。

设计原则（照搬 GeoCode 的教训，但去掉它对 GUI 用户的层层兜底）：

1. **分级探测**：probe_env() 零网络、毫秒级，随时可调；
   网络探测显式开启（network=True），因为它要花几百毫秒到几秒。

2. **失败必须可执行**：每个失败码配一段 reason，写清楚症状 → 原因 → 具体命令。
   这是给 agent（我）和给用户看同一份文本 —— 不写"出错了"，写"怎么办"。

3. **一次探测，多处消费**：dockpane 的状态栏、MCP 的 gee_status、CLI，
   都读同一个 probe 结果，不各自实现一套。
"""

from __future__ import annotations

import importlib
import json
import socket
import ssl
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from . import geoenv

# ---------------------------------------------------------------------------
# 失败码
# ---------------------------------------------------------------------------

# 环境类
ENV_PACKAGE_MISSING = "package-missing"
ENV_GDAL_MISSING = "gdal-missing"

# GEE 配置类
GEE_CREDENTIALS_MISSING = "gee-credentials-missing"
GEE_PROJECT_MISSING = "gee-project-missing"
GEE_PYTHON_NOT_FOUND = "gee-python-not-found"

# GEE 运行类（需联网）
GEE_NETWORK_UNREACHABLE = "gee-network-unreachable"
GEE_PROXY_DEAD = "gee-proxy-dead"
GEE_AUTH_INVALID = "gee-auth-invalid"
GEE_API_DISABLED = "gee-api-disabled"
GEE_PERMISSION_DENIED = "gee-permission-denied"
GEE_UNKNOWN = "gee-unknown"

GEE_HOSTS = ("earthengine.googleapis.com", "code.earthengine.google.com")


@dataclass
class Check:
    ok: bool
    code: str = ""
    reason: str = ""
    value: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {"ok": self.ok, "code": self.code, "reason": self.reason, "value": self.value}


# ---------------------------------------------------------------------------
# 必需包
# ---------------------------------------------------------------------------

REQUIRED_PACKAGES: dict[str, str] = {
    "ee": "earthengine-api",     # GEE 核心 API
    "xee": "xee",                # 出口 array
    "geedim": "geedim",          # 出口 file（按需直下）
    "xarray": "xarray",          # 数组
    "rioxarray": "rioxarray",    # 栅格 IO
    "geopandas": "geopandas",    # 矢量 IO
    "rasterio": "rasterio",      # 栅格底层
    "shapely": "shapely",        # 几何
    "pyproj": "pyproj",          # CRS
}

OPTIONAL_PACKAGES: dict[str, str] = {
    "geemap": "geemap",          # 交互地图（出口 map 的 notebook 形态）
    "dask": "dask",              # xee 分块调度
    "matplotlib": "matplotlib",  # 静态出图
    "fiona": "fiona",            # geopandas 的旧后端（pyogrio 是默认）
}


# ---------------------------------------------------------------------------
# 探测 1：零网络环境
# ---------------------------------------------------------------------------

def probe_packages() -> Check:
    missing, present = [], {}
    for mod, pkg in REQUIRED_PACKAGES.items():
        try:
            m = importlib.import_module(mod)
            present[mod] = getattr(m, "__version__", "?")
        except Exception:
            missing.append(pkg)
    if missing:
        envname = geoenv.env_name()
        return Check(
            False, ENV_PACKAGE_MISSING,
            "GEE 运行时缺少 Python 包：" + ", ".join(missing) + "\n"
            f"  安装（当前环境 {envname}）：\n"
            f"    conda install -n {envname} -c conda-forge " + " ".join(missing) + "\n"
            "  注意：geemap 在 conda-forge 上依赖较重，如只需地图预览可稍后再装。",
            {"missing": missing, "present": present},
        )
    optional = {}
    for mod, pkg in OPTIONAL_PACKAGES.items():
        try:
            m = importlib.import_module(mod)
            optional[mod] = getattr(m, "__version__", "?")
        except Exception:
            optional[mod] = None
    return Check(True, value={"required": present, "optional": optional})


def probe_gdal() -> Check:
    try:
        from osgeo import gdal
    except Exception:
        band = geoenv.gdal_bin()
        return Check(
            False, ENV_GDAL_MISSING,
            "Python 侧无法 import osgeo.gdal。\n"
            f"  说明：gdal_bin 探测结果 = {band}\n"
            "  修法：conda install -c conda-forge gdal（不要混用 pip 的 gdal）。",
            {"gdal_bin": str(band) if band else None},
        )
    # Windows 上 GDAL_DATA 缺失会让 CRS 解析降级 —— geoenv 已经修过
    from . import geoenv as _g
    return Check(True, value={
        "version": gdal.VersionInfo("RELEASE_NAME"),
        "gdal_data": _g.GDAL_ENV.get("GDAL_DATA"),
        "proj_data": _g.GDAL_ENV.get("PROJ_DATA"),
    })


def probe_config() -> Check:
    cfg = geoenv.load_config()
    return Check(True, value={
        "config_path": str(geoenv.CONFIG_PATH),
        "config_exists": geoenv.CONFIG_PATH.exists(),
        "gee_project": geoenv.gee_project() or None,
        "use_proxy": cfg["gee"].get("use_proxy"),
        "proxy": cfg["gee"].get("proxy"),
        "server_port": cfg["server"].get("port"),
    })


def probe_env() -> dict:
    """零网络全量快照。dockpane 刷新状态栏用这个。"""
    return {
        "when": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "geoenv": geoenv.describe(),
        "packages": probe_packages().as_dict(),
        "gdal": probe_gdal().as_dict(),
        "config": probe_config().as_dict(),
    }


# ---------------------------------------------------------------------------
# 探测 2：GEE 配置（零网络）
# ---------------------------------------------------------------------------

def check_gee_local() -> Check:
    """
    只查配置和凭据，不联网、不 init。
    RunGeeScript 前的第一道闸 —— 失败要给人能直接粘贴的命令。
    """
    pid = geoenv.gee_project()
    if not pid:
        return Check(False, GEE_PROJECT_MISSING,
            "GEE 项目 ID 未配置。\n"
            "  项目 ID 在 https://code.earthengine.google.com 页面顶部可见（形如 my-project-123456）。\n"
            f"  两种设法二选一：\n"
            f"    1. 写进 {geoenv.CONFIG_PATH} 的 gee.project\n"
            f"    2. 设环境变量 GEE_PROJECT",
        )

    cred = geoenv.gee_credentials_path()
    if not cred.is_file():
        return Check(False, GEE_CREDENTIALS_MISSING,
            "GEE 凭据缺失，无法调用任何 GEE 接口。\n"
            f"  期望位置：{cred}\n"
            "  在能打开浏览器的终端里跑一次（只需一次）：\n"
            "    earthengine authenticate\n"
            f"  当前环境的 earthengine 入口：{sys.prefix}\\Scripts\\earthengine.exe",
            {"project": pid, "credentials": str(cred)},
        )

    return Check(True, value={"project": pid, "credentials": str(cred)})


# ---------------------------------------------------------------------------
# 探测 3：网络（需联网，显式开启）
# ---------------------------------------------------------------------------

def _http_probe(url: str, proxy: str | None, timeout: float = 6.0) -> tuple[bool, str]:
    """返回 (是否通, 说明)。任何 HTTP 响应都算通 —— 我们要的是可达性不是状态码。"""
    # SSL context 必须挂在 HTTPSHandler 上 —— OpenerDirector.open() 不接 context 参数
    ctx = ssl.create_default_context()
    handlers = [urllib.request.HTTPSHandler(context=ctx)]
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    else:
        handlers.append(urllib.request.ProxyHandler({}))  # 强制不走代理
    opener = urllib.request.build_opener(*handlers)
    try:
        req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "geocode-preflight/1.0"})
        with opener.open(req, timeout=timeout) as r:
            return True, f"HTTP {r.status}"
    except urllib.error.HTTPError as e:
        return True, f"HTTP {e.code}"
    except urllib.error.URLError as e:
        return False, str(getattr(e, "reason", e))
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def check_gee_network(*, proxy: str | None = None, timeout: float = 6.0) -> Check:
    """
    探测 GEE 端点可达性。

    本机开着 TUN 模式（Clash），所以「不走代理」也不是真裸连 ——
    两路都测，把结果并列报告，让调用方自己选，不替用户下结论。
    """
    cfg = geoenv.load_config()["gee"]
    configured = (proxy if proxy is not None else
                  (cfg.get("proxy") if cfg.get("use_proxy") else None))

    results: dict[str, Any] = {}
    any_ok = False
    for host in GEE_HOSTS:
        url = f"https://{host}/"
        via_proxy = _http_probe(url, configured, timeout)
        direct = _http_probe(url, None, timeout)
        results[host] = {
            "via_proxy": {"ok": via_proxy[0], "detail": via_proxy[1], "proxy": configured},
            "direct": {"ok": direct[0], "detail": direct[1]},
        }
        if via_proxy[0] or direct[0]:
            any_ok = True

    if any_ok:
        return Check(True, value={"hosts": results, "proxy": configured})

    # 全不通 —— 区分「代理挂了」和「真没网」
    if configured:
        proxy_host, proxy_port = _split_hostport(configured)
        if proxy_host and not geoenv.port_open(proxy_host, proxy_port):
            return Check(False, GEE_PROXY_DEAD,
                f"配置的代理不可达：{configured}\n"
                "  说明：端口没在监听。Clash 可能没启动，或 mixed-port 不是这个号。\n"
                "  检查：\n"
                "    - Clash Verge 是否在运行\n"
                "    - 设置里的 mixed-port 是否与 geocode.json 的 gee.proxy 一致\n"
                f"  （已经确认 {proxy_host}:{proxy_port} 连不上）",
                {"hosts": results, "proxy": configured},
            )
    return Check(False, GEE_NETWORK_UNREACHABLE,
        "GEE 端点不可达（代理直连两路都失败）。\n"
        f"  测试目标：{', '.join(GEE_HOSTS)}\n"
        + (f"  用了代理：{configured}\n" if configured else "  未配置代理。\n")
        + "  若在需要代理的网络下，检查 geocode.json 的 gee.use_proxy / gee.proxy。",
        {"hosts": results, "proxy": configured},
    )


def _split_hostport(proxy: str) -> tuple[str, int]:
    s = proxy.split("://", 1)[-1].rstrip("/")
    if "@" in s:
        s = s.rsplit("@", 1)[-1]
    if ":" not in s:
        return s, 80
    h, p = s.rsplit(":", 1)
    try:
        return h, int(p)
    except ValueError:
        return h, 80


# ---------------------------------------------------------------------------
# 探测 4：GEE 运行时（需联网 + 凭据，最重）
# ---------------------------------------------------------------------------

def classify_gee_error(exc: BaseException) -> tuple[str, str]:
    """把 ee 抛出的异常翻成 (失败码, 可执行提示)。"""
    msg = str(exc)
    low = msg.lower()

    if "project" in low and ("not found" in low or "invalid" in low or "permission" in low):
        return GEE_PERMISSION_DENIED, (
            "GEE 拒绝了这个项目 ID。常见三种原因：\n"
            "  1. 项目 ID 拼错（注意不是项目『名称』，是 ID）\n"
            "  2. 该 GCP 项目没有启用 Earth Engine API：\n"
            "     https://console.cloud.google.com/apis/library/earthengine.googleapis.com\n"
            "  3. 你的账号没有被授权访问该项目"
        )
    if "has not been used in project" in low or "is disabled" in low or "api_disabled" in low:
        return GEE_API_DISABLED, (
            "Earth Engine API 在该 GCP 项目上未启用。\n"
            "  启用：https://console.cloud.google.com/apis/library/earthengine.googleapis.com\n"
            "  （选对项目，然后点『启用』）"
        )
    if "credentials" in low or "authenticate" in low or "refresh" in low or "token" in low:
        return GEE_AUTH_INVALID, (
            "GEE 凭据无效或已过期。\n"
            "  重新认证（只需一次，会打开浏览器）：\n"
            "    earthengine authenticate"
        )
    if any(t in low for t in ("timeout", "timed out", "connection", "resolve", "ssl", "proxy")):
        return GEE_NETWORK_UNREACHABLE, (
            "连不上 GEE 服务。\n"
            "  检查网络 / 代理，或跑 preflight.check_gee_network() 看两路探测结果。"
        )
    if "quota" in low or "too many requests" in low or "429" in low:
        return GEE_UNKNOWN, (
            "触发 GEE 配额限制。\n"
            "  非商业档位：Community 150 EECU-小时/月，Contributor 1000。\n"
            "  超额不会断供，会进入降并行度模式，下月 1 号（太平洋时间）重置。"
        )
    return GEE_UNKNOWN, f"未归类的 GEE 错误：{msg}"


def check_gee_runtime() -> Check:
    """
    真正初始化 ee 并做一次极轻的服务端往返。
    比 check_gee_local 重，但能验出「凭据在、项目没开 API」这类只有联网才暴露的问题。
    """
    local = check_gee_local()
    if not local.ok:
        return local

    try:
        ee, pid = geoenv.init_ee()
    except Exception as e:
        code, hint = classify_gee_error(e)
        return Check(False, code, hint, {"project": local.value.get("project"), "raw": str(e)})

    try:
        # 最轻的服务端调用：拿一个常量影像的波段名
        version = getattr(ee, "__version__", "?")
        ee.Number(1).getInfo()
    except Exception as e:
        code, hint = classify_gee_error(e)
        return Check(False, code, hint, {"project": pid, "raw": str(e)})
    finally:
        # ee 没有 teardown 概念；这里只是标出 init 已完成
        pass

    return Check(True, value={"project": pid, "ee_version": version})


# ---------------------------------------------------------------------------
# 汇总
# ---------------------------------------------------------------------------

def probe_all(*, network: bool = False) -> dict:
    """
    一次拿全。network=True 时才做联网探测（默认关 —— 状态栏刷新要快）。
    """
    out = {
        "env": probe_env(),
        "gee_local": check_gee_local().as_dict(),
    }
    if network:
        out["gee_network"] = check_gee_network().as_dict()
        out["gee_runtime"] = check_gee_runtime().as_dict()
    return out


def summarize(res: dict) -> str:
    """一行式摘要，给 CLI / dockpane 状态栏用。"""
    bits = []
    g = res.get("gee_local", {})
    bits.append("GEE:" + ("就绪" if g.get("ok") else g.get("code", "未知")))
    p = res.get("env", {}).get("packages", {})
    bits.append("包:" + ("全" if p.get("ok") else "缺"))
    d = res.get("env", {}).get("gdal", {})
    bits.append("GDAL:" + (d.get("value", {}).get("version") or "缺"))
    if "gee_network" in res:
        bits.append("网络:" + ("通" if res["gee_network"].get("ok") else res["gee_network"].get("code")))
    return " | ".join(bits)


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser(description="GeoCode 环境探测")
    ap.add_argument("--network", action="store_true", help="包含联网探测（较慢）")
    ap.add_argument("--json", action="store_true", help="输出 JSON")
    a = ap.parse_args()

    res = probe_all(network=a.network)
    if a.json:
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print(summarize(res))
        for section in ("gee_local", "gee_network", "gee_runtime"):
            if section in res and not res[section].get("ok"):
                print(f"\n[{section}] {res[section]['code']}")
                for line in res[section]["reason"].splitlines():
                    print("  " + line)
