# shared/logging/logger.py
# Structured JSON logger used by all services.
# Every log line is valid JSON — queryable by Grafana/CloudWatch.

import logging
import json
import os
from datetime import datetime


class StructuredFormatter(logging.Formatter):
    """
    Formats every log line as a JSON object.
    Attach extra fields via: logger.info("msg", extra={"call_id": "..."})
    """
    def format(self, record: logging.LogRecord) -> str:
        log = {
            "ts":      datetime.utcnow().isoformat(),
            "level":   record.levelname,
            "service": record.name,
            "message": record.getMessage(),
        }
        # Attach any extra fields passed by the caller
        for key in ("call_id", "session_id", "event_type",
                    "latency_ms", "intent", "outcome", "order_id"):
            if hasattr(record, key):
                log[key] = getattr(record, key)

        # Attach exception info if present
        if record.exc_info:
            log["exception"] = self.formatException(record.exc_info)

        return json.dumps(log, ensure_ascii=False)


def get_logger(name: str) -> logging.Logger:
    """
    Returns a structured logger for the given service name.
    Call this once per module:  logger = get_logger(__name__)
    """
    logger = logging.getLogger(name)

    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(StructuredFormatter())
        logger.addHandler(handler)

        level = os.getenv("LOG_LEVEL", "INFO").upper()
        logger.setLevel(getattr(logging, level, logging.INFO))

    return logger

