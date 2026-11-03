#!/usr/bin/env python3
"""Package a smoke-tested native build with verifiable upstream provenance."""
import hashlib
import os
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile


def main(target: str, tag: str) -> None:
    if target not in ("darwin-arm64", "linux-x86_64", "windows-x86_64"):
        raise ValueError("unsupported target")
    version = tag.removeprefix("v")
    windows = target.startswith("windows")
    original = Path("upstream/cli/target/ci/agent-browser" + (".exe" if windows else ""))
    if not original.is_file():
        raise FileNotFoundError(original)
    dist = Path("dist")
    dist.mkdir(exist_ok=True)
    asset = f"agent-browser-browse-{target}.tar.gz"
    with tempfile.TemporaryDirectory(prefix="browse-package-") as temp:
        package = Path(temp)
        binary = package / ("agent-browser-browse-native.exe" if windows else "agent-browser-browse-native")
        shutil.copy2(original, binary)
        if target == "darwin-arm64":
            subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(binary)], check=True)
            assert subprocess.check_output(["lipo", "-archs", str(binary)], text=True).strip() == "arm64"
        elif target == "linux-x86_64":
            with binary.open("rb") as stream:
                header = stream.read(20)
            assert header[:5] == b"\x7fELF\x02" and struct.unpack_from("<H", header, 18)[0] == 62
        else:
            with binary.open("rb") as stream:
                assert stream.read(2) == b"MZ"
                stream.seek(0x3c)
                stream.seek(struct.unpack("<I", stream.read(4))[0])
                assert stream.read(4) == b"PE\x00\x00"
                assert struct.unpack("<H", stream.read(2))[0] == 0x8664
        shutil.copyfile("upstream/LICENSE", package / "LICENSE.upstream")
        (package / "UPSTREAM_VERSION").write_text(version + "\n")
        (package / "UPSTREAM_COMMIT").write_text(
            subprocess.check_output(["git", "-C", "upstream", "rev-parse", "HEAD"], text=True).strip() + "\n"
        )
        (package / "PATCH_SHA256").write_text(hashlib.sha256(Path("scripts/patch_upstream.py").read_bytes()).hexdigest() + "\n")
        with tarfile.open(dist / asset, "w:gz") as archive:
            for entry in sorted(package.iterdir()):
                archive.add(entry, arcname=entry.name, recursive=False)
    print(asset)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
