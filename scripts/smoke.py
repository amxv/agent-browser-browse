#!/usr/bin/env python3
"""Offline, profile-free CLI launch smoke test for the patched browser."""
import http.server
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import threading


def main(binary: Path) -> None:
    binary = binary.resolve()
    with tempfile.TemporaryDirectory(prefix="browse-smoke-") as directory:
        root = Path(directory)
        (root / "config.json").write_text("{}\n")
        (root / "index.html").write_text(
            "<!doctype html><html><head><title>Browse smoke</title></head>"
            "<body><h1>Browse smoke</h1><a href='/next'>Next</a></body></html>"
        )

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=str(root), **kwargs)

            def log_message(self, *_args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        env = {
            **os.environ,
            "AGENT_BROWSER_CONFIG": str(root / "config.json"),
            "AGENT_BROWSER_NAMESPACE": "browse-cross-platform-ci",
        }

        def command(*args):
            result = subprocess.run(
                [str(binary), "--session", "browse-ci", *args],
                env=env, capture_output=True, text=True, timeout=90,
            )
            if result.returncode:
                raise RuntimeError(f"CLI {args} failed: {result.stdout}\n{result.stderr}")
            return result.stdout.strip()

        try:
            expected = os.environ.get("UPSTREAM_TAG", "v0.41.1").removeprefix("v")
            assert command("--version") == f"agent-browser {expected}"
            command("open", f"http://127.0.0.1:{server.server_port}/")
            assert "Browse smoke" in command("snapshot", "-i")
            output = command("eval", "JSON.stringify({title:document.title,webdriver:navigator.webdriver,ua:navigator.userAgent})")
            data = json.loads(output)
            if isinstance(data, str):
                data = json.loads(data)
            assert data["title"] == "Browse smoke", data
            assert data["webdriver"] is False, data
            assert "HeadlessChrome" not in data["ua"], data
            assert "Chrome/" in data["ua"], data
            print(f"Smoke passed on {sys.platform}: {data}")
        finally:
            try:
                command("close")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
