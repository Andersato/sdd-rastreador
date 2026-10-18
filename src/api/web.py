"""Página web del mapa servida en `/` (map-view, design.md D3 y D4).

`WebFiles` sirve los archivos de `web/` y nunca atiende rutas de `/api/`:
para ellas responde lo mismo que respondería la API sin la web montada
(405 con `Allow: GET`, 307 a la ruta sin barra final o 404). Sin esto, el
montaje en `/` se llevaría las peticiones que la API no admite, porque en
Starlette un montaje que casa del todo gana a una ruta que solo casa en la
ruta y no en el método.
"""

from starlette.datastructures import URL, MutableHeaders
from starlette.exceptions import HTTPException
from starlette.responses import RedirectResponse
from starlette.routing import BaseRoute, Match
from starlette.staticfiles import StaticFiles
from starlette.types import Receive, Scope, Send

METHOD_MESSAGE = "solo se admiten GET y HEAD"

# Solo recursos propios y las teselas de OpenStreetMap (design.md D4).
CONTENT_SECURITY_POLICY = (
    "default-src 'none'; script-src 'self'; style-src 'self'; "
    "img-src 'self' data: https://tile.openstreetmap.org; connect-src 'self'; "
    "font-src 'self'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
)
WEB_HEADERS = {
    # Revalidar siempre (ETag/Last-Modified): una versión nueva de web/ se ve al recargar.
    "Cache-Control": "no-cache",
    "X-Content-Type-Options": "nosniff",
    # Las teselas llevan `Referer: http://127.0.0.1:<puerto>/`, sin la ruta.
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Content-Security-Policy": CONTENT_SECURITY_POLICY,
}


class WebFiles(StaticFiles):
    def __init__(self, *, directory, api_routes: list[BaseRoute]):
        super().__init__(directory=directory, html=True)
        self.api_routes = api_routes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] == "http" and scope["path"].startswith("/api/"):
            response = self.api_fallback(scope)
            await response(scope, receive, send)
            return

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                for name, value in WEB_HEADERS.items():
                    headers[name] = value
            await send(message)

        try:
            await super().__call__(scope, receive, send_with_headers)
        except HTTPException as exc:
            # Sus errores (404, 405) los responde el manejador común de la app;
            # llevan también las cabeceras de la web (design.md D3).
            raise HTTPException(exc.status_code, exc.detail,
                                headers={**(exc.headers or {}), **WEB_HEADERS}) from exc

    def _matches(self, scope: Scope) -> Match:
        best = Match.NONE
        for route in self.api_routes:
            match, _ = route.matches(scope)
            if match == Match.FULL:
                return Match.FULL
            if match == Match.PARTIAL:
                best = Match.PARTIAL
        return best

    def api_fallback(self, scope: Scope):
        """Lo que respondería la API sin la web: 405, 307 o 404."""
        if self._matches(scope) == Match.PARTIAL:
            raise HTTPException(status_code=405, headers={"Allow": "GET"})
        path = scope["path"]
        if path.endswith("/"):
            stripped = {**scope, "path": path.rstrip("/")}
            if self._matches(stripped) != Match.NONE:
                return RedirectResponse(url=str(URL(scope=stripped)))
        raise HTTPException(status_code=404)
