"""Idle stop for the single-user Orca 1.4.197 devbox.

Only an empty host is eligible: no clients, terminals, browser tabs, automations,
developer commands, build workers or registered holds. A live Pi always blocks.
"""

import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import observer
import safety
from policy import IdleWindow
from nix.boundary import atomic_json, read_json
from nix.daemon import identity, worker_pids
from nix.runtime import LEASE

RUN = Path('/run/devbox')
CONFIG = Path('/etc/devbox/autostop.json')
CLI = '/opt/Orca/resources/bin/orca-ide'


def configuration():
    value = read_json(CONFIG) if CONFIG.exists() else {'enabled': True, 'idle_seconds': 1800}
    if type(value.get('enabled')) is not bool:
        raise ValueError('Invalid auto-stop configuration')
    seconds = value.get('idle_seconds', 1800)
    if type(seconds) is not int or not 30 <= seconds <= 86400:
        raise ValueError('Invalid idle timeout')
    return value['enabled'], seconds


def cli_result(args):
    command = ['/usr/sbin/runuser', '-u', 'miyakishota', '--', '/usr/bin/env',
               'HOME=/home/miyakishota', 'USER=miyakishota',
               'XDG_RUNTIME_DIR=/run/user/10001', CLI, *args, '--json']
    result = subprocess.run(command, capture_output=True, timeout=15,
                            env={'PATH': '/usr/bin:/bin', 'LANG': 'C.UTF-8'})
    if result.returncode or len(result.stdout) > 1024 * 1024:
        raise ValueError('Orca inventory unavailable')
    value = json.loads(result.stdout)
    if value.get('ok') is not True or not isinstance(value.get('result'), dict):
        raise ValueError('Orca inventory invalid')
    return value['result']


def empty_host(query=cli_result):
    terminals = query(['terminal', 'list'])
    scope = terminals.get('hostScope', {})
    if (terminals.get('terminals') != [] or terminals.get('totalCount') != 0
            or terminals.get('truncated') is not False
            or scope.get('hostIds') != ['local'] or scope.get('omittedHostIds') != []):
        raise ValueError('Open terminals or incomplete terminal inventory')
    automations = query(['automations', 'list'])
    if (automations.get('automations') != [] or automations.get('items') != []
            or automations.get('orphanCount') != 0):
        raise ValueError('Scheduled automations exist')
    if query(['tab', 'list']).get('tabs') != []:
        raise ValueError('Browser tabs exist')


def check(nix_pid):
    value = observer.observe()
    if not value['idle'] or not value['services']:
        raise ValueError('Client connected, work running, or Orca unavailable')
    safety.check_registry()
    empty_host()
    value = observer.observe()  # CLI inventory processes have now exited.
    if not value['idle'] or not value['services']:
        raise ValueError('Activity changed during observation')
    if worker_pids(group=nix_pid, exclude=(nix_pid,)):
        raise ValueError('Nix workers remain')
    return value


def live(item):
    try:
        stat = Path('/proc', str(item['pid']), 'stat').read_text().rsplit(')', 1)[1].split()
        return stat[0] != 'Z' and stat[19] == item['start']
    except FileNotFoundError:
        return False


def send(item, sig):
    if live(item):
        os.kill(item['pid'], sig)


def await_absent(items, seconds=30, reaper=None):
    until = time.monotonic() + seconds
    while any(live(item) for item in items):
        if reaper:
            reaper()
        if time.monotonic() >= until:
            raise ValueError('Service did not exit within shutdown timeout')
        time.sleep(0.2)


def ingress(block):
    if block:
        rule = 'table inet devbox_idle {\n chain input {\n type filter hook input priority -50; policy accept;\n tcp dport { 443, 6768 } drop\n }\n}\n'
        subprocess.run(['/usr/sbin/nft', '-f', '-'], input=rule.encode(),
                       check=True, timeout=5, capture_output=True)
    else:
        subprocess.run(['/usr/sbin/nft', 'delete', 'table', 'inet', 'devbox_idle'],
                       check=True, timeout=5, capture_output=True)


