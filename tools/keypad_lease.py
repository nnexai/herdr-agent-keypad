"""Bounded developer diagnostics under the Rust bridge's cooperative authority lease.

Invoke with tools/phase1_bringup/.venv/bin/python3. This is same-user mutual
exclusion, not authentication; it never manages the production lifecycle.
"""
from __future__ import annotations

import argparse
import fcntl
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from typing import Iterable

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "phase1_bringup" / "src"))

from phase1_bringup.discovery import enumerate_candidates
from phase1_bringup.serial_link import (
    EXCLUSIVE_ENV, LEASE_FD, LOCK_NAME, STATE_DIR_ENV, validate_plugin_state_dir,
)

BUSY_MESSAGE = (
    "herdr-keypad bridge owns the device: run the Herdr plugin `stop` action, "
    "confirm `status` is stopped, retry"
)


def open_authority(lock_path: Path) -> int:
    """Open an existing, validated inode without following directory/lock aliases."""
    state_dir = validate_plugin_state_dir(lock_path.parent)
    directory = os.open(state_dir, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
    try:
        actual_dir = os.fstat(directory)
        expected_dir = state_dir.lstat()
        if (actual_dir.st_dev, actual_dir.st_ino) != (expected_dir.st_dev, expected_dir.st_ino):
            raise RuntimeError("plugin state directory changed during validation")
        expected = (state_dir / LOCK_NAME).lstat()
        fd = os.open(LOCK_NAME, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=directory)
        try:
            actual = os.fstat(fd)
            current = (state_dir / LOCK_NAME).lstat()
            identity = (actual.st_dev, actual.st_ino)
            if identity != (expected.st_dev, expected.st_ino) or identity != (current.st_dev, current.st_ino):
                raise RuntimeError("bridge.lock changed during validation")
            # Keep the runner's original descriptor distinct from the child contract.
            owned = fcntl.fcntl(fd, fcntl.F_DUPFD_CLOEXEC, LEASE_FD + 1)
        finally:
            os.close(fd)
        return owned
    finally:
        os.close(directory)


def user_processes(
    proc_root: Path, *, skip_inaccessible: bool = False,
    inaccessible: set[int] | None = None,
) -> Iterable[Path]:
    for process in proc_root.iterdir():
        if not process.name.isdecimal():
            continue
        try:
            if process.stat().st_uid == os.getuid():
                yield process
        except FileNotFoundError:
            continue
        except PermissionError:
            if not skip_inaccessible:
                raise
            if inaccessible is not None:
                inaccessible.add(int(process.name))


def locate_state_dir(plugin_root: Path, proc_root: Path = Path("/proc")) -> Path:
    executable = (plugin_root.expanduser() / "bin" / "herdr-keypad").resolve()
    states: set[str] = set()
    for process in user_processes(proc_root, skip_inaccessible=True):
        try:
            if (process / "exe").resolve(strict=True) != executable:
                continue
            for entry in (process / "environ").read_bytes().split(b"\0"):
                if entry.startswith(b"HERDR_PLUGIN_STATE_DIR="):
                    states.add(os.fsdecode(entry.split(b"=", 1)[1]))
        except (FileNotFoundError, PermissionError):
            continue
    if len(states) != 1:
        raise RuntimeError(f"locate requires one running bridge state directory; found {len(states)} distinct values")
    return validate_plugin_state_dir(Path(states.pop()))


def holder_pids(
    device_paths: Iterable[Path], proc_root: Path = Path("/proc"),
    *, lock_identity: tuple[int, int] | None = None,
) -> list[int]:
    """Find visible same-uid holders; warn when namespace permissions limit inspection."""
    targets = {os.path.realpath(path) for path in device_paths}
    if not targets and lock_identity is None:
        return []
    holders: set[int] = set()
    inaccessible: set[int] = set()
    for process in user_processes(proc_root, skip_inaccessible=True, inaccessible=inaccessible):
        if lock_identity is not None and int(process.name) == os.getpid():
            continue
        try:
            for descriptor in (process / "fd").iterdir():
                try:
                    if lock_identity is not None:
                        info = descriptor.stat()
                        matches = (info.st_dev, info.st_ino) == lock_identity
                    else:
                        matches = os.readlink(descriptor) in targets
                    if matches:
                        holders.add(int(process.name))
                        break
                except FileNotFoundError:
                    continue
                except PermissionError:
                    inaccessible.add(int(process.name))
        except FileNotFoundError:
            continue
        except PermissionError:
            inaccessible.add(int(process.name))
    if inaccessible:
        print(
            f"visibility-limited /proc holder inspection; inaccessible pids: {sorted(inaccessible)}; "
            "cannot prove absence of other holders; shared bridge.lock authority remains enforced",
            file=sys.stderr,
        )
    return sorted(holders)


def final_release_check(
    lock_path: Path, device_paths: Iterable[Path], proc_root: Path = Path("/proc"),
) -> tuple[int, list[int]]:
    """Independently reacquire authority, then reject visible candidate holders."""
    fd = open_authority(lock_path)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            info = os.fstat(fd)
            return 4, holder_pids((), proc_root, lock_identity=(info.st_dev, info.st_ino))
        holders = holder_pids(device_paths, proc_root)
        return (5, holders) if holders else (0, [])
    finally:
        os.close(fd)


def signal_group(pid: int, number: int) -> None:
    try:
        os.killpg(pid, number)
    except ProcessLookupError:
        pass


def drain_group(pid: int) -> None:
    """Allow killed ordinary descendants to close fds before the release proof."""
    deadline = time.monotonic() + 5
    while True:
        live = False
        for process in user_processes(Path("/proc"), skip_inaccessible=True):
            try:
                fields = (process / "stat").read_text().rsplit(")", 1)[1].split()
                if int(fields[2]) == pid and fields[0] not in ("Z", "X"):
                    live = True
                    break
            except (FileNotFoundError, PermissionError):
                continue
        if not live or time.monotonic() >= deadline:
            return
        time.sleep(0.01)


def run_leased(args: argparse.Namespace) -> int:
    state_dir = validate_plugin_state_dir(Path(args.state_dir))
    lock_path = state_dir / LOCK_NAME
    lock_fd = open_authority(lock_path)
    child: subprocess.Popen | None = None
    inherited = False
    handlers: dict[int, object] = {}
    interrupted: list[int] = []
    result = 2
    devices: list[Path] = []
    try:
        deadline = time.monotonic() + args.wait_seconds
        while True:
            try:
                fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                break
            except BlockingIOError:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    print(BUSY_MESSAGE, file=sys.stderr)
                    return 75
                time.sleep(min(0.05, remaining))
        devices = [Path(os.path.realpath(candidate.device)) for candidate in enumerate_candidates()]
        holders = holder_pids(devices)
        if holders:
            print(f"device already open before start; holder pids: {holders}", file=sys.stderr)
            return 3
        os.dup2(lock_fd, LEASE_FD, inheritable=True)
        inherited = True
        environment = os.environ.copy()
        environment[EXCLUSIVE_ENV] = "1"
        environment[STATE_DIR_ENV] = str(state_dir)

        def forward(number: int, _frame: object) -> None:
            if not interrupted:
                interrupted.append(number)
            if child is not None:
                signal_group(child.pid, number)

        for number in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
            handlers[number] = signal.signal(number, forward)
        try:
            child = subprocess.Popen(
                args.argv, pass_fds=(LEASE_FD,), start_new_session=True, env=environment,
            )
            deadline = time.monotonic() + args.max_seconds
            termination_deadline: float | None = None
            timed_out = False
            while True:
                now = time.monotonic()
                if termination_deadline is None and (interrupted or now >= deadline):
                    timed_out = not interrupted
                    signal_group(child.pid, interrupted[0] if interrupted else signal.SIGTERM)
                    termination_deadline = now + 5
                if termination_deadline is not None and now >= termination_deadline:
                    signal_group(child.pid, signal.SIGKILL)
                try:
                    result = child.wait(timeout=0.05)
                    break
                except subprocess.TimeoutExpired:
                    continue
            if timed_out:
                result = 124
            elif interrupted:
                result = 128 + interrupted[0]
            elif result < 0:
                result = 128 - result
        except OSError as exc:
            print(f"cannot launch diagnostic: {exc}", file=sys.stderr)
            result = 2
        finally:
            if child is not None:
                signal_group(child.pid, signal.SIGKILL)
                child.wait()
                drain_group(child.pid)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"diagnostic lease failed: {exc}", file=sys.stderr)
        result = 2
    finally:
        if inherited:
            os.close(LEASE_FD)
        os.close(lock_fd)
    # All runner copies are closed before the fresh independent open description.
    try:
        release, holders = final_release_check(lock_path, devices)
        if release:
            label = "lease still held" if release == 4 else "device still open"
            print(f"{label} after release; holder pids: {holders}", file=sys.stderr)
            return release
        if not interrupted:
            print("lease released; start the bridge with the Herdr `start` action", file=sys.stderr)
        return (128 + interrupted[0]) if interrupted else result
    finally:
        for number, handler in handlers.items():
            signal.signal(number, handler)


