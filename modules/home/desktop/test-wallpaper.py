#!/usr/bin/env python3
"""Isolated wallpaper tests; the real desktoppr and GUI are never used."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('apply_wallpaper', Path(__file__).with_name('apply-wallpaper.py'))
wallpaper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(wallpaper)


class WallpaperTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory(prefix='desktop-wallpaper-test-')
        self.addCleanup(self.directory.cleanup)
        self.home = Path(self.directory.name)
        self.image = self.home / 'declared wallpaper.heic'
        self.image.write_bytes(b'declared image')
        self.previous = self.home / 'previous.heic'
        self.previous.write_bytes(b'previous image')
        self.state = self.home / 'state/wallpaper.json'
        self.control = self.home / 'fake.json'
        self.control.write_text(json.dumps({'paths': [str(self.previous)] * 2, 'sets': 0, 'queries': 0}))
        self.cli = self.home / 'fake-desktoppr'
        self.cli.write_text('#!' + sys.executable + '\n' + '''import json, os, sys
from pathlib import Path
control = Path(os.environ['FAKE_DESKTOPPR_STATE'])
data = json.loads(control.read_text())
if sys.argv[1:] == ['all']:
    data['queries'] += 1
    control.write_text(json.dumps(data))
    print('\\n'.join(data['paths']))
elif len(sys.argv) == 3 and sys.argv[1] == 'all':
    if data.get('fail_set'):
        sys.exit(7)
    data['sets'] += 1
    if not data.get('ignore_set'):
        data['paths'] = [sys.argv[2]] * len(data['paths'])
    control.write_text(json.dumps(data))
else:
    sys.exit(8)
''')
        self.cli.chmod(0o755)
        self.env = patch.dict(os.environ, {'HOME': str(self.home), 'FAKE_DESKTOPPR_STATE': str(self.control)})
        self.env.start()
        self.addCleanup(self.env.stop)
        self.gui = patch.object(wallpaper, 'console_session_ready', return_value=True)
        self.gui.start()
        self.addCleanup(self.gui.stop)
        self.sleep = patch.object(wallpaper.time, 'sleep')
        self.sleep.start()
        self.addCleanup(self.sleep.stop)

    def control_data(self, **updates):
        data = json.loads(self.control.read_text())
        if updates:
            data.update(updates)
            self.control.write_text(json.dumps(data))
        return data

    def apply(self, force=False):
        with contextlib.redirect_stdout(io.StringIO()):
            return wallpaper.apply_wallpaper(str(self.cli), self.image, self.state, force)

    def test_initial_all_displays_then_manual_choice_is_preserved(self):
        self.assertEqual(self.apply(), 'applied')
        self.assertEqual(self.control_data()['sets'], 1)
        self.assertEqual(json.loads(self.state.read_text())['display_count'], 2)
        self.control_data(paths=[str(self.previous)] * 2)
        before = self.control_data()
        self.assertEqual(self.apply(), 'unchanged')
        self.assertEqual(self.control_data(), before)

    def test_source_content_change_and_force_reapply(self):
        self.apply()
        self.control_data(paths=[str(self.previous)] * 2)
        self.assertEqual(self.apply(force=True), 'applied')
        # Refresh even if a mutable source changed at the same path.
        self.image.write_bytes(b'new declared image')
        self.assertEqual(self.apply(), 'applied')
        self.assertEqual(self.control_data()['sets'], 3)
        self.assertEqual(json.loads(self.state.read_text())['sha256'], wallpaper.image_hash(self.image))

    def test_already_matching_image_bytes_avoid_reset(self):
        self.previous.write_bytes(self.image.read_bytes())
        self.assertEqual(self.apply(), 'already-matching')
        self.assertEqual(self.control_data()['sets'], 0)
        self.assertTrue(self.state.is_file())

    def test_failed_command_does_not_publish_marker(self):
        self.control_data(fail_set=True)
        with self.assertRaises(subprocess.CalledProcessError):
            self.apply()
        self.assertFalse(self.state.exists())

    def test_unverified_success_does_not_publish_marker(self):
        self.control_data(ignore_set=True)
        with self.assertRaises(RuntimeError):
            self.apply()
        self.assertFalse(self.state.exists())

    def test_no_gui_or_no_displays_defers_without_marker(self):
        with patch.object(wallpaper, 'console_session_ready', return_value=False):
            self.assertEqual(self.apply(), 'deferred')
        self.assertEqual(self.control_data()['queries'], 0)
        self.control_data(paths=[])
        self.assertEqual(self.apply(), 'deferred')
        self.assertFalse(self.state.exists())


if __name__ == '__main__':
    unittest.main()
