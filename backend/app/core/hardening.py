"""Response headers and request screening applied to every API call.

* Security headers. The API answered with none: no `nosniff` (a browser may
  sniff an uploaded file into something executable), no HSTS, nothing against
  framing. JSON responses also get a CSP that allows nothing — they are data,
  never a page.
* NUL bytes. A `\\x00` in a query string reached PostgreSQL, which refuses NUL
  in text, and six list endpoints answered 500 (QA security probe SEC-4). It is
  never meaningful input, so it is refused up front with a 400.

A pure ASGI middleware: no request body buffering, nothing on the hot path but
a header list.
"""
from __future__ import annotations

import json

from app.core.config import settings

_BASE_HEADERS = [
    (b"x-content-type-options", b"nosniff"),
    (b"x-frame-options", b"DENY"),
    (b"referrer-policy", b"no-referrer"),
    (b"permissions-policy", b"camera=(), microphone=(), geolocation=()"),
]
_JSON_CSP = (b"content-security-policy", b"default-src 'none'; frame-ancestors 'none'")
_HSTS = (b"strict-transport-security", b"max-age=31536000; includeSubDomains")


class HardeningMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)

        raw = scope.get("query_string", b"").lower() + scope.get("raw_path", b"").lower()
        if b"%00" in raw or b"\x00" in raw or "\x00" in scope.get("path", ""):
            body = json.dumps({"error": {"code": "bad_request",
                                         "message": "The request contains an invalid character."}}).encode()
            await send({"type": "http.response.start", "status": 400,
                        "headers": [(b"content-type", b"application/json"),
                                    (b"content-length", str(len(body)).encode()), *_BASE_HEADERS]})
            await send({"type": "http.response.body", "body": body})
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                present = {k.lower() for k, _ in headers}
                extra = [h for h in _BASE_HEADERS if h[0] not in present]
                content_type = dict(headers).get(b"content-type", b"")
                if content_type.startswith(b"application/json") and _JSON_CSP[0] not in present:
                    extra.append(_JSON_CSP)
                if settings.ENVIRONMENT == "production":
                    extra.append(_HSTS)
                message = {**message, "headers": headers + extra}
            await send(message)

        await self.app(scope, receive, send_with_headers)
