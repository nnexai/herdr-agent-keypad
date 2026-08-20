"""Atomic, immutable evidence persistence for the Phase 1 tracer."""
from __future__ import annotations

import copy
import hashlib
import json
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Mapping


class EvidenceError(RuntimeError):
    """Raised when durable evidence cannot be verified."""


def _canonical_bytes(value: Any) -> bytes:
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def verify_qualification_manifest(path: Path) -> dict[str, Any]:
    """Reopen the frozen profile without opening a transport."""
    from .qualification import qualification_manifest_check

    return qualification_manifest_check(Path(path))


def verify_qualification_linkage(
    manifest_path: Path,
    result_path: Path,
    traffic_path: Path | None = None,
    *,
    require_immutable_traffic: bool = False,
) -> dict[str, Any]:
    """Verify result-to-manifest and immutable traffic hash lineage."""
    manifest = verify_qualification_manifest(Path(manifest_path))
    try:
        result = json.loads(Path(result_path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"qualification result is not valid JSON: {exc}") from exc
    if not isinstance(result, dict):
        raise EvidenceError("qualification result must be a JSON object")
    from .qualification import validate_qualification_result
    try:
        validate_qualification_result(result, manifest)
    except ValueError as exc:
        raise EvidenceError(str(exc)) from exc
    linkage = result.get("qualification")
    if not isinstance(linkage, dict) or linkage.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise EvidenceError("qualification result does not link the frozen manifest hash")
    linked_traffic = linkage.get("traffic_path")
    linked_hash = linkage.get("traffic_sha256")
    if require_immutable_traffic and (not isinstance(linked_traffic, str) or not isinstance(linked_hash, str) or len(linked_hash) != 64):
        raise EvidenceError("immutable qualification traffic path/hash linkage is required")
    if traffic_path is not None:
        traffic = Path(traffic_path)
        if not traffic.is_file() or not isinstance(linked_hash, str) or _sha256(traffic) != linked_hash:
            raise EvidenceError("qualification traffic hash does not match the linked immutable file")
    return {"manifest": manifest, "result": result}

def resolve_qualification_pointer(pointer_path: Path, manifest_path: Path, purpose: str, output_path: Path) -> dict[str, Any]:
    """Resolve one immutable result pointer and emit a concrete lock."""
    pointer_path = Path(pointer_path)
    manifest_path = Path(manifest_path)
    output_path = Path(output_path)
    try:
        pointer = json.loads(pointer_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"qualification pointer is not valid JSON: {exc}") from exc
    if pointer.get("schema_version") != 1 or pointer.get("kind") != "qualification-pointer":
        raise EvidenceError("qualification pointer schema/kind is invalid")
    pointer_purpose = pointer.get("purpose")
    if purpose == "selection-candidate":
        if pointer_purpose != "usb-eligibility":
            raise EvidenceError("selection candidate must resolve the frozen USB eligibility pointer")
    elif pointer_purpose != purpose:
        raise EvidenceError("qualification pointer purpose mismatch")

    pointer_root = pointer_path.parent.resolve().parent
    manifest = verify_qualification_manifest(manifest_path)
    if pointer.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise EvidenceError("qualification pointer manifest hash mismatch")

    def concrete_target(value: Any, field: str, root: Path = pointer_root) -> Path:
        if not isinstance(value, str) or not value or Path(value).is_absolute():
            raise EvidenceError(f"qualification pointer {field} must be a relative path")
        candidate = root / value
        if candidate.is_symlink():
            raise EvidenceError(f"qualification pointer {field} must not be a symlink")
        resolved = candidate.resolve()
        if pointer_root != resolved and pointer_root not in resolved.parents:
            raise EvidenceError(f"qualification pointer {field} escapes its root")
        if not resolved.is_file():
            raise EvidenceError(f"qualification pointer {field} is not a file")
        return resolved

    result_path = concrete_target(pointer.get("result_path"), "result_path")
    if _sha256(result_path) != pointer.get("result_sha256"):
        raise EvidenceError("qualification pointer result hash mismatch")
    result = json.loads(result_path.read_text(encoding="utf-8"))
    linkage = result.get("qualification")
    if not isinstance(linkage, dict) or linkage.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise EvidenceError("qualification result manifest linkage mismatch")
    if result.get("status") != "pass":
        raise EvidenceError("qualification pointer target is not a strict pass")
    traffic_path = concrete_target(linkage.get("traffic_path"), "traffic_path", result_path.parent)
    if _sha256(traffic_path) != linkage.get("traffic_sha256"):
        raise EvidenceError("qualification pointer traffic hash mismatch")

    lock = {
        "schema_version": 1,
        "kind": "qualification-lock",
        "purpose": purpose,
        "status": "pass",
        "transport": result.get("transport"),
        "manifest_path": str(manifest_path.resolve()),
        "manifest_sha256": manifest["manifest_sha256"],
        "pointer_path": str(pointer_path.resolve()),
        "pointer_sha256": _sha256(pointer_path),
        "result_path": str(result_path),
        "result_sha256": _sha256(result_path),
        "traffic_path": str(traffic_path),
        "traffic_sha256": linkage["traffic_sha256"],
        "physical_overlap": result.get("physical_overlap"),
        "source_pointer_purpose": pointer_purpose,
        "interruption_ids": [row.get("id") for row in result.get("interruption_matrix", []) if isinstance(row, dict) and row.get("id")],
    }
    _atomic_bytes(output_path, _canonical_bytes(lock))
    return lock

def verify_qualification_lock(path: Path, requirements: set[str] | None = None) -> dict[str, Any]:
    requirements = set(requirements or ())
    try:
        lock = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"qualification lock is not valid JSON: {exc}") from exc
    if lock.get("schema_version") != 1 or lock.get("kind") != "qualification-lock" or lock.get("status") != "pass":
        raise EvidenceError("qualification lock schema/status is invalid")
    manifest = verify_qualification_manifest(Path(lock["manifest_path"]))
    if lock.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise EvidenceError("qualification lock manifest hash mismatch")
    result_path = Path(lock["result_path"])
    if _sha256(result_path) != lock.get("result_sha256"):
        raise EvidenceError("qualification lock result hash mismatch")
    traffic_path = Path(lock["traffic_path"])
    if _sha256(traffic_path) != lock.get("traffic_sha256"):
        raise EvidenceError("qualification lock traffic hash mismatch")
    result = _load_object(result_path, "qualification result")
    linkage = result.get("qualification", {})
    if linkage.get("manifest_sha256") != manifest["manifest_sha256"] or linkage.get("traffic_sha256") != lock["traffic_sha256"]:
        raise EvidenceError("qualification lock embedded linkage mismatch")
    if "strict-traffic" in requirements:
        counters = result.get("counters", {})
        expected = counters.get("expected")
        if result.get("status") != "pass" or not isinstance(expected, int) or any(counters.get(k) != expected for k in ("sent", "received", "acknowledged")):
            raise EvidenceError("qualification lock lacks strict traffic equality")
        if any(counters.get(k) != 0 for k in ("digest_mismatch", "duplicate", "out_of_order", "malformed", "rejected", "watchdog_reset")):
            raise EvidenceError("qualification lock contains strict traffic failures")
    if "complete-interruption-matrix" in requirements:
        from .qualification import required_interruption_ids
        required = set(required_interruption_ids(manifest))
        rows = {
            row.get("id"): row
            for row in result.get("interruption_matrix", [])
            if isinstance(row, dict) and isinstance(row.get("id"), str)
        }
        if set(lock.get("interruption_ids", [])) != required or not required.issubset(rows):
            raise EvidenceError("qualification lock interruption matrix is incomplete")
        if any(rows[row_id].get("response") != "Y" for row_id in required):
            raise EvidenceError("qualification lock contains an unavailable or failed applicable interruption")
    if requirements & {"qualification-semantic", "latency", "physical-proof", "recovery-proof"}:
        from .qualification import validate_qualification_result
        try:
            validate_qualification_result(result, manifest)
        except ValueError as exc:
            raise EvidenceError(str(exc)) from exc
    if "physical-proof" in requirements:
        if result.get("physical_overlap") != "Y" or not isinstance(linkage.get("physical_lock_sha256"), str):
            raise EvidenceError("qualification lock lacks linked physical proof")
    if "recovery-proof" in requirements and manifest.get("recovery_proof_required", True):
        if not isinstance(linkage.get("recovery_lock_sha256"), str):
            raise EvidenceError("qualification lock lacks linked recovery proof")
    return lock

