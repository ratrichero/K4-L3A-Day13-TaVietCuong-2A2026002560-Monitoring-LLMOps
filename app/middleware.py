from __future__ import annotations

import re
import time
import uuid

from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from structlog.contextvars import bind_contextvars, clear_contextvars

_REQUEST_ID_HEADER = "x-request-id"
_VALID_REQUEST_ID = re.compile(r"^req-[0-9a-f]{8}$")


def new_correlation_id() -> str:
    """Sinh correlation ID mới theo format req-<8-hex>."""
    return f"req-{uuid.uuid4().hex[:8]}"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Xóa context cũ để không rò correlation/metadata giữa các request
        clear_contextvars()

        # Nhận x-request-id do client truyền nếu đúng format, không thì sinh mới
        incoming = request.headers.get(_REQUEST_ID_HEADER, "").strip()
        if _VALID_REQUEST_ID.match(incoming):
            correlation_id = incoming
        else:
            correlation_id = new_correlation_id()

        bind_contextvars(correlation_id=correlation_id)
        request.state.correlation_id = correlation_id

        start = time.perf_counter()
        response = await call_next(request)
        response_time_ms = round((time.perf_counter() - start) * 1000, 2)

        # Trả lại correlation ID và thời gian xử lý để client/observability nối dây
        response.headers[_REQUEST_ID_HEADER] = correlation_id
        response.headers["x-response-time-ms"] = f"{response_time_ms}"

        return response
