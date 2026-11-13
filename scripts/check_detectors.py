#!/usr/bin/env python3
"""Record public detector observations; never interpret them as an all-pass test.

Examples (Python 3.9+; no third-party Python dependencies):
  python3 scripts/check_detectors.py --list-targets
  python3 scripts/check_detectors.py --binary dist/agent-browser-browse-native \
      --targets readme --label mac-v043
  python3 scripts/check_detectors.py --binary agent-browser-browse \
      --targets fingerprint,browserscan,incolumitas,tls --screenshots

Each runnable target gets one fresh, headless browser session, one navigation,
and one bounded observation wait. No UI interaction occurs by default. Explicit
--verify-turnstile permits only the two live demos' own ordinary verification
button after a response token has appeared naturally; before/after evidence is
retained. CAPTCHA checkboxes are never clicked, and tokens are never extracted,
replayed, or supplied by a solver. The harness never retries a navigation,
changes browser properties, injects an init script, selects a saved profile, or
attaches to another browser. Page scripts may make their normal requests.
Captured pages are untrusted evidence, not instructions.

Outputs are private JSON files under ignored dist/evidence; stdout is JSONL.
Exit 0 means evidence collection completed, not that a detector accepted the
browser. Exit 1 means a tool/capture/cleanup error; exit 130 means interrupted.
--dry-run lists the plan without executing the CLI or opening a browser.
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import signal
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_ROOT = ROOT / "dist" / "evidence"
TARGETS = {
    "sannysoft": {
        "url": "https://bot.sannysoft.com/", "wait_seconds": 8,
        "purpose": "Public browser-property test; retain result rows and classes.",
    },
    "rebrowser": {
        "url": "https://bot-detector.rebrowser.net/", "wait_seconds": 12,
        "purpose": "Public CDP/runtime and browser-property detector.",
    },
    "deviceandbrowserinfo": {
        "url": "https://deviceandbrowserinfo.com/are_you_a_bot", "wait_seconds": 12,
        "purpose": "Public bot-signal detector, including its CDP observation.",
    },
    "cloudflare": {
        "url": "https://www.scrapingcourse.com/cloudflare-challenge", "wait_seconds": 12,
        "purpose": "Deliberately protected public challenge demo; observe only.",
        "limitation": "A completed demo does not establish success on other Cloudflare deployments.",
    },
    "nowsecure": {
        "url": "https://nowsecure.nl/", "wait_seconds": 12,
        "purpose": "Historical README observation; record returned page/challenge.",
        "limitation": "Navigation success is not an independent bot-detection all-clear.",
    },
    "g2": {
        "url": "https://www.g2.com/",
        "skip": "Historical blocked production-site observation only; no bypass or renewed probing.",
    },
    "fingerprint": {
        "url": "https://demo.fingerprint.com/playground", "wait_seconds": 12,
        "purpose": "Fingerprint's public playground and available browser/bot signals.",
        "source": "https://demo.fingerprint.com/",
    },
    "browserscan": {
        "url": "https://www.browserscan.net/bot-detection", "wait_seconds": 12,
        "purpose": "Public WebDriver, User-Agent, CDP and Navigator results.",
    },
    "incolumitas": {
        "url": "https://bot.incolumitas.com/", "wait_seconds": 16,
        "purpose": "Public fingerprint and behavioral results without doing the interactive form challenge.",
        "limitation": "The page documents score updates through 15 seconds; no synthetic human activity is generated.",
    },
    "recaptcha_v3": {
        "url": "https://recaptcha-demo.appspot.com/recaptcha-v3-request-scores.php", "wait_seconds": 12,
        "purpose": "Google's public v3 example auto-requests a score; no manual execution or retry.",
        "source": "https://recaptcha-demo.appspot.com/",
        "limitation": "The demo explicitly says its sample score is not a production traffic/account assessment.",
    },
    "turnstile": {
        "url": "https://demo.turnstile.workers.dev/", "wait_seconds": 12,
        "purpose": "Cloudflare's official dummy-key demo: widget plumbing only, not bot-detection coverage.",
        "source": "https://github.com/cloudflare/turnstile-demo-workers",
        "expected_sitekey": "1x00000000000000000000AA",
        "limitation": "The verified dummy key always passes. Token presence or Success is not a real detector result or server-side verification.",
    },
    "turnstile_managed": {
        "url": "https://zerocaptcha.io/captcha-test/cloudflare-turnstile-managed", "wait_seconds": 12,
        "purpose": "Purpose-built public live Turnstile demo; observe only and stop without clicking any checkbox.",
        "source": "https://zerocaptcha.io/captcha-test",
        "expected_sitekey": "0x4AAAAAAFMVDQUY9ZAPO0ni", "advertised_mode": "managed",
        "limitation": "Mode is advertised by the demo owner and configured in Cloudflare's dashboard, not independently provable from HTML. Token presence is not Siteverify validation.",
    },
    "turnstile_noninteractive": {
        "url": "https://zerocaptcha.io/captcha-test/cloudflare-turnstile-non-interactive", "wait_seconds": 12,
        "purpose": "Purpose-built public live non-interactive Turnstile demo; observe natural completion without interaction.",
        "source": "https://zerocaptcha.io/captcha-test",
        "expected_sitekey": "0x4AAAAAAFMVD5shSUWybiHc", "advertised_mode": "non-interactive",
        "limitation": "Mode is advertised by the demo owner and configured in Cloudflare's dashboard, not independently provable from HTML. No solver, token replay, or reset is performed; the site's own Verify button is used only with explicit --verify-turnstile after natural issuance.",
    },
    "shieldsquare": {
        "url": None,
        "skip": "No verified current public authorized ShieldSquare/Radware detector demo was found; vendor sales pages are not tests.",
        "source": "https://www.radware.com/products/bot-manager/",
    },
    "tls": {
        "url": "https://tls.peet.ws/api/all", "wait_seconds": 1,
        "purpose": "Browser navigation captures the server-observed TLS/HTTP fingerprint JSON.",
        "limitation": "An observation only: TLS consistency requires a paired baseline on the same browser/OS/network; intermediaries can affect it.",
    },
}
GROUPS = {
    "readme": ["sannysoft", "rebrowser", "deviceandbrowserinfo", "cloudflare", "nowsecure", "g2"],
    "extended": ["fingerprint", "browserscan", "incolumitas", "recaptcha_v3", "turnstile", "turnstile_managed", "turnstile_noninteractive", "shieldsquare", "tls"],
    "all": list(TARGETS),
}

# Read-only observation. No property definitions, page-global assignments,
# console tricks, additional network fetches, or calls to CAPTCHA APIs.
PROBE = r"""(async () => {
  const clip = (s, n) => { s = String(s == null ? '' : s); return {
    text: s.slice(0, n), characters: s.length, truncated: s.length > n
  }; };
  const safe = (fn) => { try { return fn(); } catch (e) { return {error: String(e)}; } };
  const text = document.body ? document.body.innerText : '';
  const rows = Array.from(document.querySelectorAll(
    'tr, dt, dd, pre, code, [role="status"], [role="alert"], [data-testid], ' +
    '[class*="result"], [class*="status"], [class*="success"], [class*="warning"], ' +
    '[class*="fail"], [class*="pass"], [data-result]'
  ));
  const dom = rows.slice(0, 500).map(e => ({
    tag: e.tagName, id: e.id, class: e.getAttribute('class'),
    role: e.getAttribute('role'), ariaLabel: e.getAttribute('aria-label'),
    text: clip(e.innerText || e.textContent, 8000),
    color: safe(() => getComputedStyle(e).color),
    backgroundColor: safe(() => getComputedStyle(e).backgroundColor),
    cells: e.tagName === 'TR' ? Array.from(e.cells).map(c => ({
      text: clip(c.innerText, 4000), class: c.getAttribute('class'),
      color: safe(() => getComputedStyle(c).color),
      backgroundColor: safe(() => getComputedStyle(c).backgroundColor)
    })) : undefined
  }));
  const frames = Array.from(document.querySelectorAll('iframe')).map(f => ({
    src: f.getAttribute('src'), title: f.title, name: f.name,
    width: f.clientWidth, height: f.clientHeight,
    sameOriginText: safe(() => f.contentDocument ? clip(f.contentDocument.body?.innerText, 12000) : null)
  }));
  const descriptor = safe(() => {
    const d = Object.getOwnPropertyDescriptor(Navigator.prototype, 'webdriver');
    return d ? {configurable: d.configurable, enumerable: d.enumerable,
      getter: d.get ? Function.prototype.toString.call(d.get) : null} : null;
  });
  const fingerprint = {
    webdriver: safe(() => ({type: typeof navigator.webdriver,
      value: typeof navigator.webdriver === 'undefined' ? null : navigator.webdriver,
      inNavigator: 'webdriver' in navigator, ownProperty: Object.prototype.hasOwnProperty.call(navigator, 'webdriver'),
      prototypeDescriptor: descriptor})),
    userAgent: navigator.userAgent, appVersion: navigator.appVersion,
    platform: navigator.platform, vendor: navigator.vendor,
    language: navigator.language, languages: Array.from(navigator.languages || []),
    hardwareConcurrency: navigator.hardwareConcurrency, deviceMemory: navigator.deviceMemory,
    maxTouchPoints: navigator.maxTouchPoints, cookieEnabled: navigator.cookieEnabled,
    pdfViewerEnabled: navigator.pdfViewerEnabled,
    plugins: safe(() => Array.from(navigator.plugins).map(p => ({
      name: p.name, filename: p.filename, description: p.description, length: p.length
    }))),
    mimeTypes: safe(() => Array.from(navigator.mimeTypes).map(m => ({type: m.type, suffixes: m.suffixes}))),
    chrome: safe(() => ({type: typeof window.chrome,
      keys: window.chrome ? Object.keys(window.chrome).sort() : [],
      appType: typeof window.chrome?.app, runtimeType: typeof window.chrome?.runtime})),
    screen: {width: screen.width, height: screen.height, availWidth: screen.availWidth,
      availHeight: screen.availHeight, colorDepth: screen.colorDepth, pixelDepth: screen.pixelDepth},
    viewport: {innerWidth, innerHeight, outerWidth, outerHeight, devicePixelRatio},
    timezone: safe(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
    userAgentData: safe(() => navigator.userAgentData?.toJSON() || null)
  };
  if (navigator.userAgentData?.getHighEntropyValues) {
    try { fingerprint.highEntropyUA = await navigator.userAgentData.getHighEntropyValues(
      ['architecture', 'bitness', 'model', 'platformVersion', 'fullVersionList', 'uaFullVersion', 'wow64']
    ); } catch (e) { fingerprint.highEntropyUA = {error: String(e)}; }
  }
  const responseInputs = Array.from(document.querySelectorAll(
    '[name="cf-turnstile-response"], [name="g-recaptcha-response"]'
  )).map(e => ({name: e.name, present: Boolean(e.value), length: (e.value || '').length}));
  const keys = Array.from(document.querySelectorAll('[data-sitekey]')).map(e => e.getAttribute('data-sitekey'));
  return {
    observedAt: new Date().toISOString(), url: location.href, title: document.title,
    readyState: document.readyState, text: clip(text, 160000),
    dom: {nodes: dom, selectedNodes: rows.length, truncated: rows.length > 500},
    frames, fingerprint,
    challenge: {
      textHints: (text.match(/verify (?:that )?you(?:'re| are) human|select all (?:images|squares)|complete (?:the|this) captcha|press and hold/gi) || []).slice(0, 20),
      responseInputs, sitekeys: keys,
      knownTurnstileTestKey: keys.some(k => /^[123]x0{10,}/.test(k || '')),
      note: 'Heuristic hints only. Cross-origin challenge text may be unavailable; no challenge is clicked or solved.'
    },
    jsonDocument: safe(() => { try { return JSON.parse(document.body?.textContent || ''); } catch (_) { return null; } })
  };
})()"""


REBROWSER_EXERCISE = r"""(() => {
  const beforeDetections = JSON.parse(document.querySelector('#detections-json').value);
  const calls = [];
  const invoke = (expression, fn) => {
    try { calls.push({expression, result: fn()}); }
    catch (e) { calls.push({expression, error: String(e)}); }
  };
  invoke('window.dummyFn()', () => window.dummyFn());
  invoke("document.getElementById('detections-json')", () => Boolean(document.getElementById('detections-json')));
  invoke("document.getElementsByClassName('div')", () => document.getElementsByClassName('div').length);
  const afterDetections = JSON.parse(document.querySelector('#detections-json').value);
  return {
    beforeDetections, calls, afterDetections, detections: afterDetections,
    interpretation: 'mainWorldExecution deliberately tests this CLI eval path as actually used. No isolated-context substitute or exposedFn is injected. Gray is not a blanket pass.'
  };
})()"""


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def emit(value):
    print(json.dumps(value, ensure_ascii=False), flush=True)


def write_json(path, value):
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def parse_json(text):
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        return None


def redact_tokens(text):
    """Keep diagnostic stdout, but never persist CAPTCHA tokens or long opaque blobs.

    Public demos sometimes print a token (or its prefix) in their rendered text.
    This intentionally broad mask also hides other long opaque strings; the
    command record makes this loss explicit. Ordinary fingerprint hashes remain.
    """
    # The demos display prefixes such as 'cf-turnstile-response: 1.<16 chars>…'.
    # Mask these even when they are too short for the generic opaque-string rule.
    prefix_pattern = (r"(?i)((?:cf-turnstile-response|g-recaptcha-response)\s*:\s*)"
                      r"(?:[0-9]+\.[A-Za-z0-9_.-]+|03[A-Za-z0-9_-]+)"
                      r"(?:…|\\u2026|\.{3})?")
    text, count = re.subn(prefix_pattern, r"\1[REDACTED_TOKEN_PREFIX]", text)
    patterns = [
        r"\b[01]\.[A-Za-z0-9_.-]{8,}(?:…|\\u2026|\.{3})",
        r"\b03[A-Za-z0-9_-]{18,}\b",
        r"\b[01]\.[A-Za-z0-9_.-]{18,}\b",
        r"[A-Za-z0-9_-]{80,}",
        r"(?i)(?<=token=)[^&\s\"'<>\\]+",
    ]
    for pattern in patterns:
        text, found = re.subn(pattern, "[REDACTED_TOKEN_LIKE_STRING]", text)
        count += found
    return text, count


def cli_data(command):
    parsed = command.get("json")
    return parsed.get("data", {}) if isinstance(parsed, dict) else {}


def probe_result(command):
    data = cli_data(command)
    result = data.get("result") if isinstance(data, dict) else None
    return parse_json(result) if isinstance(result, str) else result


def command_ok(command):
    parsed = command.get("json")
    return (command.get("exit_code") == 0 and not command.get("error")
            and not (isinstance(parsed, dict) and parsed.get("success") is False))


def run_command(argv, env, cwd, timeout, stdin=None):
    started = time.monotonic()
    record = {"argv": argv, "cwd": str(cwd), "started_at": utc_now(), "timeout_seconds": timeout}
    if stdin is not None:
        record["stdin"] = stdin
    process = None
    try:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            stdout, stderr = process.communicate(stdin, timeout=timeout)
        except subprocess.TimeoutExpired:
            # Kill only this CLI process. The owned daemon is closed in finally.
            process.kill()
            stdout, stderr = process.communicate()
            record["error"] = "command_timeout"
        stdout, stdout_redactions = redact_tokens(stdout)
        stderr, stderr_redactions = redact_tokens(stderr)
        record.update(stdout=stdout, stderr=stderr, exit_code=process.returncode,
                      token_like_redactions={"stdout": stdout_redactions, "stderr": stderr_redactions})
        parsed = parse_json(stdout)
        if parsed is not None:
            record["json"] = parsed
    except OSError as error:
        record.update(stdout="", stderr="", exit_code=None, error=str(error))
    except KeyboardInterrupt:
        if process is not None and process.poll() is None:
            process.kill()
            process.communicate()
        raise
    record["duration_seconds"] = round(time.monotonic() - started, 3)
    return record


def browser_version(cdp_command):
    """Read metadata from only the current owned browser's loopback endpoint."""
    data = cli_data(cdp_command)
    endpoint = data.get("cdpUrl") if isinstance(data, dict) else None
    record = {"source": "owned-browser /json/version", "started_at": utc_now()}
    try:
        parsed = urllib.parse.urlsplit(endpoint or "")
        if (parsed.scheme not in ("ws", "wss") or parsed.hostname not in ("localhost", "127.0.0.1", "::1")
                or not parsed.port or parsed.username or parsed.password):
            raise ValueError("No loopback CDP endpoint was returned; browser version remains in the UA probe if available")
        host = "[::1]" if parsed.hostname == "::1" else parsed.hostname
        url = "http://{}:{}/json/version".format(host, parsed.port)
        record["url"] = url
        # Never send the local metadata request through an inherited proxy.
        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
        with opener.open(url, timeout=5) as response:
            record.update(status=response.status, stdout=response.read(65536).decode("utf-8", "replace"))
        record["json"] = parse_json(record["stdout"])
    except Exception as error:
        record["error"] = str(error)
    return record


def selected_targets(values):
    selected = []
    for value in values:
        for name in value.split(","):
            name = name.strip().lower()
            if name not in TARGETS and name not in GROUPS:
                raise ValueError("Unknown target/group: " + name)
            for target in GROUPS.get(name, [name]):
                if target not in selected:
                    selected.append(target)
    return selected


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--binary", default="agent-browser-browse", help="CLI executable or path; never a shell command")
    parser.add_argument("--targets", nargs="+", default=["readme"], help="Names/groups, separated by spaces or commas; default: readme")
    parser.add_argument("--label", default="detectors", help="Evidence directory label")
    parser.add_argument("--output-dir", type=Path, default=EVIDENCE_ROOT, help="Parent directory inside ignored dist/evidence")
    parser.add_argument("--wait-seconds", type=float, help="Override each target's one observation window (0..30 seconds)")
    parser.add_argument("--command-timeout", type=float, default=45, help="Hard subprocess timeout (5..60 seconds)")
    parser.add_argument("--browser-args", help="Explicit scoped Chrome --args override; use --browser-args='--flag,...'; recorded verbatim")
    parser.add_argument("--executable-path", help="Explicit scoped Chrome executable override; no persistent config change")
    parser.add_argument("--screenshots", action="store_true", help="Save optional viewport PNGs; text/DOM remain primary evidence")
    parser.add_argument("--exercise-rebrowser", action="store_true", help="Invoke Rebrowser's documented dummyFn/sourceURL/main-world probes using actual CLI eval; does not expose any fake function")
    parser.add_argument("--verify-turnstile", action="store_true", help="Only on the two real demos, click their ordinary Verify with Cloudflare button after natural token issuance; never interact with CAPTCHA")
    parser.add_argument("--list-targets", action="store_true")
    parser.add_argument("--dry-run", action="store_true", help="Print target plan without executing the CLI")
    args = parser.parse_args()
    if args.list_targets:
        emit({"targets": TARGETS, "groups": GROUPS})
        return 0
    try:
        targets = selected_targets(args.targets)
        if args.wait_seconds is not None and not 0 <= args.wait_seconds <= 30:
            raise ValueError("--wait-seconds must be between 0 and 30")
        if not 5 <= args.command_timeout <= 60:
            raise ValueError("--command-timeout must be between 5 and 60")
        out_parent = args.output_dir.expanduser().resolve()
        out_parent.relative_to(EVIDENCE_ROOT.resolve())
    except ValueError as error:
        emit({"status": "invalid_arguments", "error": str(error), "required_output_parent": str(EVIDENCE_ROOT)})
        return 2
    plan = [{"name": name, **TARGETS[name], "wait_seconds": args.wait_seconds if args.wait_seconds is not None
             else TARGETS[name].get("wait_seconds", 0)} for name in targets]
    if args.dry_run:
        emit({"status": "dry_run", "binary": args.binary, "targets": plan, "headless": True,
              "fresh_session_per_target": True, "navigation_attempts_per_target": 1, "output_parent": str(out_parent),
              "explicit_overrides": {"browser_args": args.browser_args, "executable_path": args.executable_path},
              "exercise_rebrowser": args.exercise_rebrowser, "verify_turnstile": args.verify_turnstile})
        return 0
    binary = shutil.which(args.binary)
    if binary is None:
        emit({"status": "missing_binary", "binary": args.binary})
        return 2
    binary = str(Path(binary).absolute())
    os.umask(0o077)
    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + secrets.token_hex(3)
    label = re.sub(r"[^a-zA-Z0-9_-]+", "-", args.label).strip("-")[:48] or "detectors"
    output = out_parent / (label + "-" + run_id)
    output.mkdir(parents=True, exist_ok=False)
    config = output / "empty-config.json"
    config.write_text("{}\n", encoding="utf-8")
    # /tmp avoids macOS's long TMPDIR causing AF_UNIX's 103-byte limit.
    socket_root = Path(tempfile.mkdtemp(prefix="abd-", dir="/tmp"))
    namespace = "det" + secrets.token_hex(3)
    removed = sorted(k for k in os.environ if k.startswith("AGENT_BROWSER_"))
    env = {k: v for k, v in os.environ.items() if not k.startswith("AGENT_BROWSER_")}
    env.update(AGENT_BROWSER_NAMESPACE=namespace, AGENT_BROWSER_SOCKET_DIR=str(socket_root),
               AGENT_BROWSER_CONFIG=str(config), AGENT_BROWSER_DEFAULT_TIMEOUT="20000", NO_COLOR="1")
    common = [binary, "--config", str(config), "--namespace", namespace, "--idle-timeout", "2m", "--json"]
    if args.browser_args is not None:
        common += ["--args", args.browser_args]
    if args.executable_path:
        common += ["--executable-path", str(Path(args.executable_path).expanduser().absolute())]
    report = {
        "schema_version": 1, "run_id": run_id, "label": label, "started_at": utc_now(),
        "output_directory": str(output), "status": "running", "targets": [],
        "environment": {"os": platform.system(), "os_release": platform.release(), "os_version": platform.version(),
                        "machine": platform.machine(), "python": platform.python_version(),
                        "macos": platform.mac_ver()[0] or None,
                        "removed_agent_browser_variable_names": removed,
                        "proxy_variable_names_present": sorted(k for k in env if k.lower() in ("http_proxy", "https_proxy", "all_proxy"))},
        "binary": {"requested": args.binary, "invoked_path": binary, "realpath": str(Path(binary).resolve()),
                   "invoked_file_sha256": hashlib.sha256(Path(binary).read_bytes()).hexdigest(),
                   "note": "If invoked_path is a wrapper, its hash identifies the wrapper; record the native build hash separately."},
        "isolation": {"namespace": namespace, "socket_root": str(socket_root), "config": str(config),
                      "config_contents": {}, "headless": True, "saved_profiles_or_state": False,
                      "explicit_overrides": {"browser_args": args.browser_args, "executable_path": args.executable_path}},
        "method": {"navigation_attempts_per_target": 1,
                   "interactions": "no UI interaction by default; explicit Turnstile verification permits only the demo's own Verify button after natural token issuance",
                   "screenshots": args.screenshots, "verify_turnstile": args.verify_turnstile,
                   "exercise_rebrowser": args.exercise_rebrowser,
                   "probe_sha256": hashlib.sha256(PROBE.encode()).hexdigest(),
                   "limits": ["Single run per selected target; no estimated success rates.",
                              "Browser automation/evaluation itself is observable; public detectors may change.",
                              "A tool exit code or page load is not a detector pass.",
                              "Managed challenges are observed; interactive challenges are never attempted.",
                              "Token-like strings in command output are redacted and counted; CAPTCHA response values are never intentionally recorded.",
                              "TLS results are server observations, not a consistency claim without a baseline."]},
    }
    exit_code = 0
    cleanup_failed = False
    interrupted = False
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        report["binary"]["version_command"] = run_command(common + ["--version"], env, output, args.command_timeout)
        if not command_ok(report["binary"]["version_command"]):
            raise RuntimeError("CLI version command failed; no browser tests started")
        for index, target in enumerate(plan):
            name = target["name"]
            item = {"target": target, "started_at": utc_now(), "commands": []}
            report["targets"].append(item)
            if "skip" in target:
                item.update(status="skipped", reason=target["skip"])
                write_json(output / (name + ".json"), item)
                emit({"target": name, "status": "skipped", "reason": target["skip"]})
                continue
            session = "d" + secrets.token_hex(3) + "-" + str(index)
            item["session"] = session
            prefix = common + ["--session", session]
            item["cleanup_command"] = {"argv": prefix + ["close"], "env": {
                "AGENT_BROWSER_SOCKET_DIR": str(socket_root), "AGENT_BROWSER_NAMESPACE": namespace,
                "AGENT_BROWSER_CONFIG": str(config)}}

            def command(arguments, stdin=None, timeout=None):
                result = run_command(prefix + arguments, env, output, timeout or args.command_timeout, stdin)
                item["commands"].append(result)
                return result

            emit({"target": name, "status": "starting", "session": session, "url": target["url"]})
            try:
                command(["open", target["url"]])
                # A fixed, bounded observation window is deliberate for detector
                # debugging; it avoids asserting that a third-party UI is final.
                if target["wait_seconds"]:
                    command(["wait", str(round(target["wait_seconds"] * 1000))],
                            timeout=max(args.command_timeout, target["wait_seconds"] + 5))
                if name == "rebrowser" and args.exercise_rebrowser:
                    exercise = command(["eval", "--stdin"], stdin=REBROWSER_EXERCISE)
                    item["manual_exercise"] = {
                        "source": "https://github.com/rebrowser/rebrowser-bot-detector/blob/main/index.html",
                        "result": cli_data(exercise),
                        "interpretation": "Intentional calls through the actual CLI eval context. Main-world interception may be detected; exposeFunctionLeak is not exercised because no callback is exposed.",
                    }
                probe = command(["eval", "--stdin"], stdin=PROBE)
                observations = probe_result(probe)
                item["observations"] = observations
                command(["snapshot"])
                if args.verify_turnstile:
                    verification = {"requested": True, "status": "skipped", "button_clicks_attempted": 0,
                                    "observations_before": observations,
                                    "interpretation": "Natural token issuance and server verification are distinct. Inspect the demo's recorded backend reply; a successful click is not a detector pass."}
                    item["turnstile_verification"] = verification
                    challenge = observations.get("challenge", {}) if isinstance(observations, dict) else {}
                    token_present = any(i.get("name") == "cf-turnstile-response" and i.get("present") is True
                                        and isinstance(i.get("length"), int) and i["length"] > 0
                                        for i in challenge.get("responseInputs", []))
                    actual_url = urllib.parse.urlsplit(observations.get("url", "") if isinstance(observations, dict) else "")
                    expected_url = urllib.parse.urlsplit(target["url"])
                    same_demo = (actual_url.scheme, actual_url.netloc, actual_url.path.rstrip("/")) == (
                        expected_url.scheme, expected_url.netloc, expected_url.path.rstrip("/"))
                    if name not in ("turnstile_managed", "turnstile_noninteractive"):
                        verification["reason"] = "ineligible_target; only the two real demo target IDs permit verification"
                    elif not isinstance(observations, dict):
                        verification["reason"] = "initial_probe_unavailable"
                    elif not same_demo:
                        verification["reason"] = "unexpected_demo_url; no form submitted"
                    elif target["expected_sitekey"] not in challenge.get("sitekeys", []):
                        verification["reason"] = "expected_live_sitekey_not_observed; no form submitted"
                    elif not token_present:
                        verification["reason"] = "no_naturally_issued_token; no click, reset or challenge interaction attempted"
                    else:
                        verification.update(button_clicks_attempted=1, button_command_index=len(item["commands"]),
                                            post_submit_wait_seconds=5)
                        submitted = command(["find", "role", "button", "click", "--name", "Verify with Cloudflare"])
                        verification["submission_command_succeeded"] = command_ok(submitted)
                        command(["wait", "5000"], timeout=max(args.command_timeout, 10))
                        after = command(["eval", "--stdin"], stdin=PROBE)
                        verification["observations_after"] = probe_result(after)
                        command(["snapshot"])
                        verification["status"] = "captured_after_submission" if command_ok(submitted) and isinstance(
                            verification["observations_after"], dict) else "submission_or_capture_error"
                command(["session", "info"])
                cdp = command(["get", "cdp-url"])
                item["browser_version"] = browser_version(cdp)
                if args.screenshots:
                    command(["screenshot", str(output / (name + ".png"))])
                item["status"] = "captured" if isinstance(observations, dict) else "capture_error"
                if isinstance(observations, dict):
                    item["possible_interactive_challenge"] = bool(observations.get("challenge", {}).get("textHints"))
                    item["detector_verdict"] = "unclassified; inspect recorded text, DOM and snapshot"
                if item["status"] == "capture_error" or any(not command_ok(c) for c in item["commands"]):
                    exit_code = 1
                    item["tool_errors"] = True
            except KeyboardInterrupt:
                item["status"] = "interrupted"
                raise
            except Exception as error:
                item.update(status="capture_error", error=str(error))
                exit_code = 1
            finally:
                cleanup = command(["close"], timeout=20)
                item["cleanup_succeeded"] = command_ok(cleanup)
                cleanup_failed = cleanup_failed or not item["cleanup_succeeded"]
                item["finished_at"] = utc_now()
                write_json(output / (name + ".json"), item)
                write_json(output / "run.json", report)
                emit({"target": name, "status": item["status"], "cleanup_succeeded": item["cleanup_succeeded"],
                      "evidence": str(output / (name + ".json"))})
            if cleanup_failed:
                exit_code = 1
                report["stopped_reason"] = "Owned session did not close; stopping before another browser launch"
                break
    except KeyboardInterrupt:
        interrupted = True
        exit_code = 130
    except Exception as error:
        report["error"] = str(error)
        exit_code = 1
    finally:
        report["session_list_after"] = run_command(common + ["session", "list"], env, output, 10)
        listed = cli_data(report["session_list_after"])
        remaining = listed.get("sessions") if isinstance(listed, dict) else None
        if not command_ok(report["session_list_after"]) or remaining != []:
            cleanup_failed = True
            if exit_code == 0:
                exit_code = 1
            report["cleanup_verification_error"] = "Could not confirm this run's isolated namespace was empty; retaining its socket directory"
        if not cleanup_failed:
            shutil.rmtree(socket_root)
        report.update(status="interrupted" if interrupted else "completed" if exit_code == 0 else "partial",
                      finished_at=utc_now(), exit_code=exit_code, cleanup_failed=cleanup_failed,
                      socket_directory_retained=cleanup_failed)
        write_json(output / "run.json", report)
        emit({"status": report["status"], "exit_code": exit_code, "evidence": str(output / "run.json"),
              "captured_targets": len(report["targets"]), "cleanup_failed": cleanup_failed})
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
