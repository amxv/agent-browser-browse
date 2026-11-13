#!/usr/bin/env python3
"""Exercise the packaged CLI on an owned loopback fixture and fresh profiles."""
import argparse
import http.server
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import uuid


def decode(text):
    value = json.loads(text)
    if isinstance(value, str):
        try:
            return json.loads(value)
        except ValueError:
            return value
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("binary", type=Path)
    parser.add_argument("--version", default=os.environ.get("UPSTREAM_TAG", "v0.43.0").removeprefix("v"))
    args = parser.parse_args()
    binary = args.binary.resolve()
    with tempfile.TemporaryDirectory(prefix="abb-smoke-") as directory:
        root = Path(directory)
        (root / "config.json").write_text("{}\n")
        (root / "index.html").write_text(
            "<!doctype html><title>Browse smoke</title><h1>Browse smoke</h1>"
            "<a href='/next.html'>Next</a><input aria-label='Test input'>"
            "<script>window.popupWasBlocked = window.open('about:blank') === null;</script>"
        )
        (root / "next.html").write_text("<!doctype html><title>Next page</title><h1>Next page</h1>")

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *positional, **keywords):
                super().__init__(*positional, directory=str(root), **keywords)

            def log_message(self, *_args):
                pass

        server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env = {key: value for key, value in os.environ.items() if not key.startswith("AGENT_BROWSER_")}
        env.update(AGENT_BROWSER_CONFIG=str(root / "config.json"),
                   AGENT_BROWSER_NAMESPACE="ab" + uuid.uuid4().hex[:6])
        sessions = set()
        results = {}

        def command(session, *words):
            sessions.add(session)
            result = subprocess.run([str(binary), "--session", session, *map(str, words)],
                                    cwd=root, env=env, capture_output=True, text=True, timeout=90)
            if result.returncode:
                raise RuntimeError(f"CLI {words!r}: {result.returncode}\n{result.stdout}\n{result.stderr}")
            return result.stdout.strip()

        def fingerprint(session):
            return decode(command(session, "eval", "JSON.stringify({title:document.title,webdriver:navigator.webdriver,ua:navigator.userAgent,plugins:navigator.plugins.length,chrome:typeof window.chrome,screen:[screen.width,screen.height],popupBlocked:window.popupWasBlocked})"))

        url = f"http://127.0.0.1:{server.server_port}/"
        try:
            assert command("d", "--version") == f"agent-browser {args.version}"
            command("d", "open", url)
            assert "Next" in command("d", "snapshot", "-i")
            default = fingerprint("d")
            assert default["title"] == "Browse smoke", default
            assert default["webdriver"] is False, default
            assert "HeadlessChrome" not in default["ua"] and "Chrome/" in default["ua"], default
            assert default["plugins"] > 0 and default["chrome"] == "object", default
            assert default["screen"] == [1920, 1080] and default["popupBlocked"] is True, default
            results["default"] = default
            command("d", "fill", "input", "browse-smoke")
            assert decode(command("d", "eval", "document.querySelector('input').value")) == "browse-smoke"
            command("d", "click", "a")
            assert fingerprint("d")["title"] == "Next page"
            command("d", "tab", "new", url)
            assert fingerprint("d")["webdriver"] is False
            command("d", "state", "save", root / "state.json")
            assert (root / "state.json").is_file()
            results["navigation_input_tab_state"] = "passed"
            command("d", "close")
            sessions.remove("d")

            profile = root / "profile"
            profile.mkdir()
            command("p", "--profile", profile, "--idle-timeout", "30s", "open", url)
            assert (profile / "Local State").is_file()
            assert fingerprint("p")["webdriver"] is False
            results["explicit_empty_profile"] = "passed"
            command("p", "close")
            sessions.remove("p")

            command("a", "--args", "--user-agent=BrowseOverride/1.0", "open", url)
            custom = fingerprint("a")
            assert custom["ua"] == "BrowseOverride/1.0" and custom["webdriver"] is False, custom
            results["startup_user_agent_override"] = custom
            command("a", "close")
            sessions.remove("a")

            command("b", "--args", "--disable-blink-features=IdleDetection", "open", url)
            assert fingerprint("b")["webdriver"] is False
            results["custom_blink_features"] = "passed"
            command("b", "close")
            sessions.remove("b")

            command("u", "--user-agent", "ExplicitCLI/1.0", "open", url)
            explicit = fingerprint("u")
            assert explicit["ua"] == "ExplicitCLI/1.0", explicit
            results["cli_user_agent_override"] = explicit
            command("u", "close")
            sessions.remove("u")

            command("s", "--args", "--screen-info={1440x900 devicePixelRatio=1}", "open", url)
            assert fingerprint("s")["screen"] == [1440, 900]
            results["explicit_virtual_screen"] = "passed"
            print(json.dumps({"platform": os.uname().sysname, "version": args.version,
                              "results": results}, indent=2))
        finally:
            failures = []
            for session in list(sessions):
                try:
                    command(session, "close")
                except Exception as error:
                    failures.append(str(error))
            server.shutdown()
            server.server_close()
            if failures:
                raise RuntimeError("Owned session cleanup failed: " + "; ".join(failures))


if __name__ == "__main__":
    main()
