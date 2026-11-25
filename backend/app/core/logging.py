"""Structured logging with redaction.

Log events and identifiers, never personal content. Any extra field whose name looks
sensitive (token, cookie, secret, password, key, session, authorization) is redacted.
"""

import json
import logging
import re
import sys
from contextvars import ContextVar
from datetime import UTC, datetime

request_id_var: ContextVar[str | None] = ContextVar("request_id", default=None)

_SENSITIVE = re.compile(
    r"(authorization|cookie|token|secret|password|api[_-]?key|session|verifier|credential)",
    re.IGNORECASE,
)
_STANDARD = set(logging.LogRecord("", 0, "", 0, "", None, None).__dict__) | {"message", "asctime"}
REDACTED = "[REDACTED]"


def redact(fields: dict[str, object]) -> dict[str, object]:
    return {key: (REDACTED if _SENSITIVE.search(key) else value) for key, value in fields.items()}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        request_id = request_id_var.get()
        if request_id:
            payload["request_id"] = request_id
        extras = {k: v for k, v in record.__dict__.items() if k not in _STANDARD}
        payload.update(redact(extras))
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level.upper())
    # Uvicorn's own access log duplicates ours (and would print query strings).
    logging.getLogger("uvicorn.access").disabled = True
