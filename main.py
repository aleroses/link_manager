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
    """Rutas de prueba en localhost.

    /pagina rechaza HEAD con 405. /html acepta HEAD como HTML y el GET
    trae el title. /binario responde un PDF y no debería recibir GET.
    """

    gets_binario = 0

    def do_HEAD(self) -> None:
        if self.path.startswith("/html"):
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        if self.path.startswith("/binario"):
            self.send_response(200)
            self.send_header("Content-Type", "application/pdf")
            self.send_header("Content-Length", "0")
            self.end_headers()
            return
        self.send_response(405)
        self.send_header("Content-Length", "0")
        self.send_header("Allow", "GET")
        self.end_headers()

    def do_GET(self) -> None:
        if self.path.startswith("/binario"):
            _ServidorLocal.gets_binario += 1
            cuerpo = b"%PDF"
            tipo = "application/pdf"
        elif self.path.startswith("/html"):
            cuerpo = (
                "<html><head><title>Desde HEAD</title></head><body>ok</body></html>"
            ).encode("utf-8")
            tipo = "text/html; charset=utf-8"
        else:
            cuerpo = (
                "<html><head><title>  Título   local  </title></head>"
                "<body>ok</body></html>"
            ).encode("utf-8")
            tipo = "text/html; charset=utf-8"
        self.send_response(200)
        self.send_header("Content-Type", tipo)
        self.send_header("Content-Length", str(len(cuerpo)))
        self.end_headers()
        self.wfile.write(cuerpo)

    def log_message(self, formato: str, *args: object) -> None:
        return


