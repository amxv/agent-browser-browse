# agent-browser-browse

An **unofficial, browsing-focused** build of [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser), for **Apple Silicon macOS only**. It complements the official CLI rather than replacing it.

| Command | Use case | CDP Runtime events |
| --- | --- | --- |
| `agent-browser` | Develop/test web applications, inspect console logs and page errors | Enabled, upstream behavior |
| `agent-browser-browse` | Browse public websites, research, extract data or interact with sites | Disabled after initialization (limited console/page-error streams) |

The browsing build retains normal CLI operations (`open`, `snapshot`, `click`, `eval`, etc.) and applies these defaults without per-agent flags:

- **Stable macOS Google Chrome** if installed, falling back to upstream Chrome discovery if not.
- **Headless** unless you deliberately pass `--headed`.
- **`--disable-blink-features=AutomationControlled`** on Chrome launches.
- **Normal Chrome user-agent in headless mode**, derived from the installed Chrome version at runtime (rather than hard-coding a version or overriding with CDP). Explicit user-agent options retain precedence.
- **15-minute default idle timeout**, with explicit CLI/env overrides still supported.
- **`Runtime.enable` followed immediately by `Runtime.disable`** in four relevant CDP initialization paths, reducing detectable runtime instrumentation, at the cost of console and page-error event streaming. This is a pragmatic compatibility patch, not a guarantee against bot detection.

No cookies, profiles, or other account state are selected by default. The local `agent-browser-browse` command is a wrapper that **isolates its daemon/socket namespace** from the upstream CLI and uses an empty browse-specific config, so your global agent-browser config cannot accidentally interfere. Users may still explicitly override flags and config.

## Automatic builds

The [release workflow](.github/workflows/release.yml) checks the official upstream **stable GitHub release** every six hours, but uses a macOS ARM64 runner **only when this repository lacks that version's release**. It clones the exact upstream version tag, applies [strict version-sensitive patches](scripts/patch_upstream.py), builds and smoke-tests an ARM64 binary, then publishes a version-matched GitHub Release with `SHA256SUMS`.

If upstream changes the relevant code and a patch anchor no longer matches, the workflow **fails instead of publishing a partially patched binary**. The previous release stays available. Check the GitHub Actions log to adapt the patch and rerun the workflow. A release may lag the official Homebrew version if a build fails or is still running.

The daily macOS LaunchAgent `xyz.ashray.agent-browser-updater` installs the newest matching patched release through [scripts/install-macos.sh](scripts/install-macos.sh) after its existing Homebrew update. It retries hourly when a patch release is not available yet, without compiling Rust locally. The updater verifies SHA-256, architecture, and version before atomically switching the browsing command.

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

Upstream is Apache-2.0 licensed; binaries include its LICENSE. This project is not affiliated with or endorsed by Vercel.
