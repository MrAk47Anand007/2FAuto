"""Build a macOS Server installer package on a macOS host."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = ROOT / "build" / "macos-server"


def build(*, use_built: bool = False) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("macOS packages must be built on macOS")
    if not use_built:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_runtime.py"),
                        "--onefile", "--name", "twofauto-runtime"], cwd=ROOT, check=True)
    runtime = ROOT / "build" / "runtime" / "twofauto-runtime"
    if not runtime.is_file():
        raise RuntimeError("Frozen runtime is missing")
    root = BUILD / "pkg-root"
    bin_dir = root / "usr" / "local" / "lib" / "2fauto"
    daemon_dir = root / "Library" / "LaunchDaemons"
    bin_dir.mkdir(parents=True, exist_ok=True)
    daemon_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime, bin_dir / "twofauto-runtime")
    shutil.copy2(HERE / "com.twofauto.server.plist", daemon_dir / "com.twofauto.server.plist")
    (bin_dir / "twofauto-runtime").chmod(0o755)
    (daemon_dir / "com.twofauto.server.plist").chmod(0o644)
    scripts = HERE / "scripts"
    (scripts / "postinstall").chmod(0o755)
    output = BUILD / "2FAuto-Server-0.1.0.pkg"
    subprocess.run(["pkgbuild", "--root", str(root), "--scripts", str(scripts),
                    "--identifier", "com.twofauto.server", "--version", "0.1.0",
                    "--install-location", "/", str(output)], check=True)
    return output


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-built", action="store_true")
    args = parser.parse_args()
    print(build(use_built=args.use_built))
