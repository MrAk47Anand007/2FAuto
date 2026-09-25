"""Build the role-selecting Windows MSI from frozen backend and Tauri shell."""

import argparse
import hashlib
import os
import platform
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
WINDOWS = ROOT / "packaging" / "windows"
BUILD = ROOT / "build" / "windows"
WINSW_URL = "https://github.com/winsw/winsw/releases/download/v2.12.0/WinSW-x64.exe"
WINSW_SHA256 = "05b82d46ad331cc16bdc00de5c6332c1ef818df8ceefcd49c726553209b3a0da"
WINSW_LICENSE_URL = "https://raw.githubusercontent.com/winsw/winsw/v2/LICENSE.txt"
WINSW_LICENSE_SHA256 = "1cdf703c10a70e5973bf3acf2a5eeabe7746237155b92db2034aeae26fdf7802"


def find_wix() -> Path:
    candidates = [
        Path(os.environ["WIX_TOOLS"]) if "WIX_TOOLS" in os.environ else None,
        Path(os.environ.get("LOCALAPPDATA", "")) / "tauri" / "WixTools314",
        Path(os.environ.get("WIX", "")) / "bin",
    ]
    for candidate in candidates:
        if candidate is not None and (candidate / "candle.exe").is_file() and (candidate / "light.exe").is_file():
            return candidate
    raise RuntimeError("WiX v3 tools are required; set WIX_TOOLS to their directory")


def verify_winsw() -> Path:
    BUILD.mkdir(parents=True, exist_ok=True)
    path = BUILD / "WinSW-x64.exe"
    if not path.is_file():
        urllib.request.urlretrieve(WINSW_URL, path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    if digest != WINSW_SHA256:
        raise RuntimeError("The WinSW service wrapper checksum did not match")
    return path


def verify_winsw_license() -> Path:
    path = BUILD / "WinSW-LICENSE.txt"
    if not path.is_file():
        urllib.request.urlretrieve(WINSW_LICENSE_URL, path)
    if hashlib.sha256(path.read_bytes()).hexdigest() != WINSW_LICENSE_SHA256:
        raise RuntimeError("The WinSW license checksum did not match")
    return path


def find_signtool() -> Path:
    command = shutil.which("signtool")
    if command:
        return Path(command)
    kit = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Windows Kits" / "10" / "bin"
    matches = sorted(kit.glob("*/x64/signtool.exe"), reverse=True)
    if matches:
        return matches[0]
    raise RuntimeError("Windows SDK SignTool is required for a signed release")


def sign(path: Path, *, thumbprint: str, tool: Path) -> None:
    if not thumbprint or any(character not in "0123456789abcdefABCDEF" for character in thumbprint):
        raise RuntimeError("Code-signing certificate thumbprint is invalid")
    subprocess.run([str(tool), "sign", "/sha1", thumbprint, "/fd", "SHA256",
                    "/tr", "http://timestamp.digicert.com", "/td", "SHA256", str(path)], check=True)
    subprocess.run([str(tool), "verify", "/pa", "/v", str(path)], check=True)


def build(*, use_built: bool, sign_thumbprint: str | None = None) -> Path:
    if platform.system() != "Windows":
        raise RuntimeError("Windows MSI must be built on Windows")
    if not use_built:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_runtime.py"),
                        "--onefile", "--name", "twofauto-runtime"], cwd=ROOT, check=True)
    runtime = ROOT / "build" / "runtime" / "twofauto-runtime.exe"
    if not runtime.is_file():
        raise RuntimeError("Build the single-file runtime first")
    target = subprocess.check_output(["rustc", "-vV"], text=True).split("host: ")[1].splitlines()[0]
    sidecar = ROOT / "desktop" / "src-tauri" / "binaries" / f"twofauto-runtime-{target}.exe"
    sidecar.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime, sidecar)
    desktop = ROOT / "desktop" / "src-tauri" / "target" / "release" / "twofauto-desktop.exe"
    if not use_built:
        subprocess.run(["bun", "install", "--frozen-lockfile"], cwd=ROOT / "desktop", check=True)
        subprocess.run(["bun", "run", "tauri", "build", "--no-bundle"], cwd=ROOT / "desktop", check=True)
    if not desktop.is_file():
        raise RuntimeError("Build the Tauri desktop executable first")

    winsw = verify_winsw()
    winsw_license = verify_winsw_license()
    signing_tool = find_signtool() if sign_thumbprint else None
    if signing_tool and sign_thumbprint:
        signed_winsw = BUILD / "WinSW-for-package.exe"
        shutil.copy2(winsw, signed_winsw)
        for target_file in (runtime, desktop, signed_winsw):
            sign(target_file, thumbprint=sign_thumbprint, tool=signing_tool)
        winsw = signed_winsw
    wix = find_wix()
    output = BUILD / "2FAuto-0.1.0-x64-roles.msi"
    object_file = BUILD / "2fauto.wixobj"
    definitions = {
        "RuntimeExe": runtime,
        "DesktopExe": desktop,
        "ServiceExe": winsw,
        "ServiceXml": WINDOWS / "twofauto-service.xml",
        "ServiceLicense": winsw_license,
        "LicenseRtf": WINDOWS / "license.rtf",
    }
    subprocess.run([
        str(wix / "candle.exe"), "-arch", "x64",
        *(f"-d{key}={value}" for key, value in definitions.items()),
        "-out", str(object_file), str(WINDOWS / "2fauto.wxs"),
    ], cwd=ROOT, check=True)
    subprocess.run([
        str(wix / "light.exe"), "-ext", "WixUIExtension",
        "-out", str(output), str(object_file),
    ], cwd=ROOT, check=True)
    if signing_tool and sign_thumbprint:
        sign(output, thumbprint=sign_thumbprint, tool=signing_tool)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-built", action="store_true", help="Reuse verified runtime and desktop binaries")
    parser.add_argument("--sign-thumbprint", help="Sign executables and MSI with a certificate already in the Windows store")
    arguments = parser.parse_args()
    print(build(use_built=arguments.use_built, sign_thumbprint=arguments.sign_thumbprint))
