# agent-browser-browse

An **unofficial, browsing-focused** build of [vercel-labs/agent-browser](https://github.com/vercel-labs/agent-browser) for **Apple Silicon macOS and Linux x86_64**. It sits alongside the official CLI and uses its own browser-session namespace.

| Command | Use case | CDP Runtime events |
| --- | --- | --- |
| `agent-browser` | Develop and test web apps, inspect console logs and page errors | Enabled (upstream behavior) |
| `agent-browser-browse` | Browse public websites, research, extract data, use authorized sites | Disabled after initialization, so console and page-error streams are limited |

## Browse defaults

All normal CLI commands (`open`, `snapshot`, `click`, `eval`, tabs, state) work as upstream. The browse build changes these defaults:

- Uses **installed stable Google Chrome** instead of cached Chrome for Testing.
- Runs **headless**, with a **1920×1080 virtual screen** (Chrome 142+) and Chrome's normal **popup blocking**.
- Disables the **`AutomationControlled`** Blink feature.
- Sets a **user agent that matches the installed Chrome version** in headless mode.
- Disables CDP **`Runtime`** right after initialization.
- Uses a **15-minute idle timeout**.

Explicit CLI options, environment variables and config still take precedence. The wrapper uses the `abb` namespace and an empty config, so no cookies, profiles or account state are selected. These defaults make the browser look more like normal Chrome; they are not a guarantee against detection.

## Install or update

Install stable Google Chrome first. The installers need Bash, Python 3.9+ and curl. They verify the release checksum, architecture and provenance before switching versions, and keep the previous version and your config.

```bash
git clone https://github.com/amxv/agent-browser-browse.git
cd agent-browser-browse

bash scripts/install-macos.sh 0.45.0   # Apple Silicon macOS
bash scripts/install-linux.sh 0.45.0   # Linux x86_64
```

Make sure `~/.local/bin` is on your `PATH`. Linux also honors `XDG_DATA_HOME` and `XDG_BIN_HOME`. Windows and Linux ARM64 are not supported.

## Usage

```bash
SESSION="$(agent-browser-browse session id --scope worktree --prefix research)"
agent-browser-browse --session "$SESSION" open https://example.com
agent-browser-browse --session "$SESSION" snapshot -i
agent-browser-browse --session "$SESSION" close
```

Always close the sessions you open, and don't run `close --all` on a shared machine. Use the official CLI when you need console or page-error events. Respect access restrictions and challenge requirements.

## Bot-detection results

Each release is checked against a fixed set of public bot-detection pages, covering SannySoft, Rebrowser, Fingerprint, BrowserScan, Cloudflare, Turnstile, reCAPTCHA, TLS and more. The [detector release bar](docs/detector-release-bar.md) lists every test, the result a release must reach, and the failures already accepted as limitations.

- [v0.45.0 parity check](docs/verification-0.45.0.md) (macOS): matched v0.43.0 on every test.
- [v0.43.0 verification report](docs/verification-0.43.0.md) (macOS and Linux): the full baseline, including limitations and experiments.

Results can change with Chrome version, network reputation and detector updates.

## Development

Build, patch, test and release instructions are in [AGENTS.md](AGENTS.md).

Upstream is Apache-2.0 licensed. This project is not affiliated with or endorsed by Vercel.
