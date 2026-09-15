import importlib.util
from pathlib import Path
import tempfile
import unittest


SOURCE = Path(__file__).resolve().parents[1] / "idle-controller" / "observer.py"
spec = importlib.util.spec_from_file_location("idle_observer", SOURCE)
observer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(observer)


class ObserverTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.proc = Path(self.tmp.name)
        (self.proc / "net").mkdir()
        self.tcp()
        self.tcp(ipv6=True)
        self.process(20, 10001, observer.ORCA, [observer.ORCA, "--serve"])

    def tcp(self, port=None, state="0A", ipv6=False):
        text = "sl local_address rem_address st tx_queue rx_queue\n"
        if port is not None:
            address = "0" * (32 if ipv6 else 8)
            text += f"0: {address}:{port:04X} {address}:0000 {state} 0:0 0:0\n"
        (self.proc / "net" / ("tcp6" if ipv6 else "tcp")).write_text(text)

    def process(self, pid, uid, exe, args, start="1234"):
        entry = self.proc / str(pid)
        entry.mkdir(exist_ok=True)
        (entry / "status").write_text(f"Name:\ttest\nUid:\t{uid}\t{uid}\t{uid}\t{uid}\n")
        (entry / "cmdline").write_bytes(b"\0".join(arg.encode() for arg in args) + b"\0")
        fields = ["S"] + ["0"] * 18 + [start]
        (entry / "stat").write_text(f"{pid} (test (with) space) " + " ".join(fields))
        (entry / "exe").symlink_to(exe)
        return entry

    def test_known_service_layout_and_identity(self):
        self.process(21, 10001, observer.ORCA, [observer.ORCA, observer.CLI, "serve", "--port", "6768"])
        self.process(22, 10001, observer.ORCA, [observer.ORCA, observer.PTY, "--socket", "/run/pty", "--token", "hidden"])
        self.process(23, 10001, observer.ORCA, [observer.ORCA + " --type=zygote --no-zygote-sandbox"])
        self.process(24, 10001, "/usr/bin/Xvfb", ["Xvfb", ":99"])
        result = observer.observe(self.proc)
        self.assertTrue(result["idle"], result)
        self.assertEqual(observer.service_identity(result)[0], (20, "1234", observer.ORCA))
        self.assertEqual([item["pid"] for item in result["services"] if item["role"] == "serve-cli"], [21])
        self.assertNotIn("hidden", str(result))

    def test_connections_block_both_ports_and_families(self):
        for ipv6 in (False, True):
            for port in (443, 6768):
                for state in ("01", "02", "03", "04", "08", "09"):
                    with self.subTest(ipv6=ipv6, port=port, state=state):
                        self.tcp(port, state, ipv6)
                        self.assertFalse(observer.observe(self.proc)["idle"])
                self.tcp(ipv6=ipv6)

    def test_listeners_timewait_and_other_ports_do_not_block(self):
        for port, state in ((443, "0A"), (6768, "06"), (22, "01")):
            self.tcp(port, state)
            self.assertTrue(observer.observe(self.proc)["idle"])

    def test_custom_node_script_or_cli_command_blocks(self):
        for index, args in enumerate((
            [observer.ORCA, "/home/miyakishota/task.js"],
            [observer.ORCA, "--serve", "--eval=do_work()"],
            [observer.ORCA, observer.CLI, "terminal", "exec"],
            [observer.ORCA, "--type=utility", "--utility-sub-type=node.mojom.NodeService"],
        ), 30):
            self.process(index, 10001, observer.ORCA, args)
        result = observer.observe(self.proc)
        self.assertFalse(result["idle"])
        self.assertEqual(len(result["blockers"]), 4)

    def test_shell_and_nix_build_uids_block(self):
        self.process(30, 10001, "/bin/zsh", ["zsh"])
        for uid in observer.BUILD_UIDS:
            self.process(uid, uid, "/bin/sleep", ["sleep", "60"])
        self.process(40, 0, "/bin/root-service", ["root-service"])
        result = observer.observe(self.proc)
        self.assertFalse(result["idle"])
        self.assertEqual(len(result["blockers"]), 5)

    def test_process_disappearance_is_allowed(self):
        (self.proc / "99").mkdir()
        self.assertTrue(observer.observe(self.proc)["idle"])

    def test_malformed_or_missing_observation_blocks(self):
        (self.proc / "net" / "tcp6").unlink()
        self.assertFalse(observer.observe(self.proc)["idle"])
        self.tcp(ipv6=True)
        (self.proc / "20" / "status").write_text("unreadable Uid data")
        self.assertFalse(observer.observe(self.proc)["idle"])

    def test_orca_absence_blocks(self):
        (self.proc / "20" / "status").write_text("Uid:\t0\t0\t0\t0\n")
        self.assertFalse(observer.observe(self.proc)["idle"])

    def test_shutdown_may_observe_no_orca(self):
        (self.proc / "20" / "status").write_text("Uid:\t0\t0\t0\t0\n")
        result = observer.observe(self.proc, require_orca=False)
        self.assertTrue(result["idle"], result)
        self.assertEqual(result["services"], [])

    def test_zombies_skip_empty_command_and_missing_exe(self):
        for pid, uid in ((30, 10001), (31, 30001)):
            entry = self.process(pid, uid, "/bin/zsh", ["zsh"])
            (entry / "stat").write_text(f"{pid} (zombie) Z " + "0 " * 18 + "1234")
            (entry / "cmdline").write_bytes(b"")
            (entry / "exe").unlink()
        self.assertTrue(observer.observe(self.proc)["idle"])


if __name__ == "__main__":
    unittest.main()
