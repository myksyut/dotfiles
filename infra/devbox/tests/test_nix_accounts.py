"""Dedicated build identities must not alias unrelated accounts."""

import importlib
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("nix.provision")
        self.users = [
            SimpleNamespace(
                pw_name="miyakishota", pw_uid=10001, pw_gid=10001, pw_shell="/bin/zsh"
            )
        ]
        self.users += [
            SimpleNamespace(
                pw_name=f"nixbld{i}",
                pw_uid=30000 + i,
                pw_gid=30000,
                pw_shell="/usr/sbin/nologin",
            )
            for i in range(1, 5)
        ]
        self.groups = [
            SimpleNamespace(gr_name="miyakishota", gr_gid=10001, gr_mem=[]),
            SimpleNamespace(
                gr_name="nixbld",
                gr_gid=30000,
                gr_mem=[f"nixbld{i}" for i in range(1, 5)],
            ),
        ]

    def validate(self):
        with (
            patch.object(
                self.module.pwd,
                "getpwnam",
                side_effect=lambda n: next(u for u in self.users if u.pw_name == n),
            ),
            patch.object(
                self.module.pwd,
                "getpwuid",
                side_effect=lambda i: next(u for u in self.users if u.pw_uid == i),
            ),
            patch.object(self.module.pwd, "getpwall", return_value=self.users),
            patch.object(
                self.module.grp,
                "getgrnam",
                side_effect=lambda n: next(g for g in self.groups if g.gr_name == n),
            ),
            patch.object(self.module.grp, "getgrall", return_value=self.groups),
            patch.object(self.module.os, "getgrouplist", side_effect=lambda n, g: [g]),
        ):
            self.module.validate_accounts()

    def test_fixed_nonlogin_identities(self):
        self.validate()

    def test_duplicate_build_uid_refused(self):
        self.users.append(
            SimpleNamespace(
                pw_name="alias", pw_uid=30001, pw_gid=100, pw_shell="/bin/sh"
            )
        )
        with self.assertRaises(ValueError):
            self.validate()

    def test_duplicate_build_gid_refused(self):
        self.groups.append(SimpleNamespace(gr_name="alias", gr_gid=30000, gr_mem=[]))
        with self.assertRaises(ValueError):
            self.validate()

    def test_developer_must_not_be_build_member(self):
        self.groups[1].gr_mem.append("miyakishota")
        with self.assertRaises(ValueError):
            self.validate()

    def test_build_account_cannot_login(self):
        self.users[1].pw_shell = "/bin/sh"
        with self.assertRaises(ValueError):
            self.validate()


if __name__ == "__main__":
    unittest.main()
