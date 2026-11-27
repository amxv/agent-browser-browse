#!/usr/bin/env python3
"""Summarize check_detectors.py evidence and compare it with the release bar.

Usage:
  python3 scripts/compare_detectors.py dist/evidence/<baseline> dist/evidence/<candidate>

Each directory gets one column of extracted results and a per-check verdict
against docs/detector-release-bar.md. Exit 0 means every directory met the bar.
Exit 1 means at least one check regressed or could not be read. A missing
result is never treated as a pass. The extraction is heuristic: when a check
fails, inspect the recorded text and DOM before drawing conclusions.
"""
import argparse
import json
import re
import sys
from pathlib import Path

RATINGS = {-1: "green", 0: "gray", 0.5: "yellow", 1: "red"}


def load(directory, name):
    path = Path(directory) / f"{name}.json"
    return json.loads(path.read_text()) if path.is_file() else None


def page_text(observations):
    value = (observations or {}).get("text")
    if isinstance(value, dict):
        value = value.get("text")
    return value or ""


def target_text(item):
    return page_text((item or {}).get("observations"))


def rebrowser_flags(detections):
    """Return (red, yellow) detection type lists, or None if absent."""
    if not detections:
        return None
    flags = {"red": [], "yellow": []}
    for detection in detections:
        color = RATINGS.get(detection.get("rating"))
        if color in flags:
            flags[color].append(detection.get("type"))
    return sorted(flags["red"]), sorted(flags["yellow"])


def extract(directory):
    out = {}
    run = load(directory, "run") or {}
    out["os"] = (run.get("environment") or {}).get("os")

    item = load(directory, "sannysoft")
    if item:
        classes = [cell.get("class") or ""
                   for node in item["observations"].get("dom", {}).get("nodes", [])
                   for cell in node.get("cells") or []]
        out["sannysoft_failed"] = sum("failed" in c for c in classes)
        fp = item["observations"].get("fingerprint") or {}
        out["webdriver"] = (fp.get("webdriver") or {}).get("value")
        out["user_agent"] = fp.get("userAgent")
        screen = fp.get("screen") or {}
        out["screen"] = (screen.get("width"), screen.get("height"))
        match = re.search(r'"Browser": "([^"]+)"', (item.get("browser_version") or {}).get("stdout", ""))
        out["chrome"] = match.group(1) if match else None

    item = load(directory, "rebrowser")
    if item:
        result = ((item.get("manual_exercise") or {}).get("result") or {}).get("result") or {}
        out["rebrowser_before"] = rebrowser_flags(result.get("beforeDetections"))
        out["rebrowser_after"] = rebrowser_flags(result.get("afterDetections"))

    item = load(directory, "deviceandbrowserinfo")
    if item:
        text = target_text(item)
        match = re.search(r'"?isBot"?\s*:\s*(true|false)', text)
        out["dabi_is_bot"] = match.group(1) if match else None
        out["dabi_true_signals"] = len(re.findall(r'"[A-Za-z]+"\s*:\s*true', text))

    item = load(directory, "cloudflare")
    if item:
        text = target_text(item)
        out["cloudflare_passed"] = bool(re.search(r"You bypassed|challenge.*(passed|success)", text, re.I))

    item = load(directory, "fingerprint")
    if item:
        text = target_text(item)
        values = {}
        for key in ["bot", "tampering", "anti_detect_browser", "suspect_score"]:
            match = re.search(rf'(?m)^{key}: "?([^"\n]+)"?$', text)
            values[key] = match.group(1) if match else None
        out["fingerprint"] = values

    item = load(directory, "browserscan")
    if item:
        text = target_text(item)
        match = re.search(r"Test Results:?\s*(\w+)", text)
        out["browserscan"] = match.group(1) if match else ("Normal" if "Normal" in text else None)

    item = load(directory, "incolumitas")
    if item:
        text = target_text(item)
        out["incolumitas_fail"] = sorted(re.findall(r'"(\w+)"\s*:\s*"FAIL"', text))
        out["incolumitas_ok"] = len(re.findall(r'"OK"', text))

    item = load(directory, "recaptcha_v3")
    if item:
        text = target_text(item)
        success = re.search(r'"success"\s*:\s*(true|false)', text)
        score = re.search(r'"score"\s*:\s*([\d.]+)', text)
        out["recaptcha"] = (success and success.group(1), score and float(score.group(1)))

    for name in ["turnstile_managed", "turnstile_noninteractive"]:
        item = load(directory, name)
        if item:
            verification = item.get("turnstile_verification") or {}
            text = page_text(verification.get("observations_after"))
            match = re.search(r'"?success"?\s*:\s*(true|false)', text)
            out[name] = match.group(1) if match else None

    item = load(directory, "tls")
    if item:
        document = item["observations"].get("jsonDocument") or {}
        if isinstance(document, dict):
            document = document.get("value", document)
        document = document if isinstance(document, dict) else {}
        out["tls"] = (document.get("http_version"), (document.get("tls") or {}).get("ja4"),
                      (document.get("http2") or {}).get("akamai_fingerprint_hash"))
    return out


