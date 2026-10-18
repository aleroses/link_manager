"""Punto de entrada del Gestor de Enlaces.

Sin argumentos abre la ventana. Con --probar ejecuta las pruebas de
consola de la persistencia y del verificador.
"""

from __future__ import annotations

import json
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import datos
import verificador


def _configurar_salida() -> None:
    """Pide UTF-8 en la consola para que las tildes se lean igual en ambos sistemas."""
    for flujo in (sys.stdout, sys.stderr):
        reconfigure = getattr(flujo, "reconfigure", None)
        if reconfigure is None:
            continue
        try:
            reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass


class _Comprobaciones:
    def __init__(self) -> None:
        self.correctas = 0
        self.fallos = 0

    def comprobar(self, condicion: bool, nombre: str, detalle: str = "") -> None:
        if condicion:
            self.correctas += 1
            print(f"OK     {nombre}")
            return
        self.fallos += 1
        extra = f" ({detalle})" if detalle else ""
        print(f"FALLO  {nombre}{extra}")


class _ServidorLocal(BaseHTTPRequestHandler):
    """HEAD responde 405 y GET devuelve un HTML con title, en localhost."""

    def do_HEAD(self) -> None:
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.send_header("Allow", "GET")
        self.end_headers()

    def do_GET(self) -> None:
        cuerpo = (
            "<html><head><title>  Título   local  </title></head>"
            "<body>ok</body></html>"
        ).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, formato: str, *args: object) -> None:
        return


def probar_persistencia(informe: _Comprobaciones) -> None:
    with tempfile.TemporaryDirectory() as carpeta:
        base = Path(carpeta)
        ruta = base / "enlaces.json"

        cargados = datos.cargar_enlaces(ruta)
        texto = ruta.read_text(encoding="utf-8")
        informe.comprobar(
            cargados == [] and json.loads(texto) == [],
            "crear enlaces.json vacío si no existe",
        )

        enlace = datos.enlace_nuevo("https://example.com/cañón")
        enlace["notas"] = "revisar después"
        enlace["estado"] = "caído"
        enlace["categoria"] = "lectura"
        datos.guardar_enlaces([enlace], ruta)
        recuperado = datos.cargar_enlaces(ruta)
        informe.comprobar(
            len(recuperado) == 1
            and recuperado[0]["url"] == "https://example.com/cañón"
            and recuperado[0]["notas"] == "revisar después"
            and recuperado[0]["estado"] == "caído"
            and recuperado[0]["visitado"] is False
            and recuperado[0]["categoria"] == "lectura"
            and recuperado[0]["codigo_http"] is None,
            "guardar y volver a cargar conserva tildes y campos",
        )
        informe.comprobar(
            not list(base.glob("*.tmp")),
            "el guardado no deja archivos temporales",
        )

        original = "{ esto no es json"
        ruta.write_text(original, encoding="utf-8")
        tras_corrupto = datos.cargar_enlaces(ruta)
        respaldo = ruta.with_name(ruta.name + ".bak")
        informe.comprobar(
            tras_corrupto == []
            and respaldo.is_file()
            and respaldo.read_text(encoding="utf-8") == original
            and json.loads(ruta.read_text(encoding="utf-8")) == []
            and not list(base.glob("*.tmp")),
            "un JSON corrupto se copia a .bak y el archivo queda vacío",
        )

        ruta.write_text("<<<", encoding="utf-8")
        datos.cargar_enlaces(ruta)
        copias = sorted(base.glob("*.bak"))
        informe.comprobar(
            len(copias) == 2 and respaldo.read_text(encoding="utf-8") == original,
            "un segundo archivo corrupto no pisa el .bak anterior",
        )

        informe.comprobar(
            datos.ruta_datos(base) == base / "enlaces.json"
            and not (base / ".sonda_escritura").exists(),
            "si la carpeta es escribible, el JSON queda junto al script",
        )

        marcador = base / "no_es_directorio.txt"
        marcador.write_text("x", encoding="utf-8")
        config = base / "config-prueba"
        elegida = datos.ruta_datos(marcador, carpeta_config=config)
        informe.comprobar(
            elegida == config / "enlaces.json" and config.is_dir(),
            "si la ruta no es escribible, se usa la carpeta de configuración",
        )


