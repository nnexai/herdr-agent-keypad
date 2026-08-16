"""The fixed, host-owned eleven-gate physical bring-up state machine."""
from __future__ import annotations

import secrets
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .evidence import EvidenceWriter
from .protocol import MachineFact, ProtocolSession
from .ui import AWAITING_COPY, TerminalUI, parse_batch_response, parse_response

GUIDED_ORDER = ("Identify", "Displays", "Keys", "Encoder", "LEDs", "Brightness", "Reboot", "Pair", "Recover", "Traffic", "Selection")


@dataclass(frozen=True)
class StimulusRow:
    step_id: str
    stimulus: str
    panel: int
    instruction: str
    expected: str
    physical_kind: str


@dataclass(frozen=True)
class Gate:
    name: str
    rows: tuple[StimulusRow, ...]
    dependent: bool = False


def _rows() -> tuple[Gate, ...]:
    return (
        Gate("Identify", (StimulusRow("IDENTIFY", "WAIT", 1, "Confirm the connected delivered keypad and visible identity facts.", "A bounded hello is acknowledged; physical identity remains unavailable until observed.", "identity"),)),
        Gate("Displays", tuple(StimulusRow(f"DISPLAY-{panel}", f"PANEL-{panel}", panel, f"Observe display {panel}: position, upright orientation, and requested color.", "The numbered panel is visible, upright from the agreed desk view, and the requested color is correct.", "display") for panel in range(1, 5))),
        Gate("Keys", tuple(StimulusRow(f"KEY-{key}", f"KEY-{key}", key, f"Press physical KEY-{key}; validate its raw library key index {key - 1}.", "Only the intended physical key produces the matching raw key event.", "key") for key in range(1, 5))),
        Gate("Encoder", (
            StimulusRow("ENCODER-CW", "ENC-CW", 1, "Turn the encoder clockwise by the prompted detent count.", "Clockwise movement is observed in the requested direction.", "encoder"),
            StimulusRow("ENCODER-CCW", "ENC-CCW", 1, "Turn the encoder counter-clockwise by the prompted detent count.", "Counter-clockwise movement is observed in the requested direction.", "encoder"),
            StimulusRow("ENCODER-CLICK", "ENC-CLICK", 1, "Click the encoder once; validate raw library key index 4 (BOOT0-safe observation only).", "The physical encoder click produces the matching raw key event without triggering reset.", "encoder_click"),
        )),
        Gate("LEDs", tuple(StimulusRow(f"LED-{led}", f"LED-{led}", 1, f"Observe library LED {led} at the requested bounded color and brightness.", "The intended physical LED illuminates without assuming its position.", "led") for led in range(14))),
        Gate("Brightness", (
            StimulusRow("BRIGHTNESS-LOW", "BRIGHTNESS-LOW", 1, "Observe the low proof-brightness sample.", "Visible but lowest usable brightness is observed.", "brightness"),
            StimulusRow("BRIGHTNESS-MEDIUM", "BRIGHTNESS-MEDIUM", 1, "Observe the medium brightness sample.", "The medium requested brightness is observed.", "brightness"),
            StimulusRow("BRIGHTNESS-HIGH", "BRIGHTNESS-HIGH", 1, "Observe the high brightness sample.", "The high requested brightness is observed.", "brightness"),
        )),
        Gate("Reboot", (StimulusRow("REBOOT", "REBOOT", 1, "Reset the keypad through the bounded software reboot stimulus.", "The startup WAIT surface returns and a fresh session is established.", "reboot"),)),
        Gate("Pair", (), dependent=True),
        Gate("Recover", (), dependent=True),
        Gate("Traffic", (), dependent=True),
        Gate("Selection", (), dependent=True),
    )


GATES = _rows()

def _expected_raw_key(row: StimulusRow) -> int:
    if row.physical_kind == "key":
        return int(row.step_id.rsplit("-", 1)[1]) - 1
    if row.physical_kind == "encoder_click":
        return 4
    raise RuntimeError(f"row {row.step_id} does not have a key event")

