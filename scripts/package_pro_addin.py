# -*- coding: utf-8 -*-
"""ArcGIS Pro add-in 打包与部署（change C9 p1b-arcgis-addin）。

用法（在仓库根，任选其一）：
  python scripts/package_pro_addin.py build    # dotnet build + 打包 zip
  python scripts/package_pro_addin.py deploy   # 拷贝 zip 到 MyDocuments/ArcGIS/AddIns/ArcGISPro
  python scripts/package_pro_addin.py all      # build + deploy

打包布局（§9.4 标准布局）：zip 根 Config.daml + Install/*.dll。
部署目标：[MyDocuments]\\ArcGIS\\AddIns\\ArcGISPro（目录不存在则创建）。

扩展名必须为 .esriAddInX（末尾带 X）：ArcGIS Pro 3.7 的 add-in 扫描器只认
.esriAddInX / .proConfigX（见 ArcGIS.Desktop.Framework.Registry.Script.cs 与
CustomizationRegistry.cs）。ArcMap/Desktop 时代的 .esriAddIn 不被 Pro 读取，
文件会被静默忽略、AssemblyCache 永不落盘。
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRO_DIR = ROOT / "Pro"
PROJ = PRO_DIR / "GeoCodePro.csproj"
BUILD_DIR = PRO_DIR / "bin" / "Release" / "net10.0-windows"
ZIP_PATH = PRO_DIR / "GeoCodePro.addin.zip"
ADDIN_DIR = Path(os.path.expandvars(r"%USERPROFILE%\Documents")) / "ArcGIS" / "AddIns" / "ArcGISPro"
# Pro 3.7 只识别 .esriAddInX（末尾带 X）；.esriAddIn 会被静默忽略。
ADDIN_NAME = "GeoCodePro-MCP.esriAddInX"


def build() -> Path:
    """dotnet build -c Release，零错误退出；失败给可读报错。"""
    print(f"[build] dotnet build {PROJ.name} -c Release")
    r = subprocess.run(
        ["dotnet", "build", str(PROJ), "-c", "Release"],
        cwd=str(ROOT), capture_output=True, text=True, shell=False,
        encoding="utf-8", errors="replace",
    )
    out = (r.stdout or "") + (r.stderr or "")
    # MSBuild 本地化输出可能是 GBK 乱码，但退出码是权威信号
    if r.returncode != 0:
        sys.stderr.write(out[-4000:])
        raise SystemExit(f"[build] 失败（退出码 {r.returncode}）——见上方构建输出")
    print("[build] 成功")
    return package()


def package() -> Path:
    """标准布局打包：zip 根 Config.daml + Install/*.dll，输出 .esriAddInX。"""
    dlls = sorted(BUILD_DIR.glob("*.dll"))
    if not dlls:
        raise SystemExit(f"[package] 找不到构建产物：{BUILD_DIR}")
    ADDIN_DIR.parent.mkdir(parents=True, exist_ok=True)
    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as z:
        z.write(PRO_DIR / "Config.daml", "Config.daml")
        for dll in dlls:
            z.write(dll, f"Install/{dll.name}")
    print(f"[package] {ZIP_PATH}（Config.daml + Install/{len(dlls)} dll）")
    return ZIP_PATH


def deploy(zip_path: Path | None = None) -> Path:
    """拷贝 zip 到 MyDocuments\\ArcGIS\\AddIns\\ArcGISPro，落为 .esriAddInX。"""
    zp = zip_path or ZIP_PATH
    if not zp.exists():
        raise SystemExit(f"[deploy] zip 不存在：{zp}——先 build")
    ADDIN_DIR.mkdir(parents=True, exist_ok=True)
    dest = ADDIN_DIR / ADDIN_NAME
    shutil.copy2(zp, dest)
    # 清理历史上部署过的错误扩展名（.esriAddIn），避免 Pro 混淆
    for legacy in ("GeoCodePro-MCP.esriAddIn", "Skel.addin.esriAddIn"):
        stale = ADDIN_DIR / legacy
        if stale.exists():
            stale.unlink()
            print(f"[deploy] 移除旧扩展名文件：{stale.name}")
    print(f"[deploy] {dest}")
    return dest


def main() -> None:
    ap = argparse.ArgumentParser(description="GeoCode Pro add-in 打包与部署")
    ap.add_argument("cmd", choices=["build", "deploy", "all"], nargs="?", default="all")
    args = ap.parse_args()
    if args.cmd in ("build", "all"):
        build()
    if args.cmd in ("deploy", "all"):
        deploy()


if __name__ == "__main__":
    main()
