"""Offline installer and packaging regressions. Never touches the real HOME."""
import hashlib
import importlib.util
import io
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from unittest import mock


SCRIPTS = Path(__file__).resolve().parent


def load_module(name):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


package = load_module("package")
merge_sums = load_module("merge_sums")


class InstallerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        host = (platform.system(), platform.machine())
        if host not in (("Darwin", "arm64"), ("Linux", "x86_64")) or not shutil.which("cc"):
            raise unittest.SkipTest("Native installer fixtures require Mac ARM64 or Linux x86_64 and cc")
        cls.macos = host[0] == "Darwin"
        cls.target = "darwin-arm64" if cls.macos else "linux-x86_64"
        cls.asset = f"agent-browser-browse-{cls.target}.tar.gz"
        cls.fixture_dir = tempfile.TemporaryDirectory(prefix="browse-native-fixture-")
        cls.addClassCleanup(cls.fixture_dir.cleanup)
        cls.native = Path(cls.fixture_dir.name) / "native"
        source = r"""
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
int main(int argc, char **argv) {
    if (argc == 2 && strcmp(argv[1], "--version") == 0) {
        const char *v = getenv("BROWSE_TEST_VERSION");
        printf("agent-browser %s\n", v ? v : "0.43.0"); return 0;
    }
    const char *ns = getenv("AGENT_BROWSER_NAMESPACE");
    if (!ns || strcmp(ns, "abb") != 0) return 4;
    if (getenv("AGENT_BROWSER_SOCKET_DIR")) return 5;
    const char *active = getenv("BROWSE_TEST_ACTIVE");
    puts(active ? "{\"success\":true,\"data\":{\"sessions\":[\"fixture\"]}}"
                : "{\"success\":true,\"data\":{\"sessions\":[]}}");
    return 0;
}
"""
        subprocess.run(["cc", "-x", "c", "-", "-o", str(cls.native)], input=source, text=True, check=True, capture_output=True)
        if cls.macos:
            subprocess.run(["codesign", "--force", "--sign", "-", "--timestamp=none", str(cls.native)], check=True, capture_output=True)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="browse-installer-test-")
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.home = self.root / "home"
        self.home.mkdir()
        self.base = self.home / ".local/share/agent-browser-browse"
        self.bin_dir = self.home / ".local/bin"
        self.wrapper = self.bin_dir / "agent-browser-browse"
        self.current = self.base / "current"
        self.download = self.root / "download"
        self.download.mkdir()
        fakebin = self.root / "fakebin"
        fakebin.mkdir()
        curl = fakebin / "curl"
        curl.write_text(
            "#!/usr/bin/env python3\n"
            "import os,pathlib,shutil,sys\n"
            "args=sys.argv[1:]\n"
            "url=next(a for a in args if a.startswith('https://'))\n"
            "assert url.startswith('https://github.com/amxv/agent-browser-browse/releases/download/v0.43.0/')\n"
            "dest=args[args.index('--output')+1]\n"
            "shutil.copyfile(pathlib.Path(os.environ['BROWSE_TEST_DOWNLOAD'])/url.rsplit('/',1)[1],dest)\n"
        )
        curl.chmod(0o755)
        script_name = "install-macos.sh" if self.macos else "install-linux.sh"
        script = (SCRIPTS / script_name).read_text()
        # Only this disposable copy uses the fake curl, never the real installer.
        if self.macos:
            script = script.replace(
                "export PATH=/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin",
                'export PATH="$BROWSE_TEST_PATH"',
            )
            script = script.replace("$HOME", "$BROWSE_TEST_INSTALL_ROOT")
        self.wrapper_text = re.search(r"<<'WRAPPER'\n(.*?)\nWRAPPER", script, re.S).group(1) + "\n"
        self.script = self.root / script_name
        self.script.write_text(script)
        self.env = {
            **os.environ,
            "BROWSE_TEST_INSTALL_ROOT": str(self.home),
            "XDG_DATA_HOME": str(self.home / ".local/share"),
            "XDG_BIN_HOME": str(self.bin_dir),
            "PATH": str(fakebin) + os.pathsep + os.environ["PATH"],
            "BROWSE_TEST_PATH": str(fakebin) + os.pathsep + os.environ["PATH"],
            "BROWSE_TEST_DOWNLOAD": str(self.download),
            "AGENT_BROWSER_NAMESPACE": "unrelated-custom-namespace",
            "AGENT_BROWSER_SOCKET_DIR": str(self.root / "unrelated-sockets"),
        }
        self.env.pop("BROWSE_TEST_ACTIVE", None)
        self.env.pop("BROWSE_TEST_VERSION", None)
        self.make_archive()

    def make_archive(self, binary=None, extra=None):
        contents = {
            "agent-browser-browse-native": self.native.read_bytes() if binary is None else binary,
            "LICENSE.upstream": b"Fixture license\n",
            "UPSTREAM_VERSION": b"0.43.0\n",
            "UPSTREAM_COMMIT": b"a" * 40 + b"\n",
            "PATCH_SHA256": b"b" * 64 + b"\n",
        }
        self.contents = contents
        with tarfile.open(self.download / self.asset, "w:gz") as archive:
            for name, data in contents.items():
                info = tarfile.TarInfo(name)
                info.size = len(data)
                archive.addfile(info, io.BytesIO(data))
            if extra is not None:
                archive.addfile(extra)
        self.digest = hashlib.sha256((self.download / self.asset).read_bytes()).hexdigest()
        self.sums = self.download / "SHA256SUMS"
        self.sums.write_text(
            f"{self.digest}  {self.asset}\n"
            + "c" * 64 + "  agent-browser-browse-other-platform.tar.gz\n"
        )

    def install_existing(self, version="0.42.0"):
        target = self.base / "versions" / version
        target.mkdir(parents=True)
        for name, data in self.contents.items():
            (target / name).write_bytes(data)
        (target / "UPSTREAM_VERSION").write_text(version + "\n")
        (target / "agent-browser-browse-native").chmod(0o755)
        self.current.symlink_to(target)
        self.bin_dir.mkdir(parents=True)
        self.wrapper.write_text(self.wrapper_text)
        self.wrapper.chmod(0o755)
        (self.base / "empty-config.json").write_text('{"custom":"preserve"}\n')
        return target

    def run_install(self, success=True):
        result = subprocess.run(
            ["bash", str(self.script), "0.43.0"], env=self.env,
            text=True, capture_output=True, timeout=30,
        )
        if success:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertFalse((self.base / ".install-lock").exists())
        self.assertFalse(list(self.base.glob(".stage.*")))
        return result

    def test_multiasset_upgrade_retains_previous_and_custom_config(self):
        old = self.install_existing()
        old_bytes = (old / "agent-browser-browse-native").read_bytes()
        self.run_install()
        self.assertEqual(self.current.resolve().name, "0.43.0")
        self.assertEqual((old / "agent-browser-browse-native").read_bytes(), old_bytes)
        self.assertEqual((self.base / "empty-config.json").read_text(), '{"custom":"preserve"}\n')
        self.assertEqual(self.wrapper.read_text(), self.wrapper_text)

    def test_first_install_and_repeat_are_idempotent(self):
        self.run_install()
        target = self.current.resolve()
        before = (target / "agent-browser-browse-native").stat().st_ino
        self.run_install()
        self.assertEqual(self.current.resolve(), target)
        self.assertEqual((target / "agent-browser-browse-native").stat().st_ino, before)

    def test_duplicate_target_checksum_is_rejected(self):
        self.sums.write_text(self.sums.read_text() + f"{self.digest}  {self.asset}\n")
        self.run_install(False)
        self.assertFalse(self.current.exists())

    def test_missing_target_checksum_is_rejected(self):
        self.sums.write_text("c" * 64 + "  agent-browser-browse-other-platform.tar.gz\n")
        self.run_install(False)

    def test_checksum_failure_keeps_current(self):
        old = self.install_existing()
        self.sums.write_text("0" * 64 + f"  {self.asset}\n")
        self.run_install(False)
        self.assertEqual(self.current.resolve(), old)

    def test_optimized_python_cannot_bypass_checksum_validation(self):
        old = self.install_existing()
        self.env["PYTHONOPTIMIZE"] = "1"
        self.sums.write_text("0" * 64 + f"  {self.asset}\n")
        result = self.run_install(False)
        self.assertIn("checksum mismatch", result.stdout + result.stderr)
        self.assertEqual(self.current.resolve(), old)
        self.assertFalse((self.base / "versions/0.43.0").exists())

    def test_wrong_architecture_is_rejected_before_execution(self):
        self.make_archive(binary=b"#!/bin/sh\nexit 0\n")
        self.run_install(False)
        self.assertFalse(self.current.exists())

    def test_compiled_version_mismatch_is_rejected(self):
        self.env["BROWSE_TEST_VERSION"] = "0.99.0"
        self.run_install(False)
        self.assertFalse(self.current.exists())

    def test_nonregular_archive_member_is_rejected(self):
        link = tarfile.TarInfo("UPSTREAM_VERSION")
        link.type = tarfile.SYMTYPE
        link.linkname = str(self.home / "do-not-touch")
        self.make_archive(extra=link)
        self.run_install(False)
        self.assertFalse((self.home / "do-not-touch").exists())

    def test_archive_traversal_is_rejected(self):
        self.make_archive(extra=tarfile.TarInfo("../escape"))
        self.run_install(False)
        self.assertFalse((self.base / "escape").exists())

    def test_conflicting_existing_version_is_not_activated(self):
        old = self.install_existing()
        target = self.base / "versions/0.43.0"
        target.mkdir()
        marker = target / "custom-file"
        marker.write_text("preserve")
        self.run_install(False)
        self.assertEqual(self.current.resolve(), old)
        self.assertEqual(marker.read_text(), "preserve")

    def test_active_owned_session_prevents_switch(self):
        old = self.install_existing()
        self.env["BROWSE_TEST_ACTIVE"] = "1"
        self.run_install(False)
        self.assertEqual(self.current.resolve(), old)

    def test_custom_wrapper_is_preserved(self):
        self.bin_dir.mkdir(parents=True)
        self.wrapper.write_text("#!/bin/sh\necho custom\n")
        self.run_install(False)
        self.assertEqual(self.wrapper.read_text(), "#!/bin/sh\necho custom\n")

    def test_external_current_symlink_is_preserved(self):
        self.base.mkdir(parents=True)
        elsewhere = self.root / "external"
        elsewhere.mkdir()
        self.current.symlink_to(elsewhere)
        self.run_install(False)
        self.assertEqual(self.current.resolve(), elsewhere)


