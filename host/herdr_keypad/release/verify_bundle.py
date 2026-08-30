#!/usr/bin/env python3
"""Verify unsigned Herdr keypad release bundles and the native release workflow.

This module intentionally uses only the Python standard library.  Python is a CI
verification tool, never a runtime dependency of the plugin archive.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import stat
import struct
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any, Iterable


TARGETS: dict[str, dict[str, str]] = {
    "x86_64-unknown-linux-gnu": {"os": "linux", "arch": "x86_64"},
    "aarch64-apple-darwin": {"os": "macos", "arch": "arm64"},
}
ALLOWED_FILES = {
    "herdr-plugin.toml",
    "LIFECYCLE.md",
    "bin/herdr-keypad",
    "release-manifest.json",
}
SAFE_HASH = re.compile(r"^[0-9a-f]{64}$")
SAFE_REVISION = re.compile(r"^[0-9a-f]{40,64}$")
SAFE_VERSION = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
FORBIDDEN_ARCHIVE_PATH = re.compile(
    r"(?:python|node(?:js)?|java|jvm|rustup|cargo|pip|npm|yarn|venv|virtualenv|"
    r"source|fixture|evidence|credential|secret|\.git|__pycache__)", re.I
)
FORBIDDEN_BINARY_TEXT = (
    re.compile(r"\bpython(?:[0-9]+(?:\.[0-9]+)?)?\b", re.I),
    re.compile(r"(?:^|[/\\])node(?:js)?(?:\.exe)?(?:$|[ \t])|\bnode_modules\b|\bNODE_PATH\b", re.I),
    re.compile(r"\b(?:java|jvm|rustup|cargo|pip|npm|yarn)\b", re.I),
    re.compile(r"(?:virtualenv|\.venv|/venv(?:/|$))", re.I),
    re.compile(r"/(?:home|Users|tmp)/", re.I),
    re.compile(r"\b(?:bash|zsh|fish)\b", re.I),
    re.compile(r"BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY", re.I),
    re.compile(r"\bsk-[A-Za-z0-9_-]{8,}"),
    re.compile(r"(?:api[_-]?key|access[_-]?token|password|credential|secret)", re.I),
    re.compile(r"(?:transcript|prompt|raw upstream|diagnostic payload)", re.I),
)
FORBIDDEN_METADATA_TEXT = (
    re.compile(r"/(?:home|Users|tmp|proc|sys)/", re.I),
    re.compile(r"(?:BEGIN (?:OPENSSH|RSA|EC|DSA) PRIVATE KEY|sk-[A-Za-z0-9_-]{8,})", re.I),
    re.compile(r"(?:account[_-]?id|transcript|prompt|raw upstream|diagnostic payload)", re.I),
)


class VerificationError(Exception):
    """A safe, user-actionable verification failure."""


def fail(message: str) -> None:
    raise VerificationError(message)


def _expect_keys(value: Any, required: Iterable[str], where: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        fail(f"schema: {where} must be an object")
    required_set = set(required)
    actual = set(value)
    missing = sorted(required_set - actual)
    extra = sorted(actual - required_set)
    if missing:
        fail(f"schema: {where} missing required field(s): {', '.join(missing)}")
    if extra:
        fail(f"schema: {where} has unknown field(s): {', '.join(extra)}")
    return value


def _string(value: Any, where: str, *, minimum: int = 1, maximum: int = 1024) -> str:
    if not isinstance(value, str) or not (minimum <= len(value) <= maximum):
        fail(f"schema: {where} must be a string of length {minimum}..{maximum}")
    if any(ord(char) < 0x20 and char not in "\n\t" for char in value):
        fail(f"schema: {where} contains unsafe control characters")
    return value


def _hash(value: Any, where: str) -> str:
    text = _string(value, where, minimum=64, maximum=64)
    if not SAFE_HASH.fullmatch(text):
        fail(f"schema: {where} must be a lowercase SHA-256 hex digest")
    return text


def _schema_contract(schema_path: Path) -> None:
    try:
        schema = json.loads(schema_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        fail(f"schema: cannot read manifest schema: {exc}")
    if schema.get("$schema") != "https://json-schema.org/draft/2020-12/schema":
        fail("schema: manifest schema must use JSON Schema draft 2020-12")
    if schema.get("type") != "object" or schema.get("additionalProperties") is not False:
        fail("schema: top-level manifest schema must be closed")
    required = set(schema.get("required", []))
    expected = {
        "schema_version",
        "plugin",
        "bridge",
        "target",
        "compiler",
        "source",
        "cargo_lock",
        "lifecycle",
        "binary",
        "reproducibility",
        "dependencies",
        "tests",
        "signing",
        "notarization",
    }
    if required != expected:
        fail("schema: manifest required-field contract is incomplete")


def _validate_manifest(manifest: Any, schema_path: Path) -> dict[str, Any]:
    _schema_contract(schema_path)
    root = _expect_keys(
        manifest,
        {
            "schema_version",
            "plugin",
            "bridge",
            "target",
            "compiler",
            "source",
            "cargo_lock",
            "lifecycle",
            "binary",
            "reproducibility",
            "dependencies",
            "tests",
            "signing",
            "notarization",
        },
        "manifest",
    )
    if root["schema_version"] != 1 or isinstance(root["schema_version"], bool):
        fail("schema: schema_version must be 1")

    plugin = _expect_keys(root["plugin"], {"id", "version"}, "plugin")
    if plugin["id"] != "herdr-keypad":
        fail("schema: plugin.id must be herdr-keypad")
    plugin_version = _string(plugin["version"], "plugin.version", maximum=32)
    if not SAFE_VERSION.fullmatch(plugin_version):
        fail("schema: plugin.version must be a semantic release version")

    bridge = _expect_keys(root["bridge"], {"version"}, "bridge")
    bridge_version = _string(bridge["version"], "bridge.version", maximum=32)
    if bridge_version != plugin_version or not SAFE_VERSION.fullmatch(bridge_version):
        fail("schema: bridge.version must match plugin.version")

    target = _expect_keys(root["target"], {"triple", "os", "arch"}, "target")
    target_triple = _string(target["triple"], "target.triple", maximum=64)
    if target_triple not in TARGETS:
        fail("target: unsupported target triple")
    expected_platform = TARGETS[target_triple]
    if target.get("os") != expected_platform["os"] or target.get("arch") != expected_platform["arch"]:
        fail("target: target triple and platform metadata disagree")

    compiler = _expect_keys(compiler := root["compiler"], {"toolchain", "rustc", "cargo"}, "compiler")
    for name in ("toolchain", "rustc", "cargo"):
        _string(compiler[name], f"compiler.{name}", maximum=256)

    source = _expect_keys(root["source"], {"revision", "archives"}, "source")
    revision = _string(source["revision"], "source.revision", minimum=40, maximum=64)
    if not SAFE_REVISION.fullmatch(revision):
        fail("source: revision must be a lowercase commit hash")
    archives = source["archives"]
    if not isinstance(archives, list) or len(archives) != 2:
        fail("source.archives must contain exactly two provenance records")
    roots: set[str] = set()
    for index, record in enumerate(archives):
        item = _expect_keys(record, {"root", "sha256"}, f"source.archives[{index}]")
        root_name = _string(item["root"], f"source.archives[{index}].root", maximum=32)
        if root_name in roots or root_name not in {"source-a", "source-b"}:
            fail("source.archives must contain distinct source-a and source-b records")
        roots.add(root_name)
        _hash(item["sha256"], f"source.archives[{index}].sha256")
    if roots != {"source-a", "source-b"}:
        fail("source.archives must retain both source-a and source-b provenance records")

    cargo_lock = _expect_keys(root["cargo_lock"], {"sha256"}, "cargo_lock")
    _hash(cargo_lock["sha256"], "cargo_lock.sha256")

    lifecycle = _expect_keys(root["lifecycle"], {"path", "sha256"}, "lifecycle")
    if lifecycle["path"] != "LIFECYCLE.md":
        fail("lifecycle.path must be LIFECYCLE.md")
    _hash(lifecycle["sha256"], "lifecycle.sha256")

    binary = _expect_keys(root["binary"], {"path", "sha256", "size"}, "binary")
    if binary["path"] != "bin/herdr-keypad":
        fail("binary.path must resolve to bin/herdr-keypad")
    _hash(binary["sha256"], "binary.sha256")
    if isinstance(binary["size"], bool) or not isinstance(binary["size"], int) or binary["size"] < 1:
        fail("schema: binary.size must be a positive integer")

    reproducibility = _expect_keys(
        root["reproducibility"], {"status", "hash_a", "hash_b", "equal"}, "reproducibility"
    )
    if reproducibility["status"] != "passed" or reproducibility["equal"] is not True:
        fail("reproducibility: unsigned comparison must be passed and equal")
    _hash(reproducibility["hash_a"], "reproducibility.hash_a")
    _hash(reproducibility["hash_b"], "reproducibility.hash_b")
    if reproducibility["hash_a"] != reproducibility["hash_b"]:
        fail("reproducibility: compared unsigned hashes differ")
    if reproducibility["hash_a"] != binary["sha256"]:
        fail("reproducibility: compared hash does not match packaged binary")

    dependencies = _expect_keys(root["dependencies"], {"tool", "status", "libraries"}, "dependencies")
    if dependencies["tool"] not in {"ldd", "otool -L"} or dependencies["status"] != "passed":
        fail("dependencies: target-native inspection must be passed")
    if not isinstance(dependencies["libraries"], list):
        fail("schema: dependencies.libraries must be an array")
    for index, library in enumerate(dependencies["libraries"]):
        _string(library, f"dependencies.libraries[{index}]", maximum=256)

    tests = _expect_keys(root["tests"], {"status", "command"}, "tests")
    if tests["status"] != "passed":
        fail("tests: target-native tests must be passed")
    test_command = _string(tests["command"], "tests.command", maximum=512)
    if not test_command.startswith("cargo test"):
        fail("tests.command must identify the locked Cargo test command")

    for name in ("signing", "notarization"):
        status = _expect_keys(root[name], {"status", "reason"}, name)
        if status["status"] != "not-run":
            fail(f"{name}: unsigned bundle cannot claim an operation passed")
        reason = _string(status["reason"], f"{name}.reason", maximum=256)
        if not reason:
            fail(f"{name}: a reason is required when operation is not-run")

    metadata = json.dumps(root, sort_keys=True)
    for pattern in FORBIDDEN_METADATA_TEXT:
        if pattern.search(metadata):
            fail("metadata: manifest contains unsafe path, credential, or evidence text")
    return root


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as exc:
        fail(f"hash: cannot read {path.name}: {exc}")
    return digest.hexdigest()


def _safe_archive_name(name: str) -> str:
    if "\x00" in name:
        fail("archive: NUL byte in member path")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        fail(f"archive: unsafe member path {name!r}")
    normalized = "/".join(path.parts)
    if FORBIDDEN_ARCHIVE_PATH.search(normalized):
        fail(f"forbidden archive path: {normalized}")
    return normalized


def _archive_prefix(names: list[str]) -> str:
    if not names:
        fail("archive: package is empty")
    first_parts = {name.split("/", 1)[0] for name in names}
    if len(first_parts) == 1 and next(iter(first_parts)) not in {"bin", "herdr-plugin.toml", "LIFECYCLE.md", "release-manifest.json"}:
        return next(iter(first_parts)) + "/"
    return ""


def _materialize_archive(archive: Path, destination: Path) -> Path:
    member_names: list[str] = []
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as package:
            for info in package.infolist():
                if info.is_dir():
                    continue
                member_names.append(_safe_archive_name(info.filename))
            prefix = _archive_prefix(member_names)
            for info in package.infolist():
                if info.is_dir():
                    continue
                normalized = _safe_archive_name(info.filename)
                relative = normalized[len(prefix) :] if prefix and normalized.startswith(prefix) else normalized
                if not relative:
                    continue
                target = destination.joinpath(*relative.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                with package.open(info) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                mode = (info.external_attr >> 16) & 0o777
                if mode:
                    target.chmod(mode)
    else:
        try:
            is_tar = tarfile.is_tarfile(archive)
        except OSError as exc:
            fail(f"archive: cannot inspect package: {exc}")
        if not is_tar:
            fail("archive: expected a directory, ZIP, TAR, or compressed TAR bundle")
        with tarfile.open(archive, "r:*") as package:
            members = package.getmembers()
            for member in members:
                if member.isdir():
                    continue
                if not member.isfile():
                    fail(f"archive: symlink or special member is forbidden: {member.name}")
                member_names.append(_safe_archive_name(member.name))
            prefix = _archive_prefix(member_names)
            for member in members:
                if member.isdir():
                    continue
                normalized = _safe_archive_name(member.name)
                relative = normalized[len(prefix) :] if prefix and normalized.startswith(prefix) else normalized
                if not relative:
                    continue
                target = destination.joinpath(*relative.split("/"))
                target.parent.mkdir(parents=True, exist_ok=True)
                source = package.extractfile(member)
                if source is None:
                    fail(f"archive: cannot read member {member.name}")
                with source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)
                target.chmod(member.mode & 0o777)
    return destination


def _materialize(bundle: Path) -> tuple[Path, tempfile.TemporaryDirectory[str] | None]:
    if bundle.is_dir():
        return bundle, None
    if not bundle.is_file():
        fail(f"bundle: path does not exist: {bundle}")
    temporary = tempfile.TemporaryDirectory(prefix="herdr-keypad-bundle-")
    try:
        return _materialize_archive(bundle, Path(temporary.name)), temporary
    except Exception:
        temporary.cleanup()
        raise


def _files(root: Path) -> list[str]:
    found: list[str] = []
    for current, directories, names in os.walk(root, followlinks=False):
        current_path = Path(current)
        for directory in directories:
            path = current_path / directory
            if path.is_symlink():
                fail(f"forbidden bundle entry: symlink {path.relative_to(root)}")
        for name in names:
            path = current_path / name
            relative = path.relative_to(root).as_posix()
            if path.is_symlink() or not path.is_file():
                fail(f"forbidden bundle entry: non-regular file {relative}")
            found.append(relative)
    return sorted(found)


def _read_json(path: Path, label: str) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        fail(f"{label}: invalid JSON: {exc}")


def _validate_plugin_manifest(path: Path) -> dict[str, Any]:
    try:
        manifest = tomllib.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, tomllib.TOMLDecodeError) as exc:
        fail(f"argv: invalid herdr-plugin.toml: {exc}")
    if manifest.get("id") != "herdr-keypad":
        fail("argv: plugin id must be herdr-keypad")
    if not SAFE_VERSION.fullmatch(str(manifest.get("version", ""))):
        fail("argv: plugin version is unsafe")
    if manifest.get("platforms") != ["linux", "macos"]:
        fail("argv: plugin platforms must be exactly linux and macos")
    startup = manifest.get("startup")
    if not isinstance(startup, list) or len(startup) != 1:
        fail("argv: exactly one startup command is required")
    _validate_command(startup[0], "startup", "startup")
    actions = manifest.get("actions")
    if not isinstance(actions, list):
        fail("argv: actions must be an array")
    expected_actions = {"start", "stop", "restart", "status", "repair", "re-pair"}
    actual_actions: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            fail("argv: action entry must be an object")
        action_id = action.get("id")
        if not isinstance(action_id, str) or action_id in actual_actions or action_id not in expected_actions:
            fail("argv: action surface is not the closed native action set")
        actual_actions.add(action_id)
        _validate_command(action, action_id, action_id)
        if action_id == "status" and action.get("contexts") != ["global"]:
            fail("argv: status must remain a global read-only action")
    if actual_actions != expected_actions:
        fail("argv: action surface is incomplete")
    if "events" in manifest:
        fail("argv: event/watchdog metadata is not allowed")
    return manifest


def _validate_command(entry: Any, name: str, expected_arg: str) -> None:
    if not isinstance(entry, dict):
        fail(f"argv: {name} entry must be an object")
    command = entry.get("command")
    if not isinstance(command, list) or command != ["bin/herdr-keypad", expected_arg]:
        fail(f"argv: {name} must directly invoke the bundled bin/herdr-keypad {expected_arg} command")
    if any(not isinstance(part, str) or "\\" in part or ".." in part or "\x00" in part for part in command):
        fail(f"argv: {name} contains unsafe argument text")


def _lifecycle_section(document: str, heading: str) -> str:
    start = document.find(heading)
    if start < 0:
        fail(f"lifecycle: missing required heading {heading!r}")
    body = document[start + len(heading) :]
    end = body.find("\n## ")
    return body if end < 0 else body[:end]


def _numbered_steps(body: str) -> list[str]:
    steps: list[str] = []
    for line in body.splitlines():
        match = re.match(r"^\s*[0-9]+\.\s+(.*)$", line)
        if match:
            steps.append(match.group(1))
    return steps


def _ordered(document: str, terms: Iterable[str], label: str) -> None:
    previous = 0
    for term in terms:
        position = document.find(term)
        if position < 0:
            fail(f"lifecycle: {label} omits {term!r}")
        if position < previous:
            fail(f"lifecycle: {label} is out of order at {term!r}")
        previous = position


def _validate_lifecycle(path: Path) -> str:
    try:
        document = path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(f"lifecycle: cannot read document: {exc}")
    headings = [
        "## Supported targets and package",
        "## Install with Herdr",
        "## Start, status, stop, and restart",
        "## Disable",
        "## Unlink",
        "## Remove",
        "## Update activation",
        "## Failed-update recovery",
        "## Configuration and diagnostics",
    ]
    _ordered(document, headings, "required sections")
    for heading in headings:
        if not _lifecycle_section(document, heading).strip():
            fail(f"lifecycle: section {heading!r} is empty")
    install = _numbered_steps(_lifecycle_section(document, "## Install with Herdr"))
    _ordered(
        "\n".join(install),
        [
            "Install the selected known release through Herdr",
            "Herdr places the plugin under `HERDR_PLUGIN_ROOT`",
            "No additional configuration is required",
            "Use the plugin's startup action",
        ],
        "install procedure",
    )
    lifecycle = _numbered_steps(_lifecycle_section(document, "## Start, status, stop, and restart"))
    _ordered("\n".join(lifecycle), ["Invoke `start`", "Invoke `status`", "Invoke `stop`", "Invoke `restart`"], "action procedure")
    if "read-only" not in _lifecycle_section(document, "## Start, status, stop, and restart").lower():
        fail("lifecycle: status must be explicitly read-only")
    for heading, operation in [("## Disable", "disable"), ("## Unlink", "unlink"), ("## Remove", "remove")]:
        body = _lifecycle_section(document, heading)
        steps = _numbered_steps(body)
        _ordered("\n".join(steps), ["Invoke `stop`", "Confirm a successful stop", f"Invoke `{operation}`"], heading)
        if "does not stop an already-running bridge" not in body:
            fail(f"lifecycle: {heading} must explain that Herdr does not stop a live bridge")
    update = _lifecycle_section(document, "## Update activation")
    _ordered(update, ["explicit restart", "next Herdr start", "old bridge authority ends", "fresh USB, Herdr, and Codex sessions"], "update procedure")
    if "live handoff" in update or "immediate automatic activation" in update:
        fail("lifecycle: update procedure makes an unsafe live-activation claim")
    recovery = _lifecycle_section(document, "## Failed-update recovery")
    recovery_steps = _numbered_steps(recovery)
    _ordered(
        "\n".join(recovery_steps),
        ["Invoke `stop`", "Manually reinstall one specifically selected known plugin release through Herdr", "Invoke `start`", "Invoke `status`"],
        "recovery procedure",
    )
    if "No automatic rollback" not in recovery:
        fail("lifecycle: failed-update recovery must state that rollback is manual")
    forbidden = [
        "/home/", "/Users/", "/tmp/", "127.0.0.1", "localhost", "BEGIN OPENSSH", "sk-", "account_id",
        "transcript", "prompt", "raw error", "diagnostic payload",
    ]
    for text in forbidden:
        if text in document:
            fail(f"lifecycle: privacy-bound document contains forbidden text {text!r}")
    for required in ["HERDR_PLUGIN_ROOT", "HERDR_PLUGIN_CONFIG_DIR", "HERDR_PLUGIN_STATE_DIR", "Linux x86-64", "macOS Apple Silicon", "bounded", "stderr"]:
        if required not in document:
            fail(f"lifecycle: document omits required bounded term {required!r}")
    return document


def _binary_strings(path: Path) -> list[str]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        fail(f"binary: cannot read executable: {exc}")
    return [match.decode("ascii", "ignore") for match in re.findall(rb"[ -~]{4,}", data)]


def _run_tool(command: list[str], label: str) -> str:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        fail(f"dependencies: {label} could not run: {exc}")
    output = (result.stdout + result.stderr).strip()
    if result.returncode != 0 and not (label == "ldd" and "not a dynamic executable" in output):
        fail(f"dependencies: {label} failed")
    if "not found" in output.lower():
        fail(f"dependencies: {label} reports an unresolved library")
    return output


def _inspect_binary(path: Path, target: str) -> tuple[str, list[str]]:
    try:
        data = path.read_bytes()
    except OSError as exc:
        fail(f"binary: cannot read executable: {exc}")
    mode = path.stat().st_mode
    if not mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH):
        fail("binary: packaged executable is not executable")
    if target == "x86_64-unknown-linux-gnu":
        if len(data) < 20 or data[:4] != b"\x7fELF" or data[4] != 2 or data[5] != 1:
            fail("target: executable is not a little-endian 64-bit ELF")
        machine = struct.unpack_from("<H", data, 18)[0]
        if machine != 62:
            fail("target: executable is not x86-64 ELF")
        _run_tool(["readelf", "-h", str(path)], "readelf")
        dependencies = _run_tool(["ldd", str(path)], "ldd")
        return "ldd", [line.strip() for line in dependencies.splitlines() if line.strip()]
    if len(data) < 8 or data[:4] != b"\xcf\xfa\xed\xfe":
        fail("target: executable is not a little-endian 64-bit Mach-O")
    cpu_type = struct.unpack_from("<I", data, 4)[0]
    if cpu_type != 0x0100000C:
        fail("target: executable is not arm64 Mach-O")
    _run_tool(["otool", "-hv", str(path)], "otool -hv")
    dependencies = _run_tool(["otool", "-L", str(path)], "otool -L")
    libraries = [line.strip() for line in dependencies.splitlines() if line.strip()]
    if libraries and libraries[0].endswith(":"):
        libraries = libraries[1:]
    return "otool -L", libraries


def _verify_bundle(bundle: Path, expected_target: str, schema_path: Path, expected_revision: str | None = None) -> None:
    if expected_target not in TARGETS:
        fail(f"target: unsupported requested target {expected_target}")
    root, temporary = _materialize(bundle)
    try:
        actual_files = _files(root)
        unknown = sorted(set(actual_files) - ALLOWED_FILES)
        if unknown:
            fail(f"forbidden bundle entry: {', '.join(unknown)}")
        missing = sorted(ALLOWED_FILES - set(actual_files))
        if missing:
            fail(f"bundle: missing required entry/entries: {', '.join(missing)}")

        manifest = _validate_manifest(_read_json(root / "release-manifest.json", "manifest"), schema_path)
        target = manifest["target"]["triple"]
        if target != expected_target:
            fail(f"target: manifest selects {target}, expected {expected_target}")
        if expected_revision is not None and manifest["source"]["revision"] != expected_revision:
            fail("source: manifest revision does not match workflow commit")
        plugin = _validate_plugin_manifest(root / "herdr-plugin.toml")
        if manifest["plugin"]["version"] != plugin["version"]:
            fail("schema: manifest plugin version does not match herdr-plugin.toml")

        lifecycle_text = _validate_lifecycle(root / "LIFECYCLE.md")
        lifecycle_hash = _sha256(root / "LIFECYCLE.md")
        if lifecycle_hash != manifest["lifecycle"]["sha256"]:
            fail("lifecycle: document hash does not match release manifest")
        if not lifecycle_text:
            fail("lifecycle: document is empty")

        binary = root / "bin/herdr-keypad"
        binary_hash = _sha256(binary)
        if binary_hash != manifest["binary"]["sha256"]:
            fail("hash: packaged binary SHA-256 does not match release manifest")
        if binary.stat().st_size != manifest["binary"]["size"]:
            fail("hash: packaged binary size does not match release manifest")
        dependency_tool, dependency_lines = _inspect_binary(binary, expected_target)
        if manifest["dependencies"]["tool"] != dependency_tool:
            fail("dependencies: manifest tool does not match target-native inspection")
        declared_libraries = manifest["dependencies"]["libraries"]
        for library in declared_libraries:
            if not any(library in line for line in dependency_lines):
                fail(f"dependencies: declared library {library!r} was not observed")
        for text in _binary_strings(binary):
            for pattern in FORBIDDEN_BINARY_TEXT:
                if pattern.search(text):
                    fail("forbidden executable string: production runtime, source path, credential, or evidence dependency")
    finally:
        if temporary is not None:
            temporary.cleanup()


def _sha256_text(path: str) -> str:
    return _sha256(Path(path))


def _command_output(command: list[str], fallback: str) -> str:
    try:
        result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        return fallback
    return result.stdout.strip() or fallback


def _write_manifest(args: argparse.Namespace) -> None:
    required = {
        "output": args.output,
        "binary": args.binary,
        "binary_b": args.binary_b,
        "plugin_root": args.plugin_root,
        "source_archive_a": args.source_archive_a,
        "source_archive_b": args.source_archive_b,
        "cargo_lock": args.cargo_lock,
        "source_revision": args.source_revision,
    }
    missing = [name for name, value in required.items() if not value]
    if missing:
        fail(f"manifest: --write-manifest requires {', '.join('--' + name.replace('_', '-') for name in missing)}")
    target = args.target
    if target not in TARGETS:
        fail("target: unsupported target for manifest generation")
    plugin_root = Path(args.plugin_root)
    plugin = _validate_plugin_manifest(plugin_root / "herdr-plugin.toml")
    binary = Path(args.binary)
    binary_b = Path(args.binary_b)
    lifecycle = plugin_root / "LIFECYCLE.md"
    lifecycle_text = _validate_lifecycle(lifecycle)
    dependency_tool, dependency_lines = _inspect_binary(binary, target)
    binary_hash = _sha256(binary)
    binary_b_hash = _sha256(binary_b)
    libraries: list[str] = []
    for line in dependency_lines:
        match = re.search(r"(?:=>\s*)?([^\s(]+(?:\.dylib|\.so(?:\.[0-9]+)*)?)", line)
        if match and match.group(1) not in libraries:
            libraries.append(match.group(1))
    compiler_toolchain = args.toolchain or "unknown"
    manifest = {
        "schema_version": 1,
        "plugin": {"id": plugin["id"], "version": plugin["version"]},
        "bridge": {"version": plugin["version"]},
        "target": {"triple": target, **TARGETS[target]},
        "compiler": {
            "toolchain": compiler_toolchain,
            "rustc": args.rustc or _command_output(["rustc", "--version"], "unknown"),
            "cargo": args.cargo or _command_output(["cargo", "--version"], "unknown"),
        },
        "source": {
            "revision": args.source_revision,
            "archives": [
                {"root": "source-a", "sha256": _sha256_text(args.source_archive_a)},
                {"root": "source-b", "sha256": _sha256_text(args.source_archive_b)},
            ],
        },
        "cargo_lock": {"sha256": _sha256_text(args.cargo_lock)},
        "lifecycle": {"path": "LIFECYCLE.md", "sha256": _sha256(lifecycle)},
        "binary": {"path": "bin/herdr-keypad", "sha256": binary_hash, "size": binary.stat().st_size},
        "reproducibility": {"status": "passed", "hash_a": binary_hash, "hash_b": binary_b_hash, "equal": binary_hash == binary_b_hash},
        "dependencies": {"tool": dependency_tool, "status": "passed", "libraries": libraries},
        "tests": {"status": "passed", "command": args.test_command or "cargo test --locked --manifest-path host/herdr_keypad/native/Cargo.toml --test release_bundle"},
        "signing": {"status": "not-run", "reason": "Unsigned CI artifact"},
        "notarization": {"status": "not-run", "reason": "Unsigned CI artifact"},
    }
    schema_path = Path(args.schema)
    _validate_manifest(manifest, schema_path)
    if not lifecycle_text:
        fail("lifecycle: document is empty")
    try:
        output = Path(args.output)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except OSError as exc:
        fail(f"manifest: cannot write output: {exc}")


def _workflow_contract(workflow_path: Path) -> None:
    try:
        workflow = workflow_path.read_text(encoding="utf-8")
    except (OSError, UnicodeError) as exc:
        fail(f"workflow: cannot read workflow: {exc}")
    action_refs = re.findall(r"uses:\s*[^\s@]+@([^\s#]+)", workflow)
    if not action_refs or any(not re.fullmatch(r"[0-9a-f]{40}", ref) for ref in action_refs):
        fail("workflow: every third-party action must be pinned to an immutable 40-character commit SHA")
    required_fragments = [
        "runs-on: ubuntu-24.04",
        "runs-on: macos-14-xlarge",
        'uname -m',
        '"arm64"',
        'git archive --format=tar "$GITHUB_SHA"',
        "tar -xf",
        'CARGO_TARGET_DIR="$WORK/target-a"',
        'CARGO_TARGET_DIR="$WORK/target-b"',
        'CARGO_HOME="$WORK/cargo-home-a"',
        'CARGO_HOME="$WORK/cargo-home-b"',
        "cargo build --release --locked",
        "cargo test --locked",
        "--target x86_64-unknown-linux-gnu",
        "--target aarch64-apple-darwin",
        "--test release_bundle",
        "macos_",
        "readelf",
        "ldd",
        "otool -L",
        "sha256sum",
        "GITHUB_SHA",
        "source-a",
        "source-b",
        "release-manifest.json",
        "verify_bundle.py",
        "upload-artifact",
        '"status": "not-run"',
    ]
    for fragment in required_fragments:
        if fragment not in workflow:
            fail(f"workflow: missing required native release contract fragment {fragment!r}")
    if workflow.count("git archive --format=tar \"$GITHUB_SHA\"") < 4:
        fail("workflow: each target must materialize two independent commit-bound source archives")
    if workflow.count("cargo build --release --locked") < 4:
        fail("workflow: each target must build both isolated roots with Cargo.lock")
    if workflow.count("CARGO_TARGET_DIR=\"$WORK/target-a\"") < 2 or workflow.count("CARGO_TARGET_DIR=\"$WORK/target-b\"") < 2:
        fail("workflow: both roots must use distinct Cargo target directories for test and build")
    if "macos-14-xlarge" not in workflow or "if [[ \"$(uname -m)\" != \"arm64\" ]]" not in workflow:
        fail("workflow: macOS job must assert the native arm64 runner before building")
    if re.search(r"(?:signing|notarization|codesign|notarytool).*?(?:passed|success|true)", workflow, re.I | re.S):
        fail("workflow: unsigned workflow contains a signing or notarization success claim")
    if re.search(r"(?:python|node|java|jvm|venv|pip|npm)\s+(?:host/|herdr-keypad)", workflow, re.I):
        fail("workflow: production package command names a separately installed runtime")
    if "actions/upload-artifact@" not in workflow:
        fail("workflow: target artifacts must be uploaded")


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path)
    parser.add_argument("--target")
    parser.add_argument("--schema", type=Path, default=Path(__file__).resolve().parents[1] / "bundle/manifest.schema.json")
    parser.add_argument("--source-revision")
    parser.add_argument("--workflow", type=Path)
    parser.add_argument("--check-workflow-contract", action="store_true")
    parser.add_argument("--write-manifest", action="store_true")
    parser.add_argument("--output", "--manifest-output", dest="output", type=Path)
    parser.add_argument("--binary", type=Path)
    parser.add_argument("--binary-b", type=Path)
    parser.add_argument("--plugin-root", type=Path)
    parser.add_argument("--source-archive-a")
    parser.add_argument("--source-archive-b")
    parser.add_argument("--cargo-lock")
    parser.add_argument("--toolchain")
    parser.add_argument("--rustc")
    parser.add_argument("--cargo")
    parser.add_argument("--test-command")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.check_workflow_contract:
            if args.workflow is None:
                fail("workflow: --check-workflow-contract requires --workflow")
            _workflow_contract(args.workflow)
            print(f"verified workflow contract: {args.workflow}")
        elif args.write_manifest:
            _write_manifest(args)
            print(f"wrote unsigned release manifest: {args.output}")
        elif args.bundle is not None:
            if args.target is None:
                fail("target: --bundle requires --target")
            _verify_bundle(args.bundle, args.target, args.schema, args.source_revision)
            print(f"verified {args.target} bundle: {args.bundle}")
        else:
            fail("usage: choose --bundle, --write-manifest, or --check-workflow-contract")
    except VerificationError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
