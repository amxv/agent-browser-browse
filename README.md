# agent-browser-browse

An **unofficial, browsing-focused** build of [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser), with **macOS ARM64, Linux x86_64, and Windows x86_64** build targets. It complements the official CLI rather than replacing it. Availability of new platform assets depends on successful CI and subsequent publication; a PR alone does not publish them.

| Command | Use case | CDP Runtime events |
| --- | --- | --- |
| `agent-browser` | Develop/test web applications, inspect console logs and page errors | Enabled, upstream behavior |
| `agent-browser-browse` | Browse public websites, research, extract data or interact with sites | Disabled after initialization (limited console/page-error streams) |

The browsing build retains normal CLI operations (`open`, `snapshot`, `click`, `eval`, etc.) and applies these defaults without per-agent flags:

- **Stable Google Chrome** on macOS, Linux, or Windows if installed, falling back to upstream Chrome discovery if not.
- **Headless** unless you deliberately pass `--headed`.
- **`--disable-blink-features=AutomationControlled`** on Chrome launches.
- **Platform-matched Chrome user-agent in headless mode**, derived from the installed stable Chrome version at runtime (rather than hard-coding a version or overriding with CDP). Explicit user-agent options retain precedence. If the Chrome version is unavailable, this step is skipped rather than guessing.
- **15-minute default idle timeout**, with explicit CLI/env overrides still supported.
- **`Runtime.enable` followed immediately by `Runtime.disable`** in four relevant CDP initialization paths, reducing detectable runtime instrumentation, at the cost of console and page-error event streaming. This is a pragmatic compatibility patch, not a guarantee against bot detection.

No cookies, profiles, or other account state are selected by default. The local `agent-browser-browse` command is a wrapper that **isolates its daemon/socket namespace** from the upstream CLI and uses an empty browse-specific config, so your global agent-browser config cannot accidentally interfere. Users may still explicitly override flags and config.

## Platform support and evidence

| Platform | Binary / install helper | Evidence so far |
| --- | --- | --- |
| macOS ARM64 | `darwin-arm64`; existing `scripts/install-macos.sh` | Native 0.41.1 and detector pages were exercised on an Apple Silicon Mac on 2026-11-03. |
| Linux x86_64 | `linux-x86_64`; `scripts/install-linux.sh VERSION` | Source patch, compilation and loopback smoke are checked separately. Live detector sites must be evaluated on Linux; macOS results do not transfer. |
| Windows x86_64 | `windows-x86_64`; `scripts/install-windows.ps1 -Version VERSION` | GitHub Actions Windows build and loopback smoke are the initial validation path. Live detector pages and installer use require a Windows host. |

Use the official `agent-browser` CLI for debugging console/page-error events. All browse installations use a **separate daemon namespace and empty config**; none select a user profile by default. The installers pin the exact requested version and verify release checksums and compiled version; the Windows helper additionally validates the x64 PE header.

### Detection caveats

The patch attempts to reduce `Runtime.enable` leakage, `navigator.webdriver`, and the headless user-agent mismatch. **Passing one detection page is not a guarantee about other sites, sessions, or future browser versions.** Headless user-agent normalization is only applied to recognized stable Google Chrome paths and only when the version can be read. Chrome for Testing and other Chromium variants are usable through upstream discovery, but are not claimed to have the same fingerprint.

## Detection test results (macOS only)

