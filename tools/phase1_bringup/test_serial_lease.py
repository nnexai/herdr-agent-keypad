"""Hardware-free behavior checks for the cooperative Rust authority lease."""
from __future__ import annotations

import contextlib
import fcntl
import importlib.util
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "tools/phase1_bringup/src"
sys.path.insert(0, str(SOURCE))
from phase1_bringup.pairing import PairingBinding, PairingStore
from phase1_bringup.serial_link import (
    EXCLUSIVE_ENV, STATE_DIR_ENV, open_leased_serial, validate_plugin_state_dir,
)

SPEC = importlib.util.spec_from_file_location("keypad_lease", ROOT / "tools/keypad_lease.py")
assert SPEC is not None and SPEC.loader is not None
lease = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(lease)

GUARD = "from phase1_bringup.serial_link import require_inherited_bridge_lock; require_inherited_bridge_lock()"
# The test process never enumerates or opens real hardware. This is injection at
# the Python boundary, not a runner CLI bypass.
RUNNER = (
    f"import sys; sys.path.insert(0, {str(ROOT / 'tools')!r}); "
    "import keypad_lease; keypad_lease.enumerate_candidates = lambda: []; "
    "raise SystemExit(keypad_lease.main())"
)


class SerialLeaseTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.state = self.root / "state"
        self.state.mkdir(mode=0o700)
        self.lock = self.state / "bridge.lock"
        self.lock.touch(mode=0o600)
        self.environment = os.environ.copy()
        self.environment["PYTHONPATH"] = str(SOURCE)
        self.environment.pop(EXCLUSIVE_ENV, None)
        self.environment.pop(STATE_DIR_ENV, None)
        self.environment.pop("HERDR_PLUGIN_STATE_DIR", None)

    def command(self, code: str, *options: str) -> list[str]:
        return [sys.executable, "-c", RUNNER, "run", "--state-dir", str(self.state),
                *options, "--", sys.executable, "-c", code]

    def run_child(self, code: str, *options: str) -> subprocess.CompletedProcess:
        return subprocess.run(self.command(code, *options), env=self.environment,
                              capture_output=True, text=True, timeout=15)

    def wait_file(self, path: Path) -> str:
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            try:
                text = path.read_text()
                if text:
                    return text
            except FileNotFoundError:
                pass
            time.sleep(0.01)
        self.fail(f"child did not publish readiness: {path}")

    def assert_lock_free(self) -> None:
        # Fresh open description, never the runner's inherited descriptor.
        deadline = time.monotonic() + 5
        with self.lock.open("r+") as stream:
            while True:
                try:
                    fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    return
                except BlockingIOError:
                    if time.monotonic() >= deadline:
                        self.fail("authority was not released")
                    time.sleep(0.01)

    def kill_escapee(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def assert_not_live(self, pid: int) -> None:
        try:
            state = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[0]
        except FileNotFoundError:
            return
        self.assertIn(state, ("Z", "X"))

    def test_state_validation_rejects_missing_symlinked_or_public_authority(self) -> None:
        self.assertEqual(validate_plugin_state_dir(self.state), self.state)
        self.lock.unlink()
        with self.assertRaises(RuntimeError):
            validate_plugin_state_dir(self.state)
        target = self.root / "other.lock"
        target.touch(mode=0o600)
        self.lock.symlink_to(target)
        with self.assertRaises(RuntimeError):
            validate_plugin_state_dir(self.state)
        self.lock.unlink()
        self.lock.touch(mode=0o600)
        alias = self.root / "alias"
        alias.symlink_to(self.state, target_is_directory=True)
        with self.assertRaises(RuntimeError):
            validate_plugin_state_dir(alias)
        self.state.chmod(0o755)
        with self.assertRaises(RuntimeError):
            validate_plugin_state_dir(self.state)
        rejected = self.run_child("raise SystemExit(0)")
        self.assertEqual(rejected.returncode, 2, rejected.stderr)
        self.assertNotIn("lease released", rejected.stderr)

    def test_validation_rejects_relative_parent_alias_and_public_lock(self) -> None:
        for path in (Path("state"), self.state / ".." / "state"):
            with self.assertRaises(RuntimeError):
                validate_plugin_state_dir(path)
        self.lock.chmod(0o644)
        with self.assertRaises(RuntimeError):
            validate_plugin_state_dir(self.state)

    def test_busy_authority_returns_75_without_starting_child(self) -> None:
        with self.lock.open("r+") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
            rejected = self.run_child("raise AssertionError('must not start')")
        self.assertEqual(rejected.returncode, 75, rejected.stderr)
        self.assertIn("Herdr plugin `stop`", rejected.stderr)
        self.assertNotIn("lease released", rejected.stderr)

    def test_guard_accepts_runner_and_rejects_standalone_invocation(self) -> None:
        accepted = self.run_child(GUARD)
        self.assertEqual(accepted.returncode, 0, accepted.stderr)
        self.assertIn("lease released", accepted.stderr)
        rejected = subprocess.run([sys.executable, "-c", GUARD], env=self.environment,
                                  capture_output=True, text=True, timeout=5)
        self.assertNotEqual(rejected.returncode, 0)
        self.assert_lock_free()

    def test_guard_rejects_wrong_inode_even_with_same_basename(self) -> None:
        other = self.root / "other"
        other.mkdir(mode=0o700)
        wrong = other / "bridge.lock"
        wrong.touch(mode=0o600)
        result = self.run_child(
            f"import os; fd=os.open({str(wrong)!r}, os.O_RDWR); "
            "os.dup2(fd,9,inheritable=True); " + GUARD
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("does not name the validated bridge.lock", result.stderr)

    def test_guard_rejects_cloexec_fd(self) -> None:
        result = self.run_child("import os; os.set_inheritable(9,False); " + GUARD)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CLOEXEC", result.stderr)

    def test_guard_acquires_correct_unlocked_fd_without_claiming_authentication(self) -> None:
        # D3a: correct unlocked fd is unsupported standalone use, but still safe
        # mutual exclusion; the guard must not pretend it proves runner identity.
        code = (
            f"import os; fd=os.open({str(self.lock)!r},os.O_RDWR); "
            "os.dup2(fd,9,inheritable=True); " + GUARD
        )
        environment = dict(self.environment, **{EXCLUSIVE_ENV: "1", STATE_DIR_ENV: str(self.state)})
        result = subprocess.run([sys.executable, "-c", code], env=environment,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assert_lock_free()

    def test_timeout_is_bounded_and_releases_authority(self) -> None:
        result = self.run_child("import time; time.sleep(5)", "--max-seconds", "1")
        self.assertEqual(result.returncode, 124, result.stderr)
        self.assert_lock_free()

    def test_same_group_grandchild_is_killed_before_release_proof(self) -> None:
        pidfile = self.root / "group.pid"
        code = (
            "import subprocess,sys; from pathlib import Path; "
            "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(60)'],"
            "pass_fds=(9,),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL); "
            f"Path({str(pidfile)!r}).write_text(str(p.pid)); raise SystemExit(7)"
        )
        result = self.run_child(code)
        pid = int(self.wait_file(pidfile))
        self.addCleanup(self.kill_escapee, pid)
        self.assertEqual(result.returncode, 7, result.stderr)
        self.assertIn("lease released", result.stderr)
        self.assert_not_live(pid)
        self.assert_lock_free()

    def test_double_fork_setsid_escapee_prevents_false_lease_release(self) -> None:
        pidfile = self.root / "escaped.pid"
        code = f"""import os,sys,time
from pathlib import Path
pid=os.fork()
if pid:
    os.waitpid(pid,0)
    raise SystemExit(0)
os.setsid()
pid=os.fork()
if pid:
    os._exit(0)
fd=os.open(os.devnull,os.O_RDWR)
os.dup2(fd,1)
os.dup2(fd,2)
Path({str(pidfile)!r}).write_text(str(os.getpid()))
time.sleep(60)
"""
        # Arrange cleanup even when assertions fail after the detached child starts.
        try:
            result = self.run_child(code)
            pid = int(self.wait_file(pidfile))
            self.assertEqual(result.returncode, 4, result.stderr)
            self.assertIn(str(pid), result.stderr)
            self.assertNotIn("lease released", result.stdout + result.stderr)
        finally:
            if pidfile.exists():
                self.kill_escapee(int(pidfile.read_text()))
        self.assert_lock_free()

    def test_escaped_device_holder_returns_5_and_cli_never_reports_success(self) -> None:
        device = self.root / "fake-tty"
        device.touch()
        ready = self.root / "device.pid"
        code = (
            "import os,time; from pathlib import Path; "
            f"fd=os.open({str(device)!r},os.O_RDWR); "
            f"Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)"
        )
        child = subprocess.Popen([sys.executable, "-c", code], start_new_session=True,
                                 close_fds=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            pid = int(self.wait_file(ready))
            outcome = lease.final_release_check(self.lock, [device], Path("/proc"))
            self.assertEqual(outcome, (5, [pid]))
            command = self.command("raise SystemExit(0)")
            command[2] = RUNNER.replace(
                "raise SystemExit(keypad_lease.main())",
                f"keypad_lease.final_release_check = lambda *args: {outcome!r}; "
                "raise SystemExit(keypad_lease.main())",
            )
            result = subprocess.run(command, env=self.environment,
                                    capture_output=True, text=True, timeout=10)
            self.assertEqual(result.returncode, 5, result.stderr)
            self.assertIn(str(pid), result.stderr)
            self.assertNotIn("lease released", result.stdout + result.stderr)
        finally:
            child.kill()
            child.wait(timeout=5)
        self.assert_lock_free()

    def test_device_holder_blocks_start_even_with_free_authority(self) -> None:
        with (patch.object(lease, "enumerate_candidates", return_value=[type("Candidate", (), {"device": "/fake"})()]),
              patch.object(lease, "holder_pids", return_value=[1234]),
              patch.object(lease.subprocess, "Popen") as spawn,
              contextlib.redirect_stderr(io.StringIO())):
            result = lease.main(["run", "--state-dir", str(self.state), "--", "unused"])
        self.assertEqual(result, 3)
        spawn.assert_not_called()
        self.assert_lock_free()

    def test_sigterm_terminates_group_and_runs_release_check_without_success_line(self) -> None:
        ready = self.root / "signal.pid"
        code = f"import os,time; from pathlib import Path; Path({str(ready)!r}).write_text(str(os.getpid())); time.sleep(60)"
        proof = self.root / "release-checked"
        command = self.command(code)
        command[2] = f"""import sys
from pathlib import Path
sys.path.insert(0, {str(ROOT / 'tools')!r})
import keypad_lease
keypad_lease.enumerate_candidates = lambda: []
original = keypad_lease.final_release_check
def checked(*args):
    result = original(*args)
    Path({str(proof)!r}).write_text(str(result[0]))
    return result
keypad_lease.final_release_check = checked
raise SystemExit(keypad_lease.main())
"""
        runner = subprocess.Popen(command, env=self.environment,
                                  stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        try:
            pid = int(self.wait_file(ready))
            runner.send_signal(signal.SIGTERM)
            stdout, stderr = runner.communicate(timeout=10)
            self.assertNotEqual(runner.returncode, 0)
            self.assertNotIn("lease released", stdout + stderr)
            self.assertEqual(proof.read_text(), "0")
            self.assert_not_live(pid)
            self.assert_lock_free()
        finally:
            if runner.poll() is None:
                runner.kill()
                runner.communicate(timeout=5)
            if ready.exists():
                self.kill_escapee(int(ready.read_text()))

    def test_serial_guard_runs_before_pyserial_import(self) -> None:
        import builtins

        original = builtins.__import__
        def checked(name, *args, **kwargs):
            if name == "serial":
                raise AssertionError("pyserial imported before guard")
            return original(name, *args, **kwargs)
        with (patch.dict(os.environ, {}, clear=True), patch("builtins.__import__", checked)):
            with self.assertRaisesRegex(RuntimeError, "lease runner"):
                open_leased_serial("/never-open", timeout=0.2)

    def test_serial_helper_preserves_timeouts_and_requests_exclusive_open(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import Mock
        serial = Mock()
        with (patch("phase1_bringup.serial_link.require_inherited_bridge_lock") as guard,
              patch.dict(sys.modules, {"serial": SimpleNamespace(Serial=serial)})):
            open_leased_serial("/fake", timeout=0.25, write_timeout=3)
        guard.assert_called_once_with()
        serial.assert_called_once_with("/fake", 115200, timeout=0.25, write_timeout=3, exclusive=True)

    def test_pairing_save_retains_exact_rust_schema(self) -> None:
        path = self.root / "binding.json"
        PairingStore(path).save(PairingBinding("keypad-a", 1, "firmware-a"))
        value = json.loads(path.read_text())
        self.assertEqual(set(value), {"schema_version", "device_id", "protocol", "firmware"})
        self.assertEqual(value["schema_version"], 1)
        self.assertEqual(value["protocol"], 1)

    def fake_process(self, proc: Path, pid: int, executable: Path, state: Path) -> None:
        process = proc / str(pid)
        process.mkdir()
        (process / "exe").symlink_to(executable)
        (process / "environ").write_bytes(b"OTHER=value\0HERDR_PLUGIN_STATE_DIR=" + os.fsencode(state) + b"\0")

    def test_locate_uses_exact_executable_and_one_distinct_state_in_injected_proc(self) -> None:
        plugin = self.root / "plugin"
        (plugin / "bin").mkdir(parents=True)
        executable = plugin / "bin/herdr-keypad"
        executable.touch()
        proc = self.root / "proc"
        proc.mkdir()
        with self.assertRaisesRegex(RuntimeError, "found 0"):
            lease.locate_state_dir(plugin, proc)
        self.fake_process(proc, 100, executable, self.state)
        self.fake_process(proc, 101, executable, self.state)
        unrelated = self.root / "unrelated"
        unrelated.touch()
        self.fake_process(proc, 102, unrelated, self.root / "ignored")
        self.assertEqual(lease.locate_state_dir(plugin, proc), self.state)
        self.fake_process(proc, 103, executable, self.root / "other-state")
        with self.assertRaisesRegex(RuntimeError, "found 2"):
            lease.locate_state_dir(plugin, proc)

    def test_locate_skips_inaccessible_candidates_but_requires_verified_match(self) -> None:
        plugin = self.root / "plugin"
        (plugin / "bin").mkdir(parents=True)
        executable = plugin / "bin/herdr-keypad"
        executable.touch()
        for method, relative in (("stat", ""), ("resolve", "exe"), ("read_bytes", "environ")):
            with self.subTest(boundary=method):
                proc = self.root / f"proc-{method}"
                proc.mkdir()
                self.fake_process(proc, 101, executable, self.root / "unverified-state")
                blocked = proc / "101" / relative
                original = getattr(Path, method)

                def denied(path, *args, **kwargs):
                    if path == blocked:
                        raise PermissionError(13, "Permission denied", str(path))
                    return original(path, *args, **kwargs)

                with patch.object(Path, method, denied):
                    with self.assertRaisesRegex(RuntimeError, "found 0"):
                        lease.locate_state_dir(plugin, proc)
                    self.fake_process(proc, 100, executable, self.state)
                    self.assertEqual(lease.locate_state_dir(plugin, proc), self.state)

    def test_holder_scan_reports_partial_visibility_and_keeps_visible_holders(self) -> None:
        device = self.root / "fake-tty"
        device.touch()
        boundaries = (("stat", ""), ("iterdir", "fd"),
                      ("readlink", "fd/0"), ("stat", "fd/0"))
        for index, (method, relative) in enumerate(boundaries):
            with self.subTest(boundary=(method, relative)):
                proc = self.root / f"proc-holders-{index}"
                for pid in (100, 101):
                    descriptors = proc / str(pid) / "fd"
                    descriptors.mkdir(parents=True)
                    (descriptors / "0").symlink_to(device)
                blocked = proc / "100" / relative
                owner = os if method == "readlink" else Path
                original = getattr(owner, method)

                def denied(path, *args, **kwargs):
                    if Path(path) == blocked:
                        raise PermissionError(13, "Permission denied", str(path))
                    return original(path, *args, **kwargs)

                warning = io.StringIO()
                with (patch.object(owner, method, denied),
                      contextlib.redirect_stderr(warning)):
                    if method == "stat" and relative:
                        info = device.stat()
                        holders = lease.holder_pids(
                            (), proc, lock_identity=(info.st_dev, info.st_ino),
                        )
                    else:
                        holders = lease.holder_pids([device], proc)
                self.assertEqual(holders, [101])
                self.assertIn("visibility-limited", warning.getvalue())
                self.assertIn("100", warning.getvalue())
                self.assertIn("cannot prove absence of other holders", warning.getvalue())

    def test_final_release_with_partial_visibility_still_checks_authority_and_visible_devices(self) -> None:
        proc = self.root / "proc"
        for pid in (100, 101):
            (proc / str(pid) / "fd").mkdir(parents=True)
        visible_fd = proc / "101/fd/0"
        device = self.root / "fake-tty"
        device.touch()
        visible_fd.symlink_to(device)
        original = Path.iterdir

        def denied(path):
            if path == proc / "100/fd":
                raise PermissionError(13, "Permission denied", str(path))
            return original(path)

        warning = io.StringIO()
        with patch.object(Path, "iterdir", denied), contextlib.redirect_stderr(warning):
            self.assertEqual(lease.final_release_check(self.lock, [device], proc), (5, [101]))
            visible_fd.unlink()
            visible_fd.symlink_to(self.lock)
            with self.lock.open("r+") as stream:
                fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
                self.assertEqual(lease.final_release_check(self.lock, [device], proc), (4, [101]))
            visible_fd.unlink()
            self.assertEqual(lease.final_release_check(self.lock, [device], proc), (0, []))
        self.assertEqual(warning.getvalue().count("visibility-limited"), 3)
        self.assertIn("shared bridge.lock authority remains enforced", warning.getvalue())

    def test_cli_bounds_and_missing_child_fail_closed(self) -> None:
        for options in (("--wait-seconds", "11"), ("--wait-seconds", "nan"),
                        ("--max-seconds", "0"), ("--max-seconds", "3601")):
            result = self.run_child("raise SystemExit(0)", *options)
            self.assertEqual(result.returncode, 2, result.stderr)
        result = subprocess.run(self.command("raise SystemExit(0)")[:-4], env=self.environment,
                                capture_output=True, text=True, timeout=5)
        self.assertEqual(result.returncode, 2, result.stderr)


if __name__ == "__main__":
    unittest.main()
