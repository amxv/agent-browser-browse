# v0.45.0 detector parity check

**Measured on November 27, 2026 (UTC), macOS only.** This is a parity check of the v0.45.0 browsing build against the published v0.43.0 build. Both ran the same public-detector matrix back to back, on the same machine, network and Chrome build. The method, target definitions, privacy rules and interpretation limits are those of the [v0.43.0 verification report](verification-0.43.0.md); this note does not repeat them.

## Builds compared

| Build | Source | Native SHA-256 |
| --- | --- | --- |
| v0.43.0 baseline | Published, installed v0.43.0 release | `fcbdd83c614bf7e6b78b24d857c4c534352b32aecabf0c7d9046ae7646f38939` |
| v0.45.0 candidate | Local `ci` build of upstream [v0.45.0](https://github.com/vercel-labs/agent-browser/releases/tag/v0.45.0) (`f0a98351ec920bd826b22c98dacf8414f04b9832`), patched by `scripts/patch_upstream.py` at `017ef52` | `cc579d26a2ddb55ff5f0f615ce73a4c38fbd561db351cffab009647d9f58799e` |

Environment: macOS 26.3.1 ARM64, Google Chrome **158.0.8127.37** for every capture in both runs. The patch script SHA-256 was `15eeafbba3979871a9bd398111c889ce0f1a4548cfc95dd8e960684215792d19`.

Before the detector runs, the v0.45.0 build passed the loopback browser smoke suite and all 23 Python patch, installer and package regressions.

## Results

Both runs used `--targets all --exercise-rebrowser --verify-turnstile`. Each run captured 13 targets and skipped G2 and ShieldSquare explicitly, as before. All owned sessions closed and the namespace ended empty.

| Target | v0.43.0 on Chrome 158 | v0.45.0 on Chrome 158 |
| --- | --- | --- |
| SannySoft | 0 failed cells | 0 failed cells |
| Rebrowser, before deliberate calls | 15 green, 1 yellow (`useragent`), 0 red, 4 gray | Same |
| Rebrowser, after deliberate calls | 17 green, 1 yellow (`useragent`), 1 red (`mainWorldExecution`), 1 gray | Same |
| DeviceAndBrowserInfo | `isBot: false`; 0 true signals | Same |
| ScrapingCourse Cloudflare demo | Challenge-success content reached | Same |
| Fingerprint | `bot: not_detected`, `tampering: false`, `anti_detect_browser: false`, `suspect_score: 0`, `developer_tools: false` | Same |
| BrowserScan | **Normal** | **Normal** |
| incolumitas | 35 OK, 1 FAIL (legacy `WEBDRIVER`) | Same |
| reCAPTCHA v3 demo | `success: true`, score `0.9` | Same |
| Live managed Turnstile demo | `success: true` after one ordinary Verify click | Same |
| Live non-interactive Turnstile demo | `success: true` after one ordinary Verify click | Same |
| TLS endpoint | HTTP/2; JA4 `t13d1517h2_8daaf6152771_cb7bf5808d99`; same HTTP/2 fingerprint hash | Identical |
| Browser properties | `navigator.webdriver` false; Chrome 158 UA without `HeadlessChrome`; 1920×1080 screen | Same |

v0.43.0 on Chrome 158 reproduced the v0.43.0 report's principal results, and v0.45.0 matched it on every recorded result. The known limitations carry over unchanged: deliberate main-world eval is visible to Rebrowser, the Rebrowser user-agent warning remains, and incolumitas's legacy WebDriver check still fails.

Both harness runs exited 1 ("partial") for the same reason: incolumitas's `open` hit the CLI's 25-second load-state timeout. The page content was still captured and summarized above. This was not a detector verdict.

## Notes on upstream v0.45.0

- `prepare_domains` now enables `Page` before `Runtime`. A new frame-context lookup, used only when evaluating inside a selected same-process iframe, also calls `Runtime.disable` and then `Runtime.enable`. The patch anchors only the domain-initialization sequence and leaves the frame lookup as upstream wrote it. After an in-iframe eval, Runtime can therefore stay enabled for that session. The matrix above does not exercise that path.
- The launch now adds `--disable-renderer-backgrounding`. WebMCP features remain opt-in, as in v0.43.0.

Linux was not re-measured for v0.45.0. Hosted CI builds and tests the Linux package, but no Linux detector matrix was run.

## Reproduce

```bash
python3 scripts/check_detectors.py --binary <v0.43.0 native> --targets all \
  --exercise-rebrowser --verify-turnstile --label baseline-v043
python3 scripts/check_detectors.py --binary <v0.45.0 native> --targets all \
  --exercise-rebrowser --verify-turnstile --label candidate-v045
```

Then compare the two evidence directories with `python3 scripts/compare_detectors.py`, as described in the [detector release bar](detector-release-bar.md). The raw evidence is kept privately under the ignored `dist/evidence/baseline-v043-chrome158-20261127T121428Z-fbb42f/` and `dist/evidence/candidate-v045-chrome158-20261127T121930Z-462cbf/`.

## Improvements after the v0.45.0 release

**Measured on November 27, 2026 (UTC), macOS only, Chrome 158.0.8127.37.** Two patch changes, built on upstream v0.45.0 and not yet in a published release, address the remaining Rebrowser findings:

- **Isolated `eval`.** The default `eval` runs in a fresh isolated world (`Page.createIsolatedWorld`) on the main frame or the selected frame. It shares the DOM but not page globals, so page scripts cannot observe it. `eval --main-world <js>` keeps the previous page-world behavior.
- **Full client hints.** Chrome blanks the high-entropy client hints whenever `--user-agent` is set, which the headless browse build has to do. The patch restores them per target with `Emulation.setUserAgentOverride`: the exact running version from `Browser.getVersion`, the OS version, architecture, and Chromium's GREASE brand list. Dedicated workers inherit the values. The override applies only when the connected browser reports exactly the user agent the daemon injected.

| Check | v0.45.0 release | Improved build |
| --- | --- | --- |
| Rebrowser before deliberate calls | 15 green, 1 yellow (`useragent`), 0 red, 4 gray | **16 green, 0 yellow, 0 red, 4 gray** |
| Rebrowser after deliberate calls | 17 green, 1 yellow, 1 red (`mainWorldExecution`), 1 gray | **16 green, 0 yellow, 0 red, 4 gray** |
| `navigator.userAgentData` high-entropy values | `fullVersionList`, `platformVersion` and `architecture` empty | Match an unmodified headless Chrome (`158.0.8127.37`, `26.3.1`, `arm`, 64-bit) |
| All other release-bar checks | Met | Met |

After the deliberate calls, `dummyFn`, `sourceUrlLeak` and `mainWorldExecution` stay gray: the probes ran in the isolated world, where the page's instrumented functions and its `dummyFn` are not visible. Gray means untriggered, not a pass. The `workerConsistency` and `platformMismatch` checks stayed green.

Other observations:

- **ScrapingCourse Cloudflare demo.** One full-matrix run stayed on Cloudflare's verification page. Three alternating runs each of the released and improved builds then all passed, and the final full matrix passed. The one miss in five runs of the improved build is recorded rather than discarded.
- **Fingerprint.** Every run returned `bot: not_detected`, `tampering: false` (high confidence), `anomaly_score: 0` and `suspect_score: 0`. The tampering ML score was 0.5139 in the final full matrix. In three alternating runs per build, both builds scored only 0.134 or 0.1853, so the 0.5139 was a single high observation, not a consistent shift.
- **Unchanged limitations.** The incolumitas legacy `WEBDRIVER` row still fails; it checks `'webdriver' in navigator`, which is true in every modern Chrome. Linux was not re-measured; the hosted Linux smoke test checks the client hints and the brand list.

Verification of the improved build: all 23 Python regressions; the loopback smoke test, which now also checks isolated versus `--main-world` eval, the restored client hints, and that the generated brand list matches Chrome's own; and all 18 upstream Rust test binaries (2,874 passed, 0 failed, 384 ignored). The final detector matrix exited 0 and met the raised [release bar](detector-release-bar.md) on every check. Native SHA-256 `c1b0a41ce9c04186214df71b8bf71b8e0ace412fd1c4e0b9b987fa8e8da7cd5c`; patch script SHA-256 `5f0df9ae401942dd62fe67617e6c2e00e35c6a3f1f8605c5aa0edaf5d3c0d5a5`. Raw evidence is under the ignored `dist/evidence/final-improved-v045-20261127T142542Z-130bd9/`, `improved-v045-chrome158-*`, `cfab-*` and `fpab-*`.