Tested on **November 3, 2026** using the installed [v0.41.1 patched GitHub release](https://github.com/amxv/agent-browser-browse/releases/tag/v0.41.1), headless Chrome 156 on an Apple Silicon Mac. Each site was visited in a separate, fresh agent-browser session without a signed-in Chrome profile. These are observed results from one run per site, not guaranteed success rates.

| Detector or site | Observed result |
| --- | --- |
| [SannySoft](https://bot.sannysoft.com/) | **Passed:** no failed checks; WebDriver reported as missing (passed). |
| [Rebrowser](https://bot-detector.rebrowser.net/) | **Zero red detections.** `runtimeEnableLeak` and `navigatorWebdriver` were green. Four yellow warnings remained: `popupBlocking`, `useragent`, `headless`, and `Screen`. |
| [DeviceAndBrowserInfo](https://deviceandbrowserinfo.com/are_you_a_bot) | **0/22 bot signals:** `isBot: false`, including `isAutomatedWithCDP: false`. |
| [Cloudflare challenge test](https://www.scrapingcourse.com/cloudflare-challenge) | **Passed:** reached the test page's content, which displayed “You bypassed the Cloudflare challenge! :D”. |
| [NowSecure](https://nowsecure.nl/) | **Loaded successfully** without a challenge during the test. This is not an independent all-clear verdict. |
| [G2](https://www.g2.com/) | **Blocked:** a DataDome CAPTCHA challenge was returned instead of site content. |

The patch removed the **measured CDP `Runtime.enable` detection** on Rebrowser and DeviceAndBrowserInfo while preserving navigation, snapshots, and JavaScript evaluation. It does **not** make browser automation undetectable: real sites can consider network reputation, session history, behavior, and additional signals. The Cloudflare result is for a deliberately protected test page, not a claim that other Cloudflare deployments can be passed.

## Automatic builds

The [release workflow](.github/workflows/release.yml) checks the official upstream **stable GitHub release** every six hours and builds **only missing platform assets**. It clones the exact upstream version tag, applies [strict version-sensitive patches](scripts/patch_upstream.py), builds and smoke-tests each native binary on a matching GitHub-hosted OS, then attaches verified assets to the version-matched GitHub Release with merged `SHA256SUMS`. This supports backfilling Linux and Windows assets for an upstream version whose macOS asset already exists. The [PR workflow](.github/workflows/ci.yml) compiles and smoke-tests each platform **without publishing**.

If upstream changes the relevant code and a patch anchor no longer matches, the workflow **fails instead of publishing a partially patched binary**. The previous release stays available. Check the GitHub Actions log to adapt the patch and rerun the workflow. A release may lag the official Homebrew version if a build fails or is still running.

The daily macOS LaunchAgent `xyz.ashray.agent-browser-updater` installs the newest matching patched release through [scripts/install-macos.sh](scripts/install-macos.sh) after its existing Homebrew update. It retries hourly when a patch release is not available yet, without compiling Rust locally. The updater verifies SHA-256, architecture, and version before atomically switching the browsing command. Linux and Windows installers are explicit opt-in, not scheduled background updaters.

## Local commands

```bash
agent-browser --version              # official Homebrew CLI
agent-browser-browse --version       # matching upstream version, patched native binary

SESSION="$(agent-browser-browse session id --scope worktree --prefix research)"
agent-browser-browse --session "$SESSION" open https://example.com
agent-browser-browse --session "$SESSION" snapshot -i
agent-browser-browse --session "$SESSION" close
```

Do **not** point the browsing variant at a shared `agent-browser` daemon, and do not use `close --all` on a shared Mac. Always close sessions you open. Run the upstream CLI when you need console/page-error events. Browser protections vary by website; respect access restrictions and challenge requirements.

## Building and patching a release manually

The workflow owns normal compilation; to reproduce locally for troubleshooting:

```bash
git clone --depth 1 --branch v0.41.1 https://github.com/vercel-labs/agent-browser.git upstream
python3 scripts/patch_upstream.py upstream
cd upstream/cli
cargo fmt --all
cargo build --locked --profile ci
```

For local cross-platform smoke testing, return to this repository and run `python3 scripts/verify_patch.py upstream` and `python3 scripts/smoke.py upstream/cli/target/ci/agent-browser` (append `.exe` on Windows). Smoke tests use an ephemeral browser profile and a local test page, never an authenticated third-party account.

Upstream is Apache-2.0 licensed; binaries include its LICENSE. This project is not affiliated with or endorsed by Vercel.
