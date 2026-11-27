# AGENTS.md

Developer notes for agent-browser-browse. User-facing documentation is in [README.md](README.md).

## What this repo is

This repo holds no upstream source. It patches an exact upstream [agent-browser](https://github.com/vercel-labs/agent-browser) release tag, builds the native CLI, and publishes macOS ARM64 and Linux x86_64 packages as GitHub releases tagged with the same version as upstream.

| Path | Purpose |
| --- | --- |
| `UPSTREAM_VERSION` | Upstream version that PR and manual CI verify against. Scheduled releases track upstream on their own. |
| `scripts/patch_upstream.py` | Strict, fail-closed patch of an upstream checkout. It is the single source of every browse behavior. |
| `scripts/test_patch_upstream.py`, `scripts/test_installer.py` | Python regressions. Set `PATCHED_UPSTREAM_ROOT` to also assert on a patched checkout. |
| `scripts/run_upstream_tests.py` | Runs upstream's Rust tests in isolation. |
| `scripts/smoke.py` | Loopback browser smoke test against a built binary. |
| `scripts/package.py`, `scripts/merge_sums.py` | Package one platform and merge `SHA256SUMS` across platforms. |
| `scripts/install-macos.sh`, `scripts/install-linux.sh` | User installers. |
| `scripts/check_detectors.py`, `scripts/compare_detectors.py` | Public bot-detector harness and the comparison against the release bar. |
| `docs/` | Detector release bar and per-release verification reports. |
| `upstream/`, `dist/`, `target/` | Ignored local build inputs and outputs. `dist/evidence/` holds raw detector evidence. |

## Patch rules

- Every anchor must match **exactly once**. A missing or duplicated anchor fails the build, so a partially patched executable is never published. Don't loosen an anchor to make it match. Read the upstream change and update the patch on purpose.
- `replace_once_across` exists only for reviewed upstream moves, for example the idle-timeout constant moving from `native/daemon.rs` to `session_settings/running.rs` in v0.41.2.
- The patch makes these changes, and each should have a regression in `test_patch_upstream.py` and/or `smoke.py`:
  - `Runtime.disable` immediately after `Runtime.enable` in four initialization paths: two in `browser.rs` (anchored on the preceding `Page.enable` since v0.45.0), plus `actions.rs` and `state.rs`.
  - Stable-Chrome discovery: the standard macOS app; `google-chrome-stable` or `google-chrome` on Linux.
  - Popup blocking left on: `--disable-popup-blocking` removed.
  - Headless `--screen-info={1920x1080 devicePixelRatio=1}`, unless the caller passes one.
  - `AutomationControlled` merged into any `--disable-blink-features` argument.
  - Version-aware headless `--user-agent`. Linux accepts only a real `Google Chrome X.Y.Z.W` version string.
  - Client hints restored for that user agent. Chrome blanks the high-entropy hints whenever `--user-agent` is set, so `prepare_domains` and `enable_domains_direct` send `Emulation.setUserAgentOverride` with full metadata. The full version comes from `Browser.getVersion` (the running browser, not the installed bundle), and the brand list from a port of Chromium's GREASE algorithm. Cross-origin iframes get it through `prepare_domains`, and dedicated workers inherit it. Explicit user agents skip it.
  - `eval` runs in a fresh isolated world (`Page.createIsolatedWorld`) on the main frame or the selected frame; `eval --main-world` (first argument) keeps upstream's page-world evaluation. Other engines keep upstream behavior.
  - 15-minute `DEFAULT_IDLE_TIMEOUT_MS`.
- v0.45.0 note: upstream's `frame_execution_context` cycles `Runtime.disable` then `Runtime.enable` and leaves Runtime on. Default isolated eval no longer uses it; only `eval --main-world` inside a selected same-process iframe still does.
- The wrapper sets `AGENT_BROWSER_NAMESPACE=abb` (short because of macOS socket-path limits) and an empty config.

## Build and test locally

```bash
VERSION=0.45.0
git clone --depth 1 --branch "v$VERSION" https://github.com/vercel-labs/agent-browser.git upstream
python3 scripts/patch_upstream.py upstream
PATCHED_UPSTREAM_ROOT="$PWD/upstream" python3 -m unittest discover -s scripts -p 'test_*.py' -v

pnpm --dir upstream install --frozen-lockfile --filter dashboard
pnpm --dir upstream --filter dashboard build        # before cargo, so the real UI is embedded
cargo fmt --manifest-path upstream/cli/Cargo.toml --all
cargo build --manifest-path upstream/cli/Cargo.toml --locked --profile ci --jobs 2
python3 scripts/run_upstream_tests.py upstream
python3 scripts/smoke.py upstream/cli/target/ci/agent-browser --version "$VERSION"

python3 scripts/package.py darwin-arm64 "v$VERSION"   # or linux-x86_64 on the Linux host
```

- To build another version, clone it into a scratch directory instead of reusing `upstream/`, which may hold an older patched tree.
- `run_upstream_tests.py` uses a temporary empty config, strips inherited `AGENT_BROWSER_*` variables, and runs tests serially (`--test-threads=1`) with the `ci` profile, because some upstream tests mutate process-wide environment variables. Without it, the user's saved executable path or idle timeout makes tests fail.
- The `ci` profile build takes about 4–5 minutes on the Mac. Full Rust test runs have hit memory pressure before; keep `--jobs` low.
- `smoke.py` uses only an owned loopback fixture and closes its own sessions.

## CI and releases

- `.github/workflows/build.yml` is shared by PR/manual CI (`ci.yml`, which runs on PRs touching `scripts/**`, workflows or `UPSTREAM_VERSION`) and by releases. It clones the tag, checks the Cargo version, patches, builds the dashboard and CLI, runs the Python and Rust tests and smoke, and packages. Mac binaries are ad-hoc signed. Packages record the upstream license, version, commit and patch-script SHA-256.
- `.github/workflows/release.yml` runs every six hours. It finds upstream's latest stable tag, builds any platform asset missing from our release with that tag, and publishes or uploads it with a merged `SHA256SUMS`. A hosted build takes about 40 minutes.
- When upstream ships a version the patch can't handle, the scheduled run fails at the patch step. Fix `patch_upstream.py` (and its tests), bump `UPSTREAM_VERSION`, and merge through a PR so `ci.yml` verifies it. Then trigger the release instead of waiting for the schedule:

  ```bash
  gh workflow run release.yml --ref main -f upstream_tag=vX.Y.Z
  ```

- The macOS daily updater calls a local copy of `install-macos.sh`. Updater installs older than v0.43.0 need the refreshed helper, which understands the multi-platform `SHA256SUMS`.

## Detector verification for a new release

Follow [docs/detector-release-bar.md](docs/detector-release-bar.md): run `check_detectors.py --targets all --exercise-rebrowser --verify-turnstile` against the previous release's installed native binary (`~/.local/share/agent-browser-browse/versions/<v>/agent-browser-browse-native`), then against the candidate, back to back. Compare the two with `compare_detectors.py`, and record the result in `docs/verification-<version>.md`.

Harness rules (the scripts enforce them; keep it that way):

- Each target gets one fresh session in a private namespace, one navigation and no retries. The harness never clicks a CAPTCHA, injects spoofed properties, selects a saved profile or attaches to a shared browser.
- `--exercise-rebrowser` calls the detector's documented probes through the real default CLI `eval` (isolated world), so `dummyFn` and `mainWorldExecution` stay gray. `--verify-turnstile` clicks only the demo's own Verify button, and only after a token appears naturally.
- Exit 0 means collection completed, not that the detectors passed. Exit 1 ("partial") can be benign. incolumitas regularly hits the 25-second `open` load timeout while still being captured.
- Raw evidence under `dist/evidence/` can contain IPs and fingerprint IDs. Never commit it. Public reports must not include IPs, visitor IDs, tokens or personal paths.
- Don't run two detector matrices at the same time; Fingerprint velocity signals and similar checks can be affected.
