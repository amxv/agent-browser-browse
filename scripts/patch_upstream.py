#!/usr/bin/env python3
"""Strict, fail-closed patch of an upstream agent-browser tagged checkout.

Never silently apply only some patches. Upstream refactors must be reviewed.
The official agent-browser executable is not modified.
"""
from pathlib import Path
import sys


def replace_once(path: Path, before: str, after: str) -> None:
    original = path.read_text()
    count = original.count(before)
    if count != 1:
        raise RuntimeError(f"Patch mismatch {path}: expected 1 anchor, found {count}: {before[:100]!r}")
    path.write_text(original.replace(before, after, 1))


def replace_once_across(paths: list[Path], before: str, after: str) -> None:
    """Allow a reviewed upstream move, but require exactly one matching definition."""
    matches = []
    for path in paths:
        if path.is_file():
            matches.extend([path] * path.read_text().count(before))
    if len(matches) != 1:
        raise RuntimeError(
            f"Patch mismatch across {', '.join(map(str, paths))}: "
            f"expected 1 anchor, found {len(matches)}: {before[:100]!r}"
        )
    replace_once(matches[0], before, after)


def patch(source: Path) -> None:
    crate = source / "cli" / "Cargo.toml"
    if not crate.exists():
        raise RuntimeError(f"Not an agent-browser Rust source tree: {source}")
    browser = source / "cli/src/native/browser.rs"
    actions = source / "cli/src/native/actions.rs"
    state = source / "cli/src/native/state.rs"
    chrome = source / "cli/src/native/cdp/chrome.rs"
    daemon = source / "cli/src/native/daemon.rs"
    running = source / "cli/src/session_settings/running.rs"

    for path, anchor in [
        (browser, '            .send_command_no_params("Runtime.enable", Some(session_id))\n            .await?;'),
        (browser, '            .send_command_no_params("Runtime.enable", None)\n            .await?;'),
        (actions, '        .send_command_no_params("Runtime.enable", Some(session_id))\n        .await?;'),
        (state, '        .send_command_no_params("Runtime.enable", Some(temp_session))\n        .await?;'),
    ]:
        disable = anchor.replace('"Runtime.enable"', '"Runtime.disable"')
        client = '        self.client\n' if path == browser else '    client\n'
        replace_once(path, anchor, anchor + '\n' + client + disable)

    # Prefer the user's regular Chrome on macOS, rather than a cached Chrome for Testing.
    replace_once(chrome,
        '        None => find_chrome().ok_or_else(|| {',
        '        None => browse_default_chrome().or_else(find_chrome).ok_or_else(|| {')

    marker = 'pub fn launch_chrome(options: &LaunchOptions) -> Result<ChromeProcess, String> {'
    helpers = '''// Browse-build defaults. No user profile is selected without an explicit request.
#[cfg(target_os = "macos")]
fn browse_default_chrome() -> Option<PathBuf> {
    let path = PathBuf::from("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome");
    path.is_file().then_some(path)
}

#[cfg(not(target_os = "macos"))]
fn browse_default_chrome() -> Option<PathBuf> {
    None
}

#[cfg(target_os = "macos")]
fn browse_headless_user_agent(chrome_path: &Path) -> Option<String> {
    if chrome_path != Path::new("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome") {
        return None;
    }
    let output = std::process::Command::new("/usr/libexec/PlistBuddy")
        .args(["-c", "Print CFBundleShortVersionString", "/Applications/Google Chrome.app/Contents/Info.plist"])
        .output().ok()?;
    if !output.status.success() { return None; }
    let version = String::from_utf8(output.stdout).ok()?;
    let major = version.trim().split('.').next()?;
    if major.parse::<u32>().ok()? < 100 { return None; }
    Some(format!("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"))
}

#[cfg(not(target_os = "macos"))]
fn browse_headless_user_agent(_chrome_path: &Path) -> Option<String> {
    None
}

'''
    replace_once(chrome, marker, helpers + marker)

    # Inject at the actual Chrome launch, not the generic CLI/parser. All launch
    # paths (including new tabs) retain a stable browser fingerprint. Custom
    # --user-agent CLI requests remain explicit overrides.
    replace_once(chrome,
        '    let effective_options = resolved_options.as_ref().unwrap_or(options);\n',
        '''    let effective_options = resolved_options.as_ref().unwrap_or(options);
    let mut browse_options = effective_options.clone();
    if !browse_options.args.iter().any(|arg| arg.starts_with("--disable-blink-features=")) {
        browse_options.args.push("--disable-blink-features=AutomationControlled".to_string());
    }
    if browse_options.effectively_headless()
        && browse_options.user_agent.is_none()
        && !browse_options.args.iter().any(|arg| arg.starts_with("--user-agent="))
    {
        if let Some(ua) = browse_headless_user_agent(&chrome_path) {
            browse_options.args.push(format!("--user-agent={ua}"));
        }
    }
''')
    replace_once(chrome,
        '        match try_launch_chrome(&chrome_path, effective_options) {',
        '        match try_launch_chrome(&chrome_path, &browse_options) {')

    # Upstream v0.41.2 moved the constant from daemon.rs to session_settings.
    # Preserve its newer idle-shutdown exemptions and override semantics.
    replace_once_across([daemon, running],
        'pub const DEFAULT_IDLE_TIMEOUT_MS: u64 = 60 * 60 * 1000;',
        'pub const DEFAULT_IDLE_TIMEOUT_MS: u64 = 15 * 60 * 1000;')

    print("Applied Runtime.disable in 4 locations and all macOS browse defaults")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: patch_upstream.py /path/to/upstream-source')
    try:
        patch(Path(sys.argv[1]).resolve())
    except Exception as error:
        sys.exit(f'FAIL CLOSED: {error}')