def stop(nix_process, tailscale_process, orca_process=None):
    """Called synchronously by the supervisor, so it cannot spawn/probe during stop."""
    nix_item = {'pid': nix_process.pid, **identity(nix_process.pid)}
    ts_item = {'pid': tailscale_process.pid, **identity(tailscale_process.pid)}
    lease = read_json(LEASE)
    if (lease.get('phase') != 'running' or lease.get('boot_id') != safety.boot_id()
            or lease.get('daemon_pid') != nix_item['pid']
            or lease.get('daemon_start') != nix_item['start']):
        raise ValueError('Nix lease does not match running daemon')
    before = check(nix_process.pid)
    frozen = []
    draining = False
    launchers = [p for p in before["services"] if p.get("role") == "serve-cli"]
    if len(launchers) != 1:
        raise ValueError("Cannot identify the Orca serve launcher")
    ingress(True)
    try:
        # Freeze the observed Orca actors before the final process/connection check.
        for item in before['services']:
            send(item, signal.SIGSTOP)
            frozen.append(item)
        until = time.monotonic() + 5
        while True:
            states = [Path('/proc', str(p['pid']), 'stat').read_text().rsplit(')', 1)[1].split() for p in frozen]
            if all(s[0] in ('T', 't') and s[19] == p['start'] for p, s in zip(frozen, states)):
                break
            if time.monotonic() >= until:
                raise ValueError('Orca did not pause before final observation')
            time.sleep(0.05)
        after = observer.observe()
        if (not after['idle'] or observer.service_identity(before) != observer.service_identity(after)
                or worker_pids(group=nix_process.pid, exclude=(nix_process.pid,))):
            raise ValueError('New activity before shutdown; idle window reset')
        safety.check_registry()
        safety.begin_drain()
        draining = True
        # SIGINT is the documented shutdown operation of `orca serve`.
        send(launchers[0], signal.SIGINT)
        for item in frozen:
            send(item, signal.SIGCONT)
        frozen = []
        await_absent(launchers, seconds=20, reaper=orca_process.poll if orca_process else None)
        remainder = observer.observe(require_orca=False)
        if remainder['blockers']:
            raise ValueError('Unexpected user work during shutdown')
        for item in remainder['services']:
            send(item, signal.SIGTERM)
        await_absent(remainder['services'], seconds=20)
        if worker_pids(extra_uids=(10001,)):
            # Exited children may be zombies waiting for Fly init/supervisor to reap.
            active = [p for p in worker_pids(extra_uids=(10001,))
                      if live({'pid': p, **identity(p)})]
            if active:
                raise ValueError('Developer/build processes remain')
        nix_process.terminate()
        if nix_process.wait(timeout=30) != 0:
            raise ValueError('Nix did not exit cleanly')
        await_absent([nix_item])
        if [p for p in worker_pids(group=nix_item['pid']) if live({'pid': p, **identity(p)})]:
            raise ValueError('Nix workers remain after daemon exit')
        atomic_json(LEASE, {**lease, 'phase': 'stopped'})
        tailscale_process.terminate()
        if tailscale_process.wait(timeout=30) != 0:
            raise ValueError('Tailscale did not exit cleanly')
        await_absent([ts_item])
        os.sync()
        record = {'phase': 'stopped', 'boot_id': safety.boot_id(), 'mode': 'idle-empty-host', 'at': time.time()}
        atomic_json(Path('/data/meta/last-clean-stop.json'), record)
        safety.durable_state(safety.RECOVERY, record)
        os.sync()
        return True
    finally:
        for item in frozen:
            send(item, signal.SIGCONT)
        if not draining:
            ingress(False)


class Controller:
    def __init__(self):
        self.window = IdleWindow(seconds=1800, max_gap=90)
        self.next_check = 0
        self.failed = False
        self.state = {'enabled': True, 'idle_seconds': 1800, 'state': 'waiting', 'idle_for': 0}

    def tick(self, nix, tailscale, orca):
        now = time.monotonic()
        if self.failed or now < self.next_check:
            return False
        self.next_check = now + 30
        try:
            enabled, seconds = configuration()
            self.state.update(enabled=enabled, idle_seconds=seconds)
            self.window.seconds = seconds
            if not enabled or nix is None or not nix.available or orca is None or orca.poll() is not None:
                raise ValueError('Disabled or services unavailable')
            observation = check(nix.process.pid)
            due = self.window.observe(True, safety.boot_id(), now)
            self.state.update(state='idle', idle_for=int(now - self.window.since), reason=None)
            if due:
                self.state['state'] = 'stopping'
                return stop(nix.process, tailscale, orca)
        except (OSError, ValueError, subprocess.SubprocessError) as exc:
            self.window.observe(False, safety.boot_id(), now)
            self.state.update(state='held', idle_for=0, reason=str(exc))
        finally:
            try:
                atomic_json(RUN / 'autostop-status.json', {**self.state, 'observed_at': time.time()})
            except (OSError, ValueError):
                self.failed = True
                self.state.update(enabled=False, state='error', reason='Cannot write idle status')
        return False