def _load_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{label} is not valid JSON: {exc}") from exc
    if not isinstance(value, dict):
        raise EvidenceError(f"{label} must be a JSON object")
    return value


def _fixed_file(value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value:
        raise EvidenceError(f"{label} path is missing")
    path = Path(value)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise EvidenceError(f"{label} must be an absolute, concrete, non-symlink file")
    return path


def select_transport(
    manifest_path: Path,
    candidate_lock_path: Path,
    usb_lock_path: Path,
    wifi_lock_path: Path | None,
    output_path: Path,
) -> dict[str, Any]:
    """Select the strict USB pass without opening mutable qualification pointers."""
    manifest = verify_qualification_manifest(manifest_path)
    required = {"strict-traffic", "complete-interruption-matrix", "immutable-linkage"}
    candidate = verify_qualification_lock(candidate_lock_path, required)
    usb = verify_qualification_lock(usb_lock_path, required)
    if candidate.get("purpose") != "selection-candidate" or candidate.get("source_pointer_purpose") != "usb-eligibility":
        raise EvidenceError("selection candidate is not derived from the USB eligibility pointer")
    if usb.get("purpose") != "usb-eligibility":
        raise EvidenceError("USB lock purpose is invalid")
    linkage_fields = ("manifest_sha256", "result_path", "result_sha256", "traffic_path", "traffic_sha256")
    if any(candidate.get(field) != usb.get(field) for field in linkage_fields):
        raise EvidenceError("selection candidate and USB eligibility lock do not name the same immutable proof")
    if candidate.get("transport") != "usb" or usb.get("transport") != "usb":
        raise EvidenceError("strict USB success is required for the selected-usb branch")
    if candidate.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise EvidenceError("selection candidate does not match the frozen manifest")
    if wifi_lock_path is not None and Path(wifi_lock_path).exists():
        raise EvidenceError("Wi-Fi evidence must not exist after strict USB success")

    root = Path(__file__).resolve().parents[4]
    source_path = (root / "firmware" / "src" / "transport" / "usb_cdc.cpp").resolve()
    if not source_path.is_file():
        raise EvidenceError("selected USB adapter source is missing")
    selection = {
        "schema_version": 1,
        "kind": "selection-lock",
        "status": "pass",
        "environment": "selected-usb",
        "selected_adapter": "usb_cdc",
        "rationale": "USB selected for v1 scoped profile: all applicable qualification gates passed.",
        "manifest_path": str(Path(manifest_path).resolve()),
        "manifest_sha256": manifest["manifest_sha256"],
        "candidate_lock_path": str(Path(candidate_lock_path).resolve()),
        "candidate_lock_sha256": _sha256(Path(candidate_lock_path)),
        "usb_lock_path": str(Path(usb_lock_path).resolve()),
        "usb_lock_sha256": _sha256(Path(usb_lock_path)),
        "result_path": usb["result_path"],
        "result_sha256": usb["result_sha256"],
        "traffic_path": usb["traffic_path"],
        "traffic_sha256": usb["traffic_sha256"],
        "selected_source_path": str(source_path),
        "selected_source_sha256": _sha256(source_path),
    }
    _atomic_bytes(Path(output_path), _canonical_bytes(selection))
    return selection


def verify_selection_lock(path: Path) -> dict[str, Any]:
    selection = _load_object(path, "selection lock")
    if (
        selection.get("schema_version") != 1
        or selection.get("kind") != "selection-lock"
        or selection.get("status") != "pass"
        or selection.get("environment") != "selected-usb"
        or selection.get("selected_adapter") != "usb_cdc"
    ):
        raise EvidenceError("selection lock schema, status, or selected environment is invalid")
    if selection.get("rationale") != "USB selected for v1 scoped profile: all applicable qualification gates passed.":
        raise EvidenceError("selection rationale is not the scoped USB decision")
    manifest_path = _fixed_file(selection.get("manifest_path"), "selection manifest")
    manifest = verify_qualification_manifest(manifest_path)
    if selection.get("manifest_sha256") != manifest["manifest_sha256"]:
        raise EvidenceError("selection manifest hash mismatch")
    candidate_path = _fixed_file(selection.get("candidate_lock_path"), "selection candidate lock")
    usb_path = _fixed_file(selection.get("usb_lock_path"), "USB eligibility lock")
    if _sha256(candidate_path) != selection.get("candidate_lock_sha256"):
        raise EvidenceError("selection candidate lock hash mismatch")
    if _sha256(usb_path) != selection.get("usb_lock_sha256"):
        raise EvidenceError("selection USB lock hash mismatch")
    candidate = verify_qualification_lock(candidate_path, {"strict-traffic", "complete-interruption-matrix"})
    usb = verify_qualification_lock(usb_path, {"strict-traffic", "complete-interruption-matrix"})
    for field in ("result_path", "result_sha256", "traffic_path", "traffic_sha256"):
        if selection.get(field) != candidate.get(field) or selection.get(field) != usb.get(field):
            raise EvidenceError(f"selection {field} lineage mismatch")
    source_path = _fixed_file(selection.get("selected_source_path"), "selected adapter source")
    if _sha256(source_path) != selection.get("selected_source_sha256"):
        raise EvidenceError("selected adapter source hash mismatch")
    return selection


def selection_self_check(usb_lock_path: Path) -> None:
    """Exercise exact-path selection, negative hashes, and USB-first asymmetry."""
    usb_path = Path(usb_lock_path)
    usb = verify_qualification_lock(usb_path, {"strict-traffic", "complete-interruption-matrix"})
    if "/latest/" in usb["result_path"] or Path(usb["result_path"]).is_symlink():
        raise EvidenceError("USB eligibility lock did not resolve a concrete immutable result")
    with tempfile.TemporaryDirectory() as directory:
        temporary = Path(directory)
        broken = copy.deepcopy(usb)
        broken["result_sha256"] = "0" * 64
        broken_path = temporary / "broken.json"
        _atomic_bytes(broken_path, _canonical_bytes(broken))
        try:
            verify_qualification_lock(broken_path)
        except EvidenceError:
            pass
        else:
            raise EvidenceError("tampered qualification hash was accepted")
        candidate = copy.deepcopy(usb)
        candidate["purpose"] = "selection-candidate"
        candidate["source_pointer_purpose"] = "usb-eligibility"
        candidate_path = temporary / "candidate.json"
        _atomic_bytes(candidate_path, _canonical_bytes(candidate))
        output_path = temporary / "selection.json"
        selected = select_transport(
            Path(usb["manifest_path"]),
            candidate_path,
            usb_path,
            temporary / "absent-wifi.json",
            output_path,
        )
        if selected["environment"] != "selected-usb":
            raise EvidenceError("strict USB pass did not win asymmetric selection")


def build_selected(selection_lock_path: Path, output_path: Path) -> dict[str, Any]:
    """Build and hash the only adapter authorized by the selection lock."""
    import subprocess

    selection_path = Path(selection_lock_path)
    selection = verify_selection_lock(selection_path)
    root = Path(__file__).resolve().parents[4]
    platformio_path = root / "platformio.ini"
    main_path = root / "firmware" / "src" / "main.cpp"
    source_path = Path(selection["selected_source_path"])
    platformio = platformio_path.read_text(encoding="utf-8")
    main = main_path.read_text(encoding="utf-8")
    if "default_envs = selected-usb" not in platformio or "[env:selected-usb]" not in platformio:
        raise EvidenceError("PlatformIO selected-usb environment is not the default composition")
    if "-<transport/wifi_tls.cpp>" not in platformio:
        raise EvidenceError("selected-usb does not explicitly exclude the Wi-Fi adapter")
    if "UsbCdcLink usbLink;" not in main or "WifiTlsLink" in main:
        raise EvidenceError("firmware composition does not instantiate exactly UsbCdcLink")
    wifi_source = root / "firmware" / "src" / "transport" / "wifi_tls.cpp"
    if wifi_source.exists():
        raise EvidenceError("unselected Wi-Fi adapter source exists after the fallback was skipped")
    pio = root / "tools" / "phase1_bringup" / ".venv" / "bin" / "pio"
    completed = subprocess.run(
        [str(pio), "run", "-e", "selected-usb"],
        cwd=root,
        check=False,
        text=True,
    )
    if completed.returncode != 0:
        raise EvidenceError("selected-usb PlatformIO build failed")
    binary_path = root / ".pio" / "build" / "selected-usb" / "firmware.bin"
    if not binary_path.is_file():
        raise EvidenceError("selected-usb firmware binary is missing")
    build_root = binary_path.parent
    if any("wifi_tls" in item.name.lower() for item in build_root.rglob("*")):
        raise EvidenceError("selected-usb build contains an unselected Wi-Fi object")
    build_lock = {
        "schema_version": 1,
        "kind": "final-build-lock",
        "status": "pass",
        "environment": "selected-usb",
        "selection_lock_path": str(selection_path.resolve()),
        "selection_lock_sha256": _sha256(selection_path),
        "manifest_sha256": selection["manifest_sha256"],
        "selected_source_path": str(source_path),
        "selected_source_sha256": _sha256(source_path),
        "binary_path": str(binary_path.resolve()),
        "binary_sha256": _sha256(binary_path),
        "platformio_path": str(platformio_path.resolve()),
        "platformio_sha256": _sha256(platformio_path),
        "main_path": str(main_path.resolve()),
        "main_sha256": _sha256(main_path),
        "unselected_adapter": "wifi_tls",
        "unselected_source_present": False,
        "unselected_object_present": False,
        "unselected_symbol_present": False,
    }
    _atomic_bytes(Path(output_path), _canonical_bytes(build_lock))
    return build_lock


def verify_build_lock(path: Path) -> dict[str, Any]:
    lock = _load_object(path, "final build lock")
    if (
        lock.get("schema_version") != 1
        or lock.get("kind") != "final-build-lock"
        or lock.get("status") != "pass"
        or lock.get("environment") != "selected-usb"
    ):
        raise EvidenceError("final build lock schema/status is invalid")
    selection_path = _fixed_file(lock.get("selection_lock_path"), "build selection lock")
    selection = verify_selection_lock(selection_path)
    if _sha256(selection_path) != lock.get("selection_lock_sha256"):
        raise EvidenceError("final build selection hash mismatch")
    if lock.get("manifest_sha256") != selection.get("manifest_sha256"):
        raise EvidenceError("final build manifest hash mismatch")
    for prefix in ("selected_source", "binary", "platformio", "main"):
        item = _fixed_file(lock.get(f"{prefix}_path"), f"build {prefix}")
        if _sha256(item) != lock.get(f"{prefix}_sha256"):
            raise EvidenceError(f"final build {prefix} hash mismatch")
    if any(lock.get(field) is not False for field in ("unselected_source_present", "unselected_object_present", "unselected_symbol_present")):
        raise EvidenceError("final build contains an unselected adapter artifact")
    return lock


def archive_phase1(
    selection_lock_path: Path,
    build_lock_path: Path,
    qualification_lock_path: Path,
    output_path: Path,
) -> dict[str, Any]:
    """Create the fixed, secret-free archive marker from immutable locks."""
    selection_path = Path(selection_lock_path)
    build_path = Path(build_lock_path)
    qualification_path = Path(qualification_lock_path)
    selection = verify_selection_lock(selection_path)
    build = verify_build_lock(build_path)
    qualification = verify_qualification_lock(
        qualification_path,
        {"strict-traffic", "complete-interruption-matrix", "immutable-linkage"},
    )
    if build["selection_lock_sha256"] != _sha256(selection_path):
        raise EvidenceError("archive build does not bind the selected decision")
    if selection["result_sha256"] != qualification["result_sha256"]:
        raise EvidenceError("archive qualification does not bind the selected result")
    archive = {
        "schema_version": 1,
        "kind": "phase1-archive-lock",
        "status": "archived",
        "environment": selection["environment"],
        "selection_lock_path": str(selection_path.resolve()),
        "selection_lock_sha256": _sha256(selection_path),
        "build_lock_path": str(build_path.resolve()),
        "build_lock_sha256": _sha256(build_path),
        "qualification_lock_path": str(qualification_path.resolve()),
        "qualification_lock_sha256": _sha256(qualification_path),
        "manifest_sha256": selection["manifest_sha256"],
        "result_path": selection["result_path"],
        "result_sha256": selection["result_sha256"],
        "traffic_path": selection["traffic_path"],
        "traffic_sha256": selection["traffic_sha256"],
        "binary_path": build["binary_path"],
        "binary_sha256": build["binary_sha256"],
    }
    _atomic_bytes(Path(output_path), _canonical_bytes(archive))
    return archive


def verify_archive_lock(path: Path) -> dict[str, Any]:
    archive = _load_object(path, "Phase 1 archive lock")
    if (
        archive.get("schema_version") != 1
        or archive.get("kind") != "phase1-archive-lock"
        or archive.get("status") != "archived"
        or archive.get("environment") != "selected-usb"
    ):
        raise EvidenceError("Phase 1 archive lock schema/status is invalid")
    selection_path = _fixed_file(archive.get("selection_lock_path"), "archive selection lock")
    build_path = _fixed_file(archive.get("build_lock_path"), "archive build lock")
    qualification_path = _fixed_file(archive.get("qualification_lock_path"), "archive qualification lock")
    selection = verify_selection_lock(selection_path)
    build = verify_build_lock(build_path)
    qualification = verify_qualification_lock(
        qualification_path,
        {"strict-traffic", "complete-interruption-matrix", "immutable-linkage"},
    )
    for label, item in (("selection", selection_path), ("build", build_path), ("qualification", qualification_path)):
        if _sha256(item) != archive.get(f"{label}_lock_sha256"):
            raise EvidenceError(f"archive {label} lock hash mismatch")
    if archive.get("manifest_sha256") != selection["manifest_sha256"]:
        raise EvidenceError("archive manifest hash mismatch")
    if archive.get("result_sha256") != qualification["result_sha256"]:
        raise EvidenceError("archive result hash mismatch")
    if archive.get("binary_sha256") != build["binary_sha256"]:
        raise EvidenceError("archive binary hash mismatch")
    forbidden = ("password", "passphrase", "private_key", "certificate", "ssid", "secret")
    if any(token in key.lower() for key in archive for token in forbidden):
        raise EvidenceError("archive contains a secret-bearing field")
    if "/latest/" in json.dumps(archive, sort_keys=True):
        raise EvidenceError("archive consumes mutable latest evidence")
    return archive


def _fsync_directory(directory: Path) -> None:
    fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    temporary_path = Path(temporary)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_path, path)
        _fsync_directory(path.parent)
    finally:
        temporary_path.unlink(missing_ok=True)

