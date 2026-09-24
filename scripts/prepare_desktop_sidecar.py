"""Copy the frozen backend to Tauri's platform-qualified sidecar path."""

import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def prepare() -> Path:
    target = subprocess.check_output(["rustc", "-vV"], text=True).split("host: ")[1].splitlines()[0]
    suffix = ".exe" if sys.platform == "win32" else ""
    runtime = ROOT / "build" / "runtime" / f"twofauto-runtime{suffix}"
    if not runtime.is_file():
        raise RuntimeError("Build the onefile twofauto-runtime first")
    destination = ROOT / "desktop" / "src-tauri" / "binaries" / f"twofauto-runtime-{target}{suffix}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime, destination)
    return destination


if __name__ == "__main__":
    print(prepare())
