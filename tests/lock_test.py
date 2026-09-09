"""Verify the lock handshake without locking the developer's desktop."""
import importlib.util
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("lock_adapter", Path(__file__).resolve().parents[1] / "adapters/lock.py")
adapter = importlib.util.module_from_spec(spec)
spec.loader.exec_module(adapter)


class LockTests(unittest.TestCase):
    def test_waits_for_compositor_confirmation_not_request_acceptance(self):
        with patch.object(adapter, 'run', side_effect=['', json.dumps({'locked': True, 'secure': False}),
                                                     json.dumps({'secure': True})]) as run, \
                patch.object(adapter.time, 'sleep'):
            adapter.lock_session()
        self.assertEqual(run.call_args_list[0].args, ('omarchy', 'system', 'lock'))
        self.assertEqual([call.args for call in run.call_args_list[1:]], [('omarchy-shell', 'lock', 'status')] * 2)

    def test_request_without_confirmation_times_out(self):
        with patch.object(adapter, 'run', side_effect=['', '{"locked":true,"secure":false}']), \
                patch.object(adapter.time, 'monotonic', side_effect=[0, 0, 6]), \
                patch.object(adapter.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'did not confirm'):
                adapter.lock_session()

    def test_missing_authentication_is_an_error(self):
        with patch.object(adapter, 'run', side_effect=['', '{"passwordPam":false,"secure":false}']):
            with self.assertRaisesRegex(RuntimeError, 'authentication'):
                adapter.lock_session()

    def test_malformed_status_is_not_success(self):
        for status in ['not json', 'null', '[]']:
            with self.subTest(status=status), patch.object(adapter, 'run', side_effect=['', status]):
                with self.assertRaises((ValueError, RuntimeError)):
                    adapter.lock_session()

    def test_command_failure_is_not_success(self):
        with patch.object(adapter, 'run', side_effect=subprocess.TimeoutExpired('omarchy', 3)):
            with self.assertRaises(subprocess.TimeoutExpired):
                adapter.lock_session()


if __name__ == '__main__':
    unittest.main()
