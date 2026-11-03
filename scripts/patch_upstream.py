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


def patch(source: Path) -> None:
    crate = source / "cli" / "Cargo.toml"
    if not crate.exists():
        raise RuntimeError(f"Not an agent-browser Rust source tree: {source}")
    browser = source / "cli/src/native/browser.rs"
    actions = source / "cli/src/native/actions.rs"
    state = source / "cli/src/native/state.rs"
    chrome = source / "cli/src/native/cdp/chrome.rs"
    daemon = source / "cli/src/native/daemon.rs"

    for path, anchor in [
        (browser, '            .send_command_no_params("Runtime.enable", Some(session_id))\n            .await?;'),
        (browser, '            .send_command_no_params("Runtime.enable", None)\n            .await?;'),
        (actions, '        .send_command_no_params("Runtime.enable", Some(session_id))\n        .await?;'),
        (state, '        .send_command_no_params("Runtime.enable", Some(temp_session))\n        .await?;'),
    ]:
        disable = anchor.replace('"Runtime.enable"', '"Runtime.disable"')
        client = '        self.client\n' if path == browser else '    client\n'
        replace_once(path, anchor, anchor + '\n' + client + disable)

    # Prefer stable Google Chrome on every supported OS, rather than a cached
    # Chrome for Testing. An explicit --executable-path always takes precedence.
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

#[cfg(target_os = "linux")]
fn browse_default_chrome() -> Option<PathBuf> {
    // Do not use Chrome for Testing if a stable installation is available.
    for directory in std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()) {
        for name in ["google-chrome-stable", "google-chrome"] {
            let path = directory.join(name);
            if path.is_file() { return Some(path); }
        }
    }
    for name in ["/opt/google/chrome/chrome", "/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"] {
        let path = PathBuf::from(name);
        if path.is_file() { return Some(path); }
    }
    None
}

#[cfg(target_os = "windows")]
fn browse_default_chrome() -> Option<PathBuf> {
    for variable in ["LOCALAPPDATA", "PROGRAMFILES", "ProgramFiles(x86)"] {
        if let Some(directory) = std::env::var_os(variable) {
            let path = PathBuf::from(directory).join(r"Google\\Chrome\\Application\\chrome.exe");
            if path.is_file() { return Some(path); }
        }
    }
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

#[cfg(target_os = "linux")]
fn browse_headless_user_agent(chrome_path: &Path) -> Option<String> {
    // Do not spoof a Google Chrome UA for other Chromium forks or cached CfT.
    let name = chrome_path.file_name()?.to_str()?;
    if !matches!(name, "google-chrome" | "google-chrome-stable" | "chrome") { return None; }
    let output = std::process::Command::new(chrome_path).arg("--version").output().ok()?;
    if !output.status.success() { return None; }
    let major = browse_major_version(&String::from_utf8_lossy(&output.stdout))?;
    Some(format!("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"))
}

#[cfg(target_os = "windows")]
fn browse_headless_user_agent(chrome_path: &Path) -> Option<String> {
    let normalized = chrome_path.to_string_lossy().replace('\\\\', "/").to_ascii_lowercase();
    if !chrome_path.file_name()?.to_str()?.eq_ignore_ascii_case("chrome.exe")
        || !normalized.contains("/google/chrome/application/") {
        return None;
    }
    // Chrome.exe is a GUI-subsystem program; --version need not print stdout.
    // Read its signed Windows version resource instead of pinning a UA.
    let quoted = chrome_path.to_string_lossy().replace(char::from(39), "''");
    let script = format!("(Get-Item -LiteralPath '{quoted}').VersionInfo.ProductVersion");
    let output = std::process::Command::new("powershell.exe")
        .args(["-NoProfile", "-NonInteractive", "-Command", &script]).output().ok()?;
    if !output.status.success() { return None; }
    let major = browse_major_version(&String::from_utf8_lossy(&output.stdout))?;
    Some(format!("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"))
}

#[cfg(any(target_os = "linux", target_os = "windows"))]
fn browse_major_version(version: &str) -> Option<u32> {
    version.split_whitespace().filter_map(|part| part.split('.').next()?.parse::<u32>().ok())
        .find(|major| *major >= 100)
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

    # Shorter cleanup fallback for unattended browsing agents.
    replace_once(daemon,
        'pub const DEFAULT_IDLE_TIMEOUT_MS: u64 = 60 * 60 * 1000;',
        'pub const DEFAULT_IDLE_TIMEOUT_MS: u64 = 15 * 60 * 1000;')

    print("Applied Runtime.disable in 4 locations and cross-platform browse defaults")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: patch_upstream.py /path/to/upstream-source')
    try:
        patch(Path(sys.argv[1]).resolve())
    except Exception as error:
        sys.exit(f'FAIL CLOSED: {error}')
