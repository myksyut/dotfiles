"""An empty /nix directory is not proof of the intended persistent bind."""

import importlib
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class MountTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("nix.provision")
        self.info = SimpleNamespace(st_dev=os.makedev(8, 1), st_ino=42)
        self.records = (
            "35 1 8:1 / /data rw - ext4 /dev/vdb rw\n"
            "36 1 8:1 /nix /nix rw - ext4 /dev/vdb rw\n"
        )

    def test_both_mounts_and_matching_inodes_required(self):
        self.module.verify_mount_identity(self.records, self.info, self.info)

    def test_empty_but_unmounted_nix_refused(self):
        with self.assertRaises(ValueError):
            self.module.verify_mount_identity(
                "1 0 8:1 / / rw - ext4 /dev/vda rw\n", self.info, self.info
            )

    def test_ephemeral_data_directory_refused(self):
        with self.assertRaises(ValueError):
            self.module.verify_mount_identity(
                self.records.splitlines()[1], self.info, self.info
            )

    def test_wrong_bind_source_refused(self):
        other = SimpleNamespace(st_dev=self.info.st_dev, st_ino=43)
        with self.assertRaises(ValueError):
            self.module.verify_mount_identity(self.records, self.info, other)

    def test_overlapping_or_wrong_device_mount_refused(self):
        for records in (
            self.records + self.records,
            self.records.replace("8:1", "8:2"),
        ):
            with self.subTest(records=records), self.assertRaises(ValueError):
                self.module.verify_mount_identity(records, self.info, self.info)


if __name__ == "__main__":
    unittest.main()
