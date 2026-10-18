"""Ventana del Gestor de Enlaces.

Tema oscuro, campo para añadir una URL y lista con el estado de cada
enlace. La comprobación de red ocurre en un grupo de hasta 8 hilos.
Esos hilos no tocan widgets: dejan el resultado en una cola y el hilo
principal lo aplica con after().
"""

from __future__ import annotations

import queue
import threading
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image

import datos
import verificador

# Tope de comprobaciones simultáneas. Más hilos no aceleran la red y
# sí pueden disparar bloqueos en los sitios.
HILOS_VERIFICACION = 8
# La barra se queda un momento en el valor final para que se pueda leer.
PAUSA_CIERRE_PROGRESO_MS = 700

CARPETA_ICONOS = Path(__file__).resolve().parent / "assets" / "icons"

# Nombre interno -> archivo Lucide, sin extensión.
ICONOS = {
    "anadir": "plus",
    "abrir": "external-link",
    "copiar": "copy",
    "eliminar": "trash-2",
    "verificar": "refresh-cw",
    "buscar": "search",
    "filtrar": "filter",
    "editar": "pencil",
    "importar": "import",
    "exportar": "upload",
    "categoria": "tag",
    "check": "check",
    "alerta": "triangle-alert",
    "cerrar": "x",
}

COLORES = {
    "fondo": "#14171C",
    "barra": "#1C2128",
    "fila": "#242A33",
    "texto": "#E7E5E4",
    "secundario": "#A8A29E",
    "acento": "#4C8DFF",
    "acento_hover": "#3A78E6",
    "borde": "#343B46",
    "aviso": "#E8A04C",
    "texto_boton": "#F8FAFC",
}

COLORES_ESTADO = {
    "activo": "#3DDC97",
    "caído": "#E85D4C",
    "error": "#E8A04C",
    "pendiente": "#8B9098",
}


def texto_progreso(hechos: int, total: int) -> str:
    """Contador de la barra: '8 de 25 (32%)'.

    El porcentaje usa división entera para no mostrar 100% antes de
    terminar la última comprobación.
    """
    if total <= 0:
        return "0 de 0 (0%)"
    return f"{hechos} de {total} ({hechos * 100 // total}%)"


# Etiqueta visible -> clave interna. Visitado no es un estado.
FILTROS = (
    ("Todos", "todos"),
    ("Pendiente", "pendiente"),
    ("Activo", "activo"),
    ("Error", "error"),
    ("Caído", "caído"),
    ("Visitado", "visitado"),
    ("No visitado", "no_visitado"),
)
_CLAVE_FILTRO = {etiqueta: clave for etiqueta, clave in FILTROS}


def _palabra(cantidad: int, singular: str, plural: str) -> str:
    return f"{cantidad} {singular if cantidad == 1 else plural}"


def texto_resumen(enlaces: list) -> str:
    """Recuento de toda la colección: '1 activo, 3 caídos, 2 errores, 5 pendientes'."""
    cuentas = {"activo": 0, "caído": 0, "error": 0, "pendiente": 0}
    for enlace in enlaces:
        if not isinstance(enlace, dict):
            continue
        estado = str(enlace.get("estado") or "pendiente")
        if estado in cuentas:
            cuentas[estado] += 1
    return ", ".join(
        (
            _palabra(cuentas["activo"], "activo", "activos"),
            _palabra(cuentas["caído"], "caído", "caídos"),
            _palabra(cuentas["error"], "error", "errores"),
            _palabra(cuentas["pendiente"], "pendiente", "pendientes"),
        )
    )


def coincide(enlace: dict, filtro: str, texto: str, categoria: str = "todas") -> bool:
    """Estado, categoría y texto se aplican a la vez. El texto no distingue mayúsculas."""
    if filtro == "visitado":
        if not enlace.get("visitado"):
            return False
    elif filtro == "no_visitado":
        if enlace.get("visitado"):
            return False
    elif filtro not in {"", "todos"}:
        if str(enlace.get("estado") or "pendiente") != filtro:
            return False

    if categoria == "sin":
        if str(enlace.get("categoria") or "").strip():
            return False
    elif categoria not in {"", "todas"}:
        guardada = str(enlace.get("categoria") or "").strip()
        if guardada.casefold() != categoria.casefold():
            return False

    consulta = texto.strip().casefold()
    if not consulta:
        return True
    campos = (
        str(enlace.get("titulo") or ""),
        str(enlace.get("url") or ""),
        str(enlace.get("notas") or ""),
        str(enlace.get("categoria") or ""),
    )
    return any(consulta in campo.casefold() for campo in campos)


def texto_altas(
    anadidos: int,
    repetidos: int,
    invalidos: int,
    sin_url: int = 0,
    importacion: bool = False,
) -> str:
    """Aviso de un pegado o una importación: cuántos entraron y cuántos no."""
    if anadidos == 1:
        partes = ["Se importó 1 enlace." if importacion else "Se añadió 1 enlace."]
    elif anadidos > 1:
        verbo = "importaron" if importacion else "añadieron"
        partes = [f"Se {verbo} {anadidos} enlaces."]
    else:
        partes = ["No se importó ninguno." if importacion else "No se añadió ninguno."]
    if repetidos == 1:
        partes.append("1 ya estaba.")
    elif repetidos > 1:
        partes.append(f"{repetidos} ya estaban.")
    if invalidos == 1:
        partes.append("1 no es válido.")
    elif invalidos > 1:
        partes.append(f"{invalidos} no son válidos.")
    if sin_url == 1:
        partes.append("1 sin URL.")
    elif sin_url > 1:
        partes.append(f"{sin_url} sin URL.")
    return " ".join(partes)


