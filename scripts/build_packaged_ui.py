"""Build a client-only React bundle for the installed 2FAuto origin."""

import argparse
import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "Secure Access Hub"


def build(output: Path) -> None:
    env = os.environ.copy()
    env["TWOFAUTO_PACKAGED_UI"] = "1"
    subprocess.run(["bun", "run", "build"], cwd=FRONTEND, env=env, check=True)

    public = FRONTEND / ".output" / "public"
    shell = public / "_shell.html"
    if not shell.is_file():
        raise RuntimeError(f"Static shell was not generated: {shell}")
    if not (public / "assets").is_dir():
        raise RuntimeError("Static build has no assets directory")

    output.mkdir(parents=True, exist_ok=True)
    shutil.copytree(public, output, dirs_exist_ok=True)
    shutil.copy2(shell, output / "index.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "build" / "packaged-ui")
    arguments = parser.parse_args()
    build(arguments.output)