def bounded_float(value: str) -> float:
    number = float(value)
    if not 0 <= number <= 10:
        raise argparse.ArgumentTypeError("wait-seconds must be in 0..10")
    return number


def bounded_seconds(value: str) -> int:
    number = int(value)
    if not 1 <= number <= 3600:
        raise argparse.ArgumentTypeError("max-seconds must be in 1..3600")
    return number


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    locate = commands.add_parser("locate", help="cache the running installed bridge's actual state directory")
    locate.add_argument("--plugin-root", type=Path, default=Path.home() / ".local/share/herdr/plugins/herdr-keypad")
    run = commands.add_parser("run", help="run diagnostics with bounded exclusive authority")
    run.add_argument("--state-dir", default=os.environ.get("HERDR_PLUGIN_STATE_DIR"))
    run.add_argument("--wait-seconds", type=bounded_float, default=0)
    run.add_argument("--max-seconds", type=bounded_seconds, default=900)
    run.add_argument("argv", nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    try:
        if args.command == "locate":
            print(locate_state_dir(args.plugin_root))
            return 0
        if not args.state_dir:
            parser.error("run requires --state-dir or HERDR_PLUGIN_STATE_DIR")
        if args.argv[:1] == ["--"]:
            args.argv = args.argv[1:]
        if not args.argv:
            parser.error("run requires a child command after --")
        return run_leased(args)
    except (OSError, RuntimeError) as exc:
        print(f"keypad lease: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
