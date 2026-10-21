# Gestor de Enlaces. Licencia GPL-3.0. El texto está en LICENSE.
"""Punto de entrada del Gestor de Enlaces.

Sin argumentos abre la ventana. Con --probar ejecuta las pruebas de
consola de la persistencia y del verificador.
"""

from __future__ import annotations

import contextlib
import io
import json
import sys
import tempfile
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import datos
import registro
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
            and not list(base.glob("*.tmp"))
            and "copia .bak" in datos.aviso_carga,
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


def probar_ruta(informe: _Comprobaciones) -> None:
    with tempfile.TemporaryDirectory() as carpeta:
        base = Path(carpeta)
        aviso = io.StringIO()
        with contextlib.redirect_stderr(aviso):
            elegida = datos.ruta_datos(base)
        informe.comprobar(
            elegida == base / "data" / "enlaces.json"
            and (base / "data").is_dir()
            and not (base / "data" / ".sonda_escritura").exists()
            and not elegida.exists()
            and aviso.getvalue() == "",
            "si la carpeta es escribible, el JSON queda en data/ y no se crea el archivo",
        )

        texto = '{"version": 1}\n'
        antiguo = base / "enlaces.json"
        antiguo.write_text(texto, encoding="utf-8")
        aviso = io.StringIO()
        with contextlib.redirect_stderr(aviso):
            otra = datos.ruta_datos(base)
        informe.comprobar(
            otra == elegida
            and antiguo.read_text(encoding="utf-8") == texto
            and "ignora" in aviso.getvalue().casefold()
            and str(antiguo) in aviso.getvalue()
            and not elegida.exists(),
            "un enlaces.json en la raíz se ignora y no se migra ni se borra",
        )

        marcador = base / "no_es_directorio.txt"
        marcador.write_text("x", encoding="utf-8")
        config = base / "config-prueba"
        aviso = io.StringIO()
        with contextlib.redirect_stderr(aviso):
            fallback = datos.ruta_datos(marcador, carpeta_config=config)
        informe.comprobar(
            fallback == config / "enlaces.json" and config.is_dir() and aviso.getvalue() == "",
            "si la ruta no es escribible, se usa la carpeta de configuración",
        )


def probar_alta(informe: _Comprobaciones) -> None:
    coleccion = datos.coleccion_vacia()
    datos.crear_categoria(coleccion, "Lectura")
    existentes = [datos.enlace_nuevo("https://example.com/ya")]
    nuevos, repetidos, invalidos = datos.nuevos_enlaces(
        [
            "https://example.com/ya",
            "example.com/uno",
            "https://EXAMPLE.com/uno/",
            "no es url",
        ],
        existentes,
        coleccion,
        "lectura",
    )
    informe.comprobar(
        len(nuevos) == 1
        and nuevos[0]["url"] == "https://example.com/uno"
        and nuevos[0]["categoria"] == "Lectura"
        and repetidos == 2
        and invalidos == 1
        and [item["nombre"] for item in coleccion["categorias"]] == ["Lectura"]
        and coleccion["enlaces"] == [],
        "añadir usa la categoría elegida y descarta duplicados e inválidos",
    )
    sin_categoria, repetidos_sin, invalidos_sin = datos.nuevos_enlaces(
        ["https://example.com/libre"],
        [],
        coleccion,
        "Sin categoría",
    )
    vacio, _, _ = datos.nuevos_enlaces(
        ["https://example.com/vacio"],
        [],
        coleccion,
        "   ",
    )
    informe.comprobar(
        len(sin_categoria) == 1
        and sin_categoria[0]["categoria"] == ""
        and repetidos_sin == 0
        and invalidos_sin == 0
        and len(vacio) == 1
        and vacio[0]["categoria"] == "",
        "Sin categoría se guarda como cadena vacía",
    )

    with tempfile.TemporaryDirectory() as carpeta:
        base = Path(carpeta)
        aviso = io.StringIO()
        with contextlib.redirect_stderr(aviso):
            ruta = datos.ruta_datos(base)
        coleccion["enlaces"].append(nuevos[0])
        datos.guardar_enlaces(coleccion, ruta)
        leido = datos.cargar_enlaces(ruta)
        guardado = leido["enlaces"][0]
        informe.comprobar(
            ruta == base / "data" / "enlaces.json"
            and aviso.getvalue() == ""
            and guardado["url"] == "https://example.com/uno"
            and guardado["categoria"] == "Lectura"
            and leido["categorias"][0]["nombre"] == "Lectura",
            "un enlace nuevo se guarda en data/ con la categoría elegida",
        )


