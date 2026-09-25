"""Sign and notarize macOS release artifacts using keychain identities."""

import argparse
import subprocess
import sys
from pathlib import Path


def run(command: list[str]) -> None:
    subprocess.run(command, check=True)


def sign_release(server_runtime: Path, server_pkg: Path, desktop_app: Path, desktop_dmg: Path,
                 app_identity: str, installer_identity: str, notary_profile: str) -> Path:
    if sys.platform != "darwin":
        raise RuntimeError("macOS signing requires a Mac")
    if not all((app_identity, installer_identity, notary_profile)):
        raise RuntimeError("Signing identities and a notarytool keychain profile are required")
    run(["codesign", "--force", "--options", "runtime", "--timestamp", "--sign",
         app_identity, str(server_runtime)])
    run(["codesign", "--verify", "--verbose", str(server_runtime)])
    run([sys.executable, str(Path(__file__).with_name("build_server.py")), "--use-built"])
    # Tauri must build the .app and .dmg with APPLE_SIGNING_IDENTITY set;
    # signing the .app after the .dmg is made would leave an unsigned DMG payload.
    run(["codesign", "--verify", "--deep", "--verbose", str(desktop_app)])
    signed_pkg = server_pkg.with_name(server_pkg.stem + "-signed.pkg")
    run(["productsign", "--sign", installer_identity, str(server_pkg), str(signed_pkg)])
    run(["pkgutil", "--check-signature", str(signed_pkg)])
    for artifact in (signed_pkg, desktop_dmg):
        run(["xcrun", "notarytool", "submit", str(artifact), "--keychain-profile",
             notary_profile, "--wait"])
        run(["xcrun", "stapler", "staple", str(artifact)])
    run(["spctl", "--assess", "--type", "install", str(signed_pkg)])
    run(["spctl", "--assess", "--type", "open", str(desktop_dmg)])
    return signed_pkg


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    for name in ("server-runtime", "server-pkg", "desktop-app", "desktop-dmg"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--app-identity", required=True)
    parser.add_argument("--installer-identity", required=True)
    parser.add_argument("--notary-profile", required=True)
    options = parser.parse_args()
    print(sign_release(options.server_runtime, options.server_pkg, options.desktop_app,
                       options.desktop_dmg, options.app_identity,
                       options.installer_identity, options.notary_profile))
