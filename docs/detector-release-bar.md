# Detector release bar

Every new browse release should meet this bar before it is published as equivalent to the last verified release.

| Bar | Set by | Evidence |
| --- | --- | --- |
| Original | v0.43.0 | [v0.43.0 report](verification-0.43.0.md) (macOS and Linux) |
| Parity | v0.45.0 as first released | [v0.45.0 parity check](verification-0.45.0.md) |
| **Current** | v0.45.0 rebuilt with isolated `eval` and full client hints | [Improvements after v0.45.0](verification-0.45.0.md#improvements-after-the-v0450-release) (macOS) |

These are public third-party detectors, so they can change, and results depend on Chrome version, network and session history. Treat a miss as a reason to investigate, not automatic proof that the build regressed. The bar checks against known results. It is not a claim that the browser is undetectable.

## How to run

Run the previous release and the candidate **back to back on the same machine, network and Chrome build**. Without a same-day baseline, a detector or Chrome change cannot be told apart from a build regression. Don't run two matrices at the same time.

```bash
# 1. Build the candidate (see AGENTS.md "Build and test locally"), then run the smoke suite.
python3 scripts/smoke.py upstream/cli/target/ci/agent-browser --version <X.Y.Z>

# 2. Baseline: the previous release's native binary, either installed
#    (~/.local/share/agent-browser-browse/versions/<previous>/agent-browser-browse-native)
#    or downloaded with `gh release download v<previous>` into an empty directory,
#    checked against SHA256SUMS and extracted.
python3 scripts/check_detectors.py --binary <previous native binary> \
  --targets all --exercise-rebrowser --verify-turnstile --label baseline-<previous>

# 3. Candidate.
python3 scripts/check_detectors.py --binary upstream/cli/target/ci/agent-browser \
  --targets all --exercise-rebrowser --verify-turnstile --label candidate-<X.Y.Z>

# 4. Compare both evidence directories against the bar.
python3 scripts/compare_detectors.py dist/evidence/baseline-<...> dist/evidence/candidate-<...>
```

`compare_detectors.py` exits 0 only when every run meets every check below. It also flags a TLS difference between runs on the same Chrome build. Its extraction is heuristic, so when a check fails, read the target's JSON (text, DOM, snapshot) before concluding anything.

A `check_detectors.py` exit code of 1 ("partial") is not a detector result by itself. It means some CLI command failed. A known benign cause is incolumitas's slow page hitting the 25-second `open` load timeout while the page is still captured. Look at the failing command in the target's JSON.

### When a single check misses

Live detectors occasionally give one-off results, for example a Cloudflare demo that stays on its verification page, or one high Fingerprint `tampering_ml_score`. Before calling it a regression, rerun only that target three times each, alternating baseline and candidate:

```bash
python3 scripts/check_detectors.py --binary <binary> --targets <target> --label ab-<build>-<n>
```

It is a regression only if the candidate misses consistently and the baseline does not. Record one-off misses in the verification report instead of discarding them.

## The bar

Results are for the default headless configuration, with no extra browser arguments and the default (isolated) `eval`.

| # | Target | Required result (macOS) | Linux difference |
| --- | --- | --- | --- |
| 1 | [SannySoft](https://bot.sannysoft.com/) | 0 failed result cells | At most 1, the SwiftShader WebGL renderer cell |
| 2 | [Rebrowser](https://bot-detector.rebrowser.net/), before deliberate calls | 0 red, 0 yellow (16 green, 4 gray) | `headless` yellow allowed. `useragent` yellow tolerated until Linux is re-measured with the client-hint fix |
| 3 | Rebrowser, after `--exercise-rebrowser` calls | 0 red, 0 yellow. `runtimeEnableLeak`, `navigatorWebdriver`, `useragent`, `workerConsistency` and `popupBlocking` are green. `dummyFn`, `sourceUrlLeak`, `mainWorldExecution` and `exposeFunctionLeak` stay gray (untriggered) because the probes run in the isolated world | Same as row 2 |
| 4 | [DeviceAndBrowserInfo](https://deviceandbrowserinfo.com/are_you_a_bot) | `isBot: false`, 0 true signals (both CDP fields false) | Same |
| 5 | [ScrapingCourse Cloudflare demo](https://www.scrapingcourse.com/cloudflare-challenge) | Challenge-success content reached | Same |
| 6 | [Fingerprint playground](https://demo.fingerprint.com/playground) | `bot: not_detected`, `tampering: false`, `anti_detect_browser: false`, `suspect_score: 0` | Same |
| 7 | [BrowserScan](https://www.browserscan.net/bot-detection) | Displays **Normal** | Same |
| 8 | [incolumitas](https://bot.incolumitas.com/) | The only FAIL is the legacy `WEBDRIVER` row (newer checks 9/9 OK, Intoli 6/6 OK) | Same |
| 9 | [reCAPTCHA v3 demo](https://recaptcha-demo.appspot.com/recaptcha-v3-request-scores.php) | `success: true`, score at least `0.9` | Same |
| 10 | [Managed Turnstile demo](https://zerocaptcha.io/captcha-test/cloudflare-turnstile-managed) | Natural token, then server `success: true` after one ordinary Verify click | Same |
| 11 | [Non-interactive Turnstile demo](https://zerocaptcha.io/captcha-test/cloudflare-turnstile-non-interactive) | Same as row 10 | Same |
| 12 | [TLS endpoint](https://tls.peet.ws/api/all) | HTTP/2; JA4 and HTTP/2 fingerprint identical to the baseline on the same Chrome build | Same |
| 13 | Browser properties (recorded on every target) | `navigator.webdriver === false`; user agent without `HeadlessChrome`; screen 1920×1080 | Same |
| 14 | Client hints (`navigator.userAgentData`) | `fullVersionList` reports the running Chrome's exact version for `Google Chrome` | Same |

Observed only, with no pass criterion: NowSecure (it embeds a known Turnstile test key) and the official Workers Turnstile demo (its dummy key always passes). G2 and ShieldSquare are skipped deliberately.

## Known accepted limitations

These are part of the bar. A release does not need to fix them, but it must not add new ones:

- **incolumitas legacy `WEBDRIVER`.** The old fp-scanner check fails when `'webdriver' in navigator`, which is true in every modern Chrome, including ordinary ones. Passing it would mean deleting a native property, which Fingerprint flags as tampering. Its behavioral score is also unavailable without interaction.
- **Linux software rendering.** On ordinary Linux headless Chrome, the SwiftShader renderer trips one SannySoft cell and the Rebrowser `headless` warning. A fix depends on the host's GPU access, not on the patch.
- **`eval --main-world`.** It deliberately runs in the page's world, so Rebrowser's `mainWorldExecution` turns red when it is used. The bar measures the default `eval`.

## Where regressions usually come from

Most upstream changes that would break the bar affect the patched behaviors in `scripts/patch_upstream.py`. Check these first:

- **New `Runtime.enable` calls** that are not followed by `Runtime.disable`. These turn Rebrowser's `runtimeEnableLeak` red. Run `grep -rn '"Runtime.enable"' cli/src` and review every non-test hit.
- **Eval path changes** in `handle_evaluate` (`actions.rs`) or the `eval` parser (`commands.rs`) that bypass the isolated world. Rebrowser's `mainWorldExecution` turns red.
- **Launch argument changes** in `cli/src/native/cdp/chrome.rs` `build_chrome_args`: new flags, `--disable-popup-blocking`, screen and window size, `--enable-features` merging.
- **Browser discovery or headless changes** that bypass the stable-Chrome preference or the startup user-agent injection.
- **Target initialization changes** in `prepare_domains` or `enable_domains_direct` (`browser.rs`). The client-hint override is sent there; if it is skipped, Rebrowser's `useragent` turns yellow and row 14 fails.
- **Client-hint drift.** The patch rebuilds Chrome's GREASE brand list from Chromium's algorithm. If Chrome changes it, `smoke.py` fails its brand comparison; port the new algorithm from `components/embedder_support/user_agent_utils.cc`.

Record each release's result in `docs/verification-<version>.md`, using the v0.45.0 report as the template.
