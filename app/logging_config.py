import logging
import time
import uuid
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request, Response

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [ReqID: %(request_id)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("enterprise_rag")

class RequestTracingFilter(logging.Filter):
    def filter(self, record):
        if not hasattr(record, "request_id"):
            record.request_id = "SYSTEM"
        return True

for handler in logging.root.handlers:
    handler.addFilter(RequestTracingFilter())


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        req_id = request.headers.get("X-Request-ID", str(uuid.uuid4())[:8])
        request.state.request_id = req_id

        # Sanitize query parameters before logging
        query_params = dict(request.query_params)
        for key in list(query_params.keys()):
            if any(secret in key.lower() for secret in ("token", "password", "secret", "key")):
                query_params[key] = "[REDACTED]"

        start_time = time.perf_counter()
        
        # Log incoming request
        extra = {"request_id": req_id}
        logger.info(f"Incoming -> {request.method} {request.url.path} {query_params if query_params else ''}", extra=extra)

        try:
            response: Response = await call_next(request)
            duration_ms = (time.perf_counter() - start_time) * 1000
            response.headers["X-Request-ID"] = req_id
            logger.info(
                f"Completed -> {request.method} {request.url.path} Status: {response.status_code} ({duration_ms:.2f}ms)",
                extra=extra
            )
            return response
        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000
            logger.error(
                f"Failed -> {request.method} {request.url.path} Error: {str(exc)} ({duration_ms:.2f}ms)",
                extra=extra
            )
            raise