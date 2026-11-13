#!/usr/bin/env python3
"""Run upstream unit tests without inheriting browser configuration or flags."""
import argparse
import os
from pathlib import Path
import subprocess
import tempfile


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("upstream", type=Path, nargs="?", default=Path("upstream"))
    args = parser.parse_args()
    manifest = args.upstream.resolve() / "cli" / "Cargo.toml"
    if not manifest.is_file():
        parser.error(f"missing Cargo manifest: {manifest}")
    env = {key: value for key, value in os.environ.items()
           if not key.startswith("AGENT_BROWSER_")}
    env.update(CARGO_PROFILE_TEST_DEBUG="0", CARGO_PROFILE_DEV_DEBUG="0",
               CARGO_INCREMENTAL="0")
    with tempfile.TemporaryDirectory(prefix="abb-unit-") as directory:
        config = Path(directory) / "config.json"
        config.write_text("{}\n")
        env["AGENT_BROWSER_CONFIG"] = str(config)
        # Some upstream tests temporarily mutate process-wide environment values.
        # Serial execution also protects tests that do not acquire EnvGuard.
        command = ["cargo", "test", "--manifest-path", str(manifest), "--locked",
                   "--jobs", "1", "--", "--test-threads=1"]
        return subprocess.run(command, env=env).returncode


if __name__ == "__main__":
    raise SystemExit(main())
