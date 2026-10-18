"""Request body size cap.

Pure ASGI, like security_headers: bytes are counted as they arrive, so an
oversized upload is cut off at the limit instead of being spooled in full.
Chunked requests carry no Content-Length, hence the count and not just the header.
"""

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        detail = f"File too large: the limit is {self.max_bytes // 2**20} MB."
        declared = Headers(scope=scope).get("content-length", "")
        if declared.isdigit() and int(declared) > self.max_bytes:
            await JSONResponse({"detail": detail}, status_code=413)(scope, receive, send)
            return

        received = 0

        async def limited_receive() -> Message:
            nonlocal received
            message = await receive()
            received += len(message.get("body", b""))
            if received > self.max_bytes:
                # FastAPI re-raises an HTTPException from body parsing → a plain 413.
                raise HTTPException(413, detail)
            return message

        await self.app(scope, limited_receive, send)
