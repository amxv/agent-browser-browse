#!/usr/bin/env python3
"""Post-patch guard for critical CDP hooks and launch defaults."""
from pathlib import Path
import sys

source = Path(sys.argv[1])
files = [
    "cli/src/native/browser.rs",
    "cli/src/native/actions.rs",
    "cli/src/native/state.rs",
]
expected = [2, 1, 1]
for name, count in zip(files, expected):
    text = (source / name).read_text()
    assert text.count('send_command_no_params("Runtime.disable"') == count, name
chrome = (source / "cli/src/native/cdp/chrome.rs").read_text()
for needle in (
    'fn browse_default_chrome()',
    'fn browse_headless_user_agent(chrome_path: &Path)',
    '--disable-blink-features=AutomationControlled',
    'browse_headless_user_agent(&chrome_path)',
    'try_launch_chrome(&chrome_path, &browse_options)',
):
    assert needle in chrome, needle
print("Verified four Runtime.disable hooks and cross-platform launch defaults")