BATCH_GATE_ORDER = tuple(gate.name for gate in GATES[:7])
BATCH_DWELL_SECONDS = 1.0
MAX_BATCH_DWELL_SECONDS = 5.0

PAIRING_HOST_COPY = "Confirm that the keypad displays {challenge}. Type the challenge to pair this device."
PAIRING_DEVICE_LABEL = "PAIR"
PAIRING_SUCCESS_COPY = "Paired with the physically confirmed keypad."


def pairing_prompt(challenge: str) -> tuple[str, str]:
    from .pairing import challenge_valid

    if not challenge_valid(challenge):
        raise ValueError("pairing challenge must be fixed-width uppercase hexadecimal")
    return PAIRING_HOST_COPY.format(challenge=challenge), f"{PAIRING_DEVICE_LABEL} {challenge}"


def pairing_ui_check() -> None:
    host, device = pairing_prompt("A1B2C3")
    if host != "Confirm that the keypad displays A1B2C3. Type the challenge to pair this device.":
        raise AssertionError("pairing host copy changed")
    if device != "PAIR A1B2C3":
        raise AssertionError("pairing device copy changed")

RECOVERY_SUCCESS_COPY = "New session established; uncertain pre-disconnect work was discarded."
RECOVERY_EXCLUSIONS = ("host reboot", "suspend/resume", "cross-component product resynchronization")


def recovery_ui_check() -> None:
    if "discarded" not in RECOVERY_SUCCESS_COPY or len(RECOVERY_EXCLUSIONS) != 3:
        raise AssertionError("recovery UI copy must expose discard semantics and Phase 4 exclusions")



@dataclass(frozen=True)
class RecoveryTourStep:
    key: str
    title: str
    action: str
    checkpoint: str
    allow_unavailable: bool = False


RECOVERY_TOUR_STEPS = (
    RecoveryTourStep("reset", "Device reset", "Reset the keypad through its normal reset path.", "Confirm the delivered keypad returned to WAIT and its runtime endpoint reappeared."),
    RecoveryTourStep("normal-flash-reset", "Normal flash/reset", "Flash or reset the current firmware over the same measured USB cable.", "Confirm the delivered keypad returned to WAIT without choosing a transient /dev/tty* node."),
    RecoveryTourStep("port-move", "USB port move", "Unplug the keypad and reconnect it to another USB port.", "Confirm the same delivered keypad returned; do not select a port manually."),
    RecoveryTourStep("endpoint-renumber", "Endpoint renumber", "Connect another ACM device to force endpoint renumbering; capture the measured endpoint transition.", "Confirm exact identity still wins; ambiguity or mismatch must fail closed.", False),
    RecoveryTourStep("utility-restart", "Utility restart", "Exit this tour at the restart checkpoint, then rerun it with the printed --resume command.", "Confirm a fresh utility process establishes a fresh device session and does not replay uncertain work."),
)


def recovery_tour_check() -> None:
    if tuple(step.key for step in RECOVERY_TOUR_STEPS) != ("reset", "normal-flash-reset", "port-move", "endpoint-renumber", "utility-restart"):
        raise AssertionError("D-12 recovery tour order changed")
    if any(step.allow_unavailable for step in RECOVERY_TOUR_STEPS):
        raise AssertionError("required D-12 recovery steps must not permit unavailable")

@dataclass(frozen=True)
class BatchObservation:
    row: StimulusRow
    machine_fact: MachineFact
    machine_details: dict[str, Any]


