import secrets
import string
import threading

from agents import TracingProcessor, Trace, Span
from database import write_log, make_key

ALPHANUM = string.ascii_lowercase + string.digits


# Maps trace_id -> (session_id, trader_name). Populated by Trader before each
# run and read by the global LogTracer to route writes to per-session logs.
_TRACE_REGISTRY: dict[str, tuple[str, str]] = {}
_TRACE_LOCK = threading.Lock()


def make_trace_id(tag: str) -> str:
    """Return a string of the form 'trace_<tag><random>' (32 chars after prefix)."""
    tag += "0"
    pad_len = 32 - len(tag)
    random_suffix = "".join(secrets.choice(ALPHANUM) for _ in range(pad_len))
    return f"trace_{tag}{random_suffix}"


def register_trace(trace_id: str, session_id: str, name: str) -> None:
    with _TRACE_LOCK:
        _TRACE_REGISTRY[trace_id] = (session_id, name.lower())


def forget_trace(trace_id: str) -> None:
    with _TRACE_LOCK:
        _TRACE_REGISTRY.pop(trace_id, None)


class LogTracer(TracingProcessor):
    def _lookup(self, trace_or_span: Trace | Span) -> tuple[str, str] | None:
        trace_id = trace_or_span.trace_id
        with _TRACE_LOCK:
            return _TRACE_REGISTRY.get(trace_id)

    def _log_key(self, trace_or_span: Trace | Span) -> str | None:
        ident = self._lookup(trace_or_span)
        if not ident:
            return None
        session_id, name = ident
        return make_key(name, session_id)

    def on_trace_start(self, trace) -> None:
        key = self._log_key(trace)
        if key:
            write_log(key, "trace", f"Started: {trace.name}")

    def on_trace_end(self, trace) -> None:
        key = self._log_key(trace)
        if key:
            write_log(key, "trace", f"Ended: {trace.name}")

    def on_span_start(self, span) -> None:
        key = self._log_key(span)
        type_ = span.span_data.type if span.span_data else "span"
        if key:
            message = "Started"
            if span.span_data:
                if span.span_data.type:
                    message += f" {span.span_data.type}"
                if hasattr(span.span_data, "name") and span.span_data.name:
                    message += f" {span.span_data.name}"
                if hasattr(span.span_data, "server") and span.span_data.server:
                    message += f" {span.span_data.server}"
            if span.error:
                message += f" {span.error}"
            write_log(key, type_, message)

    def on_span_end(self, span) -> None:
        key = self._log_key(span)
        type_ = span.span_data.type if span.span_data else "span"
        if key:
            message = "Ended"
            if span.span_data:
                if span.span_data.type:
                    message += f" {span.span_data.type}"
                if hasattr(span.span_data, "name") and span.span_data.name:
                    message += f" {span.span_data.name}"
                if hasattr(span.span_data, "server") and span.span_data.server:
                    message += f" {span.span_data.server}"
            if span.error:
                message += f" {span.error}"
            write_log(key, type_, message)

    def force_flush(self) -> None:
        pass

    def shutdown(self) -> None:
        pass
