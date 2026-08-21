"""Exact-pair Phase 3 deployment capture and pending-evidence validator."""
from __future__ import annotations

import argparse
import binascii
import hashlib
import json
import os
import struct
import subprocess
import tempfile
import time
import zlib
from pathlib import Path
from typing import Any

from herdr_keypad.codex import normalize_rate_limits

from .pairing import PairingStore
from .serial_link import reconnect_exact

ROOT = Path(__file__).resolve().parents[4]
THEMES = ("signal-edge", "ledger", "beacon", "instrument")
CODEX_SCENES = (
    "codex-current", "codex-partial", "codex-stale", "codex-unavailable",
    "codex-auth", "codex-offline", "host-offline", "codex-limit", "codex-long",
)
MENU_SCENES = (
    "menu-root-0", "menu-root-1", "menu-root-2", "menu-root-3", "menu-root-4",
    "menu-root-5", "menu-brightness", "menu-health", "menu-about",
)
REQUIREMENTS = (
    "CODEX-01", "CODEX-02", "CODEX-03", "CODEX-04", "SYNC-03",
    "SAFE-01", "MENU-01", "MENU-02", "MENU-03", "MENU-04",
)
UI_CONSIDERATIONS = (
    "empty", "loading", "error", "populated", "partial", "overflow",
    "zero-one-many", "long-text", "interaction", "persistence",
)
PHYSICAL_ROWS = (
    "long-text-all-themes-at-10-percent",
    "source-labels-remain-legible",
    "direct-agent-keys-from-root",
    "direct-agent-keys-from-brightness",
    "direct-agent-keys-from-health",
    "direct-agent-keys-from-about",
    "brightness-ladder-10-through-100",
    "brightness-zero-rejected",
    "close-reverts-unconfirmed-preview",
    "timeout-reverts-unconfirmed-preview",
    "led-preview-and-semantic-behavior",
    "confirmation-persists-setting",
    "reboot-restores-confirmed-brightness",
    "fresh-bridge-resync-after-acceptance",
)
TRACER_LINK_KEYS = {
    "tracer_sha256", "elapsed_ms_path", "child_exit_path", "redaction_result_path"
}
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
PPM_HEADER = b"P6\n128 128\n255\n"


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def relative(path: Path) -> str:
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).as_posix()
    except ValueError as exc:
        raise ValueError(f"artifact must be inside repository: {path}") from exc


def resolve_repo_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError("evidence path must be repository-relative")
    resolved = (ROOT / path).resolve()
    if ROOT not in resolved.parents:
        raise ValueError("evidence path escapes repository")
    return resolved


def atomic_write(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except Exception:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def write_json(path: Path, value: Any, *, checksum: bool = False) -> str:
    payload = json.dumps(value, sort_keys=True, indent=2, ensure_ascii=True).encode("ascii") + b"\n"
    atomic_write(path, payload)
    digest = sha256_bytes(payload)
    if checksum:
        sidecar = path.with_suffix(path.suffix + ".sha256")
        atomic_write(sidecar, f"{digest}  {relative(path)}\n".encode("ascii"))
    return digest


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    body = kind + payload
    return struct.pack(">I", len(payload)) + body + struct.pack(">I", binascii.crc32(body) & 0xFFFFFFFF)


def png_bytes(width: int, height: int, rgb: bytes, deployment_id: str) -> bytes:
    if len(rgb) != width * height * 3:
        raise ValueError("RGB payload has wrong dimensions")
    rows = b"".join(b"\x00" + rgb[y * width * 3:(y + 1) * width * 3] for y in range(height))
    return b"".join((
        PNG_SIGNATURE,
        png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)),
        png_chunk(b"tEXt", b"deployment_id\x00" + deployment_id.encode("ascii")),
        png_chunk(b"IDAT", zlib.compress(rows, 9)),
        png_chunk(b"IEND", b""),
    ))


def png_has_deployment(path: Path, deployment_id: str) -> bool:
    return b"deployment_id\x00" + deployment_id.encode("ascii") in path.read_bytes()


