# agent-browser-browse

An **unofficial, browsing-focused** build of [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) for **Apple Silicon macOS and Linux x86_64**. It complements the official CLI and keeps a separate browser-session namespace.

| Command | Use case | CDP Runtime events |
| --- | --- | --- |
| `agent-browser` | Develop/test web applications, inspect console logs and page errors | Enabled, upstream behavior |
| `agent-browser-browse` | Browse public websites, research, extract data or interact with authorized sites | Disabled after initialization; console/page-error streams are limited |

## Browse defaults

Normal CLI operations such as `open`, `snapshot`, `click`, `eval`, tabs, and state remain available. The patched native binary applies these defaults:

- Prefer **installed stable Google Chrome** over cached Chrome for Testing. macOS uses the standard Google Chrome application; Linux checks executable `google-chrome-stable`/`google-chrome` paths. Explicit executable options retain precedence, with upstream discovery as fallback.
- Run **headless** unless explicitly configured otherwise.
- Configure a **1920×1080 virtual screen** in headless Chrome, with explicit screen arguments taking precedence, and retain **Chrome's normal popup blocking** unless a caller explicitly disables it. Virtual screen configuration requires Chrome 142 or newer.
- Include **`AutomationControlled` in Chrome's disabled Blink features**, also when another disabled feature is supplied through custom launch arguments.
- Use a **version-aware Chrome user-agent startup argument** in headless mode. The version comes from the actual installed Chrome. Linux requires a valid Google Chrome version response and does not relabel Chromium or Chrome for Testing. Explicit user-agent options retain precedence.
- Use a **15-minute default idle timeout**, retaining upstream override semantics and exemptions.
- Follow **`Runtime.enable` immediately with `Runtime.disable`** in four CDP initialization paths. This reduces the runtime instrumentation measured by some public detectors, at the cost of console/page-error event streaming.

The installed wrapper defaults to the `abb` namespace and an empty browse-specific config. It does not select cookies, signed-in profiles, or other account state. Explicit CLI/env overrides remain possible. These patches are browser compatibility choices, not an undetectability guarantee.

## Install or update

Install stable Google Chrome first. The installers require Bash, Python 3.9 or newer, and curl. They download a version-matched release, verify the selected asset's SHA-256, architecture, native version, and provenance files, then atomically switch `current`. The previous version and existing regular config remain intact. Active default browsing sessions or a customized wrapper stop installation without replacing them.

```bash
git clone https://github.com/amxv/agent-browser-browse.git
cd agent-browser-browse

# Apple Silicon macOS
bash scripts/install-macos.sh 0.43.0

# Linux x86_64 (release built on Ubuntu 24.04)
bash scripts/install-linux.sh 0.43.0
```

Use the command for your OS, then ensure `~/.local/bin` is on `PATH`. Linux also supports `XDG_DATA_HOME` and `XDG_BIN_HOME`. Windows and Linux ARM64 are not published or validated by this release. Earlier Windows work remains on the original cross-platform branch.

The macOS daily updater invokes a local copy of `install-macos.sh` after updating the official Homebrew CLI. Existing updater installations need the refreshed helper for multi-platform checksum manifests; the old helper expected a single-asset manifest. No local Rust compilation is needed for normal updates.

```bash
agent-browser --version
agent-browser-browse --version

SESSION="$(agent-browser-browse session id --scope worktree --prefix research)"
agent-browser-browse --session "$SESSION" open https://example.com
agent-browser-browse --session "$SESSION" snapshot -i
agent-browser-browse --session "$SESSION" close
```

Always close sessions you open. Do not point this variant at a shared upstream daemon or run `close --all` on a shared machine. Use the official CLI when console/page-error events matter. Respect access restrictions and challenge requirements.

## Measured detector results

The [v0.43.0 verification report](docs/verification-0.43.0.md) records the November 13, 2026 results on **both macOS and Linux**, exact browser/OS versions, the configuration experiments, and remaining limits. It separates successful CLI tests from third-party detector verdicts, incomplete demos, and blocked or unavailable targets.

