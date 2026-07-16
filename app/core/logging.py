"""Structured (JSON-lines) logging setup using only the stdlib."""

import json
import logging
import time


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created)),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        # Extra fields passed via logger.info(..., extra={"ctx": {...}})
        ctx = getattr(record, "ctx", None)
        if ctx:
            payload.update(ctx)
        return json.dumps(payload, default=str)


def configure_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler()
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())
    # Keep uvicorn's access log from double-printing through the root handler.
    logging.getLogger("uvicorn.access").propagate = False
