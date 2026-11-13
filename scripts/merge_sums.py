#!/usr/bin/env python3
"""Merge exact release checksums without losing existing platform entries."""
import hashlib
from pathlib import Path
import re
import sys


ASSET = re.compile(r"agent-browser-browse-[a-z0-9_-]+\.tar\.gz")
DIGEST = re.compile(r"[a-fA-F0-9]{64}")


def main(existing: Path, names: Path, dist: Path) -> None:
    available = set(names.read_text().splitlines()) if names.exists() else set()
    retained = {name for name in available if ASSET.fullmatch(name)}
    new = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in dist.glob("*.tar.gz")
        if ASSET.fullmatch(path.name) and path.is_file() and not path.is_symlink()
    }
    if not new:
        raise ValueError("no new platform archives")
    if retained & new.keys():
        raise ValueError("refusing to replace an existing release asset")
    merged = {}
    if existing.is_file():
        for line in existing.read_text().splitlines():
            fields = line.split()
            if len(fields) != 2 or not DIGEST.fullmatch(fields[0]) or not ASSET.fullmatch(fields[1]):
                raise ValueError("invalid existing checksum manifest")
            digest, name = fields
            if name in merged:
                raise ValueError(f"duplicate checksum for {name}")
            merged[name] = digest.lower()
    if not retained.issubset(merged):
        raise ValueError("an existing release archive has no checksum")
    merged = {name: merged[name] for name in retained}
    merged.update(new)
    pending = dist / ".SHA256SUMS.pending"
    pending.write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(merged.items())))
    pending.replace(dist / "SHA256SUMS")


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit("Usage: merge_sums.py EXISTING_CHECKSUMS EXISTING_ASSET_NAMES DIST")
    try:
        main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
    except (OSError, ValueError) as error:
        sys.exit(f"Checksum merge failed: {error}")