def checks(r):
    """Yield (name, observed, met) against the documented release bar."""
    linux = r.get("os") == "Linux"
    # Linux useragent is tolerated until the client-hint fix is measured there.
    allowed_yellow = {"useragent", "headless"} if linux else set()
    yield "SannySoft failed cells", r.get("sannysoft_failed"), \
        r.get("sannysoft_failed") is not None and r["sannysoft_failed"] <= (1 if linux else 0)
    before = r.get("rebrowser_before")
    yield "Rebrowser before calls (red, yellow)", before, \
        before is not None and before[0] == [] and set(before[1]) <= allowed_yellow
    after = r.get("rebrowser_after")
    yield "Rebrowser after calls (red, yellow)", after, \
        after is not None and after[0] == [] and set(after[1]) <= allowed_yellow
    yield "DeviceAndBrowserInfo isBot / true signals", (r.get("dabi_is_bot"), r.get("dabi_true_signals")), \
        r.get("dabi_is_bot") == "false" and r.get("dabi_true_signals") == 0
    yield "ScrapingCourse Cloudflare demo passed", r.get("cloudflare_passed"), r.get("cloudflare_passed") is True
    fp = r.get("fingerprint") or {}
    yield "Fingerprint playground", fp, fp == {"bot": "not_detected", "tampering": "false",
                                               "anti_detect_browser": "false", "suspect_score": "0"}
    yield "BrowserScan", r.get("browserscan"), r.get("browserscan") == "Normal"
    yield "incolumitas FAIL rows", r.get("incolumitas_fail"), \
        r.get("incolumitas_ok", 0) > 0 and r.get("incolumitas_fail") == ["WEBDRIVER"]
    recaptcha = r.get("recaptcha") or (None, None)
    yield "reCAPTCHA v3 demo (success, score)", recaptcha, \
        recaptcha[0] == "true" and recaptcha[1] is not None and recaptcha[1] >= 0.9
    for name in ["turnstile_managed", "turnstile_noninteractive"]:
        yield f"{name} server success", r.get(name), r.get(name) == "true"
    yield "navigator.webdriver", r.get("webdriver"), r.get("webdriver") is False
    ua = r.get("user_agent") or ""
    yield "User agent has no HeadlessChrome", ua[-45:], bool(ua) and "HeadlessChrome" not in ua
    yield "Screen", r.get("screen"), r.get("screen") == (1920, 1080)
    tls = r.get("tls") or (None, None, None)
    yield "TLS (HTTP, JA4, HTTP/2 hash) recorded", tls, tls[0] == "h2" and all(tls)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("evidence", nargs="+", help="check_detectors.py output directories")
    args = parser.parse_args()
    results = [extract(directory) for directory in args.evidence]
    names = [Path(directory).name for directory in args.evidence]
    all_met = True
    for index, name in enumerate(names):
        print(f"[{index}] {name}  ({results[index].get('chrome')}, {results[index].get('os')})")
    rows = [list(checks(result)) for result in results]
    for position, (label, _, _) in enumerate(rows[0]):
        print(f"\n{label}")
        for index, row in enumerate(rows):
            _, observed, met = row[position]
            all_met = all_met and met
            print(f"  [{index}] {'meets bar' if met else 'REGRESSED'}: {observed}")
    tls_values = {result.get("tls") for result in results}
    chrome_values = {result.get("chrome") for result in results}
    if len(results) > 1 and len(chrome_values) == 1 and len(tls_values) != 1:
        all_met = False
        print("\nTLS differs between runs on the same Chrome build: REGRESSED")
    print("\nResult:", "every run meets the release bar" if all_met else "at least one check regressed or was unreadable")
    return 0 if all_met else 1


if __name__ == "__main__":
    sys.exit(main())
