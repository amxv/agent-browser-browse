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
        if path == browser:
            # Domain initialization enables Page first. Frame context lookup
            # also enables Runtime in v0.45.0 and must retain upstream behavior.
            page_enable = anchor.replace('"Runtime.enable"', '"Page.enable"')
            anchor = page_enable + '\n' + client + anchor
        replace_once(path, anchor, anchor + '\n' + client + disable)

    # Prefer stable Chrome on the supported hosts over cached Chrome for Testing.
    replace_once(chrome,
        '        None => find_chrome().ok_or_else(|| {',
        '        None => browse_default_chrome().or_else(find_chrome).ok_or_else(|| {')

    # Restore Chrome's normal popup policy. Explicit caller arguments can still
    # opt into disabling it; arbitrary page scripts should not open popups.
    replace_once(chrome, '        "--disable-popup-blocking".to_string(),\n', '')

    marker = 'pub fn launch_chrome(options: &LaunchOptions) -> Result<ChromeProcess, String> {'
    helpers = '''// Browse-build defaults. No user profile is selected without an explicit request.
#[cfg(target_os = "macos")]
fn browse_default_chrome() -> Option<PathBuf> {
    let path = PathBuf::from("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome");
    path.is_file().then_some(path)
}

#[cfg(target_os = "linux")]
fn browse_default_chrome() -> Option<PathBuf> {
    use std::os::unix::fs::PermissionsExt;
    let mut candidates = Vec::new();
    for directory in std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default()) {
        for name in ["google-chrome-stable", "google-chrome"] {
            candidates.push(directory.join(name));
        }
    }
    for name in ["/opt/google/chrome/chrome", "/usr/bin/google-chrome-stable", "/usr/bin/google-chrome"] {
        candidates.push(PathBuf::from(name));
    }
    candidates.into_iter().find(|path| {
        path.metadata().is_ok_and(|meta| meta.is_file() && meta.permissions().mode() & 0o111 != 0)
    })
}

#[cfg(not(any(target_os = "macos", target_os = "linux")))]
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

// Chrome blanks high-entropy client hints (full version list, platform
// version, architecture) whenever --user-agent is set. The browse build sets
// that switch in headless mode, so it restores Chrome's own values per target
// with Emulation.setUserAgentOverride. Dedicated workers inherit the override.
static BROWSE_LAUNCH_UA: std::sync::Mutex<Option<(String, Option<serde_json::Value>)>> =
    std::sync::Mutex::new(None);

fn browse_set_launch_user_agent(user_agent: Option<String>) {
    if let Ok(mut slot) = BROWSE_LAUNCH_UA.lock() {
        *slot = user_agent.map(|ua| (ua, None));
    }
}

/// Override parameters for the browse-injected user agent, or None when the
/// launch used an explicit or upstream user agent. The connected browser must
/// report exactly the injected user agent, so a stale launch record never
/// applies to an external or later-connected browser. The full version comes
/// from the running browser, not the possibly newer installed bundle.
pub(crate) async fn browse_user_agent_override(
    client: &super::client::CdpClient,
) -> Option<serde_json::Value> {
    let user_agent = BROWSE_LAUNCH_UA.lock().ok()?.as_ref()?.0.clone();
    let version = client.send_command_no_params("Browser.getVersion", None).await.ok()?;
    if version.get("userAgent")?.as_str()? != user_agent {
        return None;
    }
    let full_version = version.get("product")?.as_str()?.rsplit('/').next()?.to_string();
    if let Some((_, Some(params))) = BROWSE_LAUNCH_UA.lock().ok()?.as_ref() {
        if params["userAgentMetadata"]["fullVersion"] == full_version.as_str() {
            return Some(params.clone());
        }
    }
    let params = browse_user_agent_metadata(&user_agent, &full_version, browse_platform_hints()?)?;
    if let Ok(mut slot) = BROWSE_LAUNCH_UA.lock() {
        if let Some((current, cached)) = slot.as_mut() {
            if *current == user_agent {
                *cached = Some(params.clone());
            }
        }
    }
    Some(params)
}

/// Chrome's seeded GREASE brand list (components/embedder_support/user_agent_utils.cc).
fn browse_brand_list(major: u32, version: &str, grease_suffix: &str) -> Vec<serde_json::Value> {
    const CHARS: [&str; 11] = [" ", "(", ":", "-", ".", "/", ")", ";", "=", "?", "_"];
    const VERSIONS: [&str; 3] = ["8", "99", "24"];
    const ORDERS: [[usize; 3]; 6] = [[0, 1, 2], [0, 2, 1], [1, 0, 2], [1, 2, 0], [2, 0, 1], [2, 1, 0]];
    let seed = major as usize;
    let grease = format!("Not{}A{}Brand", CHARS[seed % CHARS.len()], CHARS[(seed + 1) % CHARS.len()]);
    let base = [
        (grease, format!("{}{grease_suffix}", VERSIONS[seed % VERSIONS.len()])),
        ("Chromium".to_string(), version.to_string()),
        ("Google Chrome".to_string(), version.to_string()),
    ];
    let mut shuffled = vec![serde_json::Value::Null; base.len()];
    for (index, (brand, version)) in base.into_iter().enumerate() {
        shuffled[ORDERS[seed % ORDERS.len()][index]] = serde_json::json!({"brand": brand, "version": version});
    }
    shuffled
}

fn browse_user_agent_metadata(
    user_agent: &str,
    full_version: &str,
    (platform, platform_version): (&str, String),
) -> Option<serde_json::Value> {
    let parts: Vec<u32> = full_version.split('.').map(str::parse).collect::<Result<_, _>>().ok()?;
    if parts.len() != 4 || parts[0] < 100 || !user_agent.contains(&format!("Chrome/{}.0.0.0 ", parts[0])) {
        return None;
    }
    let architecture = if cfg!(target_arch = "aarch64") {
        "arm"
    } else if cfg!(target_arch = "x86_64") {
        "x86"
    } else {
        return None;
    };
    Some(serde_json::json!({
        "userAgent": user_agent,
        "userAgentMetadata": {
            "brands": browse_brand_list(parts[0], &parts[0].to_string(), ""),
            "fullVersionList": browse_brand_list(parts[0], full_version, ".0.0.0"),
            "fullVersion": full_version,
            "platform": platform,
            "platformVersion": platform_version,
            "architecture": architecture,
            "model": "",
            "mobile": false,
            "bitness": "64",
            "wow64": false,
            "formFactors": ["Desktop"],
        }
    }))
}

#[cfg(target_os = "macos")]
fn browse_platform_hints() -> Option<(&'static str, String)> {
    let output = std::process::Command::new("/usr/bin/sw_vers").arg("-productVersion").output().ok()?;
    if !output.status.success() { return None; }
    let mut parts: Vec<u32> = String::from_utf8(output.stdout).ok()?
        .trim().split('.').map(str::parse).collect::<Result<_, _>>().ok()?;
    if parts.is_empty() || parts.len() > 3 { return None; }
    parts.resize(3, 0);
    Some(("macOS", format!("{}.{}.{}", parts[0], parts[1], parts[2])))
}

// Chrome reports an empty platform version on Linux.
#[cfg(target_os = "linux")]
fn browse_platform_hints() -> Option<(&'static str, String)> {
    Some(("Linux", String::new()))
}

#[cfg(not(any(target_os = "macos", target_os = "linux")))]
fn browse_platform_hints() -> Option<(&'static str, String)> {
    None
}

#[cfg(target_os = "linux")]
fn browse_headless_user_agent(chrome_path: &Path) -> Option<String> {
    let output = std::process::Command::new(chrome_path).arg("--version").output().ok()?;
    if !output.status.success() { return None; }
    let major = browse_google_chrome_major(&String::from_utf8_lossy(&output.stdout))?;
    // Only this architecture is packaged and verified by the fork.
    if !cfg!(target_arch = "x86_64") { return None; }
    Some(format!("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{major}.0.0.0 Safari/537.36"))
}

#[cfg(any(target_os = "linux", test))]
fn browse_google_chrome_major(output: &str) -> Option<u32> {
    // Reject Chromium, Chrome for Testing, and unrelated numeric stdout.
    let version = output.trim().strip_prefix("Google Chrome ")?.split_whitespace().next()?;
    let parts: Vec<u32> = version.split('.').map(str::parse).collect::<Result<_, _>>().ok()?;
    if parts.len() != 4 || parts[0] < 100 { return None; }
    Some(parts[0])
}

#[cfg(not(any(target_os = "macos", target_os = "linux")))]
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
    if browse_options.effectively_headless()
        && !browse_options.args.iter().any(|arg| arg == "--screen-info" || arg.starts_with("--screen-info="))
    {
        browse_options.args.push("--screen-info={1920x1080 devicePixelRatio=1}".to_string());
    }
    if let Some(arg) = browse_options.args.iter_mut().rev().find(|arg| arg.starts_with("--disable-blink-features=")) {
        if !arg.trim_start_matches("--disable-blink-features=").split(',').any(|feature| feature == "AutomationControlled") {
            if !arg.ends_with('=') { arg.push(','); }
            arg.push_str("AutomationControlled");
        }
    } else {
        browse_options.args.push("--disable-blink-features=AutomationControlled".to_string());
    }
    let mut browse_launch_ua = None;
    if browse_options.effectively_headless()
        && browse_options.user_agent.is_none()
        && !browse_options.args.iter().any(|arg| arg.starts_with("--user-agent="))
    {
        if let Some(ua) = browse_headless_user_agent(&chrome_path) {
            browse_options.args.push(format!("--user-agent={ua}"));
            browse_launch_ua = Some(ua);
        }
    }
    browse_set_launch_user_agent(browse_launch_ua);
''')
    replace_once(chrome,
        '        match try_launch_chrome(&chrome_path, effective_options) {',
        '        match try_launch_chrome(&chrome_path, &browse_options) {')

    # Upstream v0.41.2 moved the constant from daemon.rs to session_settings.
    # Preserve its newer idle-shutdown exemptions and override semantics.
    replace_once_across([daemon, running],
        'pub const DEFAULT_IDLE_TIMEOUT_MS: u64 = 60 * 60 * 1000;',
        'pub const DEFAULT_IDLE_TIMEOUT_MS: u64 = 15 * 60 * 1000;')

    # Restore the client hints blanked by the headless --user-agent switch on
    # every page and cross-origin iframe target before it resumes.
    for session in ['Some(session_id)', 'None']:
        replace_once(browser,
            f'            .send_command_no_params("Runtime.disable", {session})\n            .await?;\n',
            f'            .send_command_no_params("Runtime.disable", {session})\n            .await?;\n'
            f'''        if let Some(params) = super::cdp::chrome::browse_user_agent_override(&self.client).await {{
            let _ = self
                .client
                .send_command("Emulation.setUserAgentOverride", Some(params), {session})
                .await;
        }}
''')

    # Run `eval` in an isolated world by default so page scripts cannot observe
    # it. `eval --main-world` keeps upstream's page-world evaluation.
    commands = source / "cli/src/commands.rs"
    output = source / "cli/src/output.rs"
    replace_once(commands,
        '        "eval" => {\n            // Check for flags: -b/--base64 or --stdin\n',
        '''        "eval" => {
            let browse_main_world = rest.first() == Some(&"--main-world");
            let rest: Vec<&str> = rest.iter().skip(usize::from(browse_main_world)).copied().collect();
            // Check for flags: -b/--base64 or --stdin
''')
    replace_once(commands,
        '            Ok(json!({ "id": id, "action": "evaluate", "script": script }))\n',
        '''            let mut browse_cmd = json!({ "id": id, "action": "evaluate", "script": script });
            if browse_main_world {
                browse_cmd["mainWorld"] = json!(true);
            }
            Ok(browse_cmd)
''')
    replace_once(output,
        'Options:\n  -b, --base64         Decode script from base64 (avoids shell escaping issues)\n',
        'Options:\n'
        '  --main-world         Run in the page\'s own JavaScript world (browse build default:\n'
        '                       an isolated world that shares the DOM but not page globals).\n'
        '                       Must come first, e.g. eval --main-world -b <base64>\n'
        '  -b, --base64         Decode script from base64 (avoids shell escaping issues)\n')
    replace_once(actions,
        '    let frame_id = state\n        .active_frame_id\n        .clone()\n        .filter(|_| state.engine == "chrome");\n    let (result, origin) = match frame_id {\n',
        '    let browse_main_world = cmd.get("mainWorld").and_then(Value::as_bool).unwrap_or(false);\n'
        '    let frame_id = state\n        .active_frame_id\n        .clone()\n        .filter(|_| state.engine == "chrome");\n    let (result, origin) = match frame_id {\n')
    replace_once(actions,
        '            let result = if host.is_dedicated_session {\n',
        '''            let result = if !browse_main_world {
                let mgr = state.browser.as_ref().ok_or("Browser not launched")?;
                let context =
                    super::element::create_frame_isolated_world(&mgr.client, &host.session_id, &frame_id)
                        .await?;
                mgr.eval_remote_object_in_context(&host.session_id, script, context)
                    .await?
            } else if host.is_dedicated_session {
''')
    replace_once(actions,
        '            let result = mgr.evaluate_remote_object(script).await?;\n            let url = mgr.get_url().await.unwrap_or_default();\n',
        '''            let result = if browse_main_world || state.engine != "chrome" {
                mgr.evaluate_remote_object(script).await?
            } else {
                browse_isolated_evaluate(mgr, script).await?
            };
            let url = mgr.get_url().await.unwrap_or_default();
''')
    replace_once(actions,
        'async fn handle_evaluate(cmd: &Value, state: &mut DaemonState) -> Result<Value, String> {\n',
        '''/// Evaluates in a fresh isolated world on the active tab's main frame. The
/// world shares the DOM but not page globals or instrumented page functions.
async fn browse_isolated_evaluate(
    mgr: &BrowserManager,
    script: &str,
) -> Result<super::cdp::types::RemoteObject, String> {
    let session_id = mgr.active_session_id()?.to_string();
    let tree = mgr
        .client
        .send_command_no_params("Page.getFrameTree", Some(&session_id))
        .await?;
    let frame_id = tree
        .pointer("/frameTree/frame/id")
        .and_then(Value::as_str)
        .ok_or("Could not resolve the main frame for evaluation")?
        .to_string();
    let context = super::element::create_frame_isolated_world(&mgr.client, &session_id, &frame_id).await?;
    mgr.eval_remote_object_in_context(&session_id, script, context).await
}

async fn handle_evaluate(cmd: &Value, state: &mut DaemonState) -> Result<Value, String> {
''')

    tests = '''
    #[test]
    fn test_browse_brand_list_matches_chrome() {
        let names = |list: Vec<serde_json::Value>| -> Vec<String> {
            list.iter().map(|b| format!("{}/{}", b["brand"].as_str().unwrap(), b["version"].as_str().unwrap())).collect()
        };
        assert_eq!(names(browse_brand_list(157, "157", "")),
                   ["Not-A.Brand/99", "Google Chrome/157", "Chromium/157"]);
        assert_eq!(names(browse_brand_list(158, "158.0.8127.37", ".0.0.0")),
                   ["Chromium/158.0.8127.37", "Not.A/Brand/24.0.0.0", "Google Chrome/158.0.8127.37"]);
    }

    #[test]
    fn test_browse_user_agent_metadata_requires_matching_major() {
        let ua = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/158.0.0.0 Safari/537.36";
        let hints = || ("Linux", String::new());
        let params = browse_user_agent_metadata(ua, "158.0.8127.37", hints());
        if cfg!(any(target_arch = "aarch64", target_arch = "x86_64")) {
            let params = params.unwrap();
            assert_eq!(params["userAgent"], ua);
            assert_eq!(params["userAgentMetadata"]["fullVersion"], "158.0.8127.37");
            assert_eq!(params["userAgentMetadata"]["fullVersionList"].as_array().unwrap().len(), 3);
        }
        assert!(browse_user_agent_metadata(ua, "157.0.8103.52", hints()).is_none());
        assert!(browse_user_agent_metadata(ua, "158.0.8127", hints()).is_none());
    }

    #[test]
    fn test_browse_google_chrome_version_validation() {
        assert_eq!(browse_google_chrome_major("Google Chrome 157.0.8103.39 "), Some(157));
        assert_eq!(browse_google_chrome_major("Google Chrome 152.0.7977.64"), Some(152));
        for value in ["Chromium 157.0.8103.39", "Google Chrome for Testing 157.0.8103.39",
                      "Google Chrome 157", "noise 157.0.8103.39", "Google Chrome 99.0.0.0"] {
            assert_eq!(browse_google_chrome_major(value), None, "{value}");
        }
    }
'''
    replace_once(chrome, 'mod tests {\n    use super::*;', 'mod tests {\n    use super::*;' + tests)

    print("Applied Runtime.disable in 4 locations and macOS/Linux browse defaults")


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit('Usage: patch_upstream.py /path/to/upstream-source')
    try:
        patch(Path(sys.argv[1]).resolve())
    except Exception as error:
        sys.exit(f'FAIL CLOSED: {error}')
