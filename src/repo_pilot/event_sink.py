from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Any, Callable


TraceSink = Callable[[str, dict[str, Any]], None]

_trace_sink: ContextVar[TraceSink | None] = ContextVar(
    "repopilot_trace_sink",
    default=None,
)


def set_trace_sink(sink: TraceSink) -> Token[TraceSink | None]:
    return _trace_sink.set(sink)


def reset_trace_sink(token: Token[TraceSink | None]) -> None:
    _trace_sink.reset(token)


def emit_trace_event(event_type: str, payload: dict[str, Any]) -> None:
    sink = _trace_sink.get()
    if sink is not None:
        sink(event_type, payload)
