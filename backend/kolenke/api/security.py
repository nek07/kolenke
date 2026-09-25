"""The server acts on your hh account and Gmail, so only kolenke's own page on this computer may use it:
- Host must be localhost (blocks DNS-rebinding pages from reading data);
- state-changing requests need the X-JobBot header, which other sites can't send without a CORS preflight
  that this server never allows (blocks cross-site «click here» requests).
The Next.js server proxies /api to this one on localhost, so both checks hold for the page as well."""
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

LOCAL_HOSTS = {"127.0.0.1", "localhost"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def _hostname(value: str) -> str:
    return value.split("//")[-1].rsplit(":", 1)[0].strip("[]")


class LocalOnlyMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        if _hostname(request.headers.get("host") or "") not in LOCAL_HOSTS:
            return JSONResponse({"detail": "Доступ только с этого компьютера"}, status_code=403)
        if request.method not in SAFE_METHODS:
            origin = request.headers.get("origin")
            if request.headers.get("x-jobbot") != "1" or (origin and _hostname(origin) not in LOCAL_HOSTS):
                return JSONResponse({"detail": "Запрос отклонён"}, status_code=403)
        return await call_next(request)
