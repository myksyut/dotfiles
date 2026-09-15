"""Regression checks using invented profiles, never a real browser profile."""

import copy
import contextlib
import importlib.util
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).with_name("apply-app-themes.py")
loader = importlib.util.spec_from_file_location("app_themes", SCRIPT)
themes = importlib.util.module_from_spec(loader)
loader.loader.exec_module(themes)
SPEC = json.loads(SCRIPT.with_name("themes").joinpath("zen-workspaces.json").read_text())
ORCA_SPEC = json.loads(SCRIPT.with_name("themes").joinpath("orca-theme.json").read_text())


def fixture():
    space = {"uuid": "example-workspace", "name": "Example", "theme": {"old": True}, "container": 7}
    sidebar = {"spaces": [space], "tabs": [{"url": "https://example.invalid", "pinned": True}], "folders": [{"id": "folder"}]}
    session = {
        "windows": [
            {"spaces": [space], "tabs": [{"entries": [{"url": "https://example.invalid"}]}], "groups": [42]},
            {"isPrivate": True, "spaces": [space]},
            {"isZenUnsynced": True, "spaces": [space]},
        ],
        "_closedWindows": [{"spaces": [space]}],
    }
    return {
        "zen-sessions.jsonlz4": themes.encode(sidebar),
        "sessionstore.jsonlz4": themes.encode(session),
        "prefs.js": b'// Fixture\nuser_pref("unrelated.preference", true);\nuser_pref("zen.view.window.scheme", 1);\n',
    }


def orca_fixture(existing=True):
    entries = [{"id": "warp:another", "name": "Another", "terminal": {"background": "#123456"}}]
    if existing:
        entries.append({"id": "warp:existing-sky-copy", "name": "Sky Copy", "source": "warp", "mode": "dark",
                        "importedAt": "2025-01-01T00:00:00.000Z", "sourceLabel": "Original.yaml",
                        "terminal": {"background": "#000000", "selectionBackground": "#123456"}})
    data = {"schemaVersion": 42, "settings": {"terminalCustomThemes": entries, "fontSize": 15,
                                              "terminalThemeDark": "custom:warp:existing-sky-copy",
                                              "terminalThemeLight": "Untouched Light"},
            "workspaceSession": {"tabs": ["example-tab"], "selected": "example-tab"},
            "auth": {"fake-fixture-only": "preserve"}, "projects": [{"name": "Example"}]}
    return {themes.ORCA_FILE: (json.dumps(data) + "\n").encode()}


