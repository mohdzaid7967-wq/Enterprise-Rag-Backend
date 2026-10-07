from fastapi import Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError

async def custom_http_exception_handler(request: Request, exc: HTTPException):
    req_id = getattr(request.state, "request_id", "UNKNOWN")
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "status_code": exc.status_code,
                "code": "HTTP_ERROR",
                "message": exc.detail,
                "request_id": req_id,
            }
        },
    )

async def validation_exception_handler(request: Request, exc: RequestValidationError):
    req_id = getattr(request.state, "request_id", "UNKNOWN")
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "status_code": 422,
                "code": "VALIDATION_ERROR",
                "message": "Invalid request schema or parameters",
                "details": exc.errors(),
                "request_id": req_id,
            }
        },
    )