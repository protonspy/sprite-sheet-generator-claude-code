"""Rebuild `vendor/pixel-snapper.wasm` from pinned upstream source.

Clones spritefusion-pixel-snapper at the pinned commit, applies `upstream.patch`, builds
the thin `ssc-pixel-snapper` wrapper for `wasm32-wasip1`, and copies the module and the
upstream LICENSE into `vendor/`. See `wasm/README.md` for why the patch exists.

    python wasm/build.py
    python wasm/build.py --check    # build into a temp dir and diff against vendor/
"""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

UPSTREAM_URL = "https://github.com/Hugo-Dz/spritefusion-pixel-snapper.git"
UPSTREAM_COMMIT = "ae20461f60fb39e75d15f184bab1ebec1219511c"

WASM_DIR = Path(__file__).resolve().parent
REPO = WASM_DIR.parent
BUILD_DIR = WASM_DIR / ".build"
UPSTREAM_DIR = BUILD_DIR / "upstream"
WRAPPER_DIR = WASM_DIR / "pixel-snapper"
PATCH = WASM_DIR / "upstream.patch"
ARTIFACT = WRAPPER_DIR / "target/wasm32-wasip1/release/ssc_pixel_snapper.wasm"
VENDOR_WASM = REPO / "vendor/pixel-snapper.wasm"
VENDOR_LICENSE = REPO / "vendor/LICENSE"
VENDOR_DIGEST = REPO / "vendor/pixel-snapper.wasm.sha256"


def run(cmd: list[str], cwd: Path, env: dict[str, str] | None = None) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, cwd=cwd, check=True, env=env)


def build_env() -> dict[str, str]:
    """rustc bakes source paths into panic messages, so the checkout location would
    otherwise change the bytes. Remap the two paths that vary between machines; what
    remains is the toolchain version, which `--check` cannot paper over."""
    cargo_home = Path(os.environ.get("CARGO_HOME", Path.home() / ".cargo")).resolve()
    env = dict(os.environ)
    env["RUSTFLAGS"] = " ".join(
        [
            env.get("RUSTFLAGS", ""),
            f"--remap-path-prefix={cargo_home}=/cargo",
            f"--remap-path-prefix={WASM_DIR}=/wasm",
        ]
    ).strip()
    return env


def remove_tree(root: Path) -> None:
    """git marks objects read-only, and on Windows that makes rmtree fail outright."""
    if not root.exists():
        return
    for path in root.rglob("*"):
        if path.is_file():
            path.chmod(stat.S_IWRITE | stat.S_IREAD)
    shutil.rmtree(root)


def clone_upstream() -> None:
    """Fetch exactly the pinned commit into a clean directory."""
    remove_tree(UPSTREAM_DIR)
    UPSTREAM_DIR.mkdir(parents=True)
    run(["git", "init", "--quiet"], cwd=UPSTREAM_DIR)
    run(["git", "remote", "add", "origin", UPSTREAM_URL], cwd=UPSTREAM_DIR)
    run(["git", "fetch", "--quiet", "--depth", "1", "origin", UPSTREAM_COMMIT], cwd=UPSTREAM_DIR)
    run(["git", "checkout", "--quiet", "FETCH_HEAD"], cwd=UPSTREAM_DIR)


def apply_patch() -> None:
    run(["git", "apply", str(PATCH)], cwd=UPSTREAM_DIR)


def build() -> Path:
    if ARTIFACT.exists():
        ARTIFACT.unlink()
    run(
        ["cargo", "build", "--release", "--target", "wasm32-wasip1"],
        cwd=WRAPPER_DIR,
        env=build_env(),
    )
    if not ARTIFACT.exists():
        raise SystemExit(f"cargo reported success but {ARTIFACT} is missing")
    return ARTIFACT


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="build and report whether vendor/ matches, without writing to it",
    )
    args = parser.parse_args()

    clone_upstream()
    apply_patch()
    artifact = build()

    if args.check:
        with tempfile.TemporaryDirectory() as tmp:
            fresh = Path(tmp) / "pixel-snapper.wasm"
            shutil.copy2(artifact, fresh)
            if not VENDOR_WASM.exists():
                print(f"vendor/pixel-snapper.wasm is missing; built {digest(fresh)}")
                return 2
            if digest(fresh) != digest(VENDOR_WASM):
                print(f"differs: vendored {digest(VENDOR_WASM)}, built {digest(fresh)}")
                return 2
        print(f"vendor/pixel-snapper.wasm matches this build ({digest(VENDOR_WASM)})")
        return 0

    VENDOR_WASM.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(artifact, VENDOR_WASM)
    shutil.copy2(UPSTREAM_DIR / "LICENSE", VENDOR_LICENSE)
    # A 350KB binary diff is not reviewable; a one-line digest diff is. Changing the
    # module without changing this line is what a reviewer can actually catch.
    VENDOR_DIGEST.write_text(f"{digest(VENDOR_WASM)}  pixel-snapper.wasm\n", encoding="utf-8")
    print(f"wrote {VENDOR_WASM} ({VENDOR_WASM.stat().st_size} bytes, sha256 {digest(VENDOR_WASM)})")
    print(f"wrote {VENDOR_LICENSE}")
    print(f"wrote {VENDOR_DIGEST}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
