"""Exception domain CePu, dipetakan ke kode error kontrak API."""
from fastapi import Request, status
from fastapi.responses import JSONResponse


class CePuError(Exception):
    status_code: int = status.HTTP_400_BAD_REQUEST
    error_code: str = "bad_request"

    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


class EmptyPayloadError(CePuError):
    status_code = status.HTTP_400_BAD_REQUEST
    error_code = "empty_payload"


class PayloadTooLargeError(CePuError):
    status_code = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    error_code = "payload_too_large"


class UnsupportedMediaTypeError(CePuError):
    status_code = status.HTTP_415_UNSUPPORTED_MEDIA_TYPE
    error_code = "unsupported_media_type"


class RateLimitExceededError(CePuError):
    status_code = status.HTTP_429_TOO_MANY_REQUESTS
    error_code = "rate_limit_exceeded"


class ModelNotReadyError(CePuError):
    status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    error_code = "model_not_ready"


class InvalidInternalTokenError(CePuError):
    status_code = status.HTTP_401_UNAUTHORIZED
    error_code = "invalid_internal_token"


async def cepu_error_handler(request: Request, exc: CePuError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={"error": exc.error_code, "message": exc.message},
    )


def register_exception_handlers(app) -> None:
    app.add_exception_handler(CePuError, cepu_error_handler)
