"""RFC 7807 Problem Details 공통 에러 포맷 (03-system-design.md §4.1)."""
from fastapi import Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, status_code: int, code: str, title: str, detail: str):
        self.status_code = status_code
        self.code = code
        self.title = title
        self.detail = detail


def _problem(status_code: int, code: str, title: str, detail: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "type": "about:blank",
            "title": title,
            "status": status_code,
            "detail": detail,
            "code": code,
        },
    )


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return _problem(exc.status_code, exc.code, exc.title, exc.detail)


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _problem(
        status.HTTP_422_UNPROCESSABLE_ENTITY,
        "VALIDATION_ERROR",
        "Validation Error",
        str(exc.errors()),
    )