def probar_persistencia(informe: _Comprobaciones) -> None:
    with tempfile.TemporaryDirectory() as carpeta:
        base = Path(carpeta)
        ruta = base / "enlaces.json"

        vacio = datos.coleccion_vacia()
        cargados = datos.cargar_enlaces(ruta)
        texto = ruta.read_text(encoding="utf-8")
        informe.comprobar(
            cargados == vacio and json.loads(texto) == vacio,
            "crear enlaces.json vacío si no existe",
        )

        coleccion = datos.coleccion_vacia()
        enlace = datos.enlace_nuevo("https://example.com/cañón")
        enlace["notas"] = "revisar después"
        enlace["estado"] = "caído"
        enlace["categoria"] = "lectura"
        coleccion["enlaces"].append(enlace)
        datos.guardar_enlaces(coleccion, ruta)
        recuperado = datos.cargar_enlaces(ruta)
        guardado = recuperado["enlaces"][0]
        informe.comprobar(
            recuperado["version"] == 2
            and recuperado["categorias"] == []
            and len(recuperado["enlaces"]) == 1
            and guardado["url"] == "https://example.com/cañón"
            and guardado["notas"] == "revisar después"
            and guardado["estado"] == "caído"
            and guardado["visitado"] is False
            and guardado["categoria"] == "lectura"
            and guardado["codigo_http"] is None,
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
            tras_corrupto == datos.coleccion_vacia()
            and respaldo.is_file()
            and respaldo.read_text(encoding="utf-8") == original
            and json.loads(ruta.read_text(encoding="utf-8")) == datos.coleccion_vacia()
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

        lista_antigua = '[{"url": "https://example.com"}]'
        ruta.write_text(lista_antigua, encoding="utf-8")
        tras_lista = datos.cargar_enlaces(ruta)
        informe.comprobar(
            tras_lista == datos.coleccion_vacia()
            and any(
                copia.read_text(encoding="utf-8") == lista_antigua
                for copia in base.glob("*.bak")
            ),
            "una lista antigua se copia a .bak y el archivo queda vacío",
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


def probar_categorias(informe: _Comprobaciones) -> None:
    coleccion = datos.coleccion_vacia()
    datos.crear_categoria(coleccion, "Peliculas")
    datos.crear_categoria(coleccion, "Lectura")
    fecha = coleccion["categorias"][0]["fecha_creacion"]
    rechazados: list[str] = []
    for nombre in ("", "   ", "peliculas", "Sin categoría", "Todas", "Nueva categoría"):
        try:
            datos.crear_categoria(coleccion, nombre)
        except datos.ErrorCategoria:
            rechazados.append(nombre)
    informe.comprobar(
        rechazados == ["", "   ", "peliculas", "Sin categoría", "Todas", "Nueva categoría"]
        and len(coleccion["categorias"]) == 2,
        "un nombre vacío, repetido o reservado no crea categoría",
    )
    informe.comprobar(
        datos.asegurar_categoria(coleccion, "LECTURA") == "Lectura"
        and datos.asegurar_categoria(coleccion, "Cine") == "Cine"
        and [item["nombre"] for item in coleccion["categorias"]] == ["Peliculas", "Lectura", "Cine"],
        "asegurar reutiliza la grafía guardada y crea la que falta",
    )

    peliculas = datos.enlace_nuevo("https://example.com/p")
    peliculas["categoria"] = "Peliculas"
    lectura = datos.enlace_nuevo("https://example.com/l")
    lectura["categoria"] = "Lectura"
    suelto = datos.enlace_nuevo("https://example.com/s")
    coleccion["enlaces"] = [peliculas, lectura, suelto]
    datos.renombrar_categoria(coleccion, "peliculas", "Filmes")
    informe.comprobar(
        coleccion["categorias"][0]["nombre"] == "Filmes"
        and coleccion["categorias"][0]["fecha_creacion"] == fecha
        and peliculas["categoria"] == "Filmes"
        and lectura["categoria"] == "Lectura",
        "renombrar cambia la ficha y los enlaces, y conserva la fecha",
    )
    datos.eliminar_categoria(coleccion, "Filmes", borrar_enlaces=False)
    informe.comprobar(
        peliculas["categoria"] == ""
        and lectura in coleccion["enlaces"]
        and suelto in coleccion["enlaces"]
        and [item["nombre"] for item in coleccion["categorias"]] == ["Lectura", "Cine"],
        "eliminar una categoría mueve sus enlaces a Sin categoría",
    )
    datos.eliminar_categoria(coleccion, "lectura", True)
    informe.comprobar(
        lectura not in coleccion["enlaces"]
        and peliculas in coleccion["enlaces"]
        and suelto in coleccion["enlaces"]
        and [item["nombre"] for item in coleccion["categorias"]] == ["Cine"],
        "eliminar una categoría puede borrar también sus enlaces",
    )


def probar_csv(informe: _Comprobaciones) -> None:
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "enlaces.csv"
        enlace = datos.enlace_nuevo("https://example.com/cañón")
        enlace["titulo"] = "Cañón"
        enlace["notas"] = "línea uno\nlínea dos"
        enlace["estado"] = "caído"
        enlace["categoria"] = "lectura"
        enlace["visitado"] = True
        enlace["codigo_http"] = 200
        datos.escribir_csv([enlace], ruta)
        crudo = ruta.read_bytes()
        leidos, sin_url, por_verificar = datos.leer_csv(ruta)
        informe.comprobar(
            crudo.startswith(b"\xef\xbb\xbf")
            and len(leidos) == 1
            and sin_url == 0
            and por_verificar == []
            and leidos[0]["url"] == "https://example.com/cañón"
            and leidos[0]["titulo"] == "Cañón"
            and leidos[0]["notas"] == "línea uno\nlínea dos"
            and leidos[0]["estado"] == "caído"
            and leidos[0]["categoria"] == "lectura"
            and leidos[0]["visitado"] is True
            and leidos[0]["codigo_http"] == 200,
            "el CSV conserva tildes, notas en varias líneas y visitado",
        )

        ruta.write_text(
            "url,titulo\n,sin destino\nhttps://ok.test,Bien\n",
            encoding="utf-8-sig",
        )
        leidos, sin_url, _por_verificar = datos.leer_csv(ruta)
        informe.comprobar(
            sin_url == 1 and len(leidos) == 1 and leidos[0]["url"] == "https://ok.test",
            "una fila sin URL se omite",
        )

        ruta.write_text(
            "url,estado,visitado\n"
            "https://a.test,raro,true\n"
            "https://b.test,activo,false\n"
            "https://c.test,pendiente,1\n"
            "https://d.test,error,0\n",
            encoding="utf-8-sig",
        )
        leidos, _sin_url, por_verificar = datos.leer_csv(ruta)
        informe.comprobar(
            leidos[0]["estado"] == "pendiente"
            and leidos[0]["visitado"] is True
            and por_verificar == [leidos[0]]
            and leidos[1]["estado"] == "activo"
            and leidos[1]["visitado"] is False
            and leidos[2]["estado"] == "pendiente"
            and leidos[2]["visitado"] is True
            and leidos[2] not in por_verificar
            and leidos[3]["visitado"] is False
            and leidos[3]["estado"] == "error",
            "un estado desconocido queda pendiente y visitado acepta true, false, 1 y 0",
        )

        ruta.write_text(
            "url,titulo\n"
            "https://a.test,Sin título\n"
            "https://b.test,\n"
            "https://c.test,Hecho a mano\n",
            encoding="utf-8-sig",
        )
        leidos, sin_url, _por_verificar = datos.leer_csv(ruta)
        informe.comprobar(
            sin_url == 0
            and leidos[0]["titulo"] == ""
            and leidos[0]["titulo_manual"] is False
            and leidos[1]["titulo"] == ""
            and leidos[1]["titulo_manual"] is False
            and leidos[2]["titulo"] == "Hecho a mano"
            and leidos[2]["titulo_manual"] is True,
            "un título importado se marca como manual, y Sin título queda automático",
        )

        ruta.write_text("titulo\nhola\n", encoding="utf-8-sig")
        try:
            datos.leer_csv(ruta)
        except ValueError:
            informe.comprobar(True, "un CSV sin columna url se rechaza")
        else:
            informe.comprobar(False, "un CSV sin columna url se rechaza")


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
    informe.comprobar(
        verificador.titulo_descriptivo("https://www.example.com/blog/articulo-sobre-python")
        == "example.com / articulo sobre python",
        "el título descriptivo usa el dominio sin www y el último segmento",
    )
    informe.comprobar(
        verificador.titulo_descriptivo("https://example.com") == "example.com"
        and verificador.titulo_descriptivo("https://example.com/") == "example.com",
        "sin ruta el título descriptivo es el dominio",
    )
    informe.comprobar(
        verificador.titulo_descriptivo("https://www.example.com/a/mi-nota/") == "example.com / mi nota",
        "la barra final no cuenta como segmento",
    )
    informe.comprobar(
        verificador.titulo_descriptivo("https://example.com/ca%C3%B1%C3%B3n-uno")
        == "example.com / cañón uno",
        "el segmento codificado se decodifica",
    )

    relleno = datos.enlace_nuevo("https://www.example.com/articulo-sobre-python")
    relleno["titulo"] = "Sin título"
    relleno["titulo_manual"] = True
    informe.comprobar(
        datos.resolver_titulo(relleno, "", "example.com / articulo sobre python")
        == ("example.com / articulo sobre python", False),
        "Sin título se sustituye en la siguiente verificación",
    )
    manual = datos.enlace_nuevo("https://example.com/a")
    manual["titulo"] = "Mi título"
    manual["titulo_manual"] = True
    informe.comprobar(
        datos.resolver_titulo(manual, "Otro", "example.com / a") is None,
        "un título editado a mano no se sustituye",
    )
    informe.comprobar(
        datos.resolver_edicion_titulo("Mi título", "", None, "example.com / a")
        == ("example.com / a", False)
        and datos.resolver_edicion_titulo("Automático", "Automático", "Automático", "example.com")
        == ("Automático", False)
        and datos.resolver_edicion_titulo("Antes", "Después", None, "example.com")
        == ("Después", True)
        and datos.resolver_edicion_titulo("Igual", "Igual", None, "example.com") is None,
        "guardar el diálogo distingue vacío, obtenido, editado y sin cambios",
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

        estado, codigo, titulo = verificador.verificar_url(f"http://127.0.0.1:{puerto}/html")
        informe.comprobar(
            estado == "activo" and codigo == 200 and titulo == "Desde HEAD",
            "si HEAD responde HTML, un GET parcial lee el título",
            f"recibido estado={estado} codigo={codigo} titulo={titulo!r}",
        )

        _ServidorLocal.gets_binario = 0
        estado, codigo, titulo = verificador.verificar_url(f"http://127.0.0.1:{puerto}/binario")
        informe.comprobar(
            estado == "activo"
            and codigo == 200
            and titulo == ""
            and _ServidorLocal.gets_binario == 0,
            "un HEAD que no es HTML no descarga el cuerpo",
            f"recibido estado={estado} codigo={codigo} titulo={titulo!r} gets={_ServidorLocal.gets_binario}",
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
    print("Categorías")
    probar_categorias(informe)
    print("CSV")
    probar_csv(informe)
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
