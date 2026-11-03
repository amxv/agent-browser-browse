#!/usr/bin/env python3
"""Preserve valid old release checksums while adding newly built assets."""
import hashlib
from pathlib import Path
import sys


def main(existing: Path, names: Path, dist: Path) -> None:
    available = set(names.read_text().splitlines()) if names.exists() else set()
    new = {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in dist.glob("*.tar.gz")}
    merged = {}
    if existing.is_file():
        for line in existing.read_text().splitlines():
            fields = line.split()
            if len(fields) == 2 and fields[1] in available and fields[1] not in new:
                merged[fields[1]] = fields[0]
    merged.update(new)
    (dist / "SHA256SUMS").write_text("".join(f"{digest}  {name}\n" for name, digest in sorted(merged.items())))
    if not new:
        raise ValueError("no new archives")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]), Path(sys.argv[3]))
