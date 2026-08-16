"""Physically confirmed first-use pairing with immutable opaque identity."""
from __future__ import annotations

import json
import os
import re
import secrets
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from .discovery import Candidate, DiscoveryError

CHALLENGE_WIDTH = 6
_DEVICE_ID = re.compile(r"^[A-Za-z0-9._-]{1,64}$")


class PairingError(RuntimeError):
    """Pairing failed closed; no binding was changed."""

    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code
        self.message = message


@dataclass(frozen=True)
class PairingBinding:
    device_id: str
    protocol: int
    firmware: str

    def as_dict(self) -> dict[str, Any]:
        return {"schema_version": 1, "device_id": self.device_id, "protocol": self.protocol, "firmware": self.firmware}

    @classmethod
    def from_dict(cls, value: Any) -> "PairingBinding":
        if not isinstance(value, dict) or value.get("schema_version") != 1:
            raise PairingError("invalid", "Stored keypad binding is invalid.")
        device_id = value.get("device_id")
        firmware = value.get("firmware")
        if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id) or device_id == "host":
            raise PairingError("invalid", "Stored keypad binding has an invalid device identity.")
        if value.get("protocol") != 1 or not isinstance(firmware, str) or not firmware:
            raise PairingError("incompatible", "Incompatible protocol version. Flash the matching firmware and restart this run.")
        return cls(device_id, 1, firmware)


class PairingStore:
    """Atomically persist one binding; failed pairing leaves the old file intact."""

    def __init__(self, path: Path):
        self.path = Path(path)

    def load(self) -> PairingBinding | None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PairingError("invalid", f"Stored keypad binding cannot be read: {exc}") from exc
        return PairingBinding.from_dict(data)

    def save(self, binding: PairingBinding) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=f".{self.path.name}.", dir=self.path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(binding.as_dict(), stream, sort_keys=True, separators=(",", ":"))
                stream.write("\n")
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
            directory_fd = os.open(self.path.parent, os.O_RDONLY)
            try:
                os.fsync(directory_fd)
            finally:
                os.close(directory_fd)
        except Exception:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise


def new_challenge() -> str:
    """Create a fixed-width challenge suitable for the 128x128 panel."""
    return secrets.token_hex(CHALLENGE_WIDTH // 2).upper()


def challenge_valid(challenge: str) -> bool:
    return isinstance(challenge, str) and bool(re.fullmatch(rf"[0-9A-F]{{{CHALLENGE_WIDTH}}}", challenge))


def display_suffix(device_id: str, width: int = 4) -> str:
    if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id):
        return "unavailable"
    return device_id[-width:]


def pair_exact_candidate(
    candidates: Iterable[Candidate],
    hellos: dict[str, dict[str, Any]],
    challenge: str,
    typed_challenge: str,
    store: PairingStore,
    physical_confirmed: bool,
) -> PairingBinding:
    """Pair one candidate only after exact challenge and human confirmation."""
    candidate_list = list(candidates)
    if not candidate_list:
        raise PairingError("zero", "No keypad detected")
    if len(candidate_list) != 1:
        raise PairingError("ambiguous", "Multiple compatible keypads detected. Disconnect other candidates and retry; no device was paired.")
    if not challenge_valid(challenge):
        raise PairingError("invalid_challenge", "Pairing challenge is invalid.")
    if typed_challenge != challenge:
        raise PairingError("mismatch", "The pairing challenge did not match; no device was paired.")
    if not physical_confirmed:
        raise PairingError("not_confirmed", "Pairing requires explicit confirmation of the displayed challenge.")
    hello = hellos.get(candidate_list[0].device)
    if not isinstance(hello, dict):
        raise PairingError("incompatible", "Incompatible protocol version. Flash the matching firmware and restart this run.")
    device_id = hello.get("device_id")
    firmware = hello.get("firmware")
    protocol = hello.get("protocol")
    if not isinstance(device_id, str) or not _DEVICE_ID.fullmatch(device_id) or device_id == "host":
        raise PairingError("incompatible", "Incompatible protocol version. Flash the matching firmware and restart this run.")
    if protocol != 1 or not isinstance(firmware, str) or not firmware:
        raise PairingError("incompatible", "Incompatible protocol version. Flash the matching firmware and restart this run.")
    binding = PairingBinding(device_id, protocol, firmware)
    store.save(binding)
    return binding


def pairing_check() -> None:
    from tempfile import TemporaryDirectory
    from .discovery import EXPECTED_PID, EXPECTED_VID

    class Port:
        def __init__(self, device: str):
            self.device = device
            self.vid = EXPECTED_VID
            self.pid = EXPECTED_PID

    with TemporaryDirectory() as directory:
        store = PairingStore(Path(directory) / "binding.json")
        candidate = Candidate("/dev/ttyACM0", EXPECTED_VID, EXPECTED_PID, "serial", "1-1:1.0", "Espressif", "USB JTAG/serial debug unit", "00")
        challenge = "A1B2C3"
        hellos = {candidate.device: {"device_id": "opaque-device-1", "firmware": "phase1-bringup", "protocol": 1}}
        try:
            pair_exact_candidate([candidate], hellos, challenge, "FFFFFF", store, True)
        except PairingError as exc:
            if exc.code != "mismatch" or store.load() is not None:
                raise AssertionError("wrong challenge altered the binding")
        else:
            raise AssertionError("wrong challenge was accepted")
        binding = pair_exact_candidate([candidate], hellos, challenge, challenge, store, True)
        if store.load() != binding or display_suffix(binding.device_id) != "ce-1":
            raise AssertionError("exact pairing did not persist the opaque identity")
        try:
            pair_exact_candidate([candidate, candidate], hellos, challenge, challenge, store, True)
        except PairingError as exc:
            if exc.code != "ambiguous" or store.load() != binding:
                raise AssertionError("ambiguity replaced the original binding")
        else:
            raise AssertionError("multiple candidates were accepted")
        try:
            pair_exact_candidate([candidate], hellos, challenge, challenge, store, False)
        except PairingError as exc:
            if exc.code != "not_confirmed" or store.load() != binding:
                raise AssertionError("unconfirmed pairing altered the binding")
        else:
            raise AssertionError("unconfirmed pairing was accepted")
