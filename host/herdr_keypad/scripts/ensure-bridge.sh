#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUNTIME=${XDG_RUNTIME_DIR:-"$HOME/.cache"}
STATE="$RUNTIME/herdr-keypad"
LOCK="$STATE/bridge.lock"
PIDFILE="$STATE/bridge.pid"
mkdir -p "$STATE"
chmod 700 "$STATE"

if [ "${1:-}" = "stop-for-acceptance" ]; then
    if [ ! -s "$PIDFILE" ]; then
        echo "herdr-keypad bridge is not owned by this guard" >&2
        exit 1
    fi
    pid=$(cat "$PIDFILE")
    case "$pid" in
        ''|*[!0-9]*) echo "invalid bridge pid" >&2; exit 1 ;;
    esac
    if [ ! -r "/proc/$pid/cmdline" ] || [ ! -e "/proc/$pid/fd/9" ]; then
        echo "bridge ownership no longer matches" >&2
        exit 1
    fi
    cmd=$(tr '\000' ' ' < "/proc/$pid/cmdline")
    lock_target=$(readlink "/proc/$pid/fd/9" 2>/dev/null || true)
    case "$cmd" in
        *herdr_keypad* ) : ;;
        *) echo "bridge ownership no longer matches" >&2; exit 1 ;;
    esac
    [ "$lock_target" = "$LOCK" ] || { echo "bridge lock ownership no longer matches" >&2; exit 1; }
    kill -TERM "$pid"
    i=0
    while kill -0 "$pid" 2>/dev/null && [ "$i" -lt 50 ]; do
        i=$((i + 1)); sleep 0.1
    done
    if kill -0 "$pid" 2>/dev/null; then
        echo "bridge did not stop within bounded timeout" >&2
        exit 1
    fi
    rm -f "$PIDFILE"
    exit 0
fi
if [ "${1:-}" = "run-exclusive" ]; then
    shift
    [ "${1:-}" = "--" ] || { echo "usage: run-exclusive -- COMMAND [ARG...]" >&2; exit 2; }
    shift
    [ "$#" -gt 0 ] || { echo "run-exclusive requires a command" >&2; exit 2; }
    "$ROOT/scripts/ensure-bridge.sh" stop-for-acceptance
    wrapped_status=0
    cleanup_status=0
    cleanup() {
        trap - EXIT HUP INT TERM
        set +e
        "$ROOT/scripts/ensure-bridge.sh" >/dev/null 2>&1 &
        restart_pid=$!
        i=0
        while [ "$i" -lt 50 ]; do
            if [ -s "$PIDFILE" ] && kill -0 "$(cat "$PIDFILE" 2>/dev/null)" 2>/dev/null &&
                [ -r "/proc/$(cat "$PIDFILE")/fd/9" ] &&
                [ "$(readlink "/proc/$(cat "$PIDFILE")/fd/9" 2>/dev/null)" = "$LOCK" ]; then
                wait "$restart_pid" 2>/dev/null
                exit "$wrapped_status"
            fi
            if ! kill -0 "$restart_pid" 2>/dev/null; then break; fi
            i=$((i + 1)); sleep 0.1
        done
        wait "$restart_pid" 2>/dev/null
        echo "guarded bridge ownership was not restored" >&2
        cleanup_status=125
        exit "$cleanup_status"
    }
    on_hup() { wrapped_status=129; exit "$wrapped_status"; }
    on_int() { wrapped_status=130; exit "$wrapped_status"; }
    on_term() { wrapped_status=143; exit "$wrapped_status"; }
    trap cleanup EXIT
    trap on_hup HUP
    trap on_int INT
    trap on_term TERM
    "$@"
    wrapped_status=$?
    exit "$wrapped_status"
fi

# The lock is held across exec, so the Python bridge itself is the sole owner.
exec 9>"$LOCK"
if ! flock -n 9; then
    exit 0
fi
export HERDR_KEYPAD_PIDFILE="$PIDFILE"
printf '%s\n' "$$" > "$PIDFILE"
trap 'rm -f "$PIDFILE"' EXIT HUP INT TERM
PYTHON=${HERDR_KEYPAD_PYTHON:-"$ROOT/../../tools/phase1_bringup/.venv/bin/python"}
[ -x "$PYTHON" ] || PYTHON=${PYTHON_FALLBACK:-python3}
export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec "$PYTHON" -m herdr_keypad --run-bridge --binding "${HERDR_KEYPAD_BINDING:-$HOME/.config/herdr/keypad-binding.json}"
