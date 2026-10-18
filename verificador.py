"""Comprueba si una URL responde y clasifica el resultado.

Estados devueltos:
- activo: el servidor responde con un código entre 200 y 399.
- error: el servidor responde con 4xx o 5xx, o la URL no es válida.
- caído: timeout, DNS, SSL o fallo de conexión.

Si HEAD responde y el contenido parece HTML, un GET parcial (como
máximo 64 KB) lee el título. Si HEAD falla o el servidor lo rechaza,
el GET también decide el estado. Sin etiqueta title el título queda
vacío: quien guarda el enlace puede sustituirlo por uno descriptivo.
"""

from __future__ import annotations

import html
import re
from html.parser import HTMLParser
from urllib.parse import unquote, urlparse

import requests

TIEMPO_LIMITE = 8
MAX_CUERPO = 65536
# Cadena fija de navegador. No describe el sistema donde corre la app:
# solo evita que algunos sitios rechacen un cliente "python-requests".
AGENTE_NAVEGADOR = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)
# Estos códigos significan "HEAD no sirve aquí": se reintenta con GET.
CODIGOS_SIN_HEAD = {405, 501}
_ANFITRIONES_LOCALES = {"localhost", "127.0.0.1", "::1"}


class _LectorTitulo(HTMLParser):
    """Recoge el texto de la primera etiqueta title."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._dentro = False
        self._partes: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "title":
            self._dentro = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "title":
            self._dentro = False

    def handle_data(self, data: str) -> None:
        if self._dentro:
            self._partes.append(data)

    def texto(self) -> str:
        unido = html.unescape("".join(self._partes))
        limpio = re.sub(r"\s+", " ", unido).strip()
        return limpio[:300]


def normalizar_url(url: str) -> str:
    """Recorta la URL y le pone https:// si no trae esquema.

    Lanza ValueError si queda vacía o si el esquema no es http/https.
    """
    limpia = url.strip()
    if not limpia:
        raise ValueError("la URL está vacía")
    if any(caracter in limpia for caracter in ("\n", "\r", "\t")):
        raise ValueError("la URL contiene caracteres de control")
    if limpia.startswith("//"):
        limpia = "https:" + limpia
    elif "://" not in limpia:
        limpia = "https://" + limpia

    partes = urlparse(limpia)
    if partes.scheme.lower() not in {"http", "https"} or not partes.hostname:
        raise ValueError("la URL debe ser http o https")
    if any(caracter.isspace() for caracter in partes.netloc):
        raise ValueError("el dominio no es válido")
    return limpia


def clave_url(url: str) -> str:
    """Clave para detectar duplicados. No es la URL que se guarda.

    Esquema y host van en minúsculas, se quita la barra final (la raíz
    se queda en /) y se ignora el fragmento. La query se conserva, así
    que ?id=1 y ?id=2 siguen siendo enlaces distintos.
    """
    partes = urlparse(normalizar_url(url))
    esquema = partes.scheme.lower()
    host = (partes.hostname or "").lower()
    if ":" in host:
        host = f"[{host}]"
    puerto = partes.port
    if (esquema == "http" and puerto == 80) or (esquema == "https" and puerto == 443):
        puerto = None
    autoridad = f"{host}:{puerto}" if puerto else host
    ruta = partes.path or "/"
    if len(ruta) > 1 and ruta.endswith("/"):
        ruta = ruta.rstrip("/")
    clave = f"{esquema}://{autoridad}{ruta}"
    if partes.query:
        clave = f"{clave}?{partes.query}"
    return clave


def titulo_descriptivo(url: str) -> str:
    """Dominio sin www y, si hay, la última parte legible de la ruta.

    Los guiones del último segmento pasan a espacios. Una URL que no
    se puede normalizar devuelve cadena vacía.
    """
    try:
        destino = normalizar_url(url)
    except ValueError:
        return ""
    partes = urlparse(destino)
    host = (partes.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    segmento = _ultimo_segmento_legible(partes.path)
    if not host:
        return segmento
    if segmento:
        return f"{host} / {segmento}"
    return host


def _ultimo_segmento_legible(ruta: str) -> str:
    segmentos = [unquote(parte) for parte in ruta.split("/") if parte]
    if not segmentos:
        return ""
    texto = segmentos[-1].replace("-", " ")
    return re.sub(r"\s+", " ", texto).strip()


def clasificar_codigo(codigo: int) -> str:
    """Traduce un código HTTP al estado que guarda la aplicación."""
    if 200 <= codigo <= 399:
        return "activo"
    # Cualquier otra respuesta HTTP es un error del servidor o del
    # recurso. "caído" se reserva para cuando no hay respuesta.
    return "error"


def extraer_titulo(contenido: bytes, encoding: str | None) -> str:
    """Lee el title de un fragmento HTML. Si no hay, devuelve cadena vacía."""
    codec = encoding or "utf-8"
    texto = contenido.decode(codec, errors="replace")
    lector = _LectorTitulo()
    try:
        lector.feed(texto)
        lector.close()
    except Exception:
        return ""
    return lector.texto()


def _parece_html(respuesta: requests.Response) -> bool:
    tipo = respuesta.headers.get("Content-Type", "").lower()
    if not tipo:
        return True
    return "html" in tipo or "xml" in tipo


def _leer_cuerpo_limitado(respuesta: requests.Response) -> bytes:
    trozos: list[bytes] = []
    leidos = 0
    for bloque in respuesta.iter_content(chunk_size=8192):
        if not bloque:
            continue
        trozos.append(bloque)
        leidos += len(bloque)
        if leidos >= MAX_CUERPO:
            break
    return b"".join(trozos)[:MAX_CUERPO]


def _titulo_de_respuesta(respuesta: requests.Response) -> str:
    if not _parece_html(respuesta):
        return ""
    try:
        cuerpo = _leer_cuerpo_limitado(respuesta)
    except requests.RequestException:
        return ""
    return extraer_titulo(cuerpo, respuesta.encoding)


def _titulo_por_get(sesion: requests.Session, destino: str) -> str:
    """Lee el título con un GET parcial. Un fallo deja el título vacío."""
    try:
        respuesta = sesion.get(
            destino,
            timeout=TIEMPO_LIMITE,
            allow_redirects=True,
            stream=True,
        )
    except requests.RequestException:
        return ""
    try:
        return _titulo_de_respuesta(respuesta)
    finally:
        respuesta.close()


def verificar_url(url: str) -> tuple[str, int | None, str]:
    """Devuelve (estado, codigo_http, titulo).

    Prueba HEAD y, si el método falla o el servidor lo rechaza, GET.
    Si HEAD responde y el contenido parece HTML, un segundo GET, de como
    máximo 64 KB, solo aporta el título: el código sigue siendo el del HEAD.
    Una URL mal formada devuelve estado "error" y código None: no es
    una caída de red. Un 403 se queda en "error"; marcarlo como activo
    a mano corresponderá a la interfaz. Sin title el título queda vacío.
    """
    try:
        destino = normalizar_url(url)
    except ValueError:
        return ("error", None, "")

    try:
        with requests.Session() as sesion:
            sesion.headers["User-Agent"] = AGENTE_NAVEGADOR
            anfitrion = (urlparse(destino).hostname or "").lower()
            if anfitrion in _ANFITRIONES_LOCALES:
                sesion.trust_env = False

            respuesta_head: requests.Response | None = None
            try:
                respuesta_head = sesion.head(
                    destino,
                    timeout=TIEMPO_LIMITE,
                    allow_redirects=True,
                )
            except requests.exceptions.InvalidURL:
                return ("error", None, "")
            except requests.RequestException:
                respuesta_head = None

            if respuesta_head is not None and respuesta_head.status_code not in CODIGOS_SIN_HEAD:
                codigo = respuesta_head.status_code
                pedir_titulo = _parece_html(respuesta_head)
                respuesta_head.close()
                titulo = _titulo_por_get(sesion, destino) if pedir_titulo else ""
                return (clasificar_codigo(codigo), codigo, titulo)
            if respuesta_head is not None:
                respuesta_head.close()

            try:
                respuesta = sesion.get(
                    destino,
                    timeout=TIEMPO_LIMITE,
                    allow_redirects=True,
                    stream=True,
                )
            except requests.exceptions.InvalidURL:
                return ("error", None, "")

            try:
                codigo = respuesta.status_code
                titulo = _titulo_de_respuesta(respuesta)
                return (clasificar_codigo(codigo), codigo, titulo)
            finally:
                respuesta.close()
    except requests.exceptions.InvalidURL:
        return ("error", None, "")
    except requests.RequestException:
        return ("caído", None, "")
