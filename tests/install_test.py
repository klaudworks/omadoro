"""Installer checks using temporary files and a mocked desktop command boundary."""
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import shutil
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
        self.backups = []
        self.addCleanup(lambda: [shutil.rmtree(p) for p in self.backups if p.exists()])
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
        if "disable" in args:
            self.backups.append(Path('/tmp') / ('omadoro-backup-install-test-' + self.home.name))
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
        with patch.object(installer.time, 'time_ns', return_value='install-test-' + self.home.name):
            self.install()
        backup = self.backups[0]
        self.assertEqual((backup / 'old.txt').read_text(), 'old artifact')
        self.assertEqual(json.loads((backup / 'saved-entry.json').read_text()), saved)
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

    def test_refuses_installing_over_source_checkout(self):
        with patch.object(installer, "TARGET", REPO):
            with self.assertRaisesRegex(RuntimeError, "separate checkout"):
                self.install()


if __name__ == '__main__':
    unittest.main()