def probar_categorias(informe: _Comprobaciones) -> None:
    coleccion = datos.coleccion_vacia()
    datos.crear_categoria(coleccion, "Peliculas")
    datos.crear_categoria(coleccion, "Lectura")
    fecha = coleccion["categorias"][0]["fecha_creacion"]
    rechazados: list[str] = []
    for nombre in (
        "",
        "   ",
        "peliculas",
        "Sin categoría",
        "Todas",
        "Nueva categoría",
        "Nueva categoría...",
    ):
        try:
            datos.crear_categoria(coleccion, nombre)
        except datos.ErrorCategoria:
            rechazados.append(nombre)
    informe.comprobar(
        rechazados
        == [
            "",
            "   ",
            "peliculas",
            "Sin categoría",
            "Todas",
            "Nueva categoría",
            "Nueva categoría...",
        ]
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

        ruta.write_bytes("url,titulo\nhttps://a.test,cañón\n".encode("cp1252"))
        leidos, _sin_url, _por_verificar = datos.leer_csv(ruta)
        informe.comprobar(
            leidos[0]["titulo"] == "cañón",
            "un CSV en la codificación de Windows se lee igual",
        )

        ruta.write_text("url\n" + ("x" * 140000) + "\n", encoding="utf-8")
        try:
            datos.leer_csv(ruta)
        except ValueError as exc:
            informe.comprobar(
                "mal formado" in str(exc),
                "un CSV mal formado se rechaza con un mensaje claro",
            )
        else:
            informe.comprobar(False, "un CSV mal formado se rechaza con un mensaje claro")

        ruta.write_bytes(b"\x81\x81")
        try:
            datos.leer_csv(ruta)
        except ValueError as exc:
            informe.comprobar(
                "UTF-8" in str(exc),
                "un CSV con una codificación desconocida se rechaza",
            )
        else:
            informe.comprobar(False, "un CSV con una codificación desconocida se rechaza")


def probar_diagnostico(informe: _Comprobaciones) -> None:
    fallo = OSError("network is unreachable")
    fallo.errno = 101
    informe.comprobar(
        verificador.es_sin_conexion(fallo)
        and not verificador.es_sin_conexion(TimeoutError("timed out")),
        "una red caída se distingue de un sitio que no responde",
    )
    with tempfile.TemporaryDirectory() as carpeta:
        registro.iniciar(Path(carpeta))
        registro.anotar("fallo de prueba")
        texto = (Path(carpeta) / "gestor.log").read_text(encoding="utf-8")
        registro.cerrar()
        informe.comprobar(
            "fallo de prueba" in texto,
            "el registro escribe gestor.log y se puede cerrar",
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


def _columnas_pintadas(app) -> int:
    hijos = app.lista.winfo_children()
    if not hijos:
        return 0
    columnas = 0
    for hijo in hijos[0].winfo_children():
        info = hijo.grid_info()
        if info:
            columnas = max(columnas, int(info["column"]) + 1)
    return columnas


def _cancelar_redimension(app) -> None:
    if app._after_redimension is not None:
        try:
            app.after_cancel(app._after_redimension)
        except Exception:
            pass
        app._after_redimension = None


def probar_columnas(informe: _Comprobaciones) -> None:
    import customtkinter as ctk

    import interfaz

    minimo = interfaz.ANCHO_MINIMO_COLUMNA
    casos = [(ancho, maximo, 1) for ancho in (0, -5, 479, 480, 959) for maximo in (2, 3)]
    casos.extend(
        [
            (960, 2, 2),
            (960, 3, 2),
            (1439, 3, 2),
            (1440, 3, 3),
            (4000, 2, 2),
            (4000, 3, 3),
            (2000, 0, 1),
        ]
    )
    fallos = [
        f"{ancho}/{maximo}->{interfaz.columnas_para_ancho(ancho, minimo, maximo)}!={esperado}"
        for ancho, maximo, esperado in casos
        if interfaz.columnas_para_ancho(ancho, minimo, maximo) != esperado
    ]
    if interfaz.columnas_para_ancho(2000, 0, 3) != 1:
        fallos.append("minimo 0")
    informe.comprobar(
        not fallos,
        "el ancho del contenedor decide las columnas en los límites",
        "; ".join(fallos),
    )
    medir = lambda texto: len(texto) * 10
    informe.comprobar(
        interfaz.recortar_texto("hola", medir, 40) == "hola"
        and interfaz.recortar_texto("abcdef", medir, 50) == "ab..."
        and interfaz.recortar_texto("abc", medir, 0) == "",
        "un texto que no cabe se corta con puntos suspensivos",
    )
    pendiente = datos.enlace_nuevo("https://example.com/nuevo")
    con_fecha = datos.enlace_nuevo("https://example.com/visto")
    con_fecha["estado"] = "activo"
    con_fecha["ultima_verificacion"] = "2026-10-18T12:00:00+00:00"
    importado = datos.enlace_nuevo("https://example.com/csv")
    importado["estado"] = "activo"
    dia = datetime.fromisoformat("2026-10-18T12:00:00+00:00").astimezone().strftime("%d/%m/%Y")
    informe.comprobar(
        interfaz.texto_ultima_verificacion(pendiente) == "sin verificar"
        and interfaz.texto_ultima_verificacion(con_fecha) == f"verificado {dia}"
        and interfaz.texto_ultima_verificacion(importado) == ""
        and interfaz.texto_ultima_verificacion(
            {"estado": "pendiente", "ultima_verificacion": "no-es-fecha"}
        )
        == "sin verificar",
        "la fila muestra la fecha corta o sin verificar",
    )

    ctk.set_appearance_mode("dark")
    with tempfile.TemporaryDirectory() as carpeta:
        ruta = Path(carpeta) / "enlaces.json"
        coleccion = datos.coleccion_vacia()
        nombres = ["Alfa", "Beta", "Gamma", "Delta", "Epsilon"]
        for nombre in nombres:
            datos.crear_categoria(coleccion, nombre)
        for indice in range(30):
            enlace = datos.enlace_nuevo(
                f"https://example.com/item-{indice}/" + "segmento-" * 8
            )
            enlace["titulo"] = f"Título largo número {indice} " + ("palabra " * 14)
            enlace["notas"] = "una nota larga " * 12
            enlace["estado"] = "activo" if indice % 2 == 0 else "pendiente"
            enlace["categoria"] = "" if indice % 6 == 0 else nombres[indice % len(nombres)]
            coleccion["enlaces"].append(enlace)
        datos.guardar_enlaces(coleccion, ruta)
        datos.aviso_ruta = ""
        app = interfaz.Aplicacion(ruta=ruta)
        try:
            app.minsize(400, 400)
            app.geometry("800x700")
            app.update()
            _cancelar_redimension(app)
            app._aplicar_columnas()
            ancho = app._ancho_contenedor()
            tarjetas = min(
                interfaz.columnas_para_ancho(ancho, minimo, interfaz.MAX_COLUMNAS_TARJETAS),
                6,
            )
            pintadas = _columnas_pintadas(app)
            informe.comprobar(
                app._mostrando_tarjetas()
                and app._columnas == tarjetas
                and pintadas == app._columnas
                and (ancho >= minimo * 2 or app._columnas == 1),
                "la cuadrícula de tarjetas sigue el ancho del contenedor",
                f"ancho={ancho} columnas={app._columnas} pintadas={pintadas}",
            )

            app._al_cambiar_vista("Todos los enlaces")
            app.update()
            _cancelar_redimension(app)
            app._aplicar_columnas()
            ancho = app._ancho_contenedor()
            enlaces = min(
                interfaz.columnas_para_ancho(ancho, minimo, interfaz.MAX_COLUMNAS_ENLACES),
                30,
            )
            textos_largos = [
                item
                for item in app._recortes
                if not item["envolver"] and len(item["texto"]) > 40
            ]
            informe.comprobar(
                app._columnas == enlaces
                and _columnas_pintadas(app) == app._columnas
                and any(item["etiqueta"].cget("text").endswith("...") for item in textos_largos),
                "la lista de enlaces sigue el ancho del contenedor",
                f"ancho={ancho} columnas={app._columnas}",
            )

            app._filtro = "activo"
            app.menu_filtro.set("Activo")
            app.refrescar_lista()
            app.update()
            app.lista._parent_canvas.yview_moveto(0.45)
            app.update_idletasks()
            app.geometry("1800x700")
            app.update()
            _cancelar_redimension(app)
            antes = float(app.lista._parent_canvas.yview()[0])
            app._aplicar_columnas()
            app.update_idletasks()
            despues = float(app.lista._parent_canvas.yview()[0])
            ancho = app._ancho_contenedor()
            activos = sum(1 for enlace in app.enlaces if enlace.get("estado") == "activo")
            esperadas = min(
                interfaz.columnas_para_ancho(ancho, minimo, interfaz.MAX_COLUMNAS_ENLACES),
                activos,
            )
            informe.comprobar(
                app._filtro == "activo"
                and app.menu_filtro.get() == "Activo"
                and app._columnas == esperadas
                and _columnas_pintadas(app) == app._columnas
                and abs(despues - antes) < 0.2,
                "al cambiar de columnas se conservan el filtro y el scroll",
                f"ancho={ancho} columnas={app._columnas} scroll {antes:.2f}->{despues:.2f}",
            )

            app._volver_tarjetas()
            app.update()
            _cancelar_redimension(app)
            app._aplicar_columnas()
            ancho = app._ancho_contenedor()
            tarjetas = min(
                interfaz.columnas_para_ancho(ancho, minimo, interfaz.MAX_COLUMNAS_TARJETAS),
                6,
            )
            informe.comprobar(
                app._mostrando_tarjetas()
                and app._columnas == tarjetas
                and _columnas_pintadas(app) == app._columnas
                and app._columnas <= interfaz.MAX_COLUMNAS_TARJETAS,
                "las tarjetas no pasan de tres columnas",
                f"ancho={ancho} columnas={app._columnas}",
            )

            lote = app._lote
            app._filtro = "todos"
            app.menu_filtro.set("Todos")
            app.busqueda.delete(0, "end")
            app.update()
            en_tarjetas = (
                app.boton_verificar_tarjetas.winfo_ismapped()
                and not app.boton_verificar.winfo_ismapped()
            )
            app._entrar_seccion("Alfa")
            app.update()
            en_seccion = (
                not app.boton_verificar_tarjetas.winfo_ismapped()
                and not app.boton_verificar.winfo_ismapped()
                and app.boton_verificar_categoria.winfo_ismapped()
            )
            app._al_cambiar_vista("Todos los enlaces")
            app.update()
            en_lista = (
                app.boton_verificar.winfo_ismapped()
                and not app.boton_verificar_tarjetas.winfo_ismapped()
            )
            app._volver_tarjetas()
            app.update()
            app._entrar_seccion("Alfa")
            app.update()
            fechas = [
                item["texto"]
                for item in app._recortes
                if item["texto"] in {"sin verificar", f"verificado {dia}"}
            ]
            informe.comprobar(
                app._lote == lote
                and not app._verificacion_masiva
                and app.boton_verificar_categoria.winfo_ismapped()
                and "sin verificar" in fechas
                and en_tarjetas
                and en_seccion
                and en_lista,
                "entrar y salir de una categoría no inicia una verificación",
                f"lote={app._lote} masiva={app._verificacion_masiva} "
                f"tarjetas={en_tarjetas} seccion={en_seccion} lista={en_lista}",
            )

            datos.crear_categoria(app.coleccion, "Vacia")
            app._guardar()
            app._entrar_seccion("Vacia")
            app.update()
            app.verificar_categoria("Vacia")
            informe.comprobar(
                app._lote == lote
                and app.boton_verificar_categoria.cget("text") == "Verificar categoría"
                and app.aviso.cget("text") == "No hay enlaces en esta categoría.",
                "una categoría vacía no inicia una verificación",
            )

            original_envio = app._enviar_verificacion

            def _sin_red(*_args, **_kwargs) -> None:
                return None

            app._enviar_verificacion = _sin_red
            app._entrar_seccion("Alfa")
            app.update()
            app.verificar_categoria("Alfa")
            app.update()
            gira = (
                app._after_carga is not None
                and app.boton_verificar_categoria.cget("text") == "Verificando..."
                and not app.barra_progreso.winfo_ismapped()
            )
            app._volver_tarjetas()
            app.update()
            texto_cabecera = app.boton_verificar_categoria.cget("text")
            app._finalizar_lote()
            app.update()
            app._enviar_verificacion = original_envio
            informe.comprobar(
                gira
                and texto_cabecera == "Verificar categoría"
                and app._after_carga is None
                and not app._verificacion_masiva,
                "la animación arranca, se detiene al salir y no muestra la barra",
            )

            app._volver_tarjetas()
            app.update()
            oculto = not app.boton_verificar_categoria.winfo_ismapped()
            app._entrar_seccion("Alfa")
            app.update()
            pedidos: list[list] = []

            def _anotar(seleccion, _aviso, con_barra=True, categoria=None) -> None:
                pedidos.append(list(seleccion))

            lote_boton = app._lote
            app._iniciar_verificacion = _anotar
            app.boton_verificar_categoria.invoke()
            esperados = app._enlaces_de("Alfa")
            informe.comprobar(
                oculto
                and app.boton_verificar_categoria.winfo_ismapped()
                and len(pedidos) == 1
                and pedidos[0] == esperados
                and app._lote == lote_boton,
                "el botón de la cabecera verifica solo la categoría abierta",
            )
        finally:
            app._al_cerrar()


def _encolar_resultado(app, enlace: dict, estado: str, lote: int | None = None) -> None:
    app._token += 1
    token = app._token
    app._token_por_enlace[id(enlace)] = token
    app._resultados.put(
        (
            "resultado",
            enlace,
            estado,
            200,
            f"Titulo {token}",
            "2026-10-20T12:00:00+00:00",
            lote,
            token,
            "",
        )
    )


def _pintado_inmediato(app) -> None:
    """La pasada de prueba pinta ya, sin esperar los 150 ms de la anterior."""
    app._ultimo_repintado = 0.0
    if app._after_repintado is not None:
        try:
            app.after_cancel(app._after_repintado)
        except Exception:
            pass
        app._after_repintado = None
    app._vista_sucia = False
    app._repintado_enlaces = []


def probar_repintado(informe: _Comprobaciones) -> None:
    import time

    import customtkinter as ctk

    import interfaz

    ctk.set_appearance_mode("dark")
    original = datos.guardar_enlaces
    llamadas = {"guardar": 0, "refrescar": 0}

    def _contar_guardado(coleccion: dict, ruta: Path | None = None) -> None:
        llamadas["guardar"] += 1
        original(coleccion, ruta)

    datos.guardar_enlaces = _contar_guardado
    app = None
    try:
        with tempfile.TemporaryDirectory() as carpeta:
            ruta = Path(carpeta) / "enlaces.json"
            coleccion = datos.coleccion_vacia()
            datos.crear_categoria(coleccion, "Alfa")
            for indice in range(30):
                enlace = datos.enlace_nuevo(f"https://example.com/item-{indice}")
                enlace["titulo"] = f"Titulo {indice}"
                enlace["categoria"] = "Alfa"
                coleccion["enlaces"].append(enlace)
            datos.guardar_enlaces(coleccion, ruta)
            app = interfaz.Aplicacion(ruta=ruta)
            app.geometry("900x640")
            app.update()
            _cancelar_redimension(app)

            def _refrescar() -> None:
                llamadas["refrescar"] += 1
                interfaz.Aplicacion.refrescar_lista(app)

            app.refrescar_lista = _refrescar
            app._lote = 1
            app._verificacion_masiva = True
            app._con_barra = True
            app._total_lote = 30
            app._pendientes_lote = 30
            app._hechos_lote = 0
            app._fallo_al_guardar = False
            app._sin_conexion = False
            app._cancelar_lote = None
            app._mostrar_progreso()
            for enlace in app.enlaces:
                _encolar_resultado(app, enlace, "activo", lote=1)
            llamadas["guardar"] = 0
            llamadas["refrescar"] = 0
            _pintado_inmediato(app)
            app._recoger_resultados()
            informe.comprobar(
                llamadas["guardar"] == 1
                and llamadas["refrescar"] == 1
                and app.texto_progreso.cget("text") == "30 de 30 (100%)"
                and all(enlace.get("estado") == "activo" for enlace in app.enlaces),
                "treinta resultados en tarjetas guardan y pintan una vez",
                f"guardar={llamadas['guardar']} refrescar={llamadas['refrescar']} "
                f"progreso={app.texto_progreso.cget('text')}",
            )
            if app._after_ocultar is not None:
                try:
                    app.after_cancel(app._after_ocultar)
                except Exception:
                    pass
                app._after_ocultar = None

            app._al_cambiar_vista("Todos los enlaces")
            app.update()
            _cancelar_redimension(app)
            primero = app.enlaces[0]
            punto = app._filas[id(primero)]["punto"]
            for enlace in app.enlaces:
                _encolar_resultado(app, enlace, "caído")
            llamadas["guardar"] = 0
            llamadas["refrescar"] = 0
            _pintado_inmediato(app)
            app._recoger_resultados()
            color = punto.cget("fg_color")
            if isinstance(color, (list, tuple)):
                color = color[-1]
            informe.comprobar(
                llamadas["guardar"] == 1
                and llamadas["refrescar"] == 0
                and punto is app._filas[id(primero)]["punto"]
                and punto.winfo_exists()
                and color == interfaz.COLORES_ESTADO["caído"]
                and all(enlace.get("estado") == "caído" for enlace in app.enlaces),
                "treinta resultados con filas visibles no reconstruyen la lista",
                f"guardar={llamadas['guardar']} refrescar={llamadas['refrescar']} color={color}",
            )

            app._al_cambiar_filtro("Caído")
            app.update()
            _cancelar_redimension(app)
            _encolar_resultado(app, primero, "activo")
            llamadas["guardar"] = 0
            llamadas["refrescar"] = 0
            _pintado_inmediato(app)
            app._recoger_resultados()
            informe.comprobar(
                llamadas["guardar"] == 1
                and llamadas["refrescar"] == 1
                and primero.get("estado") == "activo",
                "un resultado que sale del filtro reconstruye la lista una vez",
                f"guardar={llamadas['guardar']} refrescar={llamadas['refrescar']}",
            )

            app.busqueda.delete(0, "end")
            llamadas["refrescar"] = 0
            _cancelar_redimension(app)
            for _ in range(8):
                app.busqueda.insert("end", "x")
                app._al_buscar()
            pendiente = llamadas["refrescar"] == 0 and app._after_busqueda is not None
            fin = time.perf_counter() + 0.45
            while time.perf_counter() < fin:
                app.update()
                _cancelar_redimension(app)
            informe.comprobar(
                pendiente and llamadas["refrescar"] == 1,
                "ocho teclas del buscador refiltran una vez",
                f"pendiente={pendiente} refrescar={llamadas['refrescar']}",
            )

            objetivo = app.enlaces[1]
            _encolar_resultado(app, objetivo, "error")
            app._al_buscar()
            if app._after_repintado is not None:
                try:
                    app.after_cancel(app._after_repintado)
                except Exception:
                    pass
                app._after_repintado = None
            app._ultimo_repintado = time.monotonic()
            app._pedir_repintado([objetivo])
            habia_despues = (
                app._after_busqueda is not None and app._after_repintado is not None
            )
            url_objetivo = str(objetivo.get("url") or "")
            app._al_cerrar()
            guardado = json.loads(ruta.read_text(encoding="utf-8"))
            escrito = next(
                item
                for item in guardado["enlaces"]
                if item.get("url") == url_objetivo
            )
            informe.comprobar(
                habia_despues
                and app._after_busqueda is None
                and app._after_repintado is None
                and app._after_resultados is None
                and not app._guardado_pendiente
                and escrito.get("estado") == "error",
                "cerrar con una tanda pendiente no pierde el guardado",
                f"estado={escrito.get('estado')} pendiente={app._guardado_pendiente}",
            )
    finally:
        datos.guardar_enlaces = original
        if app is not None and not app._cerrando:
            try:
                app._al_cerrar()
            except Exception:
                pass


def main() -> int:
    _configurar_salida()
    informe = _Comprobaciones()
    print("Persistencia")
    probar_persistencia(informe)
    print("Ruta")
    probar_ruta(informe)
    print("Categorías")
    probar_categorias(informe)
    print("Alta")
    probar_alta(informe)
    print("Columnas")
    probar_columnas(informe)
    print("Repintado")
    probar_repintado(informe)
    print("CSV")
    probar_csv(informe)
    print("Diagnóstico")
    probar_diagnostico(informe)
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

    try:
        iniciar()
    except Exception:
        print(
            "No se pudo abrir Gestor de Enlaces. El detalle está en data/gestor.log.",
            file=sys.stderr,
        )
        sys.exit(1)
