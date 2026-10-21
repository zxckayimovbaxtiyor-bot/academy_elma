"""Response policy for private API data, including errors and temporary passwords."""

from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Receive, Scope, Send


class PrivateResponseMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        async def private_send(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["Cache-Control"] = "no-store"
                headers["X-Content-Type-Options"] = "nosniff"
            await send(message)

        private = scope["type"] == "http" and scope.get("path", "").startswith(("/api/", "/media/"))
        await self.app(scope, receive, private_send if private else send)
