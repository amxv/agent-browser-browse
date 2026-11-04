"""Regression tests for the strict upstream patch and timeout relocation."""
import os
from pathlib import Path
import tempfile
import unittest

from patch_upstream import replace_once_across


OLD = "pub const DEFAULT_IDLE_TIMEOUT_MS: u64 = 60 * 60 * 1000;"
NEW = "pub const DEFAULT_IDLE_TIMEOUT_MS: u64 = 15 * 60 * 1000;"


class TimeoutPatchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.daemon = root / "daemon.rs"
        self.running = root / "running.rs"

    def test_legacy_definition(self):
        self.daemon.write_text(OLD)
        self.running.write_text("// absent in older upstream")
        replace_once_across([self.daemon, self.running], OLD, NEW)
        self.assertEqual(self.daemon.read_text(), NEW)
        self.assertNotIn(NEW, self.running.read_text())

    def test_relocated_definition(self):
        self.daemon.write_text("use crate::session_settings::DEFAULT_IDLE_TIMEOUT_MS;")
        self.running.write_text(OLD)
        replace_once_across([self.daemon, self.running], OLD, NEW)
        self.assertEqual(self.running.read_text(), NEW)
        self.assertNotIn(NEW, self.daemon.read_text())

    def test_missing_definition_fails_without_writing(self):
        self.daemon.write_text("// refactored")
        self.running.write_text("// refactored")
        with self.assertRaisesRegex(RuntimeError, "expected 1 anchor, found 0"):
            replace_once_across([self.daemon, self.running], OLD, NEW)
        self.assertEqual(self.daemon.read_text(), "// refactored")

    def test_duplicate_definitions_fail_without_writing(self):
        self.daemon.write_text(OLD)
        self.running.write_text(OLD)
        with self.assertRaisesRegex(RuntimeError, "expected 1 anchor, found 2"):
            replace_once_across([self.daemon, self.running], OLD, NEW)
        self.assertEqual(self.daemon.read_text(), OLD)
        self.assertEqual(self.running.read_text(), OLD)


class PatchedSourceTests(unittest.TestCase):
    @unittest.skipUnless(os.environ.get("PATCHED_UPSTREAM_ROOT"), "No patched tree")
    def test_expected_patches_remain_present(self):
        root = Path(os.environ["PATCHED_UPSTREAM_ROOT"]) / "cli/src"
        daemon = (root / "native/daemon.rs").read_text()
        running = (root / "session_settings/running.rs")
        timeout_sources = [daemon, running.read_text() if running.exists() else ""]
        self.assertEqual(sum(text.count(NEW) for text in timeout_sources), 1)
        self.assertEqual(sum(text.count(OLD) for text in timeout_sources), 0)
        self.assertIn("DEFAULT_IDLE_TIMEOUT_MS", daemon)

        for name, session in [
            ("browser.rs", "Some(session_id)"),
            ("browser.rs", "None"),
            ("actions.rs", "Some(session_id)"),
            ("state.rs", "Some(temp_session)"),
        ]:
            content = (root / "native" / name).read_text()
            self.assertIn(f'.send_command_no_params("Runtime.enable", {session})', content)
            self.assertIn(f'.send_command_no_params("Runtime.disable", {session})', content)

        chrome = (root / "native/cdp/chrome.rs").read_text()
        self.assertRegex(chrome, r"browse_default_chrome\(\)\s*\.or_else\(find_chrome\)")
        for preserved in [
            "let mut browse_options = effective_options.clone();",
            "browse_options.effectively_headless()",
            "browse_options.user_agent.is_none()",
            "try_launch_chrome(&chrome_path, &browse_options)",
        ]:
            self.assertIn(preserved, chrome)


if __name__ == "__main__":
    unittest.main()
