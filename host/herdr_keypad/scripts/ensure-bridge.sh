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