class PackagingTests(unittest.TestCase):
    def test_elf_header_checks_class_endian_and_machine(self):
        with tempfile.TemporaryDirectory() as temporary:
            binary = Path(temporary) / "binary"
            valid = bytearray(20)
            valid[:7] = b"\x7fELF\x02\x01\x01"
            valid[18:20] = (62).to_bytes(2, "little")
            binary.write_bytes(valid)
            package.check_architecture(binary, "linux-x86_64")
            for offset, value in ((4, 1), (5, 2), (18, 183)):
                invalid = bytearray(valid)
                invalid[offset] = value
                binary.write_bytes(invalid)
                with self.assertRaises(ValueError):
                    package.check_architecture(binary, "linux-x86_64")

    def test_source_rejects_tag_mismatch_and_dashboard_placeholder(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "cli").mkdir()
            (root / "cli/Cargo.toml").write_text('[package]\nversion = "0.43.0"\n')
            out = root / "packages/dashboard/out"
            out.mkdir(parents=True)
            (out / "index.html").write_text("<p>Dashboard not built</p>")
            with mock.patch.object(package.subprocess, "check_output", return_value="a" * 40 + "\n"):
                with self.assertRaisesRegex(ValueError, "placeholder"):
                    package.source_metadata(root, "v0.43.0")
                (out / "index.html").write_text("<html>Dashboard</html>")
                (out / "bundle.js").write_text("console.log('fixture')")
                self.assertEqual(package.source_metadata(root, "v0.43.0"), ("0.43.0", "a" * 40))
            with mock.patch.object(package.subprocess, "check_output", side_effect=["a" * 40 + "\n", "b" * 40 + "\n"]):
                with self.assertRaisesRegex(ValueError, "requested upstream tag"):
                    package.source_metadata(root, "v0.43.0")

    def test_checksum_merge_preserves_old_assets_and_rejects_incomplete_manifest(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dist = root / "dist"
            dist.mkdir()
            old = "agent-browser-browse-darwin-arm64.tar.gz"
            new = "agent-browser-browse-linux-x86_64.tar.gz"
            (dist / new).write_bytes(b"new")
            names = root / "assets"
            names.write_text(old + "\nSHA256SUMS\n")
            previous = root / "previous"
            previous.write_text("a" * 64 + f"  {old}\n")
            merge_sums.main(previous, names, dist)
            self.assertIn("a" * 64 + f"  {old}\n", (dist / "SHA256SUMS").read_text())
            self.assertIn(hashlib.sha256(b"new").hexdigest(), (dist / "SHA256SUMS").read_text())
            previous.write_text("")
            with self.assertRaisesRegex(ValueError, "no checksum"):
                merge_sums.main(previous, names, dist)

    def test_checksum_merge_rejects_duplicate_and_existing_asset_overwrite(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            dist = root / "dist"
            dist.mkdir()
            asset = "agent-browser-browse-linux-x86_64.tar.gz"
            (dist / asset).write_bytes(b"new")
            names = root / "assets"
            names.write_text("")
            previous = root / "previous"
            row = "a" * 64 + "  agent-browser-browse-darwin-arm64.tar.gz\n"
            previous.write_text(row + row)
            with self.assertRaisesRegex(ValueError, "duplicate"):
                merge_sums.main(previous, names, dist)
            names.write_text(asset + "\n")
            with self.assertRaisesRegex(ValueError, "replace an existing"):
                merge_sums.main(previous, names, dist)


if __name__ == "__main__":
    unittest.main()