class BatchRun:
    """Stimulate one fixed gate at a time and confirm its rows as a group."""

    def __init__(
        self,
        session: ProtocolSession | Any | None,
        evidence: EvidenceWriter,
        ui: TerminalUI | None = None,
        run_id: str | None = None,
        dwell_seconds: float = BATCH_DWELL_SECONDS,
        machine_only: bool = False,
    ):
        self.session = session
        self.evidence = evidence
        self.ui = ui or TerminalUI()
        self.run_id = run_id or (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3))
        self.run_suffix = self.run_id[-6:]
        self.gate_index = 0
        self.pending: list[BatchObservation] = []
        self.history: list[dict[str, Any]] = []
        self.machine_observations: list[dict[str, Any]] = []
        self.started = False
        self.stable = False
        self.stopped = False
        self.response: str | None = None
        self.dwell_seconds = min(MAX_BATCH_DWELL_SECONDS, max(0.0, float(dwell_seconds)))
        self.machine_only = machine_only

    @property
    def gate(self) -> Gate:
        return GATES[self.gate_index]

    @property
    def complete_physical_gates(self) -> bool:
        return self.gate_index >= len(BATCH_GATE_ORDER)

    def start(self) -> None:
        self.started = True
        self.ui.start(self.run_suffix)

    def _row_detail(self, observation: BatchObservation) -> str:
        detail = f"machine: {observation.machine_fact.status}"
        event = observation.machine_details.get("event")
        if isinstance(event, dict) and isinstance(event.get("key"), int):
            return f"{detail}; observed key index: {event['key']}"
        if isinstance(event, dict) and isinstance(event.get("direction"), str):
            return f"{detail}; observed encoder: {event['direction']}"
        return detail
    def _render(self, status: str = "stimulating") -> None:
        if self.machine_only and status == "awaiting-confirmation":
            status = "machine-only"
        self.ui.render_batch_gate(
            self.gate.name,
            self.gate_index + 1,
            len(BATCH_GATE_ORDER),
            tuple((observation.row.step_id, "stable", self._row_detail(observation)) for observation in self.pending),
            self.run_suffix,
            status,
        )

    def stimulate_gate(self) -> tuple[BatchObservation, ...]:
        """Stimulate every row in order, retaining bounded machine details."""
        if not self.started or self.complete_physical_gates or self.stopped:
            raise RuntimeError("no physical batch gate is active")
        if self.session is None:
            raise RuntimeError("keypad session is unavailable")
        self.pending = []
        self.stable = False
        self.ui.begin_operation(f"{self.gate.name} batch")
        self._render()
        for row in self.gate.rows:
            if row.step_id == "IDENTIFY":
                fact = self.session.hello()
            else:
                fact = self.session.stimulate(row.step_id, row.panel, row.stimulus)
            details: dict[str, Any] = {}
            if row.physical_kind in {"key", "encoder", "encoder_click"}:
                event = self.session.wait_event(row.step_id)
                payload = event.get("payload") if isinstance(event, dict) else None
                if not isinstance(payload, dict) or payload.get("step_id") != row.step_id:
                    raise RuntimeError(f"validated input event did not match {row.step_id}")
                if row.physical_kind == "encoder":
                    expected_direction = "cw" if row.stimulus == "ENC-CW" else "ccw"
                    if payload.get("kind") != "encoder_transition" or payload.get("direction") != expected_direction:
                        raise RuntimeError(
                            f"validated encoder event {payload!r} did not match {expected_direction} for {row.step_id}"
                        )
                    details["event"] = {
                        "kind": "encoder_transition",
                        "step_id": row.step_id,
                        "direction": expected_direction,
                    }
                else:
                    if payload.get("kind") != "key_transition":
                        raise RuntimeError(f"validated key event kind is invalid for {row.step_id}")
                    key_index = payload.get("key")
                    expected_raw = _expected_raw_key(row)
                    if (
                        not isinstance(key_index, int)
                        or isinstance(key_index, bool)
                        or not 0 <= key_index <= 4
                        or key_index != expected_raw
                    ):
                        raise RuntimeError(
                            f"validated key event index {key_index!r} did not match raw index {expected_raw} for {row.step_id}"
                        )
                    details["event"] = {"kind": "key_transition", "step_id": row.step_id, "key": key_index}
            elif self.dwell_seconds:
                time.sleep(self.dwell_seconds)
            observed_value: Any = details if details else "unavailable"
            self.machine_observations.append(
                {
                    "row_id": f"{self.run_id}:machine:{len(self.machine_observations) + 1}",
                    "run_id": self.run_id,
                    "step_id": row.step_id,
                    "gate": self.gate.name,
                    "machine_status": fact.status,
                    "machine_reply_seq": fact.reply_seq,
                    "observed_value": observed_value,
                    "timestamp": time.time(),
                }
            )
            self.pending.append(BatchObservation(row, fact, details))
            self._render()
        self.stable = True
        self.ui.stable_result()
        self._render("awaiting-confirmation")
        return tuple(self.pending)

    def advance_machine_gate(self) -> None:
        """Advance after stable machine evidence without authorizing PASS."""
        if not self.stable or not self.pending:
            raise RuntimeError("machine gate has no stable observations")
        self.gate_index += 1
        self.pending = []
        self.stable = False

    def _row_record(self, observation: BatchObservation, action: str, physical_status: str, ordinal: int) -> dict[str, Any]:
        fact = observation.machine_fact
        machine_details: dict[str, Any] = {"status": fact.status}
        if fact.detail:
            machine_details["detail"] = fact.detail[:128]
        if observation.machine_details.get("event"):
            event = dict(observation.machine_details["event"])
            event["step_id"] = str(event["step_id"])[:64]
            machine_details["event"] = event
        return {
            "row_id": f"{self.run_id}:{len(self.history) + ordinal + 1}",
            "run_id": self.run_id,
            "step_id": observation.row.step_id,
            "gate": self.gate.name,
            "machine_status": fact.status,
            "machine_reply_seq": fact.reply_seq,
            "human_response": action,
            "physical_status": physical_status,
            "observed_value": machine_details,
            "timestamp": time.time(),
        }

    def respond(self, text: str) -> str:
        """Finalize every pending row from one explicit gate/run-bound response."""
        if not self.started or not self.pending:
            raise RuntimeError("no confirmable physical batch gate is active")
        parsed = parse_batch_response(text, self.gate.name, self.run_suffix)
        if parsed is None:
            raise ValueError(
                f"Type Y {self.gate.name.upper()} {self.run_suffix}, "
                f"N {self.gate.name.upper()} {self.run_suffix}, or "
                f"R {self.gate.name.upper()} {self.run_suffix}."
            )
        if not self.stable:
            raise RuntimeError("group confirmation disabled until every row has stable machine evidence")
        if parsed.action == "Y" and any(item.machine_fact.status != "acknowledged" for item in self.pending):
            raise ValueError("group PASS requires acknowledged machine evidence for every row; use N or R")
        rows = [
            self._row_record(item, parsed.action, {"Y": "pass", "N": "failed", "R": "repeated"}[parsed.action], ordinal)
            for ordinal, item in enumerate(self.pending)
        ]
        self.evidence.record_rows(rows)
        self.history.extend(rows)
        self.response = parsed.action
        if parsed.action == "N":
            self.stopped = True
            self.stable = False
            self._render("fail")
            return "fail"
        if parsed.action == "R":
            self.ui.add_history(f"{self.gate.name}: repeat preserved")
            self.pending = []
            self.stable = False
            self.ui.confirmation_enabled = False
            self._render("repeat")
            return "repeat"
        self.ui.add_history(f"{self.gate.name}: PASS ({len(rows)} rows)")
        self.gate_index += 1
        self.pending = []
        self.stable = False
        if self.complete_physical_gates:
            self.ui.add_history("Physical batch gates complete; dependent gates remain not started")
            self.ui.render_not_started(GUIDED_ORDER[len(BATCH_GATE_ORDER)], self.gate_index + 1, len(GUIDED_ORDER), self.run_suffix)
        else:
            self.ui.render_not_started(self.gate.name, self.gate_index + 1, len(GUIDED_ORDER), self.run_suffix)
        return "pass"
    def machine_result(self) -> dict[str, Any]:
        status = "machine-complete" if self.complete_physical_gates else "machine-failed" if self.stopped else "machine-incomplete"
        return {
            "schema_version": 1,
            "kind": "result",
            "run_id": self.run_id,
            "status": status,
            "mode": "machine-only",
            "physical_confirmation": False,
            "machine_observations": list(self.machine_observations),
            "batch_order": list(BATCH_GATE_ORDER),
            "completed_gates": list(BATCH_GATE_ORDER[: self.gate_index]),
        }

    def result(self) -> dict[str, Any]:
        status = "pass" if self.complete_physical_gates else "fail" if self.stopped else "incomplete"
        return {
            "schema_version": 1,
            "kind": "result",
            "run_id": self.run_id,
            "status": status,
            "mode": "batch",
            "physical_map": {"rows": list(self.history), "guided_order": list(GUIDED_ORDER)},
            "batch_order": list(BATCH_GATE_ORDER),
            "completed_gates": list(BATCH_GATE_ORDER[: self.gate_index]),
        }
