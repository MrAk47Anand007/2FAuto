"""Build Linux Server .deb and .rpm from the host's frozen executable."""

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
BUILD = ROOT / "build" / "linux-server"


def build(*, use_built: bool = False) -> tuple[Path, Path]:
    if sys.platform != "linux":
        raise RuntimeError("Linux packages must be built on Linux")
    if not use_built:
        subprocess.run([sys.executable, str(ROOT / "scripts" / "build_runtime.py"),
                        "--onefile", "--name", "twofauto-runtime"], cwd=ROOT, check=True)
    runtime = ROOT / "build" / "runtime" / "twofauto-runtime"
    if not runtime.is_file():
        raise RuntimeError("Frozen runtime is missing")
    root = BUILD / "deb-root"
    binary_dir = root / "usr" / "lib" / "2fauto"
    service_dir = root / "usr" / "lib" / "systemd" / "system"
    control_dir = root / "DEBIAN"
    for directory in (binary_dir, service_dir, control_dir):
        directory.mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime, binary_dir / "twofauto-runtime")
    shutil.copy2(HERE / "twofauto.service", service_dir / "twofauto.service")
    for source in (HERE / "debian").iterdir():
        target = control_dir / source.name
        shutil.copy2(source, target)
        if source.name != "control":
            target.chmod(0o755)
    (binary_dir / "twofauto-runtime").chmod(0o755)
    deb = BUILD / "twofauto-server_0.1.0_amd64.deb"
    subprocess.run(["dpkg-deb", "--build", str(root), str(deb)], check=True)

    topdir = BUILD / "rpmbuild"
    for directory in ("BUILD", "RPMS", "SOURCES", "SPECS", "SRPMS", "BUILDROOT"):
        (topdir / directory).mkdir(parents=True, exist_ok=True)
    shutil.copy2(runtime, topdir / "SOURCES" / "twofauto-runtime")
    shutil.copy2(HERE / "twofauto.service", topdir / "SOURCES" / "twofauto.service")
    spec = (HERE / "twofauto-server.spec").read_text(encoding="utf-8")
    spec_path = topdir / "SPECS" / "twofauto-server.spec"
    spec_path.write_text(spec, encoding="utf-8")
    subprocess.run(["rpmbuild", "-bb", "--define", f"_topdir {topdir}", str(spec_path)], check=True)
    rpm = next((topdir / "RPMS").rglob("twofauto-server-*.rpm"))
    return deb, rpm


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--use-built", action="store_true")
    args = parser.parse_args()
    print(*build(use_built=args.use_built), sep="\n")
