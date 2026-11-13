#!/usr/bin/env python3
"""Validate and package a Mac ARM64 or Linux x86_64 build with provenance."""
import gzip
import hashlib
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import sys
import tarfile
import tempfile


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValueError(message)


def check_architecture(binary: Path, target: str) -> None:
    if target == "darwin-arm64":
        arch = subprocess.check_output(["lipo", "-archs", str(binary)], text=True).strip()
        require(arch == "arm64", f"expected arm64 Mach-O, found {arch!r}")
    elif target == "linux-x86_64":
        with binary.open("rb") as stream:
            header = stream.read(20)
        require(
            len(header) == 20
            and header[:7] == b"\x7fELF\x02\x01\x01"
            and struct.unpack_from("<H", header, 18)[0] == 62,
            "expected little-endian Linux x86_64 ELF executable",
        )
    else:
        raise ValueError(f"unsupported target: {target}")


def source_metadata(source: Path, tag: str) -> tuple[str, str]:
    require(bool(re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+", tag)), "invalid upstream tag")
    version = tag[1:]
    manifest = (source / "cli/Cargo.toml").read_text()
    found = re.search(r'^version\s*=\s*"([^"]+)"', manifest, re.M)
    require(bool(found and found.group(1) == version), "tag/manifest version mismatch")
    commit = subprocess.check_output(["git", "-C", str(source), "rev-parse", "HEAD"], text=True).strip()
    tagged = subprocess.check_output(["git", "-C", str(source), "rev-parse", f"{tag}^{{commit}}"], text=True).strip()
    require(bool(re.fullmatch(r"[a-f0-9]{40}", commit)) and commit == tagged, "checkout is not the requested upstream tag")
    dashboard = source / "packages/dashboard/out"
    index = (dashboard / "index.html").read_text()
    require(
        "Dashboard not built" not in index
        and bool(index.strip())
        and any(dashboard.rglob("*.js")),
        "dashboard output is absent or still a development placeholder",
    )
    return version, commit


def main(target: str, tag: str) -> None:
    require(target in ("darwin-arm64", "linux-x86_64"), "unsupported target")
    source = Path(os.environ.get("UPSTREAM_ROOT", "upstream")).resolve()
    version, commit = source_metadata(source, tag)
    original = source / "cli/target/ci/agent-browser"
    require(original.is_file() and not original.is_symlink(), "compiled executable is missing or a symlink")
    check_architecture(original, target)
    require(
        b"Dashboard not built. Run: cd packages/dashboard" not in original.read_bytes(),
        "compiled executable still embeds the dashboard placeholder; rebuild it",
    )
    built_version = subprocess.check_output([str(original), "--version"], text=True, timeout=20).strip()
    require(built_version == f"agent-browser {version}", "compiled executable version mismatch")
    dist = Path("dist")
    dist.mkdir(exist_ok=True)
    asset = dist / f"agent-browser-browse-{target}.tar.gz"
    with tempfile.TemporaryDirectory(prefix=".package-", dir=dist) as temporary:
        temporary = Path(temporary)
        package = temporary / "files"
        package.mkdir()
        binary = package / "agent-browser-browse-native"
        shutil.copy2(original, binary)
        binary.chmod(0o755)
        if target == "darwin-arm64":
            subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(binary)], check=True)
            subprocess.run(["codesign", "--verify", str(binary)], check=True)
        shutil.copyfile(source / "LICENSE", package / "LICENSE.upstream")
        (package / "UPSTREAM_VERSION").write_text(version + "\n")
        (package / "UPSTREAM_COMMIT").write_text(commit + "\n")
        patch = Path(__file__).with_name("patch_upstream.py")
        (package / "PATCH_SHA256").write_text(hashlib.sha256(patch.read_bytes()).hexdigest() + "\n")
        pending = temporary / "archive.tar.gz"
        with pending.open("wb") as raw:
            with gzip.GzipFile(filename="", mode="wb", fileobj=raw, mtime=0) as compressed:
                with tarfile.open(fileobj=compressed, mode="w") as archive:
                    for entry in sorted(package.iterdir()):
                        info = archive.gettarinfo(str(entry), arcname=entry.name)
                        info.uid = info.gid = info.mtime = 0
                        info.uname = info.gname = ""
                        info.mode = 0o755 if entry == binary else 0o644
                        with entry.open("rb") as stream:
                            archive.addfile(info, stream)
        os.replace(pending, asset)
    print(f"Packaged {asset} from upstream {commit}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit("Usage: package.py TARGET UPSTREAM_TAG (optional UPSTREAM_ROOT)")
    try:
        main(sys.argv[1], sys.argv[2])
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        sys.exit(f"Package validation failed: {error}")
