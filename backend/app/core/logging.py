from __future__ import annotations

import logging
from contextvars import ContextVar, Token

_request_id_var: ContextVar[str] = ContextVar("request_id", default="-")


class RequestIdFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = _request_id_var.get("-")
        return True


def configure_logging() -> None:
    root = logging.getLogger()
    if not root.handlers:
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(name)s request_id=%(request_id)s %(message)s",
        )
        root = logging.getLogger()
    for handler in root.handlers:
        has_filter = any(isinstance(f, RequestIdFilter) for f in handler.filters)
        if not has_filter:
            handler.addFilter(RequestIdFilter())


def set_request_id(request_id: str) -> Token:
    return _request_id_var.set(request_id)


def reset_request_id(token: Token) -> None:
    _request_id_var.reset(token)