def probar_normalizacion(informe: _Comprobaciones) -> None:
    informe.comprobar(
        verificador.normalizar_url("  example.com/ruta  ") == "https://example.com/ruta",
        "una URL sin esquema recibe https://",
    )
    informe.comprobar(
        verificador.normalizar_url("http://example.com/a") == "http://example.com/a",
        "http:// se conserva",
    )
    informe.comprobar(
        verificador.normalizar_url("//cdn.example.com/x") == "https://cdn.example.com/x",
        "una URL de protocolo relativo recibe https:",
    )
    informe.comprobar(
        verificador.clave_url("Example.com") == verificador.clave_url("https://example.com/"),
        "example.com y https://example.com/ son el mismo enlace",
    )
    informe.comprobar(
        verificador.clave_url("https://example.com/a/")
        == verificador.clave_url("https://example.com/a#seccion"),
        "la barra final y el fragmento no crean otro enlace",
    )
    informe.comprobar(
        verificador.clave_url("https://example.com/a?id=1")
        != verificador.clave_url("https://example.com/a?id=2"),
        "una query distinta es otro enlace",
    )

    for cruda in ("", "   ", "ftp://example.com/archivo", "https://"):
        estado, codigo, titulo = verificador.verificar_url(cruda)
        informe.comprobar(
            estado == "error" and codigo is None and titulo == "",
            f"URL no válida queda en error: {cruda!r}",
        )


def probar_titulo(informe: _Comprobaciones) -> None:
    html_pagina = "<html><head><title>  Hola   mundo &amp; mas </title></head></html>"
    informe.comprobar(
        verificador.extraer_titulo(html_pagina.encode("utf-8"), "utf-8") == "Hola mundo & mas",
        "el título se limpia y decodifica entidades",
    )
    informe.comprobar(
        verificador.extraer_titulo(b"<html><body>sin titulo</body></html>", "utf-8") == "",
        "sin etiqueta title el resultado es vacío",
    )


def probar_servidor_local(informe: _Comprobaciones) -> None:
    servidor = ThreadingHTTPServer(("127.0.0.1", 0), _ServidorLocal)
    hilo = threading.Thread(target=servidor.serve_forever, daemon=True)
    hilo.start()
    try:
        puerto = servidor.server_address[1]
        estado, codigo, titulo = verificador.verificar_url(f"http://127.0.0.1:{puerto}/pagina")
        informe.comprobar(
            estado == "activo" and codigo == 200 and titulo == "Título local",
            "si HEAD falla, GET lee el título",
            f"recibido estado={estado} codigo={codigo} titulo={titulo!r}",
        )
    finally:
        servidor.shutdown()
        servidor.server_close()


def probar_red(informe: _Comprobaciones) -> None:
    estado, codigo, _titulo = verificador.verificar_url("https://example.com")
    informe.comprobar(
        estado == "activo" and codigo is not None and 200 <= codigo <= 399,
        "example.com queda activo",
        f"recibido estado={estado} codigo={codigo}",
    )

    estado, codigo, _titulo = verificador.verificar_url(
        "https://example.com/no-existe-gestor-enlaces"
    )
    informe.comprobar(
        estado == "error" and codigo is not None and 400 <= codigo <= 599,
        "una ruta inexistente queda en error",
        f"recibido estado={estado} codigo={codigo}",
    )

    estado, codigo, titulo = verificador.verificar_url(
        "https://no-existe-gestor-enlaces.invalid"
    )
    informe.comprobar(
        estado == "caído" and codigo is None and titulo == "",
        "un dominio inexistente queda caído",
        f"recibido estado={estado} codigo={codigo}",
    )


def main() -> int:
    _configurar_salida()
    informe = _Comprobaciones()
    print("Persistencia")
    probar_persistencia(informe)
    print("Normalización")
    probar_normalizacion(informe)
    print("Título")
    probar_titulo(informe)
    print("Servidor local")
    probar_servidor_local(informe)
    print("Red")
    print("Las tres pruebas siguientes necesitan conexión a internet.")
    probar_red(informe)
    print()
    print(f"Resultado: {informe.correctas} correctas, {informe.fallos} fallos.")
    return 0 if informe.fallos == 0 else 1


if __name__ == "__main__":
    if "--probar" in sys.argv:
        sys.exit(main())
    from interfaz import iniciar

    iniciar()