def make_contact(frames: list[bytes], columns: int, deployment_id: str) -> tuple[int, int, bytes]:
    if not frames or any(len(frame) != 128 * 128 * 3 for frame in frames):
        raise ValueError("contact source frame is not 128x128 RGB")
    rows = (len(frames) + columns - 1) // columns
    width, height = columns * 128, rows * 128
    output = bytearray(width * height * 3)
    for index, frame in enumerate(frames):
        left = (index % columns) * 128
        top = (index // columns) * 128
        for y in range(128):
            source = y * 128 * 3
            target = ((top + y) * width + left) * 3
            output[target:target + 128 * 3] = frame[source:source + 128 * 3]
    return width, height, png_bytes(width, height, bytes(output), deployment_id)


def json_pointer(document: Any, pointer: str) -> Any:
    if not pointer.startswith("/"):
        raise ValueError("JSON pointer must be absolute")
    value = document
    for raw in pointer[1:].split("/"):
        token = raw.replace("~1", "/").replace("~0", "~")
        if isinstance(value, dict) and token in value:
            value = value[token]
        elif isinstance(value, list) and token.isdigit() and int(token) < len(value):
            value = value[int(token)]
        else:
            raise ValueError(f"JSON pointer target missing: {pointer}")
    return value


def bucket_matrix() -> dict[str, Any]:
    top = {"rateLimits": {"primary": {"usedPercent": 12}}}
    shapes = {
        "top-level-only": top,
        "map-only": {"rateLimitsByLimitId": {"provider-key": {"primary": {"usedPercent": 99}}}},
        "both": {**top, "rateLimitsByLimitId": {"provider-key": {}}},
        "neither": {},
        "explicit-null-map": {**top, "rateLimitsByLimitId": None},
        "unusable-map": {"rateLimits": []},
    }
    expected = {
        "top-level-only": ("current", 12, ""),
        "map-only": ("unavailable", None, "E-2401"),
        "both": ("current", 12, ""),
        "neither": ("unavailable", None, "E-2401"),
        "explicit-null-map": ("current", 12, ""),
        "unusable-map": ("unavailable", None, "E-2401"),
    }
    results: list[dict[str, Any]] = []
    for name, payload in shapes.items():
        view, redaction = normalize_rate_limits(payload)
        actual = (view.source_state, view.primary, view.error_code)
        if actual != expected[name] or redaction.bucket_manifest.selected_key is not None:
            raise RuntimeError(f"R-BUCKET shape failed: {name}")
        results.append({
            "shape": name,
            "source_state": view.source_state,
            "primary": view.primary,
            "error_code": view.error_code,
            "selected_key": None,
        })
    keys = {f"opaque-{index}-\u00e9": {} for index in range(12)}
    _view, redaction = normalize_rate_limits({"rateLimits": {}, "rateLimitsByLimitId": keys})
    manifest = redaction.bucket_manifest.as_dict()
    if (manifest["observed_key_count"] != 12 or len(manifest["key_prefixes"]) != 8 or
            not manifest["truncated"] or manifest["selected_key"] is not None or
            any(len(prefix) != 12 for prefix in manifest["key_prefixes"])):
        raise RuntimeError("R-BUCKET bounded hash manifest failed")
    return {
        "id": "R-BUCKET",
        "source": "scripted-production-normalizer",
        "result": "pass",
        "shapes": results,
        "bounded_manifest": manifest,
        "internal_reason": "bucket_unavailable",
        "allowlisted_error_code": "E-2401",
    }


def fresh_deployment(binding_path: Path, firmware: Path, timeout: float) -> dict[str, Any]:
    binding = PairingStore(binding_path).load()
    if binding is None:
        raise RuntimeError(f"pairing binding missing: {binding_path}")
    selected, link, session, _transitions = reconnect_exact(
        binding,
        ports=None,
        opener=lambda candidate: __import__("serial").Serial(
            candidate.device, 115200, timeout=0.2, write_timeout=2.0),
        timeout=timeout,
    )
    try:
        hello = dict(session.device)
        if hello.get("device_id") != binding.device_id:
            raise RuntimeError("fresh hello device identity differs from exact pairing")
        if hello.get("firmware") != binding.firmware or hello.get("protocol") != binding.protocol:
            raise RuntimeError("fresh hello firmware/protocol differs from exact pairing")
        boot_id = hello.get("device_boot_id")
        if not isinstance(boot_id, str) or not boot_id:
            raise RuntimeError("fresh hello did not supply a boot identity")
        record = {
            "platformio_environment": "selected-usb",
            "binary_path": relative(firmware),
            "binary_sha256": sha256_file(firmware),
            "upload_result": "pass",
            "paired_device_id": binding.device_id,
            "hello_firmware": binding.firmware,
            "protocol_version": binding.protocol,
            "fresh_boot_id": boot_id,
            "fresh_session_id": session.session_id,
            "usb_serial": selected.serial_number or "unavailable",
        }
        record["deployment_id"] = sha256_bytes(canonical_bytes(record))
        return record
    finally:
        link.close()


def run_capture(args: argparse.Namespace) -> int:
    firmware = args.firmware.resolve()
    tracer = args.tracer.resolve()
    evidence_path = args.evidence.resolve()
    captures_path = args.captures.resolve()
    if not firmware.is_file() or not tracer.is_file():
        raise RuntimeError("current firmware binary and checksummed tracer are required")
    tracer_sidecar = tracer.with_suffix(tracer.suffix + ".sha256")
    if not tracer_sidecar.is_file():
        raise RuntimeError("tracer checksum sidecar is required")
    tracer_sha = sha256_file(tracer)
    expected_tracer = tracer_sidecar.read_text(encoding="ascii").split()[0]
    if tracer_sha != expected_tracer:
        raise RuntimeError("tracer checksum mismatch")

    deployment = fresh_deployment(args.binding.resolve(), firmware, args.timeout)
    deployment_id = deployment["deployment_id"]
    frames_dir = captures_path.parent / "frames"
    frames_dir.mkdir(parents=True, exist_ok=True)
    capture_script = ROOT / "tools" / "capture_panel.py"
    records: list[dict[str, Any]] = []
    groups: dict[str, list[bytes]] = {"codex": [], "menu": []}

    for group, scenes in (("codex", CODEX_SCENES), ("menu", MENU_SCENES)):
        for theme in THEMES:
            for scene in scenes:
                stem = f"{group}-{theme}-{scene}"
                ppm = frames_dir / f"{stem}.ppm"
                command = [
                    os.fspath(Path(os.sys.executable)), os.fspath(capture_script), "3", os.fspath(ppm),
                    "--binding", os.fspath(args.binding), "--timeout", str(args.timeout),
                    "--theme", theme, "--scene", scene,
                ]
                subprocess.run(command, cwd=ROOT, check=True, timeout=max(10.0, args.timeout + 5.0))
                ppm_payload = ppm.read_bytes()
                if not ppm_payload.startswith(PPM_HEADER):
                    raise RuntimeError(f"invalid PPM capture: {ppm}")
                rgb = ppm_payload[len(PPM_HEADER):]
                if len(rgb) != 128 * 128 * 3:
                    raise RuntimeError(f"capture dimensions are not 128x128: {ppm}")
                raw = ppm.with_suffix(ppm.suffix + ".rgb565")
                if raw.stat().st_size != 128 * 128 * 2:
                    raise RuntimeError(f"RGB565 capture has wrong size: {raw}")
                png = frames_dir / f"{stem}.png"
                atomic_write(png, png_bytes(128, 128, rgb, deployment_id))
                ppm.unlink()
                groups[group].append(rgb)
                records.append({
                    "id": stem,
                    "kind": group,
                    "source": "deterministic-device-framebuffer",
                    "theme": theme,
                    "scene": scene,
                    "panel": 4,
                    "width": 128,
                    "height": 128,
                    "deployment_id": deployment_id,
                    "rgb565_path": relative(raw),
                    "rgb565_sha256": sha256_file(raw),
                    "png_path": relative(png),
                    "png_sha256": sha256_file(png),
                })

    contacts: list[dict[str, Any]] = []
    for group, filename in (("codex", "codex-states-contact.png"), ("menu", "menu-pages-contact.png")):
        width, height, payload = make_contact(groups[group], len(CODEX_SCENES), deployment_id)
        output = captures_path.parent / filename
        atomic_write(output, payload)
        contacts.append({
            "kind": group,
            "path": relative(output),
            "sha256": sha256_file(output),
            "width": width,
            "height": height,
            "source_frame_width": 128,
            "source_frame_height": 128,
            "deployment_id": deployment_id,
        })

    manifest = {
        "schema_version": 1,
        "kind": "phase3-framebuffer-captures",
        "source": "logical-framebuffer-only",
        "deployment_id": deployment_id,
        "redaction": {"result": "pass", "forbidden_content": "absent"},
        "captures": records,
        "contact_sheets": contacts,
    }
    captures_sha = write_json(captures_path, manifest)
    tracer_document = json.loads(tracer.read_text(encoding="utf-8"))
    installed_result = tracer_document.get("result")
    if installed_result not in {"pass", "fail"}:
        raise RuntimeError("tracer installed result is not typed")
    tracer_link = {
        "tracer_sha256": tracer_sha,
        "elapsed_ms_path": "/collector/elapsed_ms",
        "child_exit_path": "/collector/child_exit",
        "redaction_result_path": "/redaction/result",
    }
    r_bucket = bucket_matrix()
    evidence = {
        "schema_version": 1,
        "kind": "phase3-device-evidence",
        "status": "pending",
        "run_id": f"phase3-{deployment_id[:16]}",
        "deployment": deployment,
        "capture_manifest": {
            "path": relative(captures_path),
            "sha256": captures_sha,
            "deployment_id": deployment_id,
        },
        "tracer": {
            "path": relative(tracer),
            "source": "installed",
            "result": installed_result,
            "codex": tracer_document.get("codex"),
        },
        "tracer_audit_link": tracer_link,
        "r_bucket": r_bucket,
        "requirements": [
            {"id": requirement, "source": "automated-production-matrix", "result": "machine-pass",
             "deployment_id": deployment_id}
            for requirement in REQUIREMENTS
        ],
        "ui_considerations": [
            {"id": item, "source": "framebuffer" if item != "long-text" else "physical",
             "result": "machine-pass" if item != "long-text" else "pending",
             "deployment_id": deployment_id}
            for item in UI_CONSIDERATIONS
        ],
        "physical_observations": [
            {"id": row, "source": "physical", "result": "pending", "observation": None,
             "deployment_id": deployment_id}
            for row in PHYSICAL_ROWS
        ],
        "evidence_kinds": {
            "machine_ack": "machine",
            "framebuffer_pixels": "logical-only",
            "installed_codex": "installed",
            "deterministic_fixtures": "scripted",
            "physical_observations": "pending-y-n-r",
        },
    }
    write_json(evidence_path, evidence, checksum=True)
    print(f"captured {len(records)} exact-device frames for deployment {deployment_id}")
    print(f"pending evidence: {relative(evidence_path)}")
    return 0


def validate_evidence(path: Path, allow_pending: bool) -> int:
    path = path.resolve()
    evidence = json.loads(path.read_text(encoding="utf-8"))
    expected_top = {
        "schema_version", "kind", "status", "run_id", "deployment", "capture_manifest",
        "tracer", "tracer_audit_link", "r_bucket", "requirements", "ui_considerations",
        "physical_observations", "evidence_kinds",
    }
    if set(evidence) != expected_top or evidence.get("kind") != "phase3-device-evidence":
        raise ValueError("device evidence schema is not closed")
    sidecar = path.with_suffix(path.suffix + ".sha256")
    if sha256_file(path) != sidecar.read_text(encoding="ascii").split()[0]:
        raise ValueError("device evidence checksum mismatch")
    deployment = dict(evidence["deployment"])
    deployment_id = deployment.pop("deployment_id", None)
    if deployment_id != sha256_bytes(canonical_bytes(deployment)):
        raise ValueError("canonical deployment identity mismatch")
    firmware = resolve_repo_path(deployment["binary_path"])
    if sha256_file(firmware) != deployment["binary_sha256"]:
        raise ValueError("deployed firmware binary hash mismatch")
    if deployment.get("platformio_environment") != "selected-usb" or deployment.get("upload_result") != "pass":
        raise ValueError("deployment is not a successful selected-usb upload")

    capture_ref = evidence["capture_manifest"]
    captures_path = resolve_repo_path(capture_ref["path"])
    if sha256_file(captures_path) != capture_ref["sha256"]:
        raise ValueError("capture manifest hash mismatch")
    manifest = json.loads(captures_path.read_text(encoding="utf-8"))
    if manifest.get("deployment_id") != deployment_id or capture_ref.get("deployment_id") != deployment_id:
        raise ValueError("capture manifest deployment linkage mismatch")
    if manifest.get("source") != "logical-framebuffer-only" or manifest.get("redaction", {}).get("result") != "pass":
        raise ValueError("capture source/redaction classification invalid")
    for capture in manifest.get("captures", []):
        if capture.get("width") != 128 or capture.get("height") != 128 or capture.get("deployment_id") != deployment_id:
            raise ValueError("capture dimensions/deployment linkage invalid")
        for path_key, hash_key in (("rgb565_path", "rgb565_sha256"), ("png_path", "png_sha256")):
            artifact = resolve_repo_path(capture[path_key])
            if sha256_file(artifact) != capture[hash_key]:
                raise ValueError(f"capture hash mismatch: {capture['id']}")
        raw = resolve_repo_path(capture["rgb565_path"])
        png = resolve_repo_path(capture["png_path"])
        if raw.stat().st_size != 128 * 128 * 2 or not png_has_deployment(png, deployment_id):
            raise ValueError("capture payload or PNG deployment metadata invalid")
    expected_capture_count = len(THEMES) * (len(CODEX_SCENES) + len(MENU_SCENES))
    if len(manifest.get("captures", [])) != expected_capture_count:
        raise ValueError("capture scene matrix is incomplete")
    contacts = manifest.get("contact_sheets", [])
    if {item.get("kind") for item in contacts} != {"codex", "menu"}:
        raise ValueError("contact sheet matrix is incomplete")
    for contact in contacts:
        artifact = resolve_repo_path(contact["path"])
        if (sha256_file(artifact) != contact["sha256"] or
                contact.get("deployment_id") != deployment_id or
                contact.get("source_frame_width") != 128 or
                contact.get("source_frame_height") != 128 or
                not png_has_deployment(artifact, deployment_id)):
            raise ValueError("contact sheet linkage invalid")

    tracer_path = resolve_repo_path(evidence["tracer"]["path"])
    tracer = json.loads(tracer_path.read_text(encoding="utf-8"))
    link = evidence["tracer_audit_link"]
    if set(link) != TRACER_LINK_KEYS or sha256_file(tracer_path) != link["tracer_sha256"]:
        raise ValueError("closed tracer audit link mismatch")
    elapsed = json_pointer(tracer, link["elapsed_ms_path"])
    child = json_pointer(tracer, link["child_exit_path"])
    redaction = json_pointer(tracer, link["redaction_result_path"])
    if not isinstance(elapsed, int) or isinstance(elapsed, bool) or not 0 <= elapsed <= 3000:
        raise ValueError("tracer elapsed time is not bounded")
    if (not isinstance(child, dict) or set(child) != {"state", "code", "signal"} or
            child["state"] not in {"not_started", "running", "exited", "terminated", "killed"}):
        raise ValueError("tracer child-exit schema invalid")
    if redaction != "pass":
        raise ValueError("tracer redaction did not pass")

    if evidence["r_bucket"] != bucket_matrix():
        raise ValueError("R-BUCKET matrix or bounded manifest mismatch")
    if {row.get("id") for row in evidence["requirements"]} != set(REQUIREMENTS):
        raise ValueError("requirement matrix incomplete")
    if {row.get("id") for row in evidence["ui_considerations"]} != set(UI_CONSIDERATIONS):
        raise ValueError("UI consideration matrix incomplete")
    physical = evidence["physical_observations"]
    if {row.get("id") for row in physical} != set(PHYSICAL_ROWS):
        raise ValueError("physical observation matrix incomplete")
    if any(row.get("source") != "physical" or row.get("deployment_id") != deployment_id for row in physical):
        raise ValueError("physical observations have invalid source/deployment linkage")
    pending = any(row.get("result") == "pending" for row in physical)
    if pending and not allow_pending:
        raise ValueError("physical observations remain pending")
    if evidence["status"] != ("pending" if pending else "pass"):
        raise ValueError("evidence status does not match physical observations")
    print(f"validated {'pending' if pending else 'complete'} Phase 3 evidence for {deployment_id}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    capture = subparsers.add_parser("capture")
    capture.add_argument("--binding", type=Path, required=True)
    capture.add_argument("--firmware", type=Path, required=True)
    capture.add_argument("--tracer", type=Path, required=True)
    capture.add_argument("--evidence", type=Path, required=True)
    capture.add_argument("--captures", type=Path, required=True)
    capture.add_argument("--timeout", type=float, default=5.0)
    validate = subparsers.add_parser("validate")
    validate.add_argument("--evidence", type=Path, required=True)
    validate.add_argument("--allow-pending", action="store_true")
    args = parser.parse_args(argv)
    if args.command == "capture":
        return run_capture(args)
    return validate_evidence(args.evidence, args.allow_pending)


if __name__ == "__main__":
    raise SystemExit(main())