def cargar_iconos(carpeta: Path | None = None) -> dict[str, ctk.CTkImage]:
    """Carga el PNG de 40 px y lo muestra a 20 px para pantallas HiDPI.

    Si falta alguno, lanza FileNotFoundError con la lista. Así la ventana
    no se abre a medias.
    """
    origen = carpeta if carpeta is not None else CARPETA_ICONOS
    imagenes: dict[str, ctk.CTkImage] = {}
    faltan: list[str] = []
    for clave, nombre in ICONOS.items():
        ruta = origen / f"{nombre}-40.png"
        if not ruta.is_file():
            faltan.append(ruta.name)
            continue
        imagen = Image.open(ruta)
        imagenes[clave] = ctk.CTkImage(light_image=imagen, dark_image=imagen, size=(20, 20))
    if faltan:
        lista = ", ".join(faltan)
        raise FileNotFoundError(f"Faltan iconos en {origen}: {lista}")
    return imagenes


class Aplicacion(ctk.CTk):
    """Ventana principal. Guarda en disco después de cada cambio."""

    def __init__(self, ruta: Path | None = None, iconos: dict[str, ctk.CTkImage] | None = None) -> None:
        super().__init__()
        self.ruta = ruta if ruta is not None else datos.ruta_datos()
        self.iconos = iconos if iconos is not None else cargar_iconos()
        self.enlaces: list = datos.cargar_enlaces(self.ruta)
        # Tk no es seguro entre hilos. El hilo de red solo deja el
        # resultado aqui; el hilo principal lo aplica con after().
        # La cola guarda el diccionario, no su posición: si se borra
        # otro enlace, el resultado no se escribe en el de al lado.
        self._resultados: queue.Queue[tuple] = queue.Queue()
        self._ejecutor = ThreadPoolExecutor(
            max_workers=HILOS_VERIFICACION,
            thread_name_prefix="verificar",
        )
        self._cerrando = False
        self._lote = 0
        self._token = 0
        # El token evita que un resultado viejo pise uno más reciente
        # del mismo enlace (por ejemplo, añadir y justo después
        # verificar todos).
        self._token_por_enlace: dict[int, int] = {}
        self._cancelar_lote: threading.Event | None = None
        self._verificacion_masiva = False
        self._total_lote = 0
        self._hechos_lote = 0
        self._pendientes_lote = 0
        self._fallo_al_guardar = False
        self._filas: dict[int, dict] = {}
        self._after_resultados: str | None = None
        self._after_ocultar: str | None = None
        self._filtro = "todos"
        self._filtro_categoria = "todas"
        self.fuente_titulo = ctk.CTkFont(size=15, weight="bold")
        self.fuente_url = ctk.CTkFont(size=13)
        self.fuente_detalle = ctk.CTkFont(size=12)
        self._configurar_ventana()
        self._construir()
        self.refrescar_lista()

    def _configurar_ventana(self) -> None:
        self.title("Gestor de Enlaces")
        self.geometry("1000x680")
        self.minsize(800, 520)
        self.configure(fg_color=COLORES["fondo"])
        self.protocol("WM_DELETE_WINDOW", self._al_cerrar)

    def _construir(self) -> None:
        barra = ctk.CTkFrame(self, fg_color=COLORES["barra"], corner_radius=0)
        barra.pack(fill="x")

        interior = ctk.CTkFrame(barra, fg_color="transparent")
        interior.pack(fill="x", padx=20, pady=(18, 8))

        self.entrada = ctk.CTkEntry(
            interior,
            placeholder_text="Pega un enlace",
            height=42,
            corner_radius=10,
            border_width=1,
            border_color=COLORES["borde"],
            fg_color=COLORES["fondo"],
            text_color=COLORES["texto"],
            placeholder_text_color=COLORES["secundario"],
            font=self.fuente_url,
        )
        self.entrada.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.entrada.bind("<Return>", lambda _evento: self.anadir())
        self.entrada.bind("<<Paste>>", self._al_pegar)

        self.boton_anadir = ctk.CTkButton(
            interior,
            text="Añadir",
            image=self.iconos["anadir"],
            compound="left",
            width=128,
            height=42,
            corner_radius=10,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto_boton"],
            font=ctk.CTkFont(size=14, weight="bold"),
            command=self.anadir,
        )
        self.boton_anadir.pack(side="left")

        self.fila_verificar = ctk.CTkFrame(barra, fg_color="transparent")
        self.fila_verificar.pack(fill="x", padx=20, pady=(0, 4))
        self.fila_verificar.grid_columnconfigure(1, weight=1)

        self.boton_verificar = ctk.CTkButton(
            self.fila_verificar,
            text="Verificar todos",
            image=self.iconos["verificar"],
            compound="left",
            width=190,
            height=36,
            corner_radius=10,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto_boton"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.verificar_todos,
        )
        self.boton_verificar.grid(row=0, column=0, sticky="w")

        self.barra_progreso = ctk.CTkProgressBar(
            self.fila_verificar,
            height=10,
            corner_radius=5,
            fg_color=COLORES["fondo"],
            progress_color=COLORES["acento"],
            border_width=0,
        )
        self.barra_progreso.set(0)
        self.texto_progreso = ctk.CTkLabel(
            self.fila_verificar,
            text=texto_progreso(0, 0),
            width=148,
            anchor="e",
            text_color=COLORES["texto"],
            font=self.fuente_detalle,
        )
        self.boton_cancelar = ctk.CTkButton(
            self.fila_verificar,
            text="Cancelar",
            width=110,
            height=36,
            corner_radius=10,
            fg_color=COLORES["fondo"],
            hover_color=COLORES["borde"],
            text_color=COLORES["texto"],
            font=ctk.CTkFont(size=13),
            command=self.cancelar_verificacion,
        )

        self.fila_buscar = ctk.CTkFrame(barra, fg_color="transparent")
        self.fila_buscar.pack(fill="x", padx=20, pady=(4, 0))

        ctk.CTkLabel(
            self.fila_buscar,
            text="",
            image=self.iconos["buscar"],
            fg_color="transparent",
        ).pack(side="left", padx=(0, 8))
        self.busqueda = ctk.CTkEntry(
            self.fila_buscar,
            placeholder_text="Buscar por título, URL, notas o categoría",
            height=36,
            corner_radius=10,
            border_width=1,
            border_color=COLORES["borde"],
            fg_color=COLORES["fondo"],
            text_color=COLORES["texto"],
            placeholder_text_color=COLORES["secundario"],
            font=self.fuente_url,
        )
        self.busqueda.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.busqueda.bind("<KeyRelease>", self._al_buscar)

        ctk.CTkLabel(
            self.fila_buscar,
            text="",
            image=self.iconos["filtrar"],
            fg_color="transparent",
        ).pack(side="left", padx=(0, 8))
        self.menu_filtro = ctk.CTkOptionMenu(
            self.fila_buscar,
            values=[etiqueta for etiqueta, _clave in FILTROS],
            command=self._al_cambiar_filtro,
            width=150,
            height=36,
            corner_radius=10,
            fg_color=COLORES["fondo"],
            button_color=COLORES["borde"],
            button_hover_color=COLORES["acento"],
            dropdown_fg_color=COLORES["barra"],
            dropdown_hover_color=COLORES["borde"],
            dropdown_text_color=COLORES["texto"],
            text_color=COLORES["texto"],
            font=self.fuente_detalle,
            dropdown_font=self.fuente_detalle,
        )
        self.menu_filtro.pack(side="left")
        self.menu_filtro.set("Todos")

        ctk.CTkLabel(
            self.fila_buscar,
            text="",
            image=self.iconos["categoria"],
            fg_color="transparent",
        ).pack(side="left", padx=(12, 8))
        self.menu_categoria = ctk.CTkOptionMenu(
            self.fila_buscar,
            values=["Todas", "Sin categoría"],
            command=self._al_cambiar_categoria,
            width=170,
            height=36,
            corner_radius=10,
            fg_color=COLORES["fondo"],
            button_color=COLORES["borde"],
            button_hover_color=COLORES["acento"],
            dropdown_fg_color=COLORES["barra"],
            dropdown_hover_color=COLORES["borde"],
            dropdown_text_color=COLORES["texto"],
            text_color=COLORES["texto"],
            font=self.fuente_detalle,
            dropdown_font=self.fuente_detalle,
        )
        self.menu_categoria.pack(side="left")
        self.menu_categoria.set("Todas")

        self.aviso = ctk.CTkLabel(
            barra,
            text="",
            height=22,
            anchor="w",
            text_color=COLORES["aviso"],
            font=self.fuente_detalle,
        )
        self.aviso.pack(fill="x", padx=22, pady=(8, 12))

        self.barra_inferior = ctk.CTkFrame(self, fg_color=COLORES["barra"], corner_radius=0)
        self.barra_inferior.pack(side="bottom", fill="x")
        interior_inferior = ctk.CTkFrame(self.barra_inferior, fg_color="transparent")
        interior_inferior.pack(fill="x", padx=20, pady=10)
        self.resumen = ctk.CTkLabel(
            interior_inferior,
            text=texto_resumen([]),
            anchor="w",
            text_color=COLORES["secundario"],
            font=self.fuente_detalle,
        )
        self.resumen.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self.boton_importar = self._boton_barra(
            interior_inferior,
            "Importar",
            "importar",
            self.importar_csv,
        )
        self.boton_exportar = self._boton_barra(
            interior_inferior,
            "Exportar",
            "exportar",
            self.exportar_csv,
        )
        self.boton_reintentar = ctk.CTkButton(
            interior_inferior,
            text="Reintentar caídos",
            image=self.iconos["verificar"],
            compound="left",
            width=200,
            height=36,
            corner_radius=10,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto_boton"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.reintentar_caidos,
        )
        self.boton_reintentar.pack(side="right")
        self.boton_exportar.pack(side="right", padx=(0, 8))
        self.boton_importar.pack(side="right", padx=(0, 8))

        self.lista = ctk.CTkScrollableFrame(
            self,
            fg_color=COLORES["fondo"],
            corner_radius=0,
            scrollbar_fg_color=COLORES["fondo"],
            scrollbar_button_color=COLORES["borde"],
            scrollbar_button_hover_color=COLORES["secundario"],
        )
        self.lista.pack(fill="both", expand=True, padx=16, pady=(8, 16))
        self.entrada.focus_set()
        self._after_resultados = self.after(100, self._recoger_resultados)

    def anadir(self) -> None:
        """Normaliza la URL, rechaza duplicados y verifica en segundo plano."""
        try:
            url = verificador.normalizar_url(self.entrada.get())
        except ValueError:
            self.aviso.configure(text="Ese enlace no es válido. Usa una dirección http o https.")
            return

        if self._es_duplicado(url):
            self.aviso.configure(text="Ese enlace ya está en la lista.")
            return

        self.aviso.configure(text="")
        enlace = datos.enlace_nuevo(url)
        self.enlaces.append(enlace)
        try:
            datos.guardar_enlaces(self.enlaces, self.ruta)
        except OSError:
            self.enlaces.pop()
            self.aviso.configure(text="No se pudo guardar el enlace.")
            return

        self.entrada.delete(0, "end")
        self.refrescar_lista()
        self._enviar_verificacion(enlace, url, lote=None, cancelar=None)
        if not coincide(enlace, self._filtro, self._texto_busqueda(), self._filtro_categoria):
            self.aviso.configure(text="Enlace añadido. No coincide con el filtro actual.")

    def _es_duplicado(self, url: str) -> bool:
        clave = verificador.clave_url(url)
        for existente in self.enlaces:
            try:
                if verificador.clave_url(str(existente.get("url") or "")) == clave:
                    return True
            except ValueError:
                continue
        return False

    def _enviar_verificacion(
        self,
        enlace: dict,
        url: str,
        lote: int | None,
        cancelar: threading.Event | None,
    ) -> None:
        """Encola la comprobación. Como máximo hay 8 hilos de red."""
        self._token += 1
        token = self._token
        self._token_por_enlace[id(enlace)] = token
        self._ejecutor.submit(
            self._verificar_en_segundo_plano,
            enlace,
            url,
            lote,
            token,
            cancelar,
        )

    def _verificar_en_segundo_plano(
        self,
        enlace: dict,
        url: str,
        lote: int | None,
        token: int,
        cancelar: threading.Event | None,
    ) -> None:
        """Corre fuera del hilo principal. No llama a after() ni a widgets."""
        try:
            if cancelar is not None and cancelar.is_set():
                self._resultados.put(("omitido", lote))
                return
            estado, codigo, titulo = verificador.verificar_url(url)
            momento = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._resultados.put(
                ("resultado", enlace, estado, codigo, titulo, momento, lote, token)
            )
        except Exception:
            momento = datetime.now(timezone.utc).isoformat(timespec="seconds")
            self._resultados.put(("resultado", enlace, "caído", None, "", momento, lote, token))

    def _recoger_resultados(self) -> None:
        """Aplica lo que los hilos de red ya terminaron. Corre en el hilo principal."""
        if self._cerrando:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        try:
            while True:
                self._consumir_resultado(self._resultados.get_nowait())
        except queue.Empty:
            pass
        if self._cerrando:
            return
        self._after_resultados = self.after(100, self._recoger_resultados)

    def _consumir_resultado(self, item: tuple) -> None:
        tipo = item[0]
        if tipo == "omitido":
            _, lote = item
            self._cerrar_trabajo(lote, contado=False)
            return
        _, enlace, estado, codigo, titulo, momento, lote, token = item
        self._escribir_resultado(enlace, estado, codigo, titulo, momento, token)
        self._cerrar_trabajo(lote, contado=True)

    def _texto_busqueda(self) -> str:
        return self.busqueda.get()

    def _al_buscar(self, _evento: object = None) -> None:
        self.refrescar_lista()

    def _al_cambiar_filtro(self, etiqueta: str) -> None:
        self._filtro = _CLAVE_FILTRO.get(etiqueta, "todos")
        self.refrescar_lista()

    def _al_cambiar_categoria(self, etiqueta: str) -> None:
        if etiqueta == "Sin categoría":
            self._filtro_categoria = "sin"
        elif etiqueta == "Todas":
            self._filtro_categoria = "todas"
        else:
            self._filtro_categoria = etiqueta
        self.refrescar_lista()

    def _categorias_conocidas(self) -> list[str]:
        vistas: dict[str, str] = {}
        for enlace in self.enlaces:
            if not isinstance(enlace, dict):
                continue
            texto = str(enlace.get("categoria") or "").strip()
            if not texto or texto in {"Todas", "Sin categoría"}:
                continue
            clave = texto.casefold()
            if clave not in vistas:
                vistas[clave] = texto
        return [vistas[clave] for clave in sorted(vistas, key=str.casefold)]

    def _etiqueta_categoria(self) -> str:
        if self._filtro_categoria == "sin":
            return "Sin categoría"
        if self._filtro_categoria == "todas":
            return "Todas"
        return self._filtro_categoria

    def _asegurar_filtro_categoria(self) -> None:
        if self._filtro_categoria in {"todas", "sin"}:
            return
        conocidas = {texto.casefold() for texto in self._categorias_conocidas()}
        if self._filtro_categoria.casefold() not in conocidas:
            self._filtro_categoria = "todas"

    def _rehacer_menu_categoria(self) -> None:
        opciones = ["Todas", "Sin categoría", *self._categorias_conocidas()]
        self.menu_categoria.configure(values=opciones)
        self.menu_categoria.set(self._etiqueta_categoria())

    def _boton_barra(self, padre, texto: str, icono: str, comando) -> ctk.CTkButton:
        return ctk.CTkButton(
            padre,
            text=texto,
            image=self.iconos[icono],
            compound="left",
            width=132,
            height=36,
            corner_radius=10,
            fg_color=COLORES["fondo"],
            hover_color=COLORES["borde"],
            text_color=COLORES["texto"],
            font=ctk.CTkFont(size=13),
            command=comando,
        )

    def _al_pegar(self, _evento: object = None):
        """Si el portapapeles trae varias líneas, cada una es un enlace."""
        try:
            texto = self.clipboard_get()
        except Exception:
            return None
        lineas = [linea.strip() for linea in texto.splitlines() if linea.strip()]
        if len(lineas) <= 1:
            return None
        self._anadir_varias(lineas)
        return "break"

    def _anadir_varias(self, lineas: list[str]) -> None:
        nuevos: list[dict] = []
        repetidos = 0
        invalidos = 0
        claves = self._claves_conocidas()
        for linea in lineas:
            try:
                url = verificador.normalizar_url(linea)
                clave = verificador.clave_url(url)
            except ValueError:
                invalidos += 1
                continue
            if clave in claves:
                repetidos += 1
                continue
            claves.add(clave)
            nuevos.append(datos.enlace_nuevo(url))
        self._incorporar(nuevos, repetidos, invalidos, 0, importacion=False)

    def _claves_conocidas(self) -> set[str]:
        claves: set[str] = set()
        for enlace in self.enlaces:
            if not isinstance(enlace, dict):
                continue
            try:
                claves.add(verificador.clave_url(str(enlace.get("url") or "")))
            except ValueError:
                continue
        return claves

    def _incorporar(
        self,
        nuevos: list[dict],
        repetidos: int,
        invalidos: int,
        sin_url: int,
        importacion: bool,
        por_verificar: list[dict] | None = None,
    ) -> None:
        if nuevos:
            self.enlaces.extend(nuevos)
            try:
                datos.guardar_enlaces(self.enlaces, self.ruta)
            except OSError:
                conservados = {id(item) for item in nuevos}
                self.enlaces = [item for item in self.enlaces if id(item) not in conservados]
                self.aviso.configure(text="No se pudo guardar el enlace.")
                return
            if not importacion:
                self.entrada.delete(0, "end")
            self.refrescar_lista()
            pendientes = por_verificar if por_verificar is not None else nuevos
            for enlace in pendientes:
                if any(enlace is item for item in nuevos):
                    self._enviar_verificacion(enlace, str(enlace.get("url") or ""), None, None)
        aviso = texto_altas(len(nuevos), repetidos, invalidos, sin_url, importacion)
        if nuevos:
            visibles = [
                enlace
                for enlace in nuevos
                if coincide(enlace, self._filtro, self._texto_busqueda(), self._filtro_categoria)
            ]
            if not visibles:
                aviso = f"{aviso} No se ven con el filtro actual."
            elif len(visibles) < len(nuevos):
                aviso = f"{aviso} Algunos no se ven con el filtro actual."
        self.aviso.configure(text=aviso)

    def editar(self, enlace: dict) -> None:
        """Pide categoría y notas. No toca la URL ni el estado."""
        if not self._sigue_en_lista(enlace):
            return
        dialogo = getattr(self, "_dialogo_editar", None)
        if dialogo is not None:
            try:
                if dialogo.winfo_exists():
                    dialogo.lift()
                    return
            except Exception:
                pass

        dialogo = ctk.CTkToplevel(self)
        self._dialogo_editar = dialogo
        dialogo.title("Editar enlace")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color=COLORES["fondo"])
        dialogo.transient(self)
        self.update_idletasks()
        ancho, alto = 520, 420
        x = self.winfo_rootx() + max(0, (self.winfo_width() - ancho) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - alto) // 2)
        dialogo.geometry(f"{ancho}x{alto}+{x}+{y}")

        ctk.CTkLabel(
            dialogo,
            text="Categoría",
            anchor="w",
            text_color=COLORES["texto"],
            font=self.fuente_detalle,
        ).pack(fill="x", padx=24, pady=(20, 6))
        categoria = ctk.CTkEntry(
            dialogo,
            height=36,
            corner_radius=10,
            border_width=1,
            border_color=COLORES["borde"],
            fg_color=COLORES["barra"],
            text_color=COLORES["texto"],
            font=self.fuente_url,
        )
        categoria.pack(fill="x", padx=24)
        categoria.insert(0, str(enlace.get("categoria") or ""))

        ctk.CTkLabel(
            dialogo,
            text="Notas",
            anchor="w",
            text_color=COLORES["texto"],
            font=self.fuente_detalle,
        ).pack(fill="x", padx=24, pady=(14, 6))
        notas = ctk.CTkTextbox(
            dialogo,
            height=160,
            corner_radius=10,
            border_width=1,
            border_color=COLORES["borde"],
            fg_color=COLORES["barra"],
            text_color=COLORES["texto"],
            font=self.fuente_url,
        )
        notas.pack(fill="x", padx=24)
        notas.insert("1.0", str(enlace.get("notas") or ""))

        acciones = ctk.CTkFrame(dialogo, fg_color="transparent")
        acciones.pack(anchor="e", padx=24, pady=(16, 20))
        ctk.CTkButton(
            acciones,
            text="Cancelar",
            width=110,
            height=36,
            corner_radius=8,
            fg_color=COLORES["barra"],
            hover_color=COLORES["borde"],
            text_color=COLORES["texto"],
            command=dialogo.destroy,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            acciones,
            text="Guardar",
            width=110,
            height=36,
            corner_radius=8,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto_boton"],
            command=lambda: self._guardar_edicion(enlace, categoria, notas, dialogo),
        ).pack(side="left")

        dialogo.protocol("WM_DELETE_WINDOW", dialogo.destroy)
        dialogo.bind("<Escape>", lambda _evento: dialogo.destroy())
        dialogo.after(50, dialogo.lift)
        dialogo.after(50, categoria.focus)
        dialogo.grab_set()

    def _guardar_edicion(
        self,
        enlace: dict,
        categoria: ctk.CTkEntry,
        notas: ctk.CTkTextbox,
        dialogo: ctk.CTkToplevel,
    ) -> None:
        if not self._sigue_en_lista(enlace):
            dialogo.destroy()
            return
        anterior_categoria = enlace.get("categoria")
        anterior_notas = enlace.get("notas")
        enlace["categoria"] = categoria.get().strip()
        enlace["notas"] = notas.get("1.0", "end-1c").strip()
        try:
            datos.guardar_enlaces(self.enlaces, self.ruta)
        except OSError:
            enlace["categoria"] = anterior_categoria
            enlace["notas"] = anterior_notas
            self.aviso.configure(text="No se pudo guardar el enlace.")
            return
        dialogo.destroy()
        self.aviso.configure(text="")
        self.refrescar_lista()

    def exportar_csv(self) -> None:
        ruta = filedialog.asksaveasfilename(
            parent=self,
            title="Exportar CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv"), ("Todos los archivos", "*.*")],
            initialfile="enlaces.csv",
        )
        if not ruta:
            return
        self._exportar_a(Path(ruta))

    def _exportar_a(self, ruta: Path) -> None:
        try:
            datos.escribir_csv(self.enlaces, ruta)
        except OSError:
            self.aviso.configure(text="No se pudo exportar el CSV.")
            return
        cantidad = sum(1 for enlace in self.enlaces if isinstance(enlace, dict))
        self.aviso.configure(text=f"Se exportaron {cantidad} enlaces.")

    def importar_csv(self) -> None:
        ruta = filedialog.askopenfilename(
            parent=self,
            title="Importar CSV",
            filetypes=[("CSV", "*.csv"), ("Todos los archivos", "*.*")],
        )
        if not ruta:
            return
        self._importar_desde(Path(ruta))

    def _importar_desde(self, ruta: Path) -> None:
        try:
            leidos, sin_url, por_verificar = datos.leer_csv(ruta)
        except ValueError:
            self.aviso.configure(text="El CSV no tiene la columna url.")
            return
        except OSError:
            self.aviso.configure(text="No se pudo leer el CSV.")
            return

        nuevos: list[dict] = []
        repetidos = 0
        invalidos = 0
        claves = self._claves_conocidas()
        for enlace in leidos:
            try:
                url = verificador.normalizar_url(str(enlace.get("url") or ""))
                clave = verificador.clave_url(url)
            except ValueError:
                invalidos += 1
                continue
            enlace["url"] = url
            if clave in claves:
                repetidos += 1
                continue
            claves.add(clave)
            nuevos.append(enlace)
        self._incorporar(
            nuevos,
            repetidos,
            invalidos,
            sin_url,
            importacion=True,
            por_verificar=por_verificar,
        )

    def _pintar_resumen(self) -> None:
        self.resumen.configure(text=texto_resumen(self.enlaces))

    def verificar_todos(self) -> None:
        """Comprueba la lista completa, también lo que el filtro oculta."""
        seleccion = [enlace for enlace in self.enlaces if isinstance(enlace, dict)]
        self._iniciar_verificacion(seleccion, "Todavía no hay enlaces para verificar.")

    def reintentar_caidos(self) -> None:
        """Vuelve a comprobar los caídos, también los que el filtro oculta."""
        seleccion = [
            enlace
            for enlace in self.enlaces
            if isinstance(enlace, dict) and str(enlace.get("estado") or "") == "caído"
        ]
        self._iniciar_verificacion(seleccion, "No hay enlaces caídos.")

    def _iniciar_verificacion(self, seleccion: list, aviso_vacio: str) -> None:
        """Encola una tanda. Como máximo hay 8 hilos, compartidos con Añadir."""
        if self._verificacion_masiva or self._cerrando:
            return
        if not seleccion:
            self.aviso.configure(text=aviso_vacio)
            return

        self._lote += 1
        lote = self._lote
        cancelar = threading.Event()
        self._cancelar_lote = cancelar
        self._verificacion_masiva = True
        self._fallo_al_guardar = False
        self._hechos_lote = 0
        self._total_lote = len(seleccion)
        self._pendientes_lote = len(seleccion)
        self._mostrar_progreso()
        self.aviso.configure(text="")
        enviados = 0
        try:
            for enlace in seleccion:
                self._enviar_verificacion(
                    enlace,
                    str(enlace.get("url") or ""),
                    lote,
                    cancelar,
                )
                enviados += 1
        except RuntimeError:
            self._total_lote = enviados
            self._pendientes_lote = enviados
            if enviados == 0:
                self._finalizar_lote()

    def cancelar_verificacion(self) -> None:
        """No inicia más comprobaciones. Las que ya salieron a la red terminan."""
        if not self._verificacion_masiva or self._cancelar_lote is None:
            return
        if self._cancelar_lote.is_set():
            return
        self._cancelar_lote.set()
        self.boton_cancelar.configure(state="disabled")
        self.aviso.configure(text="Cancelando la verificación.")

    def _mostrar_progreso(self) -> None:
        self.barra_progreso.set(0)
        self.texto_progreso.configure(text=texto_progreso(0, self._total_lote))
        self.boton_cancelar.configure(state="normal")
        self.boton_verificar.configure(state="disabled", fg_color=COLORES["borde"])
        self.boton_reintentar.configure(state="disabled", fg_color=COLORES["borde"])
        self.barra_progreso.grid(row=0, column=1, sticky="ew", padx=(14, 12))
        self.texto_progreso.grid(row=0, column=2, padx=(0, 12))
        self.boton_cancelar.grid(row=0, column=3)

    def _ocultar_progreso(self) -> None:
        self.barra_progreso.grid_remove()
        self.texto_progreso.grid_remove()
        self.boton_cancelar.grid_remove()
        self.boton_verificar.configure(state="normal", fg_color=COLORES["acento"])
        self.boton_reintentar.configure(state="normal", fg_color=COLORES["acento"])

    def _pintar_progreso(self) -> None:
        total = self._total_lote
        hechos = self._hechos_lote
        self.texto_progreso.configure(text=texto_progreso(hechos, total))
        self.barra_progreso.set(0 if total <= 0 else hechos / total)

    def _cerrar_trabajo(self, lote: int | None, contado: bool) -> None:
        if lote is None or not self._verificacion_masiva or lote != self._lote:
            return
        self._pendientes_lote -= 1
        if contado:
            self._hechos_lote += 1
        self._pintar_progreso()
        if self._pendientes_lote <= 0:
            self._finalizar_lote()

    def _finalizar_lote(self) -> None:
        hechos = self._hechos_lote
        total = self._total_lote
        cancelado = self._cancelar_lote is not None and self._cancelar_lote.is_set()
        fallo = self._fallo_al_guardar
        lote = self._lote
        self._verificacion_masiva = False
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        self.boton_cancelar.configure(state="disabled")
        if fallo:
            self.aviso.configure(text="No se pudo guardar el resultado de la verificación.")
        elif cancelado:
            self.aviso.configure(
                text=f"Verificación cancelada. {hechos} de {total} comprobados."
            )
        else:
            self.aviso.configure(text=f"Verificación terminada. {hechos} de {total}.")
        self._after_ocultar = self.after(
            PAUSA_CIERRE_PROGRESO_MS,
            lambda lote=lote: self._ocultar_progreso_lote(lote),
        )

    def _ocultar_progreso_lote(self, lote: int) -> None:
        """Quita la barra solo si ese lote sigue siendo el último y ya terminó."""
        if self._cerrando or lote != self._lote or self._verificacion_masiva:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        self._ocultar_progreso()

    def _al_cerrar(self) -> None:
        """Cierra la ventana sin esperar a la red. Lo ya encolado no arranca."""
        self._cerrando = True
        if self._cancelar_lote is not None:
            self._cancelar_lote.set()
        for identificador in (self._after_resultados, self._after_ocultar):
            if identificador is None:
                continue
            try:
                self.after_cancel(identificador)
            except Exception:
                pass
        self._ejecutor.shutdown(wait=False, cancel_futures=True)
        self.destroy()

    def _sigue_en_lista(self, enlace: dict) -> bool:
        return any(item is enlace for item in self.enlaces)

    def _escribir_resultado(
        self,
        enlace: dict,
        estado: str,
        codigo: int | None,
        titulo: str,
        momento: str,
        token: int,
    ) -> None:
        """Escribe el resultado en la lista. Solo se llama desde el hilo principal."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if not self._sigue_en_lista(enlace):
            return
        if self._token_por_enlace.get(id(enlace)) != token:
            return

        enlace["estado"] = estado
        enlace["codigo_http"] = codigo
        enlace["titulo"] = titulo
        enlace["ultima_verificacion"] = momento
        try:
            datos.guardar_enlaces(self.enlaces, self.ruta)
        except OSError:
            self._fallo_al_guardar = True
            if not self._verificacion_masiva:
                self.aviso.configure(text="No se pudo guardar el resultado de la verificación.")
        self._pintar_fila(enlace)

    def _presentacion(self, enlace: dict) -> tuple[str, str, str]:
        estado = str(enlace.get("estado") or "pendiente")
        color = COLORES_ESTADO.get(estado, COLORES_ESTADO["pendiente"])
        titulo = str(enlace.get("titulo") or "").strip() or "Sin título"
        detalle = estado
        categoria = str(enlace.get("categoria") or "").strip()
        if categoria:
            detalle = f"{estado}  ·  {categoria}"
        return titulo, detalle, color

    def _pintar_fila(self, enlace: dict) -> None:
        """Actualiza la fila si sigue a la vista. Si entra o sale del filtro, redibuja."""
        self._pintar_resumen()
        visible = coincide(enlace, self._filtro, self._texto_busqueda(), self._filtro_categoria)
        info = self._filas.get(id(enlace))
        en_pantalla = False
        if info:
            try:
                en_pantalla = bool(info["punto"].winfo_exists())
            except Exception:
                en_pantalla = False
        if visible and en_pantalla and info is not None:
            titulo, detalle, color = self._presentacion(enlace)
            info["punto"].configure(fg_color=color)
            info["titulo"].configure(text=titulo)
            info["detalle"].configure(text=detalle, text_color=color)
            return
        if visible != en_pantalla:
            self.refrescar_lista()

    def refrescar_lista(self) -> None:
        conservar_foco = False
        try:
            conservar_foco = self.focus_get() == self.busqueda
        except Exception:
            conservar_foco = False
        fraccion = 0.0
        try:
            fraccion = float(self.lista._parent_canvas.yview()[0])
        except Exception:
            fraccion = 0.0

        self._filas = {}
        for hijo in self.lista.winfo_children():
            hijo.destroy()
        self._asegurar_filtro_categoria()
        visibles = [
            enlace
            for enlace in self.enlaces
            if isinstance(enlace, dict)
            and coincide(enlace, self._filtro, self._texto_busqueda(), self._filtro_categoria)
        ]
        if not self.enlaces:
            mensaje = "Todavía no hay enlaces."
        elif not visibles:
            mensaje = "Ningún enlace coincide con la búsqueda."
        else:
            mensaje = ""
        if mensaje:
            ctk.CTkLabel(
                self.lista,
                text=mensaje,
                text_color=COLORES["secundario"],
                font=self.fuente_url,
                fg_color="transparent",
            ).pack(anchor="w", padx=8, pady=28)
        else:
            for enlace in visibles:
                self._crear_fila(enlace)
        self._pintar_resumen()
        self._rehacer_menu_categoria()
        try:
            self.lista._parent_canvas.yview_moveto(fraccion)
        except Exception:
            pass
        if conservar_foco:
            self.busqueda.focus_set()

    def abrir(self, enlace: dict) -> None:
        """Abre la URL en el navegador y, si arranca, marca el enlace como visitado."""
        if not self._sigue_en_lista(enlace):
            return
        url = str(enlace.get("url") or "")
        try:
            abierto = webbrowser.open(url)
        except Exception:
            abierto = False
        if not abierto:
            self.aviso.configure(text="No se pudo abrir el enlace.")
            return

        self.aviso.configure(text="")
        enlace["visitado"] = True
        try:
            datos.guardar_enlaces(self.enlaces, self.ruta)
        except OSError:
            self.aviso.configure(text="No se pudo guardar el enlace.")
            return
        self.refrescar_lista()

    def copiar(self, enlace: dict, boton: ctk.CTkButton) -> None:
        """Copia la URL y cambia el icono a check durante un segundo."""
        url = str(enlace.get("url") or "")
        self.clipboard_clear()
        self.clipboard_append(url)
        self.update_idletasks()
        boton.configure(image=self.iconos["check"])
        pendiente = getattr(boton, "_aviso_copiado", None)
        if pendiente is not None:
            self.after_cancel(pendiente)
        boton._aviso_copiado = self.after(1000, lambda b=boton: self._restaurar_copiar(b))

    def _restaurar_copiar(self, boton: ctk.CTkButton) -> None:
        try:
            if boton.winfo_exists():
                boton.configure(image=self.iconos["copiar"])
        except Exception:
            return

    def confirmar_eliminar(self, enlace: dict) -> None:
        """Pide confirmación antes de quitar el enlace."""
        if not self._sigue_en_lista(enlace):
            return
        dialogo = getattr(self, "_dialogo_eliminar", None)
        if dialogo is not None:
            try:
                if dialogo.winfo_exists():
                    dialogo.lift()
                    return
            except Exception:
                pass

        dialogo = ctk.CTkToplevel(self)
        self._dialogo_eliminar = dialogo
        dialogo.title("Eliminar enlace")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color=COLORES["fondo"])
        dialogo.transient(self)
        self.update_idletasks()
        ancho, alto = 480, 210
        x = self.winfo_rootx() + max(0, (self.winfo_width() - ancho) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - alto) // 2)
        dialogo.geometry(f"{ancho}x{alto}+{x}+{y}")

        ctk.CTkLabel(
            dialogo,
            text="¿Eliminar este enlace?",
            text_color=COLORES["texto"],
            font=self.fuente_titulo,
        ).pack(anchor="w", padx=24, pady=(22, 8))
        ctk.CTkLabel(
            dialogo,
            text=str(enlace.get("url") or ""),
            wraplength=430,
            justify="left",
            anchor="w",
            text_color=COLORES["secundario"],
            font=self.fuente_url,
        ).pack(anchor="w", padx=24, pady=(0, 16))

        acciones = ctk.CTkFrame(dialogo, fg_color="transparent")
        acciones.pack(anchor="e", padx=24, pady=(0, 20))
        ctk.CTkButton(
            acciones,
            text="Cancelar",
            width=110,
            height=36,
            corner_radius=8,
            fg_color=COLORES["barra"],
            hover_color=COLORES["borde"],
            text_color=COLORES["texto"],
            command=dialogo.destroy,
        ).pack(side="left", padx=(0, 8))
        ctk.CTkButton(
            acciones,
            text="Eliminar",
            width=110,
            height=36,
            corner_radius=8,
            fg_color=COLORES_ESTADO["caído"],
            hover_color="#C4473A",
            text_color=COLORES["texto_boton"],
            command=lambda: self._eliminar(enlace, dialogo),
        ).pack(side="left")

        dialogo.protocol("WM_DELETE_WINDOW", dialogo.destroy)
        dialogo.bind("<Escape>", lambda _evento: dialogo.destroy())
        dialogo.after(50, dialogo.lift)
        dialogo.after(50, dialogo.focus)
        dialogo.grab_set()

    def _eliminar(self, enlace: dict, dialogo: ctk.CTkToplevel) -> None:
        try:
            dialogo.destroy()
        except Exception:
            pass
        if not self._sigue_en_lista(enlace):
            return
        self.enlaces = [item for item in self.enlaces if item is not enlace]
        try:
            datos.guardar_enlaces(self.enlaces, self.ruta)
        except OSError:
            self.aviso.configure(text="No se pudo guardar el enlace.")
            return
        self.aviso.configure(text="")
        self.refrescar_lista()

    def _boton_fila(self, padre: ctk.CTkFrame, icono: str, comando) -> ctk.CTkButton:
        return ctk.CTkButton(
            padre,
            text="",
            image=self.iconos[icono],
            width=36,
            height=36,
            corner_radius=8,
            fg_color=COLORES["fondo"],
            hover_color=COLORES["borde"],
            command=comando,
        )

    def _ligar_doble_clic(self, widget, enlace: dict) -> None:
        widget.bind("<Double-Button-1>", lambda _evento, e=enlace: self.abrir(e))
        for hijo in widget.winfo_children():
            self._ligar_doble_clic(hijo, enlace)

    def _crear_fila(self, enlace: dict) -> None:
        titulo, detalle, color = self._presentacion(enlace)

        fila = ctk.CTkFrame(self.lista, fg_color=COLORES["fila"], corner_radius=12)
        fila.pack(fill="x", pady=6, padx=4)
        fila.grid_columnconfigure(1, weight=1)

        punto = ctk.CTkFrame(fila, width=12, height=12, corner_radius=6, fg_color=color)
        punto.grid(row=0, column=0, padx=(16, 12), pady=16)
        punto.grid_propagate(False)

        textos = ctk.CTkFrame(fila, fg_color="transparent")
        textos.grid(row=0, column=1, sticky="ew", pady=14, padx=(0, 8))

        etiqueta_titulo = ctk.CTkLabel(
            textos,
            text=titulo,
            anchor="w",
            justify="left",
            text_color=COLORES["texto"],
            font=self.fuente_titulo,
            fg_color="transparent",
        )
        etiqueta_titulo.pack(fill="x")
        ctk.CTkLabel(
            textos,
            text=str(enlace.get("url") or ""),
            anchor="w",
            justify="left",
            wraplength=480,
            text_color=COLORES["secundario"],
            font=self.fuente_url,
            fg_color="transparent",
        ).pack(fill="x", pady=(2, 0))

        notas = str(enlace.get("notas") or "").strip()
        if notas:
            primera = notas.splitlines()[0].strip()
            if len(primera) > 80:
                primera = primera[:77] + "..."
            ctk.CTkLabel(
                textos,
                text=primera,
                anchor="w",
                justify="left",
                text_color=COLORES["secundario"],
                font=self.fuente_detalle,
                fg_color="transparent",
            ).pack(fill="x", pady=(2, 0))

        etiqueta_detalle = ctk.CTkLabel(
            textos,
            text=detalle,
            anchor="w",
            text_color=color,
            font=self.fuente_detalle,
            fg_color="transparent",
        )
        etiqueta_detalle.pack(fill="x", pady=(4, 0))
        self._filas[id(enlace)] = {
            "punto": punto,
            "titulo": etiqueta_titulo,
            "detalle": etiqueta_detalle,
        }

        if enlace.get("visitado"):
            ctk.CTkLabel(
                fila,
                text="",
                image=self.iconos["check"],
                fg_color="transparent",
            ).grid(row=0, column=2, padx=(4, 8), pady=16)

        acciones = ctk.CTkFrame(fila, fg_color="transparent")
        acciones.grid(row=0, column=3, padx=(4, 12), pady=12)
        self._boton_fila(acciones, "editar", lambda e=enlace: self.editar(e)).pack(side="left", padx=3)
        self._boton_fila(acciones, "abrir", lambda e=enlace: self.abrir(e)).pack(side="left", padx=3)
        boton_copiar = self._boton_fila(acciones, "copiar", lambda: None)
        boton_copiar.configure(command=lambda e=enlace, b=boton_copiar: self.copiar(e, b))
        boton_copiar.pack(side="left", padx=3)
        self._boton_fila(acciones, "eliminar", lambda e=enlace: self.confirmar_eliminar(e)).pack(
            side="left", padx=3
        )
        fila.bind("<Double-Button-1>", lambda _evento, e=enlace: self.abrir(e))
        self._ligar_doble_clic(punto, enlace)
        self._ligar_doble_clic(textos, enlace)


def _mostrar_error(mensaje: str) -> None:
    ventana = ctk.CTk()
    ventana.title("Gestor de Enlaces")
    ventana.geometry("540x200")
    ventana.minsize(420, 160)
    ventana.configure(fg_color=COLORES["fondo"])
    ctk.CTkLabel(
        ventana,
        text=mensaje,
        wraplength=480,
        justify="left",
        text_color=COLORES["texto"],
        font=ctk.CTkFont(size=14),
    ).pack(padx=24, pady=24, fill="both", expand=True)
    ventana.mainloop()


def iniciar(ruta: Path | None = None) -> None:
    """Abre la ventana. Si faltan iconos, muestra el motivo y no sigue."""
    ctk.set_appearance_mode("dark")
    try:
        iconos = cargar_iconos()
    except FileNotFoundError as exc:
        _mostrar_error(str(exc))
        return
    aplicacion = Aplicacion(ruta=ruta, iconos=iconos)
    aplicacion.mainloop()