The previous [v0.41.1 Mac-only measurements](https://github.com/amxv/agent-browser-browse/blob/4506dfe/README.md#detection-test-results) are historical. They do not establish Linux behavior or a guarantee for later releases. Network reputation, browser version, session history, behavior, and detector changes can affect the result.

Reproduce the public observations with fresh isolated sessions:

```bash
python3 scripts/check_detectors.py --list-targets
python3 scripts/check_detectors.py --binary agent-browser-browse --targets all \
  --exercise-rebrowser --verify-turnstile --label local-v043

# A deliberate per-run configuration experiment; config files remain unchanged.
python3 scripts/check_detectors.py --binary agent-browser-browse \
  --targets rebrowser --browser-args='--window-size=1920,1080' --label larger-window
```

The harness saves command results, rendered text, DOM status rows, and browser properties under ignored `dist/evidence/`. Its default mode observes pages without interaction. `--exercise-rebrowser` invokes the detector's documented probes through the CLI's actual evaluation context and records before/after results. `--verify-turnstile` submits only the two live demos' ordinary verification forms after natural token issuance and origin/sitekey checks. It never clicks a CAPTCHA control, selects a saved profile, injects spoofed properties, or retries navigation automatically. An exit code of zero means collection completed, not that every detector passed. Raw evidence can contain network or fingerprint identifiers and should be reviewed before sharing. Optional screenshots are supporting artifacts; text/DOM observations drive the report.

## Builds and release tracking

The [release workflow](.github/workflows/release.yml) checks the official stable upstream release every six hours and builds missing macOS ARM64/Linux x86_64 assets. Each build clones the exact tag, verifies the Cargo version, applies [strict version-sensitive patches](scripts/patch_upstream.py), builds the upstream dashboard, compiles the native CLI, runs Python/Rust regressions and loopback browser smoke tests, and verifies the package architecture and provenance. Mac binaries are ad-hoc signed. Packages include the upstream license, version, source commit, and patch-script SHA-256.

The same [build workflow](.github/workflows/build.yml) serves PR/manual CI and releases. Source verification currently targets the version in `UPSTREAM_VERSION`; nightly release tracking checks upstream independently. A missing or duplicated patch anchor fails the build instead of publishing a partially patched executable. The timeout patch supports both the older `native/daemon.rs` location and `session_settings/running.rs` introduced in v0.41.2. Live third-party detectors are manual observations, not CI assertions or release guarantees.

### Reproduce a source build

```bash
git clone --depth 1 --branch v0.43.0 https://github.com/vercel-labs/agent-browser.git upstream
python3 scripts/patch_upstream.py upstream
PATCHED_UPSTREAM_ROOT="$PWD/upstream" python3 -m unittest discover -s scripts -p 'test_*.py' -v

pnpm --dir upstream install --frozen-lockfile --filter dashboard
pnpm --dir upstream --filter dashboard build
cargo fmt --manifest-path upstream/cli/Cargo.toml --all
cargo build --manifest-path upstream/cli/Cargo.toml --locked --profile ci --jobs 2
python3 scripts/run_upstream_tests.py upstream
python3 scripts/smoke.py upstream/cli/target/ci/agent-browser --version 0.43.0

# Select the target matching the build machine:
python3 scripts/package.py darwin-arm64 v0.43.0
# python3 scripts/package.py linux-x86_64 v0.43.0
```

Build the dashboard before compiling Rust so its actual UI is embedded. The unit runner uses a temporary empty config, clears inherited browser environment overrides, runs tests serially, and disables debug symbols to limit memory use. It does not change the user's home directory or saved config. The smoke test exercises default navigation/input/snapshot/tab/state behavior, an explicit empty profile, custom Blink arguments, and both user-agent override paths. It uses only an owned loopback fixture and closes its own sessions.

Upstream is Apache-2.0 licensed. This project is not affiliated with or endorsed by Vercel.
