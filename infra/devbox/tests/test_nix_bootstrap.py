"""Bootstrap order/failure boundaries without privilege, network or activation."""

import importlib
import sys
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class BootstrapTests(unittest.TestCase):
    def setUp(self):
        self.module = importlib.import_module("nix.bootstrap")
        self.events = []
        self.state = {"generation_digest": "a" * 64}
        self.actions = Mock()
        self.actions.record.side_effect = lambda phase, stage, code, generation: (
            self.events.append((phase, stage))
        )
        self.actions.provision.return_value = self.state
        self.actions.request_start.return_value = {"generation_digest": "a" * 64}
        self.actions.await_ready.return_value = {"phase": "ready"}
        self.actions.sandbox.return_value = True
        self.actions.build_home.return_value = (
            "/nix/store/" + "a" * 32 + "-home-manager-generation"
        )
        self.actions.verify_profile.return_value = True

    def test_all_gates_precede_finish(self):
        self.module.execute_pipeline("/home/miyakishota/src/dotfiles", self.actions)
        self.assertEqual(
            [stage for phase, stage in self.events if phase == "started"],
            [
                "provisioning",
                "daemon-start",
                "sandbox",
                "hm-build",
                "hm-activate",
                "profile",
                "recording",
            ],
        )
        self.actions.finish.assert_called_once()
        self.actions.activate_home.assert_called_once_with(
            self.actions.build_home.return_value
        )

    def test_each_failure_records_stage_without_ready(self):
        for method, stage in (
            ("provision", "provisioning"),
            ("await_ready", "daemon-start"),
            ("sandbox", "sandbox"),
            ("build_home", "hm-build"),
            ("activate_home", "hm-activate"),
            ("verify_profile", "profile"),
        ):
            with self.subTest(method=method):
                self.setUp()
                getattr(self.actions, method).side_effect = ValueError(
                    "fixture failure"
                )
                with self.assertRaises(ValueError):
                    self.module.execute_pipeline(
                        "/home/miyakishota/src/dotfiles", self.actions
                    )
                self.assertEqual(self.events[-1], ("failed", stage))
                self.actions.finish.assert_not_called()

    def test_unknown_sandbox_or_profile_is_not_success(self):
        for method in ("sandbox", "verify_profile"):
            self.setUp()
            getattr(self.actions, method).return_value = None
            with self.assertRaises(ValueError):
                self.module.execute_pipeline(
                    "/home/miyakishota/src/dotfiles", self.actions
                )
            self.actions.finish.assert_not_called()

    def test_start_generation_mismatch_never_builds(self):
        self.actions.request_start.return_value = {"generation_digest": "b" * 64}
        with self.assertRaises(ValueError):
            self.module.execute_pipeline("/home/miyakishota/src/dotfiles", self.actions)
        self.actions.build_home.assert_not_called()

    def test_developer_environment_has_no_inherited_configuration(self):
        environment = self.module.developer_environment()
        self.assertEqual(environment["NIX_REMOTE"], "daemon")
        self.assertEqual(environment["NIX_USER_CONF_FILES"], "/dev/null")
        self.assertEqual(environment["HOME"], "/home/miyakishota")
        self.assertNotIn("SSH_AUTH_SOCK", environment)
        self.assertNotIn("NIX_CONFIG", environment)

    def test_marker_requires_actual_outside_build_uid_observation(self):
        self.assertTrue(self.module.validate_probe("marker-hidden\n", {30001}))
        for result, observed in (
            ("outside\n", {30001}),
            ("marker-hidden\n", set()),
            ("marker-hidden\n", {0}),
            ("marker-hidden\n", {10001}),
            ("marker-hidden\n", {30001.0}),
        ):
            with (
                self.subTest(result=result, observed=observed),
                self.assertRaises(ValueError),
            ):
                self.module.validate_probe(result, observed)
