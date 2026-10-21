"""Writes must carry the X-Requested-With header.

Browsers can't add a custom header to a cross-site request without a CORS
preflight, and no CORS is enabled, so together with the SameSite=Strict
cookie this blocks cross-site request forgery. Pure ASGI, so large
uploads stream through untouched.
"""

from __future__ import annotations

import json

from starlette.types import ASGIApp, Receive, Scope, Send

SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
HEADER = b"x-requested-with"


class CsrfHeaderMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["method"] not in SAFE_METHODS:
            if not any(name == HEADER for name, _ in scope.get("headers", [])):
                body = json.dumps({"error": {"code": "auth.csrf", "params": {}}}).encode()
                await send(
                    {
                        "type": "http.response.start",
                        "status": 403,
                        "headers": [
                            (b"content-type", b"application/json"),
                            (b"content-length", str(len(body)).encode()),
                        ],
                    }
                )
                await send({"type": "http.response.body", "body": body})
                return
        await self.app(scope, receive, send)
