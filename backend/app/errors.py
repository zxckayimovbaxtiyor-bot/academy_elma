"""API errors carry a stable code plus parameters; the browser turns them into uz/ru text.

The backend never returns user-facing sentences, so every learner-facing string
stays in the frontend i18n files.
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException


class AppError(Exception):
    def __init__(self, status: int, code: str, params: dict[str, Any] | None = None):
        super().__init__(code)
        self.status = status
        self.code = code
        self.params = params or {}


def not_found(entity: str) -> AppError:
    return AppError(404, f"{entity}.not_found")


def _body(code: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"error": {"code": code, "params": params or {}}}


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError) -> JSONResponse:
        return JSONResponse(_body(exc.code, exc.params), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = [
            {"loc": [str(part) for part in err.get("loc", ())], "type": err.get("type", "")}
            for err in exc.errors()
        ]
        return JSONResponse(_body("request.invalid", {"fields": fields}), status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(_body(f"http.{exc.status_code}"), status_code=exc.status_code)
