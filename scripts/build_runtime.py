"""Build a self-contained 2FAuto runtime executable for the host platform."""

import os
import argparse
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def build(*, onefile: bool = False, output_name: str = "2fauto-runtime") -> Path:
    ui_dir = ROOT / "build" / "packaged-ui"
    if not (ui_dir / "index.html").is_file():
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_packaged_ui.py")],
                       cwd=ROOT, check=True)

    dist_dir = ROOT / "build" / "runtime"
    command = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm", "--onefile" if onefile else "--onedir", "--name", output_name,
        "--distpath", str(dist_dir),
        "--workpath", str(ROOT / "build" / "pyinstaller-work"),
        "--specpath", str(ROOT / "build" / "pyinstaller-spec"),
        "--paths", str(ROOT),
        "--hidden-import", "app.main",
        "--collect-submodules", "app",
        "--collect-submodules", "uvicorn",
    ]
    for source, destination in (
        (ui_dir, "packaged-ui"),
        (ROOT / "app" / "static", "app/static"),
        (ROOT / "app" / "templates", "app/templates"),
    ):
        command += ["--add-data", f"{source}{os.pathsep}{destination}"]
    command.append(str(ROOT / "scripts" / "runtime_entry.py"))
    subprocess.run(command, cwd=ROOT, check=True)
    filename = output_name + (".exe" if os.name == "nt" else "")
    executable = dist_dir / filename if onefile else dist_dir / output_name / filename
    if not executable.is_file():
        raise RuntimeError(f"Packaged runtime was not produced: {executable}")
    return executable


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--onefile", action="store_true", help="Build the desktop sidecar")
    parser.add_argument("--name", default="2fauto-runtime")
    arguments = parser.parse_args()
    print(build(onefile=arguments.onefile, output_name=arguments.name))
