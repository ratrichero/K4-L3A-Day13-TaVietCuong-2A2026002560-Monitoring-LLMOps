from __future__ import annotations

import os
from contextlib import contextmanager
from typing import Any

try:
    from langfuse import get_client, observe, propagate_attributes

    LANGFUSE_SDK_AVAILABLE = True
except ImportError:  # pragma: no cover - chỉ dùng khi chưa cài requirements
    LANGFUSE_SDK_AVAILABLE = False

    def observe(*args: Any, **kwargs: Any):
        def decorator(func):
            return func

        return decorator

    class _DummyClient:
        def update_current_span(self, **kwargs: Any) -> None:
            return None

        def update_current_generation(self, **kwargs: Any) -> None:
            return None

        def start_as_current_observation(self, **kwargs: Any):
            from contextlib import nullcontext

            return nullcontext()

    def get_client():
        return _DummyClient()

    @contextmanager
    def propagate_attributes(**kwargs: Any):
        yield


# SDK v4 dùng LANGFUSE_TIMEOUT cho CẢ API client (giây) và OTLPSpanExporter
# (mà OTel diễn giải là MILLISECONDS). Default 5 => export span chỉ có 5ms,
# nên batch export hay "Read timed out" và trace mất quietly.
# Fix: nếu người dùng không tự set, đẩy lên 30000ms và khởi tạo client SAU
# khi biến này có mặt.
_OTLP_TIMEOUT_MS = int(os.getenv("LANGFUSE_OTLP_TIMEOUT_MS", "30000"))
if not os.getenv("LANGFUSE_TIMEOUT"):
    os.environ["LANGFUSE_TIMEOUT"] = str(_OTLP_TIMEOUT_MS)

# Lưu ý import order (best practice của Langfuse): các SDK instrumentation
# phải được import SAU khi env vars sẵn sàng. get_client() gọi lần đầu trong
# `_client_ready()` dưới đây, sau khi .env đã được load.
_client_ready = False


def ensure_client() -> Any:
    """Lấy client Langfuse (khởi tạo lần đầu sau khi env đã load xong)."""
    global _client_ready
    client = get_client()
    if not _client_ready:
        _client_ready = True
        if tracing_enabled():
            try:
                ok = bool(client.auth_check())
                print(
                    f"[langfuse] init ok | base_url={os.getenv('LANGFUSE_BASE_URL')}"
                    f" | auth_check={ok}"
                    f" | otlp_timeout_ms={os.environ.get('LANGFUSE_TIMEOUT')}",
                    flush=True,
                )
            except Exception as exc:
                print(
                    f"[langfuse] auth_check FAILED: {type(exc).__name__}: {exc}",
                    flush=True,
                )
    return client


def get_langfuse_client():
    return ensure_client()


def tracing_enabled() -> bool:
    return LANGFUSE_SDK_AVAILABLE and bool(
        os.getenv("LANGFUSE_PUBLIC_KEY") and os.getenv("LANGFUSE_SECRET_KEY")
    )