def _event_evidence(machine_details: dict[str, Any]) -> str | None:
    """Return the bounded, protocol-validated key event evidence line."""
    event = machine_details.get("event")
    if not isinstance(event, dict):
        return None
    if event.get("kind") != "key_transition":
        return None
    key_index = event.get("key")
    if not isinstance(key_index, int) or isinstance(key_index, bool) or not 0 <= key_index <= 4:
        return None
    return f"observed event: key_transition; key index: {key_index}"


class GuidedRun:
    """Bind one visible step, machine fact, and human response before recording PASS."""

    def __init__(self, session: ProtocolSession | Any | None, evidence: EvidenceWriter, ui: TerminalUI | None = None, run_id: str | None = None):
        self.session = session
        self.evidence = evidence
        self.ui = ui or TerminalUI()
        self.run_id = run_id or (time.strftime("%Y%m%dT%H%M%SZ", time.gmtime()) + "-" + secrets.token_hex(3))
        self.run_suffix = self.run_id[-6:]
        self.gate_index = 0
        self.row_index = 0
        self.started = False
        self.stable = False
        self.machine_fact: MachineFact | None = None
        self.machine_details: dict[str, Any] = {}
        self.history: list[dict[str, Any]] = []
        self.failed_terminal = False

    @property
    def gate(self) -> Gate:
        return GATES[self.gate_index]

    @property
    def row(self) -> StimulusRow | None:
        return self.gate.rows[self.row_index] if self.gate.rows else None

    @property
    def step_id(self) -> str:
        return self.row.step_id if self.row else self.gate.name.upper()

    @property
    def complete_physical_gates(self) -> bool:
        return self.gate_index >= 7

    def start(self) -> None:
        self.started = True
        self.ui.start(self.run_suffix)
        self._render_not_started_or_current()

    def _render_not_started_or_current(self) -> None:
        if not self.started:
            return
        if self.row is None:
            self.ui.render_not_started(self.gate.name, self.gate_index + 1, len(GUIDED_ORDER), self.run_suffix)
            return
        evidence = []
        if self.machine_fact is not None:
            evidence.append(f"machine: {self.machine_fact.status}")
            if self.machine_fact.detail:
                evidence.append(self.machine_fact.detail)
        event_line = _event_evidence(self.machine_details)
        if event_line:
            evidence.append(event_line)
        self.ui.render_step(self.gate.name, self.step_id, self.gate_index + 1, len(GUIDED_ORDER), self.row.instruction, self.row.expected, evidence, run_suffix=self.run_suffix)

    def _record(self, action: str, physical_status: str, observed_value: Any = "unavailable") -> None:
        row = {
            "row_id": f"{self.run_id}:{len(self.history) + 1}",
            "run_id": self.run_id,
            "step_id": self.step_id,
            "gate": self.gate.name,
            "machine_status": self.machine_fact.status if self.machine_fact else "unavailable",
            "machine_reply_seq": self.machine_fact.reply_seq if self.machine_fact else None,
            "human_response": action,
            "physical_status": physical_status,
            "observed_value": observed_value if observed_value is not None else "unavailable",
            "timestamp": time.time(),
        }
        self.history.append(row)
        if hasattr(self.evidence, "record_row"):
            self.evidence.record_row(row)

    def stimulate(self) -> MachineFact:
        """Send only a fixed stimulus; ACK is retained as machine evidence, not PASS."""
        if not self.started or self.row is None:
            raise RuntimeError("no physical row is active")
        if self.failed_terminal:
            raise RuntimeError("failed physical observation is terminal; enter typed R to restimulate")
        if self.session is None:
            raise RuntimeError("keypad session is unavailable")
        if self.step_id == "IDENTIFY":
            fact = self.session.hello()
        else:
            fact = self.session.stimulate(self.step_id, self.row.panel, self.row.stimulus)
            if self.row.physical_kind in {"key", "encoder_click"} and hasattr(self.session, "wait_event"):
                event = self.session.wait_event(self.step_id)
                payload = event.get("payload") if isinstance(event, dict) else None
                expected_raw = _expected_raw_key(self.row)
                if (
                    not isinstance(payload, dict)
                    or payload.get("kind") != "key_transition"
                    or payload.get("step_id") != self.step_id
                    or payload.get("key") != expected_raw
                ):
                    raise RuntimeError(f"validated key event did not match raw index {expected_raw} for {self.step_id}")
                self.machine_details = {"event": payload}
        self.machine_fact = fact
        self.stable = fact.status == "acknowledged"
        if self.stable:
            self.ui.stable_result()
        self._render_not_started_or_current()
        return fact

    def respond(self, text: str) -> str:
        """Apply Y/N/R only to the currently visible stable step/run token."""
        if not self.started or self.row is None:
            raise RuntimeError("no confirmable physical row is active")
        parsed = parse_response(text, self.step_id, self.run_suffix)
        if parsed is None:
            raise ValueError(f"Enter alone cannot confirm; type Y {self.step_id} {self.run_suffix}, N {self.step_id} {self.run_suffix}, or R {self.step_id} {self.run_suffix}.")
        if self.failed_terminal:
            if parsed.action != "R":
                raise RuntimeError("failed observation is terminal; explicit R is required before a fresh stimulus")
            self._record("R", "repeated", "unavailable")
            self.failed_terminal = False
            self.response = "R"
            self.machine_fact = None
            self.machine_details = {}
            self.stable = False
            self.ui.add_history(f"{self.step_id}: repeat requested with fresh stimulus required")
            return "repeat"
        if not self.stable:
            raise RuntimeError("confirmation disabled until stable machine evidence exists")
        if parsed.action == "R":
            self._record("R", "repeated", "unavailable")
            self.response = "R"
            self.stable = False
            self.ui.add_history(f"{self.step_id}: repeat preserved")
            self.ui.confirmation_enabled = False
            return "repeat"
        if parsed.action == "N":
            self._record("N", "failed", "unavailable")
            self.response = "N"
            self.failed_terminal = True
            self.stable = False
            self.ui.render_step(self.gate.name, self.step_id, self.gate_index + 1, len(GUIDED_ORDER), self.row.instruction, self.row.expected, ["machine: acknowledged", "physical: failed; type R to restimulate"], "fail", self.run_suffix)
            return "fail"
        if self.machine_fact.status != "acknowledged":
            raise RuntimeError("physical PASS requires an acknowledged machine fact")
        self._record("Y", "pass", self.machine_details.get("event", "observed"))
        self.response = "Y"
        self._advance()
        return "pass"
    def _advance(self) -> None:
        self.ui.add_history(f"{self.step_id}: PASS")
        self.row_index += 1
        self.machine_fact = None
        self.machine_details = {}
        self.response = None
        self.failed_terminal = False
        self.stable = False
        if self.row_index >= len(self.gate.rows):
            self.gate_index += 1
            self.row_index = 0
        self._render_not_started_or_current()
    def result(self) -> dict[str, Any]:
        from .evidence import _derived_physical_status
        status = _derived_physical_status(self.history) if self.history else "incomplete"
        return {
            "schema_version": 1,
            "kind": "result",
            "run_id": self.run_id,
            "status": status,
            "physical_map": {"rows": list(self.history), "guided_order": list(GUIDED_ORDER)},
            "machine_facts": {"last": self.machine_fact.status if self.machine_fact else "unavailable"},
        }


