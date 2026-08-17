#!/usr/bin/env python3
"""Fail-closed, artifact-only Phase 1 -> Phase 2 handoff verifier.

This gate deliberately does not rebuild, flash, enumerate USB, or mutate the
paired binding. It reopens immutable Phase 1 evidence and records the exact
source/UI contracts that Phase 2 may use.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEVICE_ID_RE = re.compile(r"^[0-9a-fA-F]{8,128}$")
SOURCE_FILES = (
    "firmware/src/protocol/protocol.h",
    "firmware/src/protocol/protocol.cpp",
    "firmware/src/board/physical_map.h",
    "firmware/src/board/board_adapter.h",
    "firmware/src/board/board_adapter.cpp",
    "firmware/src/main.cpp",
    ".planning/phases/01-physical-keypad-and-proven-transport/01-UI-SPEC.md",
    ".planning/phases/02-authoritative-agent-projection-and-exact-focus/02-UI-SPEC.md",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise ValueError(message)


def regular(path: Path, label: str) -> Path:
    if path.is_symlink():
        fail(f"{label} must not be a symlink: {path}")
    if not path.is_file():
        fail(f"{label} is missing or not a regular file: {path}")
    return path


def load_object(path: Path, label: str) -> dict[str, Any]:
    regular(path, label)
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"{label} is not valid JSON: {exc}")
    if not isinstance(value, dict):
        fail(f"{label} must contain an object")
    return value


def concrete_lock_path(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or value.startswith("latest"):
        fail(f"{label} must name one immutable concrete path")
    path = Path(value)
    if not path.is_absolute():
        path = ROOT / path
    return regular(path, label).resolve()


def check_lock_address(lock: dict[str, Any], key: str, expected_hash_key: str, label: str) -> Path:
    path = concrete_lock_path(lock.get(key), f"{label}.{key}")
    expected = lock.get(expected_hash_key)
    if not isinstance(expected, str) or not re.fullmatch(r"[0-9a-f]{64}", expected):
        fail(f"{label}.{expected_hash_key} is not a SHA-256")
    if sha256(path) != expected:
        fail(f"{label}.{key} hash does not match its immutable address")
    return path



def check_phase1(summary: Path, selection_path: Path, final_build_path: Path, archive_path: Path, binding_path: Path) -> dict[str, Any]:
    regular(summary, "Phase 1 completion summary")
    summary_text = summary.read_text(encoding="utf-8")
    if "plan: 13" not in summary_text or "selected USB" not in summary_text:
        fail("Phase 1 summary is not the completed 01-13 selected-USB handoff")

    selection = load_object(selection_path, "selection lock")
    final_build = load_object(final_build_path, "final-build lock")
    archive = load_object(archive_path, "archive marker")
    if selection.get("status") != "pass" or selection.get("environment") != "selected-usb":
        fail("selection lock is not a passing selected-usb lock")
    if selection.get("selected_adapter") != "usb_cdc":
        fail("selection lock does not select usb_cdc")
    if final_build.get("status") != "pass" or final_build.get("environment") != "selected-usb":
        fail("final-build lock is not a passing selected-usb lock")
    if archive.get("status") != "archived" or archive.get("environment") != "selected-usb":
        fail("Phase 1 archive marker is not archived selected-usb evidence")
    for key in ("unselected_object_present", "unselected_source_present", "unselected_symbol_present"):
        if final_build.get(key) is not False:
            fail(f"final-build lock admits an unselected Wi-Fi artifact: {key}")

    selection_lock_from_final = check_lock_address(final_build, "selection_lock_path", "selection_lock_sha256", "final-build lock")
    if selection_lock_from_final != selection_path.resolve():
        fail("final-build lock points at a different selection lock")
    if check_lock_address(archive, "selection_lock_path", "selection_lock_sha256", "archive marker") != selection_path.resolve():
        fail("archive marker points at a different selection lock")
    if check_lock_address(archive, "build_lock_path", "build_lock_sha256", "archive marker") != final_build_path.resolve():
        fail("archive marker does not address the supplied final-build lock")
    check_lock_address(selection, "candidate_lock_path", "candidate_lock_sha256", "selection lock")
    check_lock_address(selection, "usb_lock_path", "usb_lock_sha256", "selection lock")
    check_lock_address(selection, "result_path", "result_sha256", "selection lock")
    check_lock_address(final_build, "binary_path", "binary_sha256", "final-build lock")

    selected_source = concrete_lock_path(final_build.get("selected_source_path"), "final-build selected source")
    if selected_source != (ROOT / "firmware/src/transport/usb_cdc.cpp").resolve():
        fail("final-build selected source is not the Phase 1 USB CDC adapter")
    if sha256(selected_source) != final_build.get("selected_source_sha256"):
        fail("selected USB source hash changed")
    for path_value, hash_key in (("main_path", "main_sha256"), ("platformio_path", "platformio_sha256")):
        path = concrete_lock_path(final_build.get(path_value), f"final-build {path_value}")
        if sha256(path) != final_build.get(hash_key):
            fail(f"final-build {path_value} hash changed")

    for path in (ROOT / "firmware/src", ROOT / "platformio.ini"):
        candidates = [path] if path.is_file() else [item for item in path.rglob("*") if item.is_file() and not item.is_symlink()]
        for candidate in candidates:
            text = candidate.read_text(encoding="utf-8", errors="strict")
            if candidate.name == "wifi_tls.cpp" or ("wifi_tls" in text and candidate.name != "platformio.ini"):
                fail(f"Wi-Fi implementation/runtime selector found in selected Phase 1 source: {candidate}")

    binding = load_object(binding_path, "paired keypad binding")
    if set(binding) != {"device_id", "firmware", "protocol", "schema_version"}:
        fail("paired keypad binding contains unknown or missing fields")
    device_id = binding.get("device_id")
    if not isinstance(device_id, str) or not DEVICE_ID_RE.fullmatch(device_id) or device_id.lower() == "host":
        fail("paired keypad binding has an invalid exact device identity")
    if binding.get("schema_version") != 1 or binding.get("protocol") != 1 or not isinstance(binding.get("firmware"), str) or not binding["firmware"]:
        fail("paired keypad binding is not the Phase 1 protocol-1 binding")

    source_hashes = {}
    for relative in SOURCE_FILES:
        path = regular(ROOT / relative, f"contract source {relative}")
        source_hashes[relative] = sha256(path)

    return {
        "schema_version": 1,
        "phase1_summary": {"path": str(summary.resolve()), "sha256": sha256(summary)},
        "locks": {
            "selection": {"path": str(selection_path.resolve()), "sha256": sha256(selection_path)},
            "final_build": {"path": str(final_build_path.resolve()), "sha256": sha256(final_build_path)},
            "archive": {"path": str(archive_path.resolve()), "sha256": sha256(archive_path)},
        },
        "transport": {"selected": "usb_cdc", "environment": "selected-usb", "wifi_admitted": False},
        "device": {
            "fingerprint_sha256": hashlib.sha256(device_id.encode("utf-8")).hexdigest(),
            "device_id_suffix": device_id[-4:],
            "binding_path": str(binding_path.resolve()),
            "binding_sha256": sha256(binding_path),
            "protocol": binding["protocol"],
            "firmware": binding["firmware"],
        },
        "final_contract_hashes": source_hashes,
    }


def verify_receipt(receipt_path: Path, **kwargs: Any) -> dict[str, Any]:
    receipt = load_object(receipt_path, "Phase 2 handoff receipt")
    if receipt.get("schema_version") != 1 or receipt.get("kind") != "phase2-phase1-handoff":
        fail("handoff receipt has an unsupported schema or kind")
    expected = check_phase1(**kwargs)
    embedded = dict(receipt)
    embedded.pop("generated_at", None)
    if embedded.get("evidence") != expected:
        fail("handoff receipt evidence differs from current immutable Phase 1 inputs")
    return receipt


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--summary", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--final-build", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--binding", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    paths = {"summary": args.summary, "selection_path": args.selection, "final_build_path": args.final_build, "archive_path": args.archive, "binding_path": args.binding}
    try:
        if args.verify_only:
            verify_receipt(args.output or ROOT / "artifacts/phase2/phase1-handoff.json", **paths)
            print("phase2 handoff: verified")
            return 0
        if args.output is None:
            parser.error("--output is required unless --verify-only is used")
        evidence = check_phase1(**paths)
        receipt = {"kind": "phase2-phase1-handoff", "schema_version": 1, "evidence": evidence}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        verify_receipt(args.output, **paths)
        print(f"phase2 handoff: wrote {args.output}")
        return 0
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"phase2 handoff rejected: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