class AppThemesTests(unittest.TestCase):
    def test_preserves_non_theme_data_and_is_idempotent(self):
        before = fixture()
        writes, report = themes.plan_changes(before, SPEC)
        updated = dict(before, **writes)
        sidebar = themes.decode(writes["zen-sessions.jsonlz4"])
        old_sidebar = themes.decode(before["zen-sessions.jsonlz4"])
        self.assertEqual(sidebar["tabs"], old_sidebar["tabs"])
        self.assertEqual(sidebar["folders"], old_sidebar["folders"])
        sessions = themes.decode(updated["sessionstore.jsonlz4"])
        original_sessions = themes.decode(before["sessionstore.jsonlz4"])
        self.assertEqual(sessions["windows"][1:], original_sessions["windows"][1:])
        self.assertEqual(sessions["_closedWindows"], original_sessions["_closedWindows"])
        self.assertEqual(sessions["windows"][0]["groups"], [42])
        self.assertEqual(report["workspace_count"], 1)
        self.assertEqual(themes.plan_changes(updated, SPEC)[0], {})

    def test_ambiguous_profiles_are_reported_individually(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "profiles.ini").write_text("[Profile0]\nPath=Profiles/one\n[Profile1]\nPath=Profiles/two\nDefault=1\n")
            for name in ("one", "two"):
                profile = root / "Profiles" / name
                profile.mkdir(parents=True)
                (profile / "prefs.js").touch()
                (profile / "zen-sessions.jsonlz4").touch()
            self.assertEqual(len(themes.discover_profiles(root)), 2)

    def test_running_browser_is_rejected(self):
        with patch.object(themes.subprocess, "check_output", return_value="/Applications/Zen.app/Contents/MacOS/zen\n"):
            with self.assertRaisesRegex(RuntimeError, "Quit Zen"):
                themes.stopped()

    def test_concurrent_change_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "prefs.js"
            path.write_bytes(b"new external content")
            with self.assertRaisesRegex(RuntimeError, "changed since preview"):
                themes.replace_if_unchanged(path, b"old", b"our change")
            self.assertEqual(path.read_bytes(), b"new external content")
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_backup_and_partial_failure_rollback(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile"
            profile.mkdir()
            originals = fixture()
            for name, raw in originals.items():
                (profile / name).write_bytes(raw)
            writes, _ = themes.plan_changes(originals, SPEC)
            real_replace = themes.replace_if_unchanged
            calls = 0

            def fail_second(*args):
                nonlocal calls
                calls += 1
                if calls == 2:
                    raise OSError("simulated disk failure")
                return real_replace(*args)

            with patch.object(themes, "stopped"), patch.object(themes, "replace_if_unchanged", side_effect=fail_second):
                with self.assertRaisesRegex(RuntimeError, "simulated disk failure"):
                    themes.apply_changes(profile, originals, writes, root / "backups")
            self.assertEqual(themes.read_profile(profile), originals)
            backup = next((root / "backups").iterdir())
            self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
            for item in backup.iterdir():
                self.assertEqual(item.stat().st_mode & 0o777, 0o600)
                self.assertEqual(item.read_bytes(), originals[item.name])

    def test_successful_apply_then_noop(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile"
            profile.mkdir()
            originals = fixture()
            for name, raw in originals.items():
                (profile / name).write_bytes(raw)
            writes, _ = themes.plan_changes(originals, SPEC)
            with patch.object(themes, "stopped"):
                backup = themes.apply_changes(profile, originals, writes, root / "backups")
                updated = themes.read_profile(profile)
                self.assertTrue(backup.is_dir())
                self.assertEqual(themes.plan_changes(updated, SPEC)[0], {})
                self.assertIsNone(themes.apply_changes(profile, updated, {}, root / "backups"))
            self.assertEqual(len(list((root / "backups").iterdir())), 1)

    def test_unsupported_or_ambiguous_data_is_rejected(self):
        bad = fixture()
        bad["zen-sessions.jsonlz4"] = b"unexpected-format"
        with self.assertRaisesRegex(ValueError, "Unrecognized"):
            themes.plan_changes(bad, SPEC)
        bad = fixture()
        bad["prefs.js"] += b'user_pref("zen.view.window.scheme", 0);\n'
        with self.assertRaisesRegex(ValueError, "Duplicate"):
            themes.plan_changes(bad, SPEC)

    def test_orca_reuses_theme_and_preserves_other_data(self):
        before = orca_fixture()
        writes, _ = themes.plan_orca_changes(before, ORCA_SPEC)
        old = json.loads(before[themes.ORCA_FILE])
        new = json.loads(writes[themes.ORCA_FILE])
        self.assertEqual({k: v for k, v in new.items() if k != "settings"},
                         {k: v for k, v in old.items() if k != "settings"})
        self.assertEqual(new["settings"]["fontSize"], 15)
        self.assertEqual(new["settings"]["terminalThemeLight"], "Untouched Light")
        entries = new["settings"]["terminalCustomThemes"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[0], old["settings"]["terminalCustomThemes"][0])
        self.assertEqual(entries[1]["id"], "warp:existing-sky-copy")
        self.assertEqual(entries[1]["importedAt"], "2025-01-01T00:00:00.000Z")
        self.assertEqual(entries[1]["terminal"]["selectionBackground"], "#123456")
        self.assertEqual(themes.plan_orca_changes(writes, ORCA_SPEC)[0], {})

    def test_orca_seeds_a_new_theme_once(self):
        before = orca_fixture(existing=False)
        writes, _ = themes.plan_orca_changes(before, ORCA_SPEC)
        entries = json.loads(writes[themes.ORCA_FILE])["settings"]["terminalCustomThemes"]
        self.assertEqual(len(entries), 2)
        self.assertEqual(entries[-1]["id"], "manual:nix-sky-copy")
        self.assertEqual(themes.plan_orca_changes(writes, ORCA_SPEC)[0], {})

    def test_running_apps_are_read_only_and_deferred_only_if_needed(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for app, original, spec in (("zen", fixture(), SPEC), ("orca", orca_fixture(), ORCA_SPEC)):
                profile = root / app
                profile.mkdir()
                for name, raw in original.items():
                    (profile / name).write_bytes(raw)
                with patch.object(themes, "app_is_running", return_value=True):
                    report = themes.process_profile(app, profile, spec, apply=True, defer_running=True, state=root)
                self.assertEqual(report["status"], "deferred")
                self.assertEqual(themes.read_files(profile, original), original)
                planner = themes.plan_changes if app == "zen" else themes.plan_orca_changes
                desired = dict(original, **planner(original, spec)[0])
                for name, raw in desired.items():
                    (profile / name).write_bytes(raw)
                if app == "zen":
                    (profile / "sessionstore.jsonlz4").unlink()
                with patch.object(themes, "app_is_running", return_value=True):
                    report = themes.process_profile(app, profile, spec, apply=True, defer_running=True, state=root)
                self.assertEqual(report["status"], "unchanged")
            self.assertFalse((root / "desktop-theme").exists())

    def test_orca_stopped_apply_has_private_backup_and_no_duplicate(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            profile = root / "profile"
            profile.mkdir()
            original = orca_fixture()
            (profile / themes.ORCA_FILE).write_bytes(original[themes.ORCA_FILE])
            with patch.object(themes, "app_is_running", return_value=False):
                report = themes.process_profile("orca", profile, ORCA_SPEC, apply=True, state=root)
                again = themes.process_profile("orca", profile, ORCA_SPEC, apply=True, state=root)
            self.assertEqual(report["status"], "applied")
            self.assertEqual(again["status"], "unchanged")
            backup = Path(report["backup"])
            self.assertEqual((backup / themes.ORCA_FILE).read_bytes(), original[themes.ORCA_FILE])
            self.assertEqual((backup / themes.ORCA_FILE).stat().st_mode & 0o777, 0o600)

    def test_uninitialized_profiles_are_skipped(self):
        with tempfile.TemporaryDirectory() as directory, patch.object(themes, "app_is_running", return_value=False):
            root = Path(directory)
            report = themes.process_profile("orca", root, ORCA_SPEC, apply=True, state=root)
            self.assertEqual(report["status"], "skipped")
            with patch.object(themes.Path, "home", return_value=root), contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(themes.main(["--app", "all", "--apply", "--defer-running"]), 0)
            self.assertTrue(all(item["status"] == "skipped" for item in json.loads(output.getvalue())["profiles"]))

    def test_orca_theme_spec_cannot_change_non_theme_setting(self):
        bad_spec = copy.deepcopy(ORCA_SPEC)
        bad_spec["settings"]["fontSize"] = 99
        with self.assertRaisesRegex(ValueError, "unsupported settings"):
            themes.plan_orca_changes(orca_fixture(), bad_spec)

    def test_activation_and_periodic_runs_share_one_lock(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with themes.apply_lock(root) as first:
                self.assertTrue(first)
                with themes.apply_lock(root) as second:
                    self.assertFalse(second)
            with themes.apply_lock(root) as later:
                self.assertTrue(later)
            self.assertEqual((root / "desktop-theme/app-theme-sync.lock").stat().st_mode & 0o777, 0o600)

    def test_app_start_before_atomic_replace_prevents_write(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "orca-data.json"
            path.write_bytes(b"original")

            def opened_app():
                raise themes.RunningApp("App opened")

            with self.assertRaises(themes.RunningApp):
                themes.replace_if_unchanged(path, b"original", b"replacement", opened_app)
            self.assertEqual(path.read_bytes(), b"original")
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_ambiguous_json_is_rejected_without_logging_its_data(self):
        for raw in (b'{"sensitive-example-key":1,"sensitive-example-key":2}', b'{"value":NaN}'):
            with self.assertRaises(ValueError) as caught:
                themes.plan_orca_changes({themes.ORCA_FILE: raw}, ORCA_SPEC)
            self.assertNotIn("sensitive-example-key", str(caught.exception))

    def test_quiet_periodic_run_does_not_log_skipped_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with patch.object(themes.Path, "home", return_value=root), patch.dict(themes.os.environ, {"XDG_STATE_HOME": str(root / "state")}), contextlib.redirect_stdout(io.StringIO()) as output:
                result = themes.main(["--app", "all", "--apply", "--defer-running", "--quiet"])
            self.assertEqual(result, 0)
            self.assertEqual(output.getvalue(), "")

    def test_zen_preference_whitespace_supported_and_unknown_value_rejected(self):
        before = fixture()
        before["prefs.js"] = b'user_pref( "zen.view.window.scheme" , 1 );\nuser_pref("unrelated", 42);\n'
        writes, _ = themes.plan_changes(before, SPEC)
        self.assertEqual(writes["prefs.js"], b'user_pref("zen.view.window.scheme", 0);\nuser_pref("unrelated", 42);\n')
        before["prefs.js"] = b'user_pref("zen.view.window.scheme", "unsupported");\n'
        with self.assertRaisesRegex(ValueError, "Unrecognized Zen window scheme"):
            themes.plan_changes(before, SPEC)

    def test_empty_or_relative_state_directory_never_uses_working_directory(self):
        for value in ("", "relative-state"):
            with patch.dict(themes.os.environ, {"XDG_STATE_HOME": value}):
                self.assertEqual(themes.state_directory(), Path.home() / ".local/state")


if __name__ == "__main__":
    unittest.main()