def guided_order_check() -> None:
    if tuple(gate.name for gate in GATES) != GUIDED_ORDER:
        raise AssertionError("guided gate order changed")
    if any(gate.dependent and gate.rows for gate in GATES):
        raise AssertionError("dependent gates must remain visibly not started")
    physical_ids = [row.step_id for gate in GATES[:7] for row in gate.rows]
    if len(physical_ids) != len(set(physical_ids)):
        raise AssertionError("physical step identifiers must be unique")


def confirmation_check() -> None:
    from .evidence import EvidenceWriter
    from tempfile import TemporaryDirectory

    class FakeSession:
        def hello(self):
            return MachineFact("acknowledged", time.time(), 1)

        def stimulate(self, step_id, panel, stimulus):
            return MachineFact("acknowledged", time.time(), 1)

        def wait_event(self, step_id):
            if step_id == "ENCODER-CW":
                return {"payload": {"kind": "encoder_transition", "step_id": step_id, "direction": "cw"}}
            if step_id == "ENCODER-CCW":
                return {"payload": {"kind": "encoder_transition", "step_id": step_id, "direction": "ccw"}}
            raw_key = 4 if step_id == "ENCODER-CLICK" else int(step_id.rsplit("-", 1)[1]) - 1
            return {"payload": {"kind": "key_transition", "step_id": step_id, "key": raw_key}}

    with TemporaryDirectory() as directory:
        writer = EvidenceWriter(Path(directory), "test-run")
        run = GuidedRun(FakeSession(), writer, TerminalUI(), "test-run")
        run.start()
        run.stimulate()
        try:
            run.respond("Y")
        except ValueError:
            pass
        else:
            raise AssertionError("Enter alone must not confirm")
        if run.respond(f"Y IDENTIFY {run.run_suffix}") != "pass":
            raise AssertionError("explicit human confirmation did not pass")
        if run.history[0]["machine_status"] != "acknowledged" or run.history[0]["physical_status"] != "pass":
            raise AssertionError("machine and physical evidence were not kept distinct")
        for _ in range(4):
            run.stimulate()
            run.respond(f"Y {run.step_id} {run.run_suffix}")
        run.stimulate()
        expected_event = "observed event: key_transition; key index: 0"
        if expected_event not in run.ui.last_screen:
            raise AssertionError("key event detail was not visible before confirmation")
        if any(len(line) > 80 for line in run.ui.last_screen.splitlines()):
            raise AssertionError("key event detail exceeded the 80-column bound")


