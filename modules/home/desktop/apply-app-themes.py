#!/usr/bin/env python3
"""Apply only the portable Zen / Orca colors. Default is a read-only preview.

Uses Zen's native workspace storage format as verified on 2026-09-15.
Session data stays on the destination machine and never belongs in the Nix repo.
Running applications are only inspected; --defer-running retries on a later run.
"""

import argparse
import configparser
import contextlib
import copy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile

import lz4.block

MAGIC = b"mozLz40\0"
PREF = re.compile(r'^user_pref\(\s*"zen\.view\.window\.scheme"\s*,\s*-?\d+\s*\);[ \t]*$', re.MULTILINE)
PREF_START = re.compile(r'^user_pref\(\s*"zen\.view\.window\.scheme"\s*,', re.MULTILINE)
SESSION_FILES = ("zen-sessions.jsonlz4", "sessionstore.jsonlz4")
ORCA_FILE = "orca-data.json"
ORCA_SETTINGS = {"theme", "leftSidebarAppearanceMode", "terminalDividerColorDark"}


class RunningApp(RuntimeError):
    pass


def strict_json(raw):
    """Do not normalize ambiguous/corrupt app data during a theme-only edit."""
    def object_pairs(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON keys; refusing to rewrite app data")
            result[key] = value
        return result

    def invalid_number(_):
        raise ValueError("Invalid JSON number; refusing to rewrite app data")

    return json.loads(raw, object_pairs_hook=object_pairs, parse_constant=invalid_number)


@contextlib.contextmanager
def apply_lock(state):
    """Serialize our activation and periodic jobs; this is not an app-owned lock."""
    directory = state / "desktop-theme"
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd = os.open(directory / "app-theme-sync.lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
        else:
            yield True
    finally:
        # Retain the inode so a subsequent invocation cannot lock a different file.
        os.close(fd)


def state_directory():
    # XDG requires an absolute path. Empty/relative values must not send private backups into cwd.
    value = os.environ.get("XDG_STATE_HOME", "")
    path = Path(value).expanduser()
    return path if value and path.is_absolute() else Path.home() / ".local/state"


def decode(raw):
    if not raw.startswith(MAGIC):
        raise ValueError("Unrecognized Zen session format; no files changed")
    document = strict_json(lz4.block.decompress(raw[len(MAGIC):]))
    if not isinstance(document, dict):
        raise ValueError("Expected a Zen session object")
    return document


def encode(document):
    raw = json.dumps(document, ensure_ascii=False, separators=(",", ":")).encode()
    result = MAGIC + lz4.block.compress(raw)
    if decode(result) != document:
        raise ValueError("Session round-trip failed")
    return result


def discover_profiles(root):
    """Only select a profile automatically when exactly one is initialized."""
    ini = configparser.ConfigParser(interpolation=None)
    ini.read(root / "profiles.ini")
    found = set()
    for section in ini.sections():
        if not section.startswith("Profile") or not ini.has_option(section, "Path"):
            continue
        path = Path(ini.get(section, "Path")).expanduser()
        if ini.get(section, "IsRelative", fallback="1") == "1":
            path = root / path
        if (path / "zen-sessions.jsonlz4").is_file() and (path / "prefs.js").is_file():
            found.add(path.resolve())
    return sorted(found)


def app_is_running(app):
    processes = subprocess.check_output(["/bin/ps", "-axo", "comm="], text=True)
    for line in processes.splitlines():
        command = line.strip()
        if f"/{app.title()}.app/Contents/" in command or Path(command).name.lower() in {app, f"{app}-bin"}:
            return True
    return False


def stopped(app="zen"):
    if app_is_running(app):
        raise RunningApp(f"Quit {app.title()} normally before --apply, then run the preview again")


def read_files(profile, names):
    originals = {}
    for name in names:
        path = profile / name
        if path.is_symlink():
            raise ValueError(f"Refusing to replace a symlink: {name}")
        if not path.is_file():
            raise ValueError(f"Missing {name}; start the app once and quit it normally first")
        originals[name] = path.read_bytes()
    return originals


def read_profile(profile, allow_running=False):
    names = [*SESSION_FILES, "prefs.js"]
    # A running Zen removes its clean-shutdown file. Inspect its sidebar/prefs only.
    if allow_running and not (profile / SESSION_FILES[1]).exists():
        names.remove(SESSION_FILES[1])
    return read_files(profile, names)


def plan_changes(originals, spec):
    sidebar = decode(originals[SESSION_FILES[0]])
    spaces = sidebar.get("spaces")
    if not isinstance(spaces, list) or not spaces:
        raise ValueError("No initialized Zen workspaces found")
    ids = [space["uuid"] for space in spaces]
    if any(not isinstance(uid, str) or not uid for uid in ids) or len(set(ids)) != len(ids):
        raise ValueError("Unexpected workspace identifiers")
    identifiers = set(ids)
    writes, counts = {}, {}
    for name in SESSION_FILES:
        if name not in originals:
            continue
        before = decode(originals[name])
        after = copy.deepcopy(before)
        pairs = []
        if "spaces" in before:
            pairs.append((before["spaces"], after["spaces"]))
        for old_window, new_window in zip(before.get("windows", []), after.get("windows", [])):
            if any(old_window.get(key) for key in ("isPrivate", "isPopup", "isTaskbarTab", "isZenUnsynced")):
                continue
            if "spaces" in old_window:
                pairs.append((old_window["spaces"], new_window["spaces"]))
        count = 0
        for old_spaces, new_spaces in pairs:
            for old, new in zip(old_spaces, new_spaces):
                if old.get("uuid") in identifiers and old.get("theme") != spec["theme"]:
                    new["theme"] = copy.deepcopy(spec["theme"])
                    count += 1
        # Independently prove that restoring only theme fields restores the entire document.
        restored = copy.deepcopy(after)
        if "spaces" in before:
            restore_themes(before["spaces"], restored["spaces"])
        for old_window, restored_window in zip(before.get("windows", []), restored.get("windows", [])):
            if "spaces" in old_window:
                restore_themes(old_window["spaces"], restored_window["spaces"])
        if restored != before:
            raise ValueError("Non-theme data changed; refusing to save")
        if after != before:
            writes[name] = encode(after)
        counts[name] = count
    prefs = originals["prefs.js"].decode()
    if len(PREF.findall(prefs)) > 1:
        raise ValueError("Duplicate Zen window scheme preference")
    if len(PREF_START.findall(prefs)) != len(PREF.findall(prefs)):
        raise ValueError("Unrecognized Zen window scheme preference")
    replacement = f'user_pref("zen.view.window.scheme", {spec["windowScheme"]});'
    updated = PREF.sub(replacement, prefs) if PREF.search(prefs) else prefs + "\n" + replacement + "\n"
    if PREF.sub("", updated).strip() != PREF.sub("", prefs).strip():
        raise ValueError("Unexpected non-theme preference change")
    if updated != prefs:
        writes["prefs.js"] = updated.encode()
    return writes, {"workspace_count": len(ids), "changed_workspace_occurrences": counts}


def plan_orca_changes(originals, spec):
    before = strict_json(originals[ORCA_FILE])
    if not isinstance(before, dict) or not isinstance(before.get("settings"), dict):
        raise ValueError("Unrecognized Orca settings layout")
    if set(spec["settings"]) != ORCA_SETTINGS:
        raise ValueError("Orca spec contains unsupported settings")
    after = copy.deepcopy(before)
    settings = after["settings"]
    entries = settings.setdefault("terminalCustomThemes", [])
    if not isinstance(entries, list) or any(not isinstance(entry, dict) for entry in entries):
        raise ValueError("Unrecognized Orca custom theme list")
    matches = [entry for entry in entries if str(entry.get("name", "")).casefold() == spec["name"].casefold()]
    selection = settings.get("terminalThemeDark", "")
    if not isinstance(selection, str):
        raise ValueError("Unrecognized Orca terminal theme selection")
    selected = selection.removeprefix("custom:")
    target = next((entry for entry in matches if entry.get("id") == selected), matches[0] if matches else None)
    if target is None:
        if any(entry.get("id") == spec["id"] for entry in entries):
            raise ValueError("Orca theme ID is already used by another theme")
        if len(entries) >= 200:
            raise ValueError("Orca has reached its 200 custom theme limit")
        target = {"id": spec["id"], "name": spec["name"], "source": "manual", "mode": "dark",
                  "terminal": {}, "importedAt": "1970-01-01T00:00:00.000Z", "sourceLabel": "Nix desktop theme"}
        entries.append(target)
    if not isinstance(target.get("id"), str) or not target["id"] or not isinstance(target.get("terminal"), dict):
        raise ValueError("Unrecognized existing Orca Sky Copy theme")
    target["mode"] = "dark"
    target["terminal"].update(spec["terminal"])
    settings.update(spec["settings"])
    settings["terminalThemeDark"] = "custom:" + target["id"]
    allowed = ORCA_SETTINGS | {"terminalCustomThemes", "terminalThemeDark"}
    restored = copy.deepcopy(after)
    for key in allowed:
        restored["settings"].pop(key, None)
        if key in before["settings"]:
            restored["settings"][key] = copy.deepcopy(before["settings"][key])
    if restored != before:
        raise ValueError("Non-theme Orca data changed; refusing to save")
    changed = [key for key in sorted(allowed) if before["settings"].get(key) != settings.get(key)]
    writes = {ORCA_FILE: (json.dumps(after, ensure_ascii=False, indent=2) + "\n").encode()} if after != before else {}
    return writes, {"changed_settings": changed}


def restore_themes(original, restored):
    for old, new in zip(original, restored):
        new.pop("theme", None)
        if "theme" in old:
            new["theme"] = copy.deepcopy(old["theme"])


def replace_if_unchanged(path, expected, replacement, before_replace=None):
    """Check immediately before atomic replacement, after checking Zen is stopped."""
    fd, temporary = tempfile.mkstemp(prefix=".desktop-theme-", dir=path.parent)
    temporary = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            os.fchmod(stream.fileno(), path.stat().st_mode & 0o777)
            stream.write(replacement)
            stream.flush()
            os.fsync(stream.fileno())
        if path.is_symlink() or path.read_bytes() != expected:
            raise RuntimeError(f"{path.name} changed since preview; no overwrite attempted")
        if before_replace:
            before_replace()
            if path.is_symlink() or path.read_bytes() != expected:
                raise RuntimeError(f"{path.name} changed during stop check; no overwrite attempted")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def apply_changes(profile, originals, writes, backup_root, app="zen"):
    if not writes:
        return None
    stopped(app)
    if read_files(profile, originals) != originals:
        raise RuntimeError("App profile changed since preview; no files changed")
    backup_root.mkdir(parents=True, exist_ok=True, mode=0o700)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-")
    backup = Path(tempfile.mkdtemp(prefix=stamp, dir=backup_root))
    for name in writes:
        target = backup / name
        with target.open("xb") as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write(originals[name])
            stream.flush()
            os.fsync(stream.fileno())
    saved = []
    try:
        stopped(app)
        if read_files(profile, originals) != originals:
            raise RuntimeError("App profile changed after backup; no files changed")
        for name, raw in writes.items():
            stopped(app)
            replace_if_unchanged(profile / name, originals[name], raw, lambda: stopped(app))
            saved.append(name)
        for name, raw in writes.items():
            if (profile / name).read_bytes() != raw:
                raise RuntimeError("App profile changed during verification")
    except Exception as error:
        # Never overwrite a subsequent external edit while rolling back.
        for name in reversed(saved):
            try:
                stopped(app)
                replace_if_unchanged(profile / name, writes[name], originals[name], lambda: stopped(app))
            except Exception:
                pass
        raise RuntimeError(f"Apply failed: {error}. Private backup: {backup}") from error
    return backup


def process_profile(app, profile, spec, apply=False, defer_running=False, state=None):
    report = {"app": app, "profile": str(profile), "theme": spec["name"], "applied": False}
    running = app_is_running(app)
    required = ("zen-sessions.jsonlz4", "prefs.js") if app == "zen" else (ORCA_FILE,)
    if any(not (profile / name).exists() for name in required):
        return dict(report, status="skipped", reason="profile_not_initialized")
    if app == "zen" and not running and not (profile / SESSION_FILES[1]).exists():
        return dict(report, status="skipped", reason="awaiting_clean_shutdown")
    try:
        originals = read_profile(profile, allow_running=running) if app == "zen" else read_files(profile, required)
        writes, details = plan_changes(originals, spec) if app == "zen" else plan_orca_changes(originals, spec)
    except (OSError, ValueError) as error:
        if running and defer_running:
            return dict(report, status="deferred", reason="running_profile_not_ready")
        raise error
    report.update(details, changed_files=list(writes), running=running)
    if not writes:
        return dict(report, status="unchanged")
    if not apply:
        return dict(report, status="preview")
    if running or app_is_running(app):
        if defer_running:
            return dict(report, status="deferred", reason="app_running")
        raise RunningApp(f"{app.title()} was running during inspection; quit normally and run again")
    try:
        backup = apply_changes(profile, originals, writes, state / "desktop-theme/backups" / app, app=app)
    except RunningApp:
        # This exception only escapes before writes; partial-write failures retain their backup/error.
        if defer_running:
            return dict(report, status="deferred", reason="app_started_during_apply")
        raise
    return dict(report, status="applied", applied=True, backup=str(backup))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--app", choices=("zen", "orca", "all"), default="zen")
    parser.add_argument("--profile", type=Path, help="Destination profile directory for --app zen or --app orca")
    parser.add_argument("--spec", type=Path, default=Path(__file__).parent / "themes/zen-workspaces.json")
    parser.add_argument("--orca-spec", type=Path, default=Path(__file__).parent / "themes/orca-theme.json")
    parser.add_argument("--defer-running", action="store_true", help="Leave running apps open and retry necessary changes later")
    parser.add_argument("--quiet", action="store_true", help="With --apply, only log applied changes or errors")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="Write colors after checking Zen is stopped and backing up locally")
    mode.add_argument("--dry-run", action="store_true", help="Preview only (the default)")
    args = parser.parse_args(argv)
    if args.app == "all" and args.profile:
        parser.error("--profile requires --app zen or --app orca")
    state = state_directory()
    if args.apply:
        with apply_lock(state) as acquired:
            if not acquired:
                if not args.quiet:
                    print('{"status":"skipped","reason":"another_sync_is_running"}')
                return 0
            return run_profiles(args, state)
    return run_profiles(args, state)


def run_profiles(args, state):
    reports = []
    failed = False
    for app in ("zen", "orca") if args.app == "all" else (args.app,):
        root = Path.home() / "Library/Application Support" / app
        candidates = ([args.profile.expanduser().resolve()] if args.profile else
                      discover_profiles(root) if app == "zen" else
                      sorted(path.parent for path in (root / "profiles").glob("*/orca-data.json")))
        if not candidates:
            reports.append({"app": app, "status": "skipped", "reason": "no_initialized_profiles"})
            continue
        if args.app != "all" and len(candidates) > 1:
            print("Use --profile with one initialized profile directory. Candidates:", file=sys.stderr)
            for candidate in candidates:
                print(f"  {candidate}", file=sys.stderr)
            return 2
        spec = json.loads((args.spec if app == "zen" else args.orca_spec).read_text())
        for profile in candidates:
            try:
                reports.append(process_profile(app, profile, spec, args.apply, args.defer_running, state))
            except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as error:
                reports.append({"app": app, "profile": str(profile), "status": "error", "error": str(error)})
                failed = True
    if not args.quiet or not args.apply or any(item["status"] in {"applied", "error"} for item in reports):
        print(json.dumps({"profiles": reports}, ensure_ascii=False, separators=(",", ":")))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError, RuntimeError, subprocess.CalledProcessError) as error:
        print(f"desktop-app-themes: {error}", file=sys.stderr)
        sys.exit(1)
