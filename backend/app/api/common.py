from __future__ import annotations

from fastapi import Depends, Request, Response

from app.errors import AppError


def csv_response(text: str, filename: str) -> Response:
    return Response(
        content=text.encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def body_reader(max_bytes: int, error_code: str, authorize):
    """Dependency that reads a raw request body (no multipart) up to ``max_bytes``."""

    async def read(request: Request, _=Depends(authorize)) -> bytes:
        data = bytearray()
        async for chunk in request.stream():
            data += chunk
            if len(data) > max_bytes:
                raise AppError(413, error_code, {"max_mb": max_bytes // (1024 * 1024)})
        return bytes(data)

    return read
