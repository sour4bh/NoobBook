"""Security headers for generated HTML previews."""

from flask import Response


_PREVIEW_CSP = "; ".join(
    [
        "default-src 'self'",
        "img-src 'self' data: blob:",
        "style-src 'self' 'unsafe-inline'",
        "script-src 'self' 'unsafe-inline'",
        "font-src 'self' data:",
        "media-src 'self' data: blob:",
        "connect-src 'self'",
        "frame-ancestors 'self'",
    ]
)


def html_preview_response(content: str) -> Response:
    response = Response(content, mimetype="text/html")
    response.headers["Content-Security-Policy"] = _PREVIEW_CSP
    response.headers["Referrer-Policy"] = "no-referrer"
    return response
