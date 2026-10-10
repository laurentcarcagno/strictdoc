"""
Response headers for SVG files that the application serves.

An SVG opened directly (not through <img>) is a document of the application's
own origin. The policy below keeps it from running script or loading anything,
and nosniff keeps the browser from guessing another type. Use as an <img> is
not affected.
"""

from typing import List, Tuple

from starlette.types import ASGIApp, Message, Receive, Scope, Send

SVG_CONTENT_TYPE = b"image/svg+xml"
SVG_CSP = "default-src 'none'; style-src 'unsafe-inline'; sandbox"


class SvgHeadersMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers: List[Tuple[bytes, bytes]] = list(
                    message.get("headers", [])
                )
                content_type = next(
                    (
                        value
                        for name, value in headers
                        if name.lower() == b"content-type"
                    ),
                    b"",
                )
                if content_type.lower().startswith(SVG_CONTENT_TYPE):
                    headers = [
                        (name, value)
                        for name, value in headers
                        if name.lower()
                        not in (
                            b"content-security-policy",
                            b"x-content-type-options",
                        )
                    ]
                    headers.append(
                        (b"content-security-policy", SVG_CSP.encode())
                    )
                    headers.append((b"x-content-type-options", b"nosniff"))
                    message = {**message, "headers": headers}
            await send(message)

        await self.app(scope, receive, send_with_headers)
