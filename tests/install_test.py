"""Installer checks using temporary files and a mocked desktop command boundary."""
import contextlib
import importlib.util
import io
import json
import os
import stat
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

REPO = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("installer", REPO / "scripts/install-local.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)


class InstallTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.target = self.home / ".config/omarchy/plugins" / installer.PLUGIN
        self.calls = []
        for mocker in (patch.object(Path, "home", return_value=self.home),
                       patch.object(installer, "TARGET", self.target),
                       patch.object(installer.shutil, "which", return_value="/mock/bin"),
                       patch.object(installer, "run", side_effect=self.run_command)):
            mocker.start()
            self.addCleanup(mocker.stop)

    def run_command(self, *args):
        self.calls.append(args)
        if "listPlugins" in args:
            return json.dumps([{"id": installer.PLUGIN}])
        return "ok"

    def install(self):
        with contextlib.redirect_stdout(io.StringIO()):
            installer.main()

    def test_fresh_install_without_user_config(self):
        self.install()
        self.assertTrue((self.target / "LICENSE").is_file())
        self.assertTrue((self.target / "adapters/desktop.py").is_file())
        self.assertFalse((self.target / "tests").exists())
        self.assertIn(("omarchy", "restart", "shell"), self.calls)
        self.assertFalse(any("disable" in call for call in self.calls))

    def test_update_preserves_settings_placement_and_backup(self):
        self.target.mkdir(parents=True)
        (self.target / "manifest.json").write_text(json.dumps({"id": installer.PLUGIN}))
        (self.target / "old.txt").write_text("old artifact")
        saved = {"id": installer.PLUGIN, "workMinutes": 42, "futureSetting": "keep", "meetingGraceSeconds": 5}
        config = {"bar": {"layout": {"left": [{"id": "other"}, saved]}}}
        (self.home / ".config/omarchy/shell.json").write_text(json.dumps(config))
        self.install()
        backup = next(self.target.parent.glob('.omadoro-install-*'))
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)
        self.assertEqual((backup / 'plugin/old.txt').read_text(), 'old artifact')
        self.assertEqual(json.loads((backup / 'saved-entry.json').read_text()), saved)
        self.assertFalse((self.target / 'old.txt').exists())
        self.assertIn(("omarchy-shell", "shell", "setBarWidget", installer.PLUGIN, "workMinutes", "42", "{}"), self.calls)
        self.assertIn(("omarchy-shell", "shell", "setBarWidget", installer.PLUGIN, "futureSetting", '"keep"', "{}"), self.calls)
        self.assertFalse(any("meetingGraceSeconds" in call for call in self.calls))
        self.assertIn(("omarchy", "bar", "move", installer.PLUGIN, "--section", "left", "--index", "1"), self.calls)

    def test_missing_runtime_dependency_does_not_write_plugin(self):
        with patch.object(installer, "run", side_effect=subprocess.CalledProcessError(1, "python")):
            with self.assertRaises(subprocess.CalledProcessError):
                self.install()
        self.assertFalse(self.target.exists())

    def test_refuses_symlink_destination(self):
        self.target.parent.mkdir(parents=True)
        elsewhere = self.home / 'elsewhere'
        elsewhere.mkdir()
        self.target.symlink_to(elsewhere, target_is_directory=True)
        with self.assertRaisesRegex(RuntimeError, "symlink"):
            self.install()
        self.assertEqual(list(elsewhere.iterdir()), [])

    def old_install(self):
        self.target.mkdir(parents=True)
        (self.target / "manifest.json").write_text(json.dumps({"id": installer.PLUGIN}))
        (self.target / "old.txt").write_text("old artifact")

    def test_rejects_nested_destination_symlinks_without_touching_external_files(self):
        self.old_install()
        external = self.home / 'external'
        external.mkdir()
        sentinel = external / 'sentinel'
        sentinel.write_text('untouched')
        for name in ('Service.qml', 'adapters', 'components/link', 'model/deep/link'):
            with self.subTest(name=name):
                link = self.target / name
                link.parent.mkdir(parents=True, exist_ok=True)
                link.symlink_to(external if name == 'adapters' else sentinel)
                with self.assertRaisesRegex(RuntimeError, 'symlink'):
                    self.install()
                self.assertEqual(sentinel.read_text(), 'untouched')
                self.assertFalse(any('disable' in call for call in self.calls))
                link.unlink()

    def test_rejects_symlinked_parent(self):
        external = self.home / 'external'
        external.mkdir()
        (self.home / '.config').symlink_to(external)
        with self.assertRaisesRegex(RuntimeError, 'symlink'):
            self.install()
        self.assertEqual(list(external.iterdir()), [])

    def test_rejects_nonregular_destination(self):
        self.old_install()
        os.mkfifo(self.target / 'pipe')
        with self.assertRaisesRegex(RuntimeError, 'non-regular'):
            self.install()
        self.assertFalse(any('disable' in call for call in self.calls))

    def test_staging_validation_failure_leaves_existing_plugin_enabled_and_unchanged(self):
        self.old_install()
        def command(*args):
            if 'validate' in args and args[-1] != str(installer.ROOT):
                staged = Path(args[-1])
                self.assertEqual(stat.S_IMODE(staged.parent.stat().st_mode), 0o700)
                raise RuntimeError('invalid staged plugin')
            return self.run_command(*args)
        with patch.object(installer, 'run', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'invalid staged'):
                self.install()
        self.assertEqual((self.target / 'old.txt').read_text(), 'old artifact')
        self.assertFalse(any('disable' in call for call in self.calls))
        self.assertEqual(list(self.target.parent.glob('.omadoro-install-*')), [])

    def test_activation_failure_rolls_back_artifact_settings_and_placement(self):
        self.old_install()
        saved = {'id': installer.PLUGIN, 'workMinutes': 42, 'meetingGraceSeconds': 5}
        config = {'bar': {'layout': {'left': [saved]}}}
        (self.home / '.config/omarchy/shell.json').write_text(json.dumps(config))
        failed = False
        def command(*args):
            nonlocal failed
            if 'enablePlugin' in args and not failed:
                failed = True
                self.assertTrue((self.target / 'Service.qml').exists())
                raise RuntimeError('activation failed')
            return self.run_command(*args)
        with patch.object(installer, 'run', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'activation failed'):
                self.install()
        self.assertEqual((self.target / 'old.txt').read_text(), 'old artifact')
        self.assertFalse((self.target / 'Service.qml').exists())
        self.assertIn(('omarchy-shell', 'shell', 'setBarWidget', installer.PLUGIN,
                       'meetingGraceSeconds', '5', '{}'), self.calls)
        self.assertIn(('omarchy', 'bar', 'move', installer.PLUGIN, '--section', 'left', '--index', '0'), self.calls)
        self.assertEqual(list(self.target.parent.glob('.omadoro-install-*')), [])

    def test_failed_fresh_install_removes_artifact(self):
        def command(*args):
            if 'enablePlugin' in args:
                raise RuntimeError('activation failed')
            return self.run_command(*args)
        with patch.object(installer, 'run', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'activation failed'):
                self.install()
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.glob('.omadoro-install-*')), [])

    def test_exchange_failure_keeps_old_artifact(self):
        self.old_install()
        with patch.object(installer, 'exchange', side_effect=OSError('exchange failed')):
            with self.assertRaisesRegex(OSError, 'exchange failed'):
                self.install()
        self.assertEqual((self.target / 'old.txt').read_text(), 'old artifact')
        self.assertEqual(list(self.target.parent.glob('.omadoro-install-*')), [])

    def test_rejects_source_symlink(self):
        source = self.home / 'source'
        source.mkdir()
        sentinel = self.home / 'sentinel'
        sentinel.write_text('untouched')
        (source / 'manifest.json').symlink_to(sentinel)
        with patch.object(installer, 'ROOT', source):
            with self.assertRaisesRegex(RuntimeError, 'symlink'):
                self.install()
        self.assertEqual(sentinel.read_text(), 'untouched')
        self.assertFalse(self.target.exists())
        self.assertEqual(list(self.target.parent.glob('.omadoro-install-*')), [])

    def test_rollback_failure_retains_previous_artifact_and_settings(self):
        self.old_install()
        real_exchange = installer.exchange
        swaps = 0
        def exchange(left, right):
            nonlocal swaps
            swaps += 1
            if swaps == 2:
                raise OSError('rollback failed')
            real_exchange(left, right)
        with patch.object(installer, 'exchange', side_effect=exchange), \
             patch.object(installer, 'activate', side_effect=RuntimeError('activation failed')):
            with self.assertRaisesRegex(RuntimeError, 'Artifact rollback failed; recovery files retained'):
                self.install()
        backup = next(self.target.parent.glob('.omadoro-install-*'))
        self.assertEqual((backup / 'plugin/old.txt').read_text(), 'old artifact')
        self.assertTrue((backup / 'saved-entry.json').is_file())
        self.assertEqual(stat.S_IMODE(backup.stat().st_mode), 0o700)

    def test_refuses_installing_over_source_checkout(self):
        with patch.object(installer, "TARGET", REPO):
            with self.assertRaisesRegex(RuntimeError, "separate checkout"):
                self.install()


if __name__ == '__main__':
    unittest.main()
