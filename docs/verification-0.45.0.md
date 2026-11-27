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

The raw evidence is kept privately under the ignored `dist/evidence/baseline-v043-chrome158-20261127T121428Z-fbb42f/` and `dist/evidence/candidate-v045-chrome158-20261127T121930Z-462cbf/`.
