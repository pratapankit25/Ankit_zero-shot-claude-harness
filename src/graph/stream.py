"""Per-run event emitters — bridge graph nodes to SSE consumers and tests.

The runner registers a callback per run_id; nodes publish events through emit().
Unregistered run_ids are a silent no-op (e.g. the non-streaming endpoint).
"""
import threading
from collections.abc import Callable

_lock = threading.Lock()
_emitters: dict[str, Callable[[dict], None]] = {}


def register(run_id: str, callback: Callable[[dict], None]) -> None:
    with _lock:
        _emitters[run_id] = callback


def unregister(run_id: str) -> None:
    with _lock:
        _emitters.pop(run_id, None)


def emit(run_id: str, event: dict) -> None:
    with _lock:
        cb = _emitters.get(run_id)
    if cb is not None:
        try:
            cb(event)
        except Exception:
            pass  # a broken consumer must never fail the run


def emit_step(state: dict, label_en: str, label_hi: str, status: str, detail: str | None = None) -> dict:
    """Append a step to state and publish it. Returns the step dict."""
    step = {"label_en": label_en, "label_hi": label_hi, "status": status, "detail": detail}
    state.setdefault("steps", []).append(step)
    emit(state.get("run_id", ""), {"type": "step", **step})
    return step