def atomic_write_pair(path: Path, content: bytes, digest: bytes) -> None:
    """Replace an evidence file and its checksum as one verified operation."""
    path = Path(path)
    sidecar = path.with_suffix(path.suffix + ".sha256")
    path.parent.mkdir(parents=True, exist_ok=True)
    old_content = path.read_bytes() if path.exists() else None
    old_digest = sidecar.read_bytes() if sidecar.exists() else None
    content_fd, content_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    digest_fd, digest_name = tempfile.mkstemp(prefix=f".{sidecar.name}.", dir=path.parent)
    content_temp = Path(content_name)
    digest_temp = Path(digest_name)
    replaced_content = False
    replaced_digest = False
    try:
        with os.fdopen(content_fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        with os.fdopen(digest_fd, "wb") as stream:
            stream.write(digest)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(content_temp, path)
        replaced_content = True
        _fsync_directory(path.parent)
        os.replace(digest_temp, sidecar)
        replaced_digest = True
        _fsync_directory(path.parent)
        if hashlib.sha256(path.read_bytes()).hexdigest().encode("ascii") != sidecar.read_bytes().strip():
            raise EvidenceError("evidence/checksum pair verification failed")
    except Exception:
        try:
            if replaced_content:
                if old_content is None:
                    path.unlink(missing_ok=True)
                else:
                    _atomic_bytes(path, old_content)
            if replaced_digest:
                if old_digest is None:
                    sidecar.unlink(missing_ok=True)
                else:
                    _atomic_bytes(sidecar, old_digest)
        except Exception:
            pass
        raise
    finally:
        content_temp.unlink(missing_ok=True)
        digest_temp.unlink(missing_ok=True)


def _validate_json_object(path: Path, expected_kind: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise EvidenceError(f"{expected_kind} is not valid JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise EvidenceError(f"{expected_kind} must be a JSON object")
    if data.get("schema_version") != 1:
        raise EvidenceError(f"{expected_kind} has unsupported schema_version")
    if data.get("kind") != expected_kind:
        raise EvidenceError(f"{expected_kind} kind mismatch")
    return data


_ROW_FIELDS = {"row_id", "run_id", "step_id", "gate", "machine_status", "machine_reply_seq", "human_response", "physical_status", "observed_value", "timestamp"}
_MACHINE_STATUSES = {"acknowledged", "observed", "rejected", "failed", "surprising", "unavailable"}
_HUMAN_RESPONSES = {"Y", "N", "R"}
_PHYSICAL_STATUSES = {"pass", "failed", "repeated", "unavailable", "surprising"}
MACHINE_BATCH_GATES = ("IDENTIFY", "DISPLAYS", "KEYS", "ENCODER", "LEDS", "BRIGHTNESS", "REBOOT")
MACHINE_BATCH_GATE_NAMES = {gate.title() if gate != "LEDS" else "LEDs" for gate in MACHINE_BATCH_GATES}


def _canonical_physical_steps() -> tuple[tuple[str, str], ...]:
    from .guide import GATES
    return tuple((row.step_id, gate.name) for gate in GATES[:7] for row in gate.rows)


def _safe_contained_file(path: Path, root: Path, label: str) -> Path:
    root = root.resolve()
    candidate = Path(path)
    resolved = candidate.resolve() if candidate.is_absolute() else (root / candidate).resolve()
    cursor = resolved
    while cursor != root:
        if cursor.is_symlink():
            raise EvidenceError(f"{label} has a symlink ancestor")
        if cursor.parent == cursor:
            raise EvidenceError(f"{label} escapes its root")
        cursor = cursor.parent
    if resolved != root and root not in resolved.parents:
        raise EvidenceError(f"{label} escapes its root")
    if not resolved.exists():
        raise EvidenceError(f"{label} does not exist")
    if not resolved.is_file() and not resolved.is_dir():
        raise EvidenceError(f"{label} is not a regular path")
    return resolved


def _derived_physical_status(rows: list[dict[str, Any]]) -> str:
    canonical = _canonical_physical_steps()
    by_step: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        if not row.get("replaces"):
            by_step.setdefault(row["step_id"], []).append(row)
    if tuple((step, entries[0].get("gate")) for step, entries in by_step.items()) != canonical:
        return "incomplete"
    if set(by_step) != {step for step, _ in canonical}:
        return "incomplete"
    finals = {step: entries[-1] for step, entries in by_step.items()}
    if any(
        row.get("human_response") != "Y"
        or row.get("physical_status") != "pass"
        or row.get("machine_status") != "acknowledged"
        for row in finals.values()
    ):
        return "fail"
    return "pass"


def _validate_machine_observation(observation: Any, expected_run_id: str) -> dict[str, Any]:
    if not isinstance(observation, dict):
        raise EvidenceError("machine observation must be an object")
    required = {"row_id", "run_id", "step_id", "gate", "machine_status", "machine_reply_seq", "observed_value", "timestamp"}
    if not required.issubset(observation):
        raise EvidenceError("machine observation is missing required fields")
    if observation["run_id"] != expected_run_id or not isinstance(observation["row_id"], str) or not observation["row_id"]:
        raise EvidenceError("machine observation identity is invalid")
    if observation["gate"] not in MACHINE_BATCH_GATE_NAMES:
        raise EvidenceError("machine observation gate is invalid")
    if observation["machine_status"] not in _MACHINE_STATUSES:
        raise EvidenceError("machine observation status is invalid")
    if observation["observed_value"] is None:
        raise EvidenceError("machine observation observed_value must use literal unavailable")
    if not isinstance(observation["timestamp"], (int, float)):
        raise EvidenceError("machine observation timestamp is invalid")
    if "human_response" in observation or "physical_status" in observation:
        raise EvidenceError("machine observation must not contain physical confirmation fields")
    return observation

def _validate_physical_row(row: Any, expected_run_id: str | None = None) -> dict[str, Any]:
    if not isinstance(row, dict) or not _ROW_FIELDS.issubset(row):
        raise EvidenceError("physical row is missing required evidence fields")
    if not isinstance(row["row_id"], str) or not row["row_id"]:
        raise EvidenceError("physical row row_id must be non-empty")
    if expected_run_id is not None and row.get("run_id") != expected_run_id:
        raise EvidenceError("physical row run_id mismatch")
    if not isinstance(row["step_id"], str) or not row["step_id"] or not isinstance(row["gate"], str) or not row["gate"]:
        raise EvidenceError("physical row step identity is invalid")
    if row["machine_status"] not in _MACHINE_STATUSES:
        raise EvidenceError("physical row machine_status is invalid")
    if row["human_response"] not in _HUMAN_RESPONSES:
        raise EvidenceError("physical row human_response is invalid")
    if row["physical_status"] not in _PHYSICAL_STATUSES:
        raise EvidenceError("physical row physical_status is invalid")
    if row["observed_value"] is None:
        raise EvidenceError("physical row observed_value must use literal unavailable")
    if not isinstance(row["timestamp"], (int, float)):
        raise EvidenceError("physical row timestamp is invalid")
    if row.get("replaces"):
        if row.get("replacement_token") != "REPLACE":
            raise EvidenceError("replacement row requires a typed REPLACE token")
        if row["human_response"] != "Y" or row["physical_status"] != "pass":
            raise EvidenceError("replacement row must be a fresh passing observation")
    elif row["human_response"] == "Y" and row["physical_status"] == "pass" and row["machine_status"] != "acknowledged":
        raise EvidenceError("physical PASS requires a current acknowledged machine fact")
    return row


def _validate_physical_map(result: dict[str, Any], require_rows: bool = True) -> None:
    physical_map = result.get("physical_map")
    if not isinstance(physical_map, dict):
        raise EvidenceError("result is missing physical_map")
    rows = physical_map.get("rows")
    if not isinstance(rows, list) or (require_rows and not rows):
        raise EvidenceError("physical_map rows must be a non-empty list")
    seen: set[str] = set()
    for row in rows:
        checked = _validate_physical_row(row, result.get("run_id"))
        if checked["row_id"] in seen:
            raise EvidenceError("physical row ids must be unique")
        seen.add(checked["row_id"])
    guided_order = physical_map.get("guided_order")
    if guided_order is not None and (not isinstance(guided_order, list) or guided_order != ["Identify", "Displays", "Keys", "Encoder", "LEDs", "Brightness", "Reboot", "Pair", "Recover", "Traffic", "Selection"]):
        raise EvidenceError("physical_map guided order is not the fixed eleven-gate sequence")
    derived = _derived_physical_status(rows)
    if result.get("status") == "pass" and derived != "pass":
        raise EvidenceError("physical PASS is not derived from the complete canonical history")
    if result.get("status") == "pass" and len({row["step_id"] for row in rows if not row.get("replaces")}) != 30:
        raise EvidenceError("physical PASS requires exactly 30 canonical observations")

def _validate_recovery(result: dict[str, Any], require_events: bool = False, action_specific: bool = False) -> None:
    events = result.get("recovery")
    if events is None:
        if require_events:
            raise EvidenceError("result is missing recovery evidence")
        return
    if not isinstance(events, list) or (require_events and not events):
        raise EvidenceError("recovery evidence must be a non-empty list")
    seen: set[str] = set()
    for event in events:
        required = {"event_id", "transition", "descriptor", "boot_id", "session_id", "discarded_ids", "timestamp", "detail"}
        if action_specific:
            required |= {"action", "pre", "post"}
        if not isinstance(event, dict) or not required.issubset(event):
            raise EvidenceError("recovery event is incomplete")
        if event["event_id"] in seen or not isinstance(event["event_id"], str) or not event["event_id"]:
            raise EvidenceError("recovery event IDs must be unique")
        seen.add(event["event_id"])
        if not isinstance(event["descriptor"], dict) or not isinstance(event["session_id"], str):
            raise EvidenceError("recovery descriptor/session is invalid")
        if not isinstance(event["discarded_ids"], list) or any(not isinstance(item, int) for item in event["discarded_ids"]):
            raise EvidenceError("recovery discarded IDs are invalid")
        if action_specific:
            from .serial_link import validate_recovery_action_event
            try:
                validate_recovery_action_event(event, event["action"])
            except Exception as exc:
                raise EvidenceError(str(exc)) from exc

class EvidenceWriter:
    """Write one immutable manifest/result pair and verify it after reopening.

    A target directory is never overwritten. Rows are accumulated in memory until
    ``finalize``; each row is append-only and a typed replacement links old/new
    records rather than modifying an existing observation.
    """

    def __init__(self, root: Path, run_id: str):
        if not run_id or "/" in run_id or "\\" in run_id or run_id in {".", ".."}:
            raise ValueError("run_id must be a single non-empty path component")
        self.root = Path(root)
        self.run_id = run_id
        self.directory = self.root / run_id
        self._rows: list[dict[str, Any]] = []
        self._row_ids: set[str] = set()
        self._recovery: list[dict[str, Any]] = []
        self._finalized = False

    def record_row(self, row: dict[str, Any]) -> None:
        self.record_rows([row])

    def record_rows(self, rows: list[dict[str, Any]]) -> None:
        """Append a complete group after validating every row."""
        if self._finalized:
            raise EvidenceError("immutable evidence is already finalized")
        candidates = [copy.deepcopy(row) for row in rows]
        candidate_ids: set[str] = set()
        for candidate in candidates:
            _validate_physical_row(candidate, self.run_id)
            if candidate["row_id"] in self._row_ids or candidate["row_id"] in candidate_ids:
                raise EvidenceError("physical row id already exists")
            candidate_ids.add(candidate["row_id"])
        self._rows.extend(candidates)
        self._row_ids.update(candidate_ids)

    def record_recovery(self, event: dict[str, Any]) -> None:
        if self._finalized:
            raise EvidenceError("immutable evidence is already finalized")
        required = {"event_id", "transition", "descriptor", "boot_id", "session_id", "discarded_ids", "timestamp", "detail"}
        if not required.issubset(event) or not isinstance(event["event_id"], str) or not event["event_id"]:
            raise EvidenceError("recovery event is missing required fields")
        if not isinstance(event["descriptor"], dict) or not isinstance(event["session_id"], str):
            raise EvidenceError("recovery event descriptor/session is invalid")
        if not isinstance(event["discarded_ids"], list) or any(not isinstance(item, int) for item in event["discarded_ids"]):
            raise EvidenceError("recovery discarded IDs must be a bounded integer list")
        if not isinstance(event["timestamp"], (int, float)):
            raise EvidenceError("recovery event timestamp is invalid")
        if any(existing["event_id"] == event["event_id"] for existing in self._recovery):
            raise EvidenceError("recovery event id already exists")
        self._recovery.append(copy.deepcopy(event))

    def replace_row(self, old_row_id: str, replacement: dict[str, Any], typed_confirmation: str) -> None:
        if typed_confirmation != "REPLACE":
            raise EvidenceError("typed REPLACE is required to add a replacement observation")
        if not any(row["row_id"] == old_row_id for row in self._rows):
            raise EvidenceError("replacement target row does not exist")
        candidate = copy.deepcopy(replacement)
        _validate_physical_row(candidate, self.run_id)
        if candidate["row_id"] in self._row_ids:
            raise EvidenceError("replacement row id already exists")
        candidate["replaces"] = old_row_id
        candidate["replacement_token"] = "REPLACE"
        self._rows.append(candidate)
        self._row_ids.add(candidate["row_id"])
    def finalize(self, manifest: dict[str, Any], result: dict[str, Any]) -> Path:
        if self._finalized:
            raise EvidenceError("evidence directory already finalized")
        final_result = copy.deepcopy(result)
        physical_map = final_result.setdefault("physical_map", {})
        if not isinstance(physical_map, dict):
            raise EvidenceError("physical_map must be an object")
        physical_map.setdefault("rows", copy.deepcopy(self._rows))
        if self._recovery:
            final_result.setdefault("recovery", copy.deepcopy(self._recovery))
        _validate_physical_map(final_result, require_rows=final_result.get("status") not in {"fail", "incomplete"})
        path = self.write(manifest, final_result)
        self._finalized = True
        return path

    def write(self, manifest: dict[str, Any], result: dict[str, Any], extra_files: Mapping[str, bytes] | None = None) -> Path:
        if self.directory.exists():
            raise EvidenceError(f"evidence directory already exists: {self.directory}")
        attempt: Path | None = None
        try:
            self.directory.mkdir(parents=True, exist_ok=False)
            _atomic_bytes(self.directory / "manifest.json", _canonical_bytes(manifest))
            _atomic_bytes(self.directory / "result.json", _canonical_bytes(result))
            for name, content in (extra_files or {}).items():
                relative = Path(name)
                if relative.is_absolute() or ".." in relative.parts or not isinstance(content, bytes):
                    raise EvidenceError("extra evidence files must be relative byte payloads")
                _atomic_bytes(self.directory / relative, content)
            files = sorted(
                path.relative_to(self.directory)
                for path in self.directory.rglob("*")
                if path.is_file() and path.name != "SHA256SUMS"
            )
            checksums = "".join(f"{_sha256(self.directory / name)}  {name.as_posix()}\n" for name in files).encode("ascii")
            _atomic_bytes(self.directory / "SHA256SUMS", checksums)
            self.verify()
            return self.directory
        except Exception as exc:
            if self.directory.exists():
                attempt = self.root / f"failed-attempt-{self.run_id}-{time.time_ns()}"
                os.replace(self.directory, attempt)
                _fsync_directory(self.root)
            raise EvidenceError(f"evidence write preserved as {attempt}: {exc}") from exc

    def verify(self) -> dict[str, dict[str, Any]]:
        manifest_path = self.directory / "manifest.json"
        result_path = self.directory / "result.json"
        sums_path = self.directory / "SHA256SUMS"
        if not all(path.is_file() for path in (manifest_path, result_path, sums_path)):
            raise EvidenceError("manifest.json, result.json, and SHA256SUMS are required")
        manifest = _validate_json_object(manifest_path, "manifest")
        result = _validate_json_object(result_path, "result")
        if manifest.get("run_id") != self.run_id or result.get("run_id") != self.run_id:
            raise EvidenceError("evidence run_id mismatch")
        if "physical_map" in result:
            _validate_physical_map(result, require_rows=result.get("status") not in {"fail", "incomplete"})
        expected: dict[str, str] = {}
        for line in sums_path.read_text(encoding="ascii").splitlines():
            parts = line.split(maxsplit=1)
            if len(parts) != 2 or len(parts[0]) != 64:
                raise EvidenceError("invalid SHA256SUMS entry")
            relative = Path(parts[1])
            if relative.is_absolute() or ".." in relative.parts or relative.name == "SHA256SUMS":
                raise EvidenceError("SHA256SUMS contains an unsafe path")
            expected[relative.as_posix()] = parts[0]
        actual_files = {
            path.relative_to(self.directory).as_posix()
            for path in self.directory.rglob("*")
            if path.is_file() and path.name != "SHA256SUMS"
        }
        if set(expected) != actual_files or not {"manifest.json", "result.json"}.issubset(expected):
            raise EvidenceError("SHA256SUMS must cover every evidence file exactly once")
        for name, digest in expected.items():
            actual = _sha256(self.directory / name)
            if actual != digest:
                raise EvidenceError(f"hash mismatch for {name}")
        return {"manifest": manifest, "result": result}



def self_check_roundtrip(root: Path) -> Path:
    """Exercise the production writer and reopening verifier with real files."""
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    run_id = f"self-check-{time.time_ns()}"
    writer = EvidenceWriter(root, run_id)
    manifest = {"schema_version": 1, "kind": "manifest", "run_id": run_id, "status": "self-check", "protocol": {"version": 1, "max_line_bytes_including_lf": 4096}, "environment": {"python": "verified", "pyserial": "3.5"}}
    result = {"schema_version": 1, "kind": "result", "run_id": run_id, "status": "pass", "physical_observation": "unavailable", "transport": {"type": "self-check", "acknowledged": True}}
    path = writer.write(manifest, result)
    EvidenceWriter(root, run_id).verify()
    return path

def physical_schema_check() -> None:
    """Check schema and replacement invariants without creating physical evidence."""
    with tempfile.TemporaryDirectory() as directory:
        writer = EvidenceWriter(Path(directory), "schema-check")
        row = {"row_id": "schema-check:1", "run_id": "schema-check", "step_id": "IDENTIFY", "gate": "Identify", "machine_status": "acknowledged", "machine_reply_seq": 1, "human_response": "Y", "physical_status": "pass", "observed_value": "unavailable", "timestamp": time.time()}
        writer.record_row(row)
        replacement = dict(row, row_id="schema-check:2", observed_value={"device": "observed"})
        writer.replace_row(row["row_id"], replacement, "REPLACE")
        manifest = {"schema_version": 1, "kind": "manifest", "run_id": "schema-check", "status": "incomplete"}
        result = {"schema_version": 1, "kind": "result", "run_id": "schema-check", "status": "incomplete", "physical_map": {"rows": writer._rows, "guided_order": ["Identify", "Displays", "Keys", "Encoder", "LEDs", "Brightness", "Reboot", "Pair", "Recover", "Traffic", "Selection"]}}
        writer.finalize(manifest, result)
        checked = EvidenceWriter(Path(directory), "schema-check").verify()["result"]["physical_map"]["rows"]
        if len(checked) != 2 or checked[1].get("replaces") != row["row_id"]:
            raise AssertionError("replacement history is not linked and immutable")


def parse_group_responses(spec: str, run_id: str) -> dict[str, str]:
    """Parse exactly one bounded response for each machine batch gate."""
    if not isinstance(spec, str) or not spec.strip():
        raise EvidenceError("confirm-batch requires --groups for every machine gate")
    run_suffix = run_id[-6:].upper()
    parsed: dict[str, str] = {}
    for item in spec.split(","):
        item = item.strip()
        if not item or "=" not in item:
            raise EvidenceError("groups must use GATE=Y,N,R entries")
        gate, value = (part.strip().upper() for part in item.split("=", 1))
        if gate not in MACHINE_BATCH_GATES:
            raise EvidenceError(f"unknown machine gate in groups: {gate}")
        if gate in parsed:
            raise EvidenceError(f"duplicate machine gate in groups: {gate}")
        action, separator, supplied_suffix = value.partition("@")
        if action not in {"Y", "N", "R"}:
            raise EvidenceError(f"invalid group response for {gate}; use Y, N, or R")
        if separator and supplied_suffix != run_suffix:
            raise EvidenceError(f"run suffix mismatch for {gate}; expected {run_suffix}")
        parsed[gate] = action
    missing = [gate for gate in MACHINE_BATCH_GATES if gate not in parsed]
    if missing:
        raise EvidenceError("missing group responses: " + ", ".join(missing))
    return parsed


def verify_machine_run(path: Path) -> dict[str, Any]:
    """Verify a machine-only batch artifact and reject physical claims."""
    candidate = verify_physical_evidence(path)
    checked = EvidenceWriter(candidate.parent, candidate.name).verify()
    manifest = checked["manifest"]
    result = checked["result"]
    if manifest.get("workflow") != "batch-machine-only" or result.get("mode") != "machine-only":
        raise EvidenceError("evidence target is not a machine-only batch run")
    if manifest.get("run_id") != result.get("run_id") or result.get("physical_confirmation") is not False:
        raise EvidenceError("machine-only artifact identity or physical-confirmation marker is invalid")
    if "physical_map" in result:
        raise EvidenceError("machine-only artifact must not contain a physical_map")
    observations = result.get("machine_observations")
    if not isinstance(observations, list) or not observations:
        raise EvidenceError("machine-only artifact has no machine observations")
    expected_steps = _canonical_physical_steps()
    observed_steps = [(item.get("step_id"), item.get("gate")) for item in observations]
    if len(observations) != 30 or observed_steps != list(expected_steps):
        raise EvidenceError("machine-only artifact must contain exactly 30 canonical observations in order")
    if any(item.get("machine_status") != "acknowledged" for item in observations):
        raise EvidenceError("machine-only artifact contains a failed machine observation")
    seen: set[str] = set()
    for observation in observations:
        checked_observation = _validate_machine_observation(observation, str(result["run_id"]))
        if checked_observation["row_id"] in seen:
            raise EvidenceError("machine observation row ids must be unique")
        seen.add(checked_observation["row_id"])
    return checked


def _validate_reopened_machine_source(result: dict[str, Any], candidate: Path) -> dict[str, Any]:
    linkage = result.get("source_machine")
    if not isinstance(linkage, dict):
        raise EvidenceError("physical PASS requires reopened machine source linkage")
    root = candidate.parent.resolve()
    source_path = _safe_contained_file(Path(str(linkage.get("path", ""))), root, "source machine run")
    source_dir = source_path
    checked = verify_machine_run(source_dir)
    source_files = {
        "manifest_sha256": _sha256(source_dir / "manifest.json"),
        "result_sha256": _sha256(source_dir / "result.json"),
        "checksums_sha256": _sha256(source_dir / "SHA256SUMS"),
    }
    for key, value in source_files.items():
        if linkage.get(key) != value:
            raise EvidenceError(f"source machine {key} mismatch")
    if linkage.get("run_id") != checked["result"].get("run_id"):
        raise EvidenceError("source machine run identity mismatch")
    return checked

def verify_physical_evidence(
    path: Path,
    require_physical_map: bool = False,
    require_recovery: bool = False,
    *,
    action_specific: bool = False,
    reopened_machine_source: bool = False,
) -> Path:
    """Reopen a concrete immutable run and require selected evidence classes."""
    candidate = Path(path)
    if candidate.is_file() and candidate.name == "result.json":
        candidate = candidate.parent
    if not candidate.is_dir():
        raise EvidenceError(f"evidence target does not exist: {path}")
    result_path = candidate / "result.json"
    if not result_path.is_file():
        raise EvidenceError("evidence target must be a concrete run directory")
    writer = EvidenceWriter(candidate.parent, candidate.name)
    checked = writer.verify()
    result = checked["result"]
    if require_physical_map:
        _validate_physical_map(result)
    if reopened_machine_source or result.get("status") == "pass":
        _validate_reopened_machine_source(result, candidate)

    if require_recovery:
        _validate_recovery(result, require_events=True, action_specific=action_specific)
    return candidate

def verify_physical_lock(path: Path) -> dict[str, Any]:
    lock = _validate_json_object(Path(path), "physical-proof-lock")
    if lock.get("kind") != "physical-proof-lock" or lock.get("status") != "pass":
        raise EvidenceError("physical proof lock schema/status is invalid")
    evidence_root = Path(path).resolve().parent.parent
    confirmed = _safe_contained_file(Path(str(lock.get("confirmed_path", ""))), evidence_root, "confirmed physical run")
    source = _safe_contained_file(Path(str(lock.get("source_path", ""))), evidence_root, "source machine run")
    if not confirmed.is_dir() or not source.is_dir():
        raise EvidenceError("physical proof lock paths must name contained run directories")
    checked = verify_physical_evidence(confirmed, require_physical_map=True, reopened_machine_source=True)
    if lock.get("confirmed_result_sha256") != _sha256(confirmed / "result.json"):
        raise EvidenceError("physical proof lock result hash mismatch")
    if lock.get("source_result_sha256") != _sha256(source / "result.json"):
        raise EvidenceError("physical proof lock source hash mismatch")
    if lock.get("row_count") != 30:
        raise EvidenceError("physical proof lock canonical row count is invalid")
    return {"lock": lock, "confirmed": checked}


def verify_recovery_lock(path: Path) -> dict[str, Any]:
    lock = _validate_json_object(Path(path), "recovery-proof-lock")
    if lock.get("kind") != "recovery-proof-lock" or lock.get("status") != "pass":
        raise EvidenceError("recovery proof lock is incomplete or ineligible")
    from .serial_link import RECOVERY_ACTIONS, validate_recovery_action_event
    actions = lock.get("actions")
    if not isinstance(actions, list) or len(actions) != len(RECOVERY_ACTIONS):
        raise EvidenceError("recovery proof lock must contain every required action exactly once")
    seen: set[str] = set()
    for event in actions:
        action = event.get("action") if isinstance(event, dict) else None
        if action in seen or action not in RECOVERY_ACTIONS:
            raise EvidenceError("recovery proof lock action set is not canonical")
        try:
            validate_recovery_action_event(event, action)
        except Exception as exc:
            raise EvidenceError(str(exc)) from exc
        seen.add(action)
    if seen != set(RECOVERY_ACTIONS):
        raise EvidenceError("recovery proof lock action matrix is incomplete")
    return lock