def batch_order_check() -> None:
    if BATCH_GATE_ORDER != ("Identify", "Displays", "Keys", "Encoder", "LEDs", "Brightness", "Reboot"):
        raise AssertionError("batch gates must stop after Reboot")
    counts = tuple(len(gate.rows) for gate in GATES[:7])
    if counts != (1, 4, 4, 3, 14, 3, 1):
        raise AssertionError(f"batch row counts changed: {counts}")
    if any(gate.rows for gate in GATES[7:]):
        raise AssertionError("dependent gates must remain unstarted")


def batch_parser_check() -> None:
    from .ui import parse_batch_response

    if parse_batch_response("Y DISPLAYS ABC123", "Displays", "ABC123") is None:
        raise AssertionError("valid batch group response was rejected")
    for text in ("Y DISPLAYS", "Y KEYS ABC123", "Y DISPLAYS WRONG", "Y DISPLAYS ABC123 extra"):
        if parse_batch_response(text, "Displays", "ABC123") is not None:
            raise AssertionError(f"invalid batch group response was accepted: {text}")


def batch_key_event_check() -> None:
    from tempfile import TemporaryDirectory
    from .evidence import EvidenceWriter

    class FakeSession:
        def hello(self):
            return MachineFact("acknowledged", time.time(), 1)

        def stimulate(self, step_id, panel, stimulus):
            return MachineFact("acknowledged", time.time(), 1)

        def wait_event(self, step_id):
            if step_id == "ENCODER-CW":
                return {"payload": {"kind": "encoder_transition", "step_id": step_id, "direction": "cw"}}
            if step_id == "ENCODER-CCW":
                return {"payload": {"kind": "encoder_transition", "step_id": step_id, "direction": "ccw"}}
            raw_key = 4 if step_id == "ENCODER-CLICK" else int(step_id.rsplit("-", 1)[1]) - 1
            return {"payload": {"kind": "key_transition", "step_id": step_id, "key": raw_key}}

    with TemporaryDirectory() as directory:
        run = BatchRun(FakeSession(), EvidenceWriter(Path(directory), "batch-keys"), TerminalUI(), "batch-keys", dwell_seconds=0)
        run.start()
        run.gate_index = 2
        observations = run.stimulate_gate()
        if [item.machine_details["event"]["key"] for item in observations] != [0, 1, 2, 3]:
            raise AssertionError("operator KEY-1..KEY-4 did not retain raw key indices 0..3")
        if run.respond(f"Y KEYS {run.run_suffix}") != "pass":
            raise AssertionError("key gate group confirmation did not pass")
        if [row["observed_value"]["event"]["key"] for row in run.history] != [0, 1, 2, 3]:
            raise AssertionError("raw key indices were not retained in key evidence")

        click_observations = run.stimulate_gate()
        encoder_events = [item.machine_details.get("event", {}) for item in click_observations]
        if [event.get("direction") for event in encoder_events[:2]] != ["cw", "ccw"]:
            raise AssertionError("encoder direction events were not compared against the requested signals")
        click_event = encoder_events[-1]
        if click_event.get("key") != 4:
            raise AssertionError("ENC-CLICK did not validate raw key index 4")
        if "key index: 4" not in run.ui.last_screen:
            raise AssertionError("raw encoder click key index was not visible in bounded batch screen")
        if run.respond(f"Y ENCODER {run.run_suffix}") != "pass":
            raise AssertionError("encoder group confirmation did not pass")


def batch_no_ack_check() -> None:
    from tempfile import TemporaryDirectory
    from .evidence import EvidenceWriter

    class RejectingSession:
        def hello(self):
            return MachineFact("rejected", time.time(), 1, "device rejected probe")

    with TemporaryDirectory() as directory:
        run = BatchRun(RejectingSession(), EvidenceWriter(Path(directory), "batch-no-ack"), TerminalUI(), "batch-no-ack", dwell_seconds=0)
        run.start()
        run.stimulate_gate()
        try:
            run.respond(f"Y IDENTIFY {run.run_suffix}")
        except ValueError:
            pass
        else:
            raise AssertionError("ACK-only or rejected group PASS was accepted")
        if run.history:
            raise AssertionError("failed group PASS wrote physical evidence")
        if run.respond(f"N IDENTIFY {run.run_suffix}") != "fail" or run.history[0]["physical_status"] != "failed":
            raise AssertionError("group N did not preserve the failed machine attempt")
