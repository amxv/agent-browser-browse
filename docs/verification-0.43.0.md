# v0.43.0 verification report

**Measured on November 13, 2026 (UTC).** Local source builds, applicable automated tests, packaging checks and public-detector observations are recorded below. Hosted release and installed-artifact results are tracked separately at the end of this report.

The browsing build completed the selected public observations on macOS ARM64 and Linux x86_64. It did **not** pass every detector: both platforms exposed main-world execution when Rebrowser's documented probe was deliberately invoked; ordinary Linux headless Chrome retained a SwiftShader-related failure; and incolumitas retained a legacy WebDriver failure. These limitations belong alongside the successful observations.

## Source and measured environments

GitHub reported the official release publication time as **2026-11-12 23:09:31 UTC**. This verifies the requested stable release rather than inferring a version from a moving default branch.

The build is based on the official [agent-browser v0.43.0 release](https://github.com/vercel-labs/agent-browser/releases/tag/v0.43.0), with upstream source commit [`1cc19526f3641c8543d55aa6700e7c55b37ac356`](https://github.com/vercel-labs/agent-browser/commit/1cc19526f3641c8543d55aa6700e7c55b37ac356). The Linux work adapts the cross-platform direction in [PR #1, “Port browse build to Linux and Windows”](https://github.com/amxv/agent-browser-browse/pull/1) to this newer upstream version. The relevant Linux work was incorporated while preserving main's newer timeout-location handling. The original branch, including its Windows work, remains preserved. PR closure is recorded after release verification. Windows and Linux ARM64 are outside the measured scope.

| Matrix | Operating system and architecture | Actual Chrome versions | CLI version |
| --- | --- | --- | --- |
| macOS final | macOS 26.3.1, Darwin 25.3.0, ARM64 | 157.0.8103.39, then 157.0.8103.52 | 0.43.0 |
| Linux final | Ubuntu 26.04.1, kernel 7.0.0-42-generic, x86_64 | 152.0.7977.64 throughout | 0.43.0 |

The native files invoked by these matrices had the following SHA-256 values. These identify the measured local build outputs, **not** published release assets:

- macOS: `1dbf6ab522d3ac6a2f7256095ce384f14499374e5cfadc3687543933b7c487e9`
- Linux: `af1d5bbce84aa4165f6056f1f0002a52b5daefc53cb4a6eb0a3d180a5ac1fbd5`

### Chrome updated during the macOS matrix

The browser's own version endpoint recorded a patch-version change during the macOS run. The major-version user-agent remained Chrome 157, so the user-agent alone would not have revealed this change.

| Actual macOS Chrome version | Targets |
| --- | --- |
| 157.0.8103.39 | SannySoft, Rebrowser, DeviceAndBrowserInfo, ScrapingCourse Cloudflare demo, NowSecure, Fingerprint, BrowserScan, incolumitas |
| 157.0.8103.52 | reCAPTCHA v3, official dummy-key Turnstile demo, live managed Turnstile demo, live non-interactive Turnstile demo, TLS endpoint |

The earlier macOS screen experiment and the final Fingerprint/Rebrowser measurements used the same `.39` Chrome build. The later managed Turnstile outcome cannot be attributed solely to launch-configuration changes because its final measurement used `.52`. A same-version `.52` direct-Chrome TLS control was collected separately. The later core-detector rerun entirely on `.52` is recorded in its own section below; it does not replace this mixed-version matrix.

## Method and scope

Each full matrix contained **15 target entries: 13 captures and 2 explicit skips**. Each captured target used a fresh named session in a private namespace, an empty explicit config, no saved account state, and one navigation. The harness removed inherited `AGENT_BROWSER_*` settings, used short private socket paths, bounded each observation window and command, and closed only sessions it created. Both final matrices exited with code 0 and ended with an empty owned namespace. A zero harness exit means collection completed; it is not an all-detectors-pass assertion.

The final default measurements were headless. They used the browsing build's stable-Chrome discovery, version-aware user-agent startup argument, `AutomationControlled` Blink setting, 1920×1080 virtual screen, normal popup blocking, and immediate `Runtime.disable` after the four patched initialization points. The harness used an explicit two-minute idle backstop in addition to normal cleanup. Chromium documents native headless virtual-screen configuration through [`--screen-info`](https://chromium.googlesource.com/chromium/src/+/main/components/headless/screen_info/README.md); the [Chrome headless-screen guide](https://developer.chrome.com/docs/automation-and-testing/headless-screen-config) describes its availability and behavior.

The measurements did not modify Chromium source or binaries, spoof page-global properties, replace detector results, disable CSP or TLS verification, select signed-in profiles, or take over shared browsers. No production-site restriction was bypassed. GPU experiments used separate scoped launches, described below; they did not change the default matrix or global host security policy.

The primary evidence is command stdout/stderr, exit status, rendered text, DOM result rows and status classes, accessibility snapshots, and a read-only browser-property probe. The probe records `navigator.webdriver`, plugins, `window.chrome`, user-agent/client hints, screen and viewport values, and related observable properties. It does not modify those properties. Browser versions come from the owned browser's metadata endpoint. Screenshots are optional supporting artifacts; no conclusion here depends on an uninspected screenshot.

There are two explicit optional actions:

- `--exercise-rebrowser` records the detector's JSON before the three documented calls, invokes those calls through the CLI's actual `eval` path, and records the JSON afterward. It does not inject an exposed callback or substitute an isolated context to change the result.
- `--verify-turnstile` applies only to the two specified live demo targets. It requires the expected non-test sitekey, the expected demo URL, and a naturally issued nonempty response. It then clicks the ordinary **Verify with Cloudflare** form button once, waits five seconds, and records the page again. It never clicks a CAPTCHA checkbox, extracts or replays a token, calls a solver, or resets the widget. Without a natural response it records an explicit skip.

Token values are not evidence fields: response inputs are represented by presence and length. Output redaction also masks token-like strings and displayed prefixes. Raw private artifacts can still contain network/device identifiers and must be reviewed before sharing; they are ignored under `dist/evidence/`. This public report contains no IP addresses, visitor identifiers, token values, account names, or personal filesystem paths.

## Final public-detector matrix

These are one-run observations under the stated conditions, not success-rate estimates.

| Target | macOS final observation | Linux final observation | Interpretation |
| --- | --- | --- | --- |
| [SannySoft](https://bot.sannysoft.com/) | 0 failed result cells | 1 failed cell associated with the SwiftShader WebGL renderer | Ordinary Linux default retains a software-rendering signal. A separate hardware-rendering experiment is below. |
| [Rebrowser](https://bot-detector.rebrowser.net/) — automatic checks before deliberate calls | 15 green, 1 yellow, 0 red, 4 gray | 14 green, 2 yellow, 0 red, 4 gray | Gray tests were untriggered, not passes. |
| Rebrowser — after deliberate documented calls | 17 green, 1 yellow, 1 red, 1 gray | 16 green, 2 yellow, 1 red, 1 gray | `mainWorldExecution` red on both; the CLI's actual eval path is observable. |
| [DeviceAndBrowserInfo](https://deviceandbrowserinfo.com/are_you_a_bot) | `isBot: false`; 0/22 true signal details | `isBot: false`; 0/22 true signal details | `isAutomatedWithCDP` and `isAutomatedWithCDPInWebWorker` were false on both. |
| [ScrapingCourse Cloudflare demo](https://www.scrapingcourse.com/cloudflare-challenge) | Expected challenge-success content reached | Expected challenge-success content reached | Limited to this deliberately protected test page. Navigation success alone was not the criterion. |
| [NowSecure](https://nowsecure.nl/) | Page loaded; embedded known test-key Turnstile observed | Page loaded; embedded known test-key Turnstile observed | Load-only observation, not an independent live-detector all-clear. |
| G2 | Skipped | Skipped | Historical blocked production-site observation retained; no renewed bypass attempt. |
| [Fingerprint playground](https://demo.fingerprint.com/playground) | `bot: not_detected`, `tampering: false`, `anti_detect_browser: false`, `suspect_score: 0` | Same four results | Individual server-event observations; other signals and future decisions can differ. |
| [BrowserScan](https://www.browserscan.net/bot-detection) | Displayed **Normal** | Displayed **Normal** | The displayed detector result, not a claim about all sites. |
| [incolumitas](https://bot.incolumitas.com/) | Newer checks 9/9 OK; Intoli 6/6 OK; legacy `WEBDRIVER` FAIL; behavioral score unavailable | Same principal results | macOS legacy scanner: 20 OK and 1 FAIL. No all-pass or proven-false-positive claim is made for the remaining failure. |
| [Google reCAPTCHA v3 demo](https://recaptcha-demo.appspot.com/recaptcha-v3-request-scores.php) | Demo backend `success: true`, score `0.9` | Demo backend `success: true`, score `0.9` | The sample explicitly disclaims treating its score as an assessment of production traffic or an account. |
| [Official Cloudflare Workers Turnstile demo](https://demo.turnstile.workers.dev/) | Dummy-key widget response observed; verification skipped | Same | Plumbing only: the known always-pass test key supplies no live detector verdict. |
| [Live advertised managed Turnstile demo](https://zerocaptcha.io/captcha-test/cloudflare-turnstile-managed) | Natural response, then demo backend UI `success: true` after one ordinary Verify click | Same | No CAPTCHA checkbox interaction; see exact returned fields below. |
| [Live advertised non-interactive Turnstile demo](https://zerocaptcha.io/captcha-test/cloudflare-turnstile-non-interactive) | Natural response, then demo backend UI `success: true` after one ordinary Verify click | Same | No CAPTCHA interaction; mode is advertised by the demo owner. |
| ShieldSquare / Radware | Skipped | Skipped | No current authorized public detector demo was verified. Vendor sales pages were not treated as tests. |
| [TLS observation endpoint](https://tls.peet.ws/api/all) | HTTP/2, TLS 1.3; stable fields matched a direct same-version Chrome control | Initial direct control had a JA4/JA3 difference; a matched-launch follow-up matched stable fields and all 17 non-GREASE extensions | Both paired comparisons are bounded; retain the initial Linux mismatch and distinguish extension order from stable fields. |

### Separate macOS rerun on Chrome 157.0.8103.52

After the installed Chrome update, the README targets plus Fingerprint, BrowserScan and incolumitas were revisited in fresh sessions. **Every captured target reported actual Chrome 157.0.8103.52.** This separate run completed at 03:05:54 UTC with exit code 0: **8 captures, 1 explicit G2 skip, all owned sessions closed, and an empty final namespace**. The deliberate Rebrowser probes were enabled.

| Target | Separate `.52` observation |
| --- | --- |
| SannySoft | 0 failed result cells. |
| Rebrowser before deliberate calls | 15 green, 1 yellow (`useragent`), 0 red, 4 gray. |
| Rebrowser after deliberate calls | 17 green, 1 yellow (`useragent`), 1 red (`mainWorldExecution`), 1 gray (`exposeFunctionLeak`). `dummyFn` returned true; the element lookup succeeded; the class lookup returned length 0. |
| DeviceAndBrowserInfo | `isBot: false`; 0/22 true signal details. Both CDP fields remained false. |
| ScrapingCourse Cloudflare demo | Expected challenge-success content reached. |
| NowSecure | Page loaded; known test-key widget observed. Still a load-only observation. |
| G2 | Explicitly skipped; no production-site bypass attempt. |
| Fingerprint | `bot: not_detected`, `tampering: false`, `anti_detect_browser: false`, `suspect_score: 0`, `developer_tools: false`; tampering ML score `0.0607`, high confidence; anomaly score `0`. |
| BrowserScan | Displayed **Normal**. |
| incolumitas | Newer checks: 9 OK / 0 FAIL. Intoli: 6 OK / 0 FAIL. Legacy scanner: 20 OK / 1 FAIL (`WEBDRIVER`). Behavioral score remained unavailable (`...`). |

The principal results persisted on `.52`, including the limitations: actual main-world eval remained detectable, and the legacy incolumitas failure and missing behavioral score remained. The changed Fingerprint ML score is another single observation, not evidence that the Chrome update caused a model change. reCAPTCHA, live Turnstile and TLS were not revisited by this core-target rerun; their separate `.52` measurements remain in the full matrix and TLS-control sections.

Reproduction for this subset:

```bash
python3 scripts/check_detectors.py --binary agent-browser-browse \
  --targets readme,fingerprint,browserscan,incolumitas \
  --exercise-rebrowser --label current-chrome-v043
```

### Browser-property and user-agent observations

The final default captures and the separate macOS `.52` rerun recorded the following directly:

| Property | macOS | Linux |
| --- | --- | --- |
| `navigator.webdriver` | Boolean `false` | Boolean `false` |
| `navigator.plugins.length` | 5 PDF-viewer entries | 5 PDF-viewer entries |
| `typeof window.chrome` | `object` | `object` |
| `typeof window.chrome.runtime` | `undefined` | `undefined` |
| JavaScript user-agent / appVersion | Chrome 157; no `HeadlessChrome` token | Chrome 152; no `HeadlessChrome` token |
| Server-observed HTTP user-agent at TLS endpoint | Chrome 157; no `HeadlessChrome` token | Chrome 152; no `HeadlessChrome` token |
| Virtual screen / device pixel ratio | 1920×1080 / 1 | 1920×1080 / 1 |
| High-entropy UA `fullVersionList` | Empty | Empty |

The startup user-agent override has a remaining client-hint limitation: full-version, platform-version, architecture and bitness values were empty in these captures. Rebrowser's yellow version-detection warning is disclosed above. The plugin and `window.chrome` observations are concrete values, not evidence of a complete indistinguishable browser identity. No property getter was replaced by the harness.

### Rebrowser: automatic results and actual eval behavior

The [official test instructions](https://github.com/rebrowser/rebrowser-bot-detector/blob/main/index.html) prescribe calls to `window.dummyFn()`, `document.getElementById('detections-json')`, and `document.getElementsByClassName('div')`. The [detector source](https://github.com/rebrowser/rebrowser-bot-detector/blob/main/index.js) instruments the latter DOM methods. The harness first reads the existing JSON with `querySelector`, then records before/after arrays around the actual calls.

On both systems, `dummyFn` returned true, the element lookup succeeded, and the class lookup returned an empty collection. `dummyFn` and `sourceUrlLeak` became green. `mainWorldExecution` became red, demonstrating that normal CLI eval executes in a context the page can instrument. The remaining gray `exposeFunctionLeak` is unexercised because this workflow exposes no callback; inventing one would not describe the tested workflow.

`runtimeEnableLeak`, `navigatorWebdriver`, and `popupBlocking` were green on both final matrices. macOS retained the yellow `useragent` check, whose note said it could not determine the Chrome version. Linux also retained the yellow `headless` check, with software-rendering/pointer signals. The absence of automatic red checks must not be presented without the deliberate-call result.

### Fingerprint values and the scoped screen experiment

| Measurement | Chrome | Screen configuration | Bot result | Tampering / anti-detect | Tampering ML score | Suspect score |
| --- | --- | --- | --- | --- | --- | --- |
| Initial macOS v0.43 candidate | 157.0.8103.39 | Observed 800×600 default screen | `not_detected` | Both true | 0.9344, medium confidence | 5 |
| macOS explicit screen/window experiment | 157.0.8103.39 | 1920×1080 screen; 1280×720 outer window | `not_detected` | Both false | 0.0969, high confidence | 0 |
| Final macOS defaults | 157.0.8103.39 | Native 1920×1080 virtual screen | `not_detected` | Both false | 0.1712, high confidence | 0 |
| Final Linux defaults | 152.0.7977.64 | Native 1920×1080 virtual screen | `not_detected` | Both false | 0, high confidence | 0 |

The measured macOS override was `--screen-info={1920x1080 devicePixelRatio=1},--window-size=1280,720`. Its actual inner viewport was 1280×633. Rebrowser's screen/headless warning disappeared in that run; the separate final popup-policy change also made its popup check green.

This is an observed association in a small ordered comparison, not proof that screen size is the sole input to Fingerprint's proprietary model. The initial anomaly score was zero even while anti-detect detection was true; those are distinct signals. Final anomaly scores were 0 on macOS and 0.0151 on Linux. No page-global spoofing was used to produce the changed screen values.

### Live Turnstile issuance versus server verification

The two [purpose-built demo pages](https://zerocaptcha.io/captcha-test) advertise separate managed and non-interactive widgets and embed distinct non-test-pattern sitekeys. Widget mode is configured in Cloudflare's dashboard, so the advertised mode cannot be independently established from static HTML alone. Cloudflare distinguishes [widget modes](https://developers.cloudflare.com/turnstile/concepts/widget/) and [dummy testing keys](https://developers.cloudflare.com/turnstile/troubleshooting/testing/).

In each final real-demo session, the initial capture showed a naturally issued response of length 730 and a verification result of **not checked yet**. After one ordinary Verify button click, the site's rendered backend result changed as follows:

| Platform and advertised mode | `success` | `hostname` | `challenge_ts` (UTC) | `action` / `cdata` / `error-codes` |
| --- | --- | --- | --- | --- |
| macOS managed | true | `zerocaptcha.io` | 2026-11-13T02:46:58Z | none / none / none |
| macOS non-interactive | true | `zerocaptcha.io` | 2026-11-13T02:47:20Z | none / none / none |
| Linux managed | true | `zerocaptcha.io` | 2026-11-13T02:49:27Z | none / none / none |
| Linux non-interactive | true | `zerocaptcha.io` | 2026-11-13T02:49:50Z | none / none / none |

These are **site-rendered backend/Siteverify results**, preserved in before/after text and snapshots. The harness did not separately capture the backend's raw HTTP response. A token's presence, a successful CLI click, and a server verification result are different observations; only the last supports the stated server-success result.

An earlier macOS managed-demo session showed a human-verification checkbox and no response. It was left untouched and closed. The later natural completion does not erase that result or establish a success rate. The Chrome patch-version change, session conditions, network conditions and detector decisions prevent a sole-cause attribution to launch flags.

The official Workers demo used the known always-pass key. The separately inspected 2Captcha Turnstile demo used a known force-interaction test key. Neither was substituted for a real-detector result, and no solver service was used.

## Linux rendering experiments — separate from the default result

The default Linux matrix used SwiftShader and retained one SannySoft failure. Read-only host inspection found Intel HD Graphics 520 hardware but insufficient render-device access for the ordinary browser process. The following bounded experiments were kept separate:

| Scoped experiment | Launch arguments added | Observed result |
| --- | --- | --- |
| Headless ANGLE/OpenGL attempt | `--enable-gpu,--use-gl=angle,--use-angle=gl,--screen-info={1920x1080 devicePixelRatio=1}` | Still SwiftShader; did not resolve the default renderer failure. |
| Isolated Xvfb attempt, 1920×1080×24 | `--enable-gpu,--use-gl=angle,--use-angle=gl,--ozone-platform=x11` | WebGL unavailable; two SannySoft failed cells. No shared desktop/browser was used. |
| Native Vulkan without additional render-device access | `--enable-gpu,--use-angle=vulkan,--use-vulkan=native,--enable-features=Vulkan,--disable-vulkan-surface` | WebGL unavailable. This flag combination alone did not establish working hardware acceleration. |
| Same UID, existing permitted render-group access, native Vulkan | Same native Vulkan arguments | Actual Intel HD Graphics 520 / Mesa Vulkan renderer; zero SannySoft failed cells. |

The successful last experiment remained headless, with no Xvfb or display override. It changed only the owned browser process's group context through already permitted noninteractive authority. It did not change persistent group membership, ACLs, AppArmor, drivers, the sandbox, or global policy. Its Rebrowser runtime-leak check remained green, but deliberate main-world execution remained red; `pointer:none` and the user-agent warning also remained. **This conditional result is not the ordinary Linux default result and was not adopted as a default.**

A sanitized equivalent requires a host-specific existing render device and Chrome executable. Stop if the exact noninteractive permission check is denied; this procedure does not authorize changing policy or requesting credentials:

```bash
# Supply these from the local environment; do not copy another host's paths.
export RENDER_NODE='<existing authorized render device>'
export CHROME_BINARY="$(command -v google-chrome-stable)"
BROWSE_BINARY="$(command -v agent-browser-browse)"

sudo -n -u "#$(id -u)" -g "#$(stat -c %g "$RENDER_NODE")" id
```

An executable, task-owned `chrome-render-group.sh` wrapper contains:

```sh
#!/bin/sh
exec sudo -n -u "#$(id -u)" -g "#$(stat -c %g "$RENDER_NODE")" \
  "$CHROME_BINARY" "$@"
```

With `TEST_ROOT` pointing to the directory containing that owned wrapper:

```bash
python3 scripts/check_detectors.py --binary "$BROWSE_BINARY" \
  --targets sannysoft,rebrowser --exercise-rebrowser \
  --label linux-render-group \
  --executable-path "$TEST_ROOT/chrome-render-group.sh" \
  --browser-args='--enable-gpu,--use-angle=vulkan,--use-vulkan=native,--enable-features=Vulkan,--disable-vulkan-surface'
```

## TLS controls and comparison limits

The TLS target navigates the browser to the public JSON endpoint and records what that server observes. It does not infer TLS consistency from a browser-property probe.

For macOS, the final harness capture and a direct, fresh-profile Chrome **157.0.8103.52** control used the same machine, network and actual Chrome build. The direct launch used no CDP controller. TLS 1.3, HTTP/2, JA4, the HTTP/2 fingerprint, all 15 non-GREASE cipher suites in order, the reported user-agent, and the four compared UA/client-hint headers matched. The raw cipher difference was the GREASE value; JA3 differed only in extension order, with the extension multiset and remaining components matching. This supports that pair's stable-field agreement, not universal TLS consistency.

For Linux, a direct headless Chrome **152.0.7977.64** control matched the final harness's server-reported user-agent, TLS 1.3, HTTP/2 fingerprint and all 15 non-GREASE cipher suites. **JA4 and JA3 differed.** The JA4-encoded extension count differed between the captures. That initial native response was not retained in full, so its exact extra extension remains unconfirmed. This initial comparison alone does not establish Linux TLS consistency. The controls used owned fresh profiles and did not weaken sandbox settings.

An offline reconstruction found that adding the `pre_shared_key` extension to the retained browser-side extension set reproduced the native comparison's JA4 suffix. This suggests TLS resumption state as a possible explanation, but it is an **inference**: the native response's raw extension list was not retained in that comparison. A single follow-up retained both raw extension lists and aligned the direct launch more closely with the normal CLI launch. It matched the user-agent, TLS 1.3, JA4 (`t13d1517h2_8daaf6152771_cb7bf5808d99`), HTTP/2 fingerprint, all 15 non-GREASE cipher suites in order, and all 17 non-GREASE extensions. Neither follow-up extension list contained `pre_shared_key`. GREASE values and extension order differed, so raw JA3 still differed. This measured follow-up supports stable-field agreement for that pair; it does not establish the unretained original extension list or retroactively turn the first comparison into a pass.

## Reproduction and evidence index

Run the full matrix with the intended native build or installed wrapper:

```bash
python3 scripts/check_detectors.py --list-targets
python3 scripts/check_detectors.py --binary agent-browser-browse \
  --targets all --exercise-rebrowser --verify-turnstile \
  --label verification-v043
```

To record only the supplemental probes:

```bash
python3 scripts/check_detectors.py --binary agent-browser-browse \
  --targets rebrowser,turnstile_managed,turnstile_noninteractive \
  --exercise-rebrowser --verify-turnstile --label supplemental-v043
```

To explicitly select the screen/window configuration for a scoped comparison:

```bash
python3 scripts/check_detectors.py --binary agent-browser-browse \
  --targets rebrowser,fingerprint --label screen-comparison \
  --browser-args='--screen-info={1920x1080 devicePixelRatio=1},--window-size=1280,720'
```

The final build already supplies a 1920×1080 headless screen by default; the last command selects that configuration explicitly and is not a recreation of the older 800×600 baseline. `--browser-args` and `--executable-path` are logged per-run overrides, not persistent config edits. Do not interpret a later run as equivalent without checking browser version, platform, configuration and rendered detector output.

| Evidence set | Relative ignored location |
| --- | --- |
| Initial macOS candidate matrix | `dist/evidence/mac-v043-20261113T022309Z-821e21/` |
| macOS scoped screen comparison | `dist/evidence/mac-screen-20261113T022945Z-7be50c/` |
| Earlier macOS supplemental probes, including managed no-token result | `dist/evidence/mac-supplemental-20261113T023557Z-894aee/` |
| Final macOS matrix | `dist/evidence/mac-final-v043-20261113T024341Z-920c8c/` |
| Separate macOS core-target rerun entirely on Chrome `.52` | `dist/evidence/mac-current-chrome-v043-20261113T030305Z-f1c70d/` |
| Final Linux matrix | `dist/evidence/linux-final-v043-20261113T024628Z-64f002/` |
| Separate Linux render-group/Vulkan experiment | `dist/evidence/linux-final-render-group-20261113T025144Z-8993a1/` |
| Direct macOS Chrome `.52` TLS control and comparison | `dist/evidence/mac-direct-chrome-tls-final-20261113T025210Z-eda936/` |
| Linux initial direct-Chrome TLS comparison summary | `dist/evidence/linux-final-v043-20261113T024628Z-64f002/native-tls-comparison.json` |
| Linux matched-launch TLS follow-up with retained extension lists | `dist/evidence/linux-final-v043-20261113T024628Z-64f002/native-tls-followup.json` |

Locations are relative to each platform's task checkout; raw evidence is not committed. `run.json` contains the run metadata and command records, with separate target JSON files. Rebrowser's `manual_exercise.result.result` contains `beforeDetections`, `calls` and `afterDetections`. Turnstile's `turnstile_verification` contains the initial/final observations, click status and skip reasons. The latest reviewed harness also masks displayed truncated response prefixes; raw artifacts from earlier revisions require the same privacy review before export.

## Source-build and automated verification

Both hosts built the actual upstream dashboard before compiling the final patched native executable. The final native `ci` build completed in about 5m20 on macOS and 4m24 on Linux; both loopback smoke runs exited 0. The smoke covers navigation, input, snapshots, tabs, state export, an explicit empty profile, default browser properties, popup policy, virtual-screen override, custom Blink arguments, and both user-agent override paths. It closes only its own sessions.

| Check | macOS | Linux |
| --- | --- | --- |
| Native build and real embedded dashboard | Passed | Passed |
| Loopback browser smoke | Passed | Passed |
| Python patch / installer / package regression tests | 23 passed | 23 passed |
| Main Rust unit binary | 2,061 passed, 0 failed, 207 ignored | 2,064 passed, 0 failed, 206 ignored |
| All 15 applicable Rust test binaries combined | **2,133 passed, 0 failed, 215 ignored** | **2,136 passed, 0 failed, 214 ignored** |
| Final local package architecture / provenance | ARM64 Mach-O and ad-hoc signature verified | x86_64 ELF verified |
| Source generation | Exact v0.43.0 plus five intended patched Rust files | Byte-for-byte match with canonical generation |

The ignored counts are upstream's explicitly ignored browser/integration tests. They were not enabled and are not counted as passes. The local smoke and the separately documented public-detector matrix do not imply that every upstream browser e2e case passed. The official [release build](https://github.com/vercel-labs/agent-browser/actions/runs/43312165274) succeeded; its separate [commit CI run](https://github.com/vercel-labs/agent-browser/actions/runs/43312165338) had failing jobs and is not represented as wholly green here.

An initial macOS full run had two failed assertions because it inherited the user's saved executable path and idle timeout. No saved config was edited. The final isolated serial runner used a temporary empty config and removed inherited browser overrides; every applicable test then passed. Linux's completed run used the same low-memory compiler settings with two test threads and passed without a config-related failure. The committed runner and hosted workflow use one test thread to avoid process-environment races. Earlier optimized test compilations were stopped after memory pressure; no canceled run is counted as a pass.

Reproduce with the [README source-build steps](../README.md#reproduce-a-source-build), then:

```bash
PATCHED_UPSTREAM_ROOT="$PWD/upstream" python3 -m unittest discover -s scripts -p 'test_*.py' -v
python3 scripts/run_upstream_tests.py upstream
python3 scripts/smoke.py upstream/cli/target/ci/agent-browser --version 0.43.0
python3 scripts/package.py darwin-arm64 v0.43.0
# On the Linux build host: python3 scripts/package.py linux-x86_64 v0.43.0
```

The patch script's SHA-256 is `0e7adc3309844070a846fa6985880189007ba5fcb9ac230e5f3e5c50ed42111b`. Both packages record upstream commit `1cc19526f3641c8543d55aa6700e7c55b37ac356` and version `0.43.0`. The local macOS archive checksum is `078cdf49431179bec38aaf025b042d0cb7cc23c009fe624d0aa231983807aa9c`; its separately ad-hoc-signed packaged binary checksum is `7b8accedd7ff37ffda327e3000fc2911b968d40a4145b6a7fdf34a3cf1e9e72b`. The local Linux archive checksum is `e7b9c2dffb289b0198856228be6e94e010923c8de8504358b081082c3c93a44c`. These are local validation artifacts; the Ubuntu 26.04 build is not substituted for the release's Ubuntu 24.04 baseline.

Installer regressions cover multi-platform manifests, checksum rejection, archive path/link rejection, provenance, architecture, preservation of existing versions/config, active-session protection, and customized-wrapper conflicts. Every embedded installer Python invocation uses isolated mode; a regression proves that inherited `PYTHONOPTIMIZE=1` cannot bypass a bad checksum. Packaging and checksum-merging integrity checks raise explicit errors rather than relying on assertions. Shell syntax, workflow lint and whitespace checks passed.

## Publication and installation record

Local verification is complete. The authorized normal main push, hosted macOS ARM64/Ubuntu 24.04 x86_64 release builds, installation of those published artifacts on both machines, and PR #1 closure are the remaining publication steps. No published-release or installed-version success is claimed by this prepublication record; this section will be updated with their observed results.

Remaining detector findings are disclosed results: main-world eval visibility, the ordinary Linux software-renderer signal, the legacy incolumitas failure, incomplete behavioral scoring, and the limits of the TLS comparisons. No result supports a claim that browser automation is undetectable.
