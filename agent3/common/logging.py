"""common/logging.py — Mission 16.

One shared logger every module uses, so every log line carries the same
structured context (scan_id, url, etc.).

Usage (structured, event + key/value fields):
    from agent3.common import logging as log
    log.info("scan_started", scan_id=scan_id, company_id=company_id)
    log.warning("page_scan_failed", url=page_url, reason="timeout")
"""

import logging
import sys

_LOGGER_NAME = "agent3"


def _build_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:  # avoid adding duplicate handlers on re-import
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            logging.Formatter("%(asctime)s %(levelname)-7s %(name)s %(message)s")
        )
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
        logger.propagate = False
    return logger


_logger = _build_logger()


def _format(event: str, **fields) -> str:
    """Render an event name plus key=value context into one log line."""
    if not fields:
        return event
    context = " ".join(f"{key}={value}" for key, value in fields.items())
    return f"{event} | {context}"


def debug(event: str, **fields) -> None:
    _logger.debug(_format(event, **fields))


def info(event: str, **fields) -> None:
    _logger.info(_format(event, **fields))


def warning(event: str, **fields) -> None:
    _logger.warning(_format(event, **fields))


def error(event: str, **fields) -> None:
    _logger.error(_format(event, **fields))


def get_logger() -> logging.Logger:
    """Return the underlying stdlib logger (for tests or advanced config)."""
    return _logger
