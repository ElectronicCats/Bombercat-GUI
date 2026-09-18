"""Cliente HTTP para PoCs (stdlib `urllib`), con:
* evidencia automática (guarda request+response en el directorio del run),
* guard de **solo-lectura** (bloquea métodos no idempotentes salvo allow_write),
* `dry_run` (registra la petición sin enviarla),
* proxy y CA opcionales (útil con mitmproxy).
"""

from __future__ import annotations

import json as _json
import ssl
import urllib.error
import urllib.request
from dataclasses import dataclass, field

from .model import PocContext, PocError

_READONLY = {"GET", "HEAD", "OPTIONS"}


@dataclass
class HttpResponse:
    status: int
    headers: dict
    body: bytes
    url: str
    method: str

    @property
    def text(self) -> str:
        return self.body.decode("utf-8", "replace")

    def json(self):
        return _json.loads(self.body or b"null")


@dataclass
class PocHttp:
    ctx: PocContext
    proxy: str | None = None
    ca_cert: str | None = None
    timeout: float = 25.0
    verify: bool = True
    user_agent: str = "EMVy-PoC/0.3"
    _n: int = field(default=0, init=False)

    # -- núcleo -------------------------------------------------------------
    def request(
        self,
        method: str,
        url: str,
        *,
        headers: dict | None = None,
        data: bytes | None = None,
        json=None,
        allow: bool = False,
    ) -> HttpResponse:
        """`allow=True` autoriza puntualmente un método no idempotente (p.ej. un
        POST de login/probe) sin abrir `--allow-write` global; el PoC asume la
        responsabilidad. Sigue registrando evidencia y respetando dry_run."""
        method = method.upper()
        headers = dict(headers or {})
        headers.setdefault("User-Agent", self.user_agent)
        if json is not None:
            data = _json.dumps(json).encode()
            headers.setdefault("Content-Type", "application/json")

        if method not in _READONLY and not (self.ctx.allow_write or allow):
            raise PocError(
                f"{method} {url} bloqueado (modo solo-lectura). "
                "Usa --allow-write, o el PoC debe pasar allow=True si lo autoriza."
            )

        self._n += 1
        self._save(
            f"{self._n:02d}_req_{method}.txt", self._fmt_req(method, url, headers, data)
        )

        if self.ctx.dry_run:
            self.ctx.log(f"[dry-run] {method} {url}")
            resp = HttpResponse(0, {}, b"", url, method)
            self._save(f"{self._n:02d}_resp_DRYRUN.txt", "(dry-run: no enviado)")
            return resp

        resp = self._send(method, url, headers, data)
        self._save(f"{self._n:02d}_resp_{resp.status}.txt", self._fmt_resp(resp))
        return resp

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def head(self, url, **kw):
        return self.request("HEAD", url, **kw)

    def options(self, url, **kw):
        return self.request("OPTIONS", url, **kw)

    def post(self, url, *, allow=False, **kw):
        return self.request("POST", url, allow=allow, **kw)

    def put(self, url, *, allow=False, **kw):
        return self.request("PUT", url, allow=allow, **kw)

    def delete(self, url, *, allow=False, **kw):
        return self.request("DELETE", url, allow=allow, **kw)

    # -- transporte ---------------------------------------------------------
    def _opener(self):
        handlers = []
        if self.proxy:
            handlers.append(
                urllib.request.ProxyHandler({"http": self.proxy, "https": self.proxy})
            )
        ctx = (
            ssl.create_default_context(cafile=self.ca_cert)
            if self.ca_cert
            else ssl.create_default_context()
        )
        if not self.verify:
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
        handlers.append(urllib.request.HTTPSHandler(context=ctx))
        return urllib.request.build_opener(*handlers)

    def _send(self, method, url, headers, data) -> HttpResponse:
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with self._opener().open(req, timeout=self.timeout) as r:
                body = r.read()
                return HttpResponse(r.status, dict(r.headers), body, url, method)
        except urllib.error.HTTPError as e:
            body = e.read()
            return HttpResponse(e.code, dict(e.headers or {}), body, url, method)
        except Exception as e:
            self.ctx.log(f"HTTP error: {e}")
            return HttpResponse(-1, {}, str(e).encode(), url, method)

    # -- evidencia ----------------------------------------------------------
    def _save(self, name: str, text: str) -> None:
        try:
            self.ctx.save_evidence(name, text)
        except Exception:
            pass

    @staticmethod
    def _fmt_req(method, url, headers, data) -> str:
        lines = [f"{method} {url}"]
        lines += [f"{k}: {v}" for k, v in headers.items()]
        if data:
            lines += ["", data.decode("utf-8", "replace")]
        return "\n".join(lines)

    @staticmethod
    def _fmt_resp(r: HttpResponse) -> str:
        lines = [f"HTTP {r.status}  ({r.method} {r.url})"]
        lines += [f"{k}: {v}" for k, v in r.headers.items()]
        lines += ["", r.text]
        return "\n".join(lines)


def http_factory(ctx: PocContext) -> PocHttp:
    """Construye un PocHttp desde las variables del proyecto (proxy/ca/ua)."""
    return PocHttp(
        ctx,
        proxy=ctx.var("http_proxy"),
        ca_cert=ctx.var("http_ca_cert"),
        verify=(ctx.var("http_verify", "1") not in ("0", "false", "no")),
        user_agent=ctx.var("http_user_agent", "EMVy-PoC/0.3"),
    )
