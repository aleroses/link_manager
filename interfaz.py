# Gestor de Enlaces. Licencia GPL-3.0. El texto está en LICENSE.
"""Ventana del Gestor de Enlaces.

Tema oscuro, campo para añadir una URL y lista con el estado de cada
enlace. La comprobación de red ocurre en un grupo de hasta 8 hilos.
Esos hilos no tocan widgets: dejan el resultado en una cola y el hilo
principal lo aplica con after().
"""

from __future__ import annotations

import queue
import sys
import threading
import time
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from tkinter import filedialog
from tkinter.font import Font as FuenteTk

import customtkinter as ctk
from PIL import Image

import datos
import registro
import verificador

# Tope de comprobaciones simultáneas. Más hilos no aceleran la red y
# sí pueden disparar bloqueos en los sitios.
HILOS_VERIFICACION = 8
# La barra se queda un momento en el valor final para que se pueda leer.
PAUSA_CIERRE_PROGRESO_MS = 700
# A partir de esta cantidad, Abrir todos pide confirmación.
UMBRAL_ABRIR_TODOS = 5
# Ancho mínimo de una columna. Con 480, la lista pasa a dos columnas
# cuando el contenedor llega a 960 px, cerca de 1000 px de ventana.
ANCHO_MINIMO_COLUMNA = 480
MAX_COLUMNAS_ENLACES = 2
MAX_COLUMNAS_TARJETAS = 3
DEBOUNCE_REDIMENSION_MS = 150
# Una pasada de la cola pinta como mucho una vez por este intervalo.
AGRUPAR_REPINTADO_MS = 150
# El buscador espera a la última tecla antes de refiltrar.
DEBOUNCE_BUSQUEDA_MS = 150
# Vueltas del icono de carga. 12 fotogramas cada 80 ms.
FOTOGRAMAS_CARGA = 12
INTERVALO_CARGA_MS = 80
# Punto, hueco de visitado, cuatro botones y márgenes de la fila.
RESERVA_TEXTO_FILA = 292
# Icono de carpeta y márgenes del nombre en la tarjeta.
RESERVA_TEXTO_TARJETA = 96
# Márgenes del resumen de estados dentro de la tarjeta.
RESERVA_RESUMEN_TARJETA = 48

def directorio_recursos() -> Path:
    """Carpeta de los archivos empaquetados. En desarrollo, la del proyecto."""
    base = getattr(sys, "_MEIPASS", None)
    if base:
        return Path(base)
    return Path(__file__).resolve().parent


CARPETA_ICONOS = directorio_recursos() / "assets" / "icons"

# Nombre interno -> archivo Lucide, sin extensión.
ICONOS = {
    "anadir": "plus",
    "abrir": "external-link",
    "copiar": "copy",
    "eliminar": "trash-2",
    "verificar": "refresh-cw",
    "carga": "loader-circle",
    "buscar": "search",
    "filtrar": "filter",
    "editar": "pencil",
    "importar": "import",
    "exportar": "upload",
    "categoria": "tag",
    "check": "check",
    "alerta": "triangle-alert",
    "cerrar": "x",
    "carpeta": "folder",
    "carpeta_mas": "folder-plus",
    "volver": "arrow-left",
    "cuadricula": "layout-grid",
    "lista": "list",
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
ETIQUETA_SIN_CATEGORIA = "Sin categoría"
ETIQUETA_NUEVA_ALTA = "Nueva categoría..."


def columnas_para_ancho(ancho: int, minimo: int, maximo: int) -> int:
    """Cuántas columnas caben en ancho, entre 1 y maximo.

    Hace falta el doble del mínimo para abrir la segunda columna.
    """
    if maximo < 1 or minimo <= 0 or ancho < minimo * 2:
        return 1
    return max(1, min(maximo, ancho // minimo))


def recortar_texto(texto: str, medir, ancho: int) -> str:
    """Devuelve el texto, o un corte con ... si no cabe en ancho píxeles.

    medir(cadena) devuelve el ancho en píxeles de esa cadena.
    """
    if ancho <= 0:
        return ""
    if medir(texto) <= ancho:
        return texto
    puntos = "..."
    if medir(puntos) > ancho:
        return ""
    bajo = 0
    alto = len(texto)
    while bajo < alto:
        medio = (bajo + alto + 1) // 2
        if medir(texto[:medio] + puntos) <= ancho:
            bajo = medio
        else:
            alto = medio - 1
    if bajo <= 0:
        return puntos if medir(puntos) <= ancho else ""
    return texto[:bajo] + puntos


def texto_ultima_verificacion(enlace: dict) -> str:
    """Fecha corta de la última comprobación.

    Un pendiente sin fecha usable dice «sin verificar». Un estado
    conocido sin fecha no añade texto: pudo llegar de un CSV.
    """
    cruda = str(enlace.get("ultima_verificacion") or "").strip()
    if cruda:
        try:
            momento = datetime.fromisoformat(cruda)
        except ValueError:
            momento = None
        if momento is not None:
            if momento.tzinfo is None:
                momento = momento.replace(tzinfo=timezone.utc)
            return f"verificado {momento.astimezone().strftime('%d/%m/%Y')}"
    if str(enlace.get("estado") or "pendiente") == "pendiente":
        return "sin verificar"
    return ""


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
        raise FileNotFoundError(
            "Falta un icono en assets/icons/. "
            f"No se encuentra: {lista}. "
            "Restaura esa carpeta o vuelve a instalar la aplicación."
        )
    return imagenes


def fotogramas_carga(ruta: Path) -> list[ctk.CTkImage]:
    """Doce giros del icono de 40 px, mostrados a 20 px."""
    imagen = Image.open(ruta).convert("RGBA")
    fotogramas: list[ctk.CTkImage] = []
    for paso in range(FOTOGRAMAS_CARGA):
        giro = imagen.rotate(
            paso * (360 / FOTOGRAMAS_CARGA),
            resample=Image.Resampling.BICUBIC,
            expand=False,
        )
        fotogramas.append(ctk.CTkImage(light_image=giro, dark_image=giro, size=(20, 20)))
    return fotogramas


def _mensaje_permiso(exc: OSError, alternativo: str) -> str:
    """Mensaje de guardado. Distingue una carpeta sin permisos."""
    if isinstance(exc, PermissionError) or exc.errno in {1, 13}:
        return "No se puede escribir en la carpeta de datos. Revisa los permisos."
    return alternativo


class Aplicacion(ctk.CTk):
    """Ventana principal. Guarda en disco después de cada cambio."""

    def __init__(self, ruta: Path | None = None, iconos: dict[str, ctk.CTkImage] | None = None) -> None:
        super().__init__()
        self.ruta = ruta if ruta is not None else datos.ruta_datos()
        self.iconos = iconos if iconos is not None else cargar_iconos()
        self._aviso_inicial = datos.aviso_ruta
        try:
            self.coleccion: dict = datos.cargar_enlaces(self.ruta)
        except OSError as exc:
            registro.anotar("No se pudo leer la carpeta de datos.", exc)
            self.coleccion = datos.coleccion_vacia()
            self._aviso_inicial = _mensaje_permiso(
                exc,
                "No se pudo abrir el archivo de enlaces.",
            )
        else:
            if datos.aviso_carga:
                self._aviso_inicial = datos.aviso_carga
        self._vista = "categorias"
        self._seccion: str | None = None
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
        self._token_titulo = 0
        self._titulo_obtenido: str | None = None
        self._campo_titulo: ctk.CTkEntry | None = None
        self._boton_titulo: ctk.CTkButton | None = None
        # El token evita que un resultado viejo pise uno más reciente
        # del mismo enlace (por ejemplo, añadir y justo después
        # verificar todos).
        self._token_por_enlace: dict[int, int] = {}
        self._cancelar_lote: threading.Event | None = None
        self._verificacion_masiva = False
        self._con_barra = False
        self._nombre_lote: str | None = None
        self._botones_tarjeta: dict[str, ctk.CTkButton] = {}
        self._fotogramas_carga = fotogramas_carga(CARPETA_ICONOS / "loader-circle-40.png")
        self._indice_carga = 0
        self._after_carga: str | None = None
        self._total_lote = 0
        self._hechos_lote = 0
        self._pendientes_lote = 0
        self._fallo_al_guardar = False
        self._filas: dict[int, dict] = {}
        self._recortes: list[dict] = []
        self._fuentes_medida: dict[tuple, FuenteTk] = {}
        self._columnas = 1
        self._ancho_lista = 0
        self._after_redimension: str | None = None
        self._after_resultados: str | None = None
        self._after_ocultar: str | None = None
        self._after_repintado: str | None = None
        self._after_busqueda: str | None = None
        self._vista_sucia = False
        self._repintado_enlaces: list[dict] = []
        self._guardado_pendiente = False
        self._sin_conexion_suelto = False
        # 0: todavía no hubo un pintado agrupado, así que el primero es inmediato.
        self._ultimo_repintado = 0.0
        self._filtro = "todos"
        self._filtro_categoria = "todas"
        self._categoria_alta = ETIQUETA_SIN_CATEGORIA
        self.fuente_titulo = ctk.CTkFont(size=15, weight="bold")
        self.fuente_url = ctk.CTkFont(size=13)
        self.fuente_detalle = ctk.CTkFont(size=12)
        self._configurar_ventana()
        self._construir()
        self._aplicar_vista()
        self.refrescar_lista()
        if self._aviso_inicial:
            self.aviso.configure(text=self._aviso_inicial)
        self._sin_conexion = False

    @property
    def enlaces(self) -> list:
        return self.coleccion["enlaces"]

    @enlaces.setter
    def enlaces(self, valor: list) -> None:
        self.coleccion["enlaces"] = valor

    def _guardar(self) -> None:
        try:
            datos.guardar_enlaces(self.coleccion, self.ruta)
        except OSError as exc:
            registro.anotar("No se pudo guardar el archivo de enlaces.", exc)
            raise

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

        ctk.CTkLabel(
            interior,
            text="Categoría",
            text_color=COLORES["texto"],
            font=self.fuente_url,
        ).pack(side="left", padx=(0, 8))
        self.menu_alta = ctk.CTkOptionMenu(
            interior,
            values=[ETIQUETA_SIN_CATEGORIA, ETIQUETA_NUEVA_ALTA],
            command=self._al_elegir_categoria_alta,
            width=210,
            height=42,
            corner_radius=10,
            fg_color=COLORES["fondo"],
            button_color=COLORES["borde"],
            button_hover_color=COLORES["acento"],
            dropdown_fg_color=COLORES["barra"],
            dropdown_hover_color=COLORES["borde"],
            dropdown_text_color=COLORES["texto"],
            text_color=COLORES["texto"],
            font=self.fuente_url,
            dropdown_font=self.fuente_detalle,
        )
        self.menu_alta.pack(side="left", padx=(0, 12))
        self.menu_alta.set(ETIQUETA_SIN_CATEGORIA)

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

        self.fila_vista = ctk.CTkFrame(barra, fg_color="transparent")
        self.fila_vista.pack(fill="x", padx=20, pady=(8, 0))
        self.vista_control = ctk.CTkSegmentedButton(
            self.fila_vista,
            values=["Categorías", "Todos los enlaces"],
            command=self._al_cambiar_vista,
            height=36,
            corner_radius=10,
            font=self.fuente_detalle,
            fg_color=COLORES["fondo"],
            selected_color=COLORES["acento"],
            selected_hover_color=COLORES["acento_hover"],
            unselected_color=COLORES["barra"],
            unselected_hover_color=COLORES["borde"],
            text_color=COLORES["texto"],
        )
        self.vista_control.pack(side="left")
        self.vista_control.set("Categorías")
        self.vista_control._buttons_dict["Categorías"].configure(
            image=self.iconos["cuadricula"],
            compound="left",
        )
        self.vista_control._buttons_dict["Todos los enlaces"].configure(
            image=self.iconos["lista"],
            compound="left",
        )
        self.boton_volver = ctk.CTkButton(
            self.fila_vista,
            text="Volver",
            image=self.iconos["volver"],
            compound="left",
            width=120,
            height=36,
            corner_radius=10,
            fg_color=COLORES["fondo"],
            hover_color=COLORES["borde"],
            text_color=COLORES["texto"],
            font=self.fuente_detalle,
            command=self._volver_tarjetas,
        )
        self.titulo_seccion = ctk.CTkLabel(
            self.fila_vista,
            text="",
            anchor="w",
            text_color=COLORES["texto"],
            font=self.fuente_titulo,
        )
        self.boton_nueva = ctk.CTkButton(
            self.fila_vista,
            text="Nueva categoría",
            image=self.iconos["carpeta_mas"],
            compound="left",
            width=190,
            height=36,
            corner_radius=10,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto_boton"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self.nueva_categoria,
        )
        self.boton_verificar_tarjetas = ctk.CTkButton(
            self.fila_vista,
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
        self.boton_verificar_categoria = ctk.CTkButton(
            self.fila_vista,
            text="Verificar categoría",
            image=self.iconos["verificar"],
            compound="left",
            width=210,
            height=36,
            corner_radius=10,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto_boton"],
            font=ctk.CTkFont(size=13, weight="bold"),
            command=self._verificar_seccion_actual,
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

        self._etiqueta_filtro_categoria = ctk.CTkLabel(
            self.fila_buscar,
            text="",
            image=self.iconos["categoria"],
            fg_color="transparent",
        )
        self._etiqueta_filtro_categoria.pack(side="left", padx=(12, 8))
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
        self.lista._parent_canvas.bind("<Configure>", self._al_redimensionar_lista, add="+")
        self.entrada.focus_set()
        self._after_resultados = self.after(100, self._recoger_resultados)

    def anadir(self) -> None:
        """Normaliza la URL, rechaza duplicados y verifica en segundo plano."""
        nuevos, repetidos, invalidos = datos.nuevos_enlaces(
            [self.entrada.get()],
            self.enlaces,
            self.coleccion,
            self._categoria_alta,
        )
        if invalidos or (not nuevos and not repetidos):
            self.aviso.configure(text="Ese enlace no es válido. Usa una dirección http o https.")
            return
        if not nuevos:
            self.aviso.configure(text="Ese enlace ya está en la lista.")
            return

        self.aviso.configure(text="")
        enlace = nuevos[0]
        self.enlaces.append(enlace)
        try:
            self._guardar()
        except OSError as exc:
            self.enlaces.pop()
            self.aviso.configure(text=_mensaje_permiso(exc, "No se pudo guardar el enlace."))
            return

        self.entrada.delete(0, "end")
        self.refrescar_lista()
        self._enviar_verificacion(enlace, str(enlace.get("url") or ""), lote=None, cancelar=None)
        if self._mostrando_tarjetas():
            destino = str(enlace.get("categoria") or "").strip() or ETIQUETA_SIN_CATEGORIA
            self.aviso.configure(text=f"Enlace añadido en {destino}.")
        elif not coincide(
            enlace,
            self._filtro,
            self._texto_busqueda(),
            self._categoria_consulta(),
        ):
            self.aviso.configure(text="Enlace añadido. No coincide con el filtro actual.")

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
                (
                    "resultado",
                    enlace,
                    estado,
                    codigo,
                    titulo,
                    momento,
                    lote,
                    token,
                    verificador.motivo_reciente(),
                )
            )
        except Exception as exc:
            registro.anotar("Falló la comprobación de un enlace.", exc)
            momento = datetime.now(timezone.utc).isoformat(timespec="seconds")
            motivo = (
                verificador.MOTIVO_SIN_CONEXION
                if verificador.es_sin_conexion(exc)
                else ""
            )
            self._resultados.put(
                ("resultado", enlace, "caído", None, "", momento, lote, token, motivo)
            )

    def _recoger_resultados(self) -> None:
        """Aplica lo que los hilos de red ya terminaron. Corre en el hilo principal.

        Vacía la cola, escribe el JSON una vez y deja el pintado para una
        sola pasada, como mucho cada AGRUPAR_REPINTADO_MS.
        """
        if self._cerrando:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if self._after_resultados is not None:
            try:
                self.after_cancel(self._after_resultados)
            except Exception:
                pass
            self._after_resultados = None
        cambios, cierres = self._vaciar_cola()
        if cambios:
            self._guardar_tanda()
            self._pintar_resumen()
        for lote, contado in cierres:
            self._cerrar_trabajo(lote, contado=contado)
        if cambios and not self._cerrando:
            self._pedir_repintado(cambios)
        if self._cerrando:
            return
        self._after_resultados = self.after(100, self._recoger_resultados)

    def _vaciar_cola(self) -> tuple[list[dict], list[tuple[int | None, bool]]]:
        """Aplica la cola entera. No guarda ni pinta.

        El segundo valor es cada cierre de lote: el número de lote y si
        cuenta como comprobación hecha. Un resultado ignorado (enlace
        borrado o token viejo) también cierra su puesto en la barra.
        """
        cambios: list[dict] = []
        cierres: list[tuple[int | None, bool]] = []
        try:
            while True:
                item = self._resultados.get_nowait()
                tipo = item[0]
                if tipo == "omitido":
                    cierres.append((item[1], False))
                    continue
                if tipo == "titulo_dialogo":
                    _, dialogo_id, token, texto = item
                    self._aplicar_titulo_dialogo(dialogo_id, token, texto)
                    continue
                motivo = item[8] if len(item) > 8 else ""
                _, enlace, estado, codigo, titulo, momento, lote, token = item[:8]
                if self._escribir_resultado(
                    enlace, estado, codigo, titulo, momento, token, motivo, lote
                ):
                    cambios.append(enlace)
                cierres.append((lote, True))
        except queue.Empty:
            pass
        return cambios, cierres

    def _guardar_tanda(self) -> None:
        """Un guardado para todos los resultados ya aplicados."""
        if not self._guardado_pendiente:
            return
        try:
            self._guardar()
        except OSError as exc:
            self._fallo_al_guardar = True
            self._sin_conexion_suelto = False
            if not self._verificacion_masiva:
                try:
                    self.aviso.configure(
                        text=_mensaje_permiso(
                            exc,
                            "No se pudo guardar el resultado de la verificación.",
                        )
                    )
                except Exception:
                    pass
            return
        self._guardado_pendiente = False
        if self._sin_conexion_suelto:
            self._sin_conexion_suelto = False
            try:
                self.aviso.configure(
                    text="No hay conexión a internet. El enlace queda como caído."
                )
            except Exception:
                pass

    def _pedir_repintado(self, enlaces: list[dict]) -> None:
        """Marca la vista sucia y pinta ahora, o como mucho una vez cada 150 ms."""
        self._vista_sucia = True
        vistos = {id(item) for item in self._repintado_enlaces}
        for enlace in enlaces:
            if id(enlace) not in vistos:
                self._repintado_enlaces.append(enlace)
                vistos.add(id(enlace))
        if self._after_repintado is not None or self._cerrando:
            return
        transcurrido_ms = (time.monotonic() - self._ultimo_repintado) * 1000
        if self._ultimo_repintado <= 0 or transcurrido_ms >= AGRUPAR_REPINTADO_MS:
            self._aplicar_repintado()
            return
        espera = max(1, int(AGRUPAR_REPINTADO_MS - transcurrido_ms))
        self._after_repintado = self.after(espera, self._aplicar_repintado)

    def _aplicar_repintado(self) -> None:
        """Una reconstrucción, o un retoque de las filas que siguen a la vista."""
        self._after_repintado = None
        if self._cerrando or not self._vista_sucia:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        enlaces = self._repintado_enlaces
        self._vista_sucia = False
        self._repintado_enlaces = []
        self._ultimo_repintado = time.monotonic()
        if self._mostrando_tarjetas() or self._alguno_cambia_de_filtro(enlaces):
            self.refrescar_lista()
            return
        for enlace in enlaces:
            self._pintar_fila(enlace)
        self._pintar_resumen()

    def _fila_en_pantalla(self, enlace: dict) -> bool:
        info = self._filas.get(id(enlace))
        if not info:
            return False
        try:
            return bool(info["punto"].winfo_exists())
        except Exception:
            return False

    def _alguno_cambia_de_filtro(self, enlaces: list[dict]) -> bool:
        """True si algún enlace de la tanda entra o sale de lo que se ve."""
        texto = self._texto_busqueda()
        consulta = self._categoria_consulta()
        for enlace in enlaces:
            visible = self._sigue_en_lista(enlace) and coincide(
                enlace, self._filtro, texto, consulta
            )
            if visible != self._fila_en_pantalla(enlace):
                return True
        return False

    def _texto_busqueda(self) -> str:
        return self.busqueda.get()

    def _al_buscar(self, _evento: object = None) -> None:
        if self._after_busqueda is not None:
            try:
                self.after_cancel(self._after_busqueda)
            except Exception:
                pass
        self._after_busqueda = self.after(DEBOUNCE_BUSQUEDA_MS, self._aplicar_busqueda)

    def _aplicar_busqueda(self) -> None:
        self._after_busqueda = None
        if self._cerrando:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
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

    def _nombres_categoria(self) -> list[str]:
        """Nombres guardados, en el orden del archivo."""
        nombres: list[str] = []
        vistos: set[str] = set()
        for ficha in self.coleccion.get("categorias") or []:
            if not isinstance(ficha, dict):
                continue
            texto = str(ficha.get("nombre") or "").strip()
            if not texto:
                continue
            clave = texto.casefold()
            if clave in vistos:
                continue
            vistos.add(clave)
            nombres.append(texto)
        return nombres

    def _categorias_conocidas(self) -> list[str]:
        return self._nombres_categoria()

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
        nuevos, repetidos, invalidos = datos.nuevos_enlaces(
            lineas,
            self.enlaces,
            self.coleccion,
            self._categoria_alta,
        )
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
            categorias_previas = list(self.coleccion["categorias"])
            if importacion:
                for enlace in nuevos:
                    nombre = str(enlace.get("categoria") or "").strip()
                    if nombre:
                        enlace["categoria"] = datos.asegurar_categoria(self.coleccion, nombre)
            self.enlaces.extend(nuevos)
            try:
                self._guardar()
            except OSError as exc:
                conservados = {id(item) for item in nuevos}
                self.enlaces = [item for item in self.enlaces if id(item) not in conservados]
                self.coleccion["categorias"] = categorias_previas
                self.aviso.configure(text=_mensaje_permiso(exc, "No se pudo guardar el enlace."))
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
                if coincide(
                    enlace,
                    self._filtro,
                    self._texto_busqueda(),
                    self._categoria_consulta(),
                )
            ]
            if not visibles:
                aviso = f"{aviso} No se ven con el filtro actual."
            elif len(visibles) < len(nuevos):
                aviso = f"{aviso} Algunos no se ven con el filtro actual."
            if not importacion and self._mostrando_tarjetas():
                destino = str(nuevos[0].get("categoria") or "").strip() or ETIQUETA_SIN_CATEGORIA
                aviso = f"{aviso} Quedan en {destino}."
        self.aviso.configure(text=aviso)

    def _mostrando_tarjetas(self) -> bool:
        return self._vista == "categorias" and self._seccion is None

    def _fijar_categoria_alta_por_vista(self) -> None:
        """La vista pone el valor por defecto. Un cambio manual se conserva hasta salir."""
        if self._vista == "categorias" and self._seccion is not None:
            self._categoria_alta = self._seccion or ETIQUETA_SIN_CATEGORIA
            return
        self._categoria_alta = ETIQUETA_SIN_CATEGORIA

    def _al_elegir_categoria_alta(self, valor: str) -> None:
        if valor != ETIQUETA_NUEVA_ALTA:
            self._categoria_alta = valor
            return
        anterior = self._categoria_alta
        self.menu_alta.set(anterior)

        def aplicar(texto: str) -> str | None:
            error = self._crear_desde_dialogo(texto)
            if error:
                return error
            ficha = datos.buscar_categoria(self.coleccion, texto)
            if ficha is not None:
                self._categoria_alta = str(ficha.get("nombre") or texto.strip())
            else:
                self._categoria_alta = texto.strip()
            return None

        self._pedir_nombre("Nueva categoría", "", aplicar)

    def _rehacer_menu_alta(self) -> None:
        opciones = [ETIQUETA_SIN_CATEGORIA, *self._nombres_categoria(), ETIQUETA_NUEVA_ALTA]
        self.menu_alta.configure(values=opciones)
        canonica = next(
            (item for item in opciones if item.casefold() == self._categoria_alta.casefold()),
            None,
        )
        if canonica is None or canonica == ETIQUETA_NUEVA_ALTA:
            self._categoria_alta = ETIQUETA_SIN_CATEGORIA
            canonica = ETIQUETA_SIN_CATEGORIA
        else:
            self._categoria_alta = canonica
        self.menu_alta.set(canonica)

    def _categoria_consulta(self) -> str:
        """Filtro de categoría según la vista. Dentro de una sección manda la sección."""
        if self._vista == "categorias" and self._seccion is not None:
            return "sin" if self._seccion == "" else self._seccion
        return self._filtro_categoria

    def _enlaces_de(self, nombre: str) -> list[dict]:
        clave = nombre.strip().casefold()
        resultado: list[dict] = []
        for enlace in self.enlaces:
            if not isinstance(enlace, dict):
                continue
            actual = str(enlace.get("categoria") or "").strip()
            if not clave:
                if not actual:
                    resultado.append(enlace)
            elif actual.casefold() == clave:
                resultado.append(enlace)
        return resultado

    def _al_cambiar_vista(self, valor: str) -> None:
        self._seccion = None
        self._vista = "enlaces" if valor == "Todos los enlaces" else "categorias"
        self._fijar_categoria_alta_por_vista()
        self._aplicar_vista()
        self.refrescar_lista()

    def _volver_tarjetas(self) -> None:
        self._seccion = None
        self._vista = "categorias"
        self._fijar_categoria_alta_por_vista()
        try:
            self.vista_control.set("Categorías")
        except Exception:
            pass
        self._aplicar_vista()
        self.refrescar_lista()

    def _entrar_seccion(self, nombre: str) -> None:
        self._vista = "categorias"
        self._seccion = nombre
        self._fijar_categoria_alta_por_vista()
        try:
            self.vista_control.set("Categorías")
        except Exception:
            pass
        self._aplicar_vista()
        self.refrescar_lista()

    def _verificar_seccion_actual(self) -> None:
        if self._seccion is None:
            return
        self.verificar_categoria(self._seccion)

    def _aplicar_vista(self) -> None:
        en_seccion = self._vista == "categorias" and self._seccion is not None
        if self._mostrando_tarjetas():
            self.fila_buscar.pack_forget()
            self.boton_volver.pack_forget()
            self.titulo_seccion.pack_forget()
            self.boton_verificar_categoria.pack_forget()
            self.boton_nueva.pack(side="right")
            self.boton_verificar_tarjetas.pack(side="right", padx=(0, 8))
            self._ocultar_boton_progreso()
            self._sincronizar_carga()
            return
        self.fila_buscar.pack(fill="x", padx=20, pady=(4, 0), before=self.aviso)
        self.boton_nueva.pack_forget()
        self.boton_verificar_tarjetas.pack_forget()
        if en_seccion:
            self.boton_volver.pack(side="left", padx=(12, 8))
            self.titulo_seccion.configure(text=self._seccion or "Sin categoría")
            self.titulo_seccion.pack(side="left")
            self.boton_verificar_categoria.pack(side="right")
            self._etiqueta_filtro_categoria.pack_forget()
            self.menu_categoria.pack_forget()
            self._ocultar_boton_progreso()
            self._sincronizar_carga()
            return
        self.boton_volver.pack_forget()
        self.titulo_seccion.pack_forget()
        self.boton_verificar_categoria.pack_forget()
        self._etiqueta_filtro_categoria.pack(side="left", padx=(12, 8))
        self.menu_categoria.pack(side="left")
        self._mostrar_boton_progreso()
        self._sincronizar_carga()

    def _mostrar_fila_progreso(self) -> None:
        if self.fila_verificar.winfo_manager():
            return
        self.fila_verificar.pack(fill="x", padx=20, pady=(0, 4), before=self.fila_vista)

    def _mostrar_boton_progreso(self) -> None:
        """En Todos los enlaces el botón vive junto a la barra."""
        self._mostrar_fila_progreso()
        self.boton_verificar.grid(row=0, column=0, sticky="w")

    def _ocultar_boton_progreso(self) -> None:
        """Fuera de Todos los enlaces no se ve Verificar todos."""
        self.boton_verificar.grid_remove()
        if self._verificacion_masiva and self._con_barra:
            self._mostrar_fila_progreso()
            return
        self.fila_verificar.pack_forget()

    def _pintar_tarjetas(self) -> None:
        self._botones_tarjeta = {}
        fichas: list[tuple[str, bool]] = [("", False)]
        for nombre in self._nombres_categoria():
            fichas.append((nombre, True))
        columnas = self._columnas_actuales(len(fichas))
        self._columnas = columnas
        rejilla = self._rejilla(columnas)
        for indice, (nombre, editable) in enumerate(fichas):
            self._crear_tarjeta(rejilla, nombre, editable, indice, columnas)
        self._sincronizar_carga()

    def _crear_tarjeta(
        self,
        padre: ctk.CTkFrame,
        nombre: str,
        editable: bool,
        indice: int,
        columnas: int,
    ) -> None:
        enlaces = self._enlaces_de(nombre)
        tarjeta = ctk.CTkFrame(padre, fg_color=COLORES["fila"], corner_radius=12)
        tarjeta.grid(
            row=indice // columnas,
            column=indice % columnas,
            sticky="nsew",
            padx=8,
            pady=8,
        )

        cabecera = ctk.CTkFrame(tarjeta, fg_color="transparent")
        cabecera.pack(fill="x", padx=16, pady=(14, 4))
        ctk.CTkLabel(
            cabecera,
            text="",
            image=self.iconos["carpeta"],
            fg_color="transparent",
        ).pack(side="left", padx=(0, 8))
        etiqueta_nombre = ctk.CTkLabel(
            cabecera,
            text="",
            anchor="w",
            text_color=COLORES["texto"],
            font=self.fuente_titulo,
            fg_color="transparent",
        )
        etiqueta_nombre.pack(side="left", fill="x", expand=True)
        self._registrar_recorte(
            etiqueta_nombre,
            "Sin categoría" if not nombre else nombre,
            self.fuente_titulo,
            RESERVA_TEXTO_TARJETA,
        )
        ctk.CTkLabel(
            tarjeta,
            text=_palabra(len(enlaces), "enlace", "enlaces"),
            anchor="w",
            text_color=COLORES["secundario"],
            font=self.fuente_url,
            fg_color="transparent",
        ).pack(fill="x", padx=16)
        resumen = ctk.CTkLabel(
            tarjeta,
            text=texto_resumen(enlaces),
            anchor="w",
            justify="left",
            text_color=COLORES["secundario"],
            font=self.fuente_detalle,
            fg_color="transparent",
        )
        resumen.pack(fill="x", padx=16, pady=(4, 8))
        self._registrar_recorte(
            resumen,
            texto_resumen(enlaces),
            self.fuente_detalle,
            RESERVA_RESUMEN_TARJETA,
            envolver=True,
        )

        acciones = ctk.CTkFrame(tarjeta, fg_color="transparent")
        acciones.pack(fill="x", padx=12, pady=(0, 12))
        self._boton_fila(acciones, "abrir", lambda n=nombre: self.abrir_todos(n)).pack(
            side="left", padx=3
        )
        boton_verificar = self._boton_fila(
            acciones,
            "verificar",
            lambda n=nombre: self.verificar_categoria(n),
        )
        boton_verificar.pack(side="left", padx=3)
        self._botones_tarjeta[nombre] = boton_verificar
        if editable:
            self._boton_fila(acciones, "editar", lambda n=nombre: self.renombrar_categoria(n)).pack(
                side="left", padx=3
            )
            self._boton_fila(
                acciones,
                "eliminar",
                lambda n=nombre: self.confirmar_eliminar_categoria(n),
            ).pack(side="left", padx=3)
        self._ligar_tarjeta(tarjeta, nombre)

    def _ligar_tarjeta(self, widget, nombre: str) -> None:
        if isinstance(widget, ctk.CTkButton):
            return
        widget.bind("<Button-1>", lambda _evento, n=nombre: self._entrar_seccion(n))
        for hijo in widget.winfo_children():
            self._ligar_tarjeta(hijo, nombre)

    def verificar_categoria(self, nombre: str) -> None:
        enlaces = self._enlaces_de(nombre)
        if not enlaces:
            self.aviso.configure(text="No hay enlaces en esta categoría.")
            return
        self._iniciar_verificacion(
            enlaces,
            "No hay enlaces en esta categoría.",
            con_barra=False,
            categoria=nombre,
        )

    def abrir_todos(self, nombre: str) -> None:
        enlaces = self._enlaces_de(nombre)
        if not enlaces:
            self.aviso.configure(text="Esta categoría no tiene enlaces.")
            return
        if len(enlaces) > UMBRAL_ABRIR_TODOS:
            self._confirmar_abrir_todos(enlaces)
            return
        self._abrir_enlaces(enlaces)

    def _confirmar_abrir_todos(self, enlaces: list[dict]) -> None:
        dialogo = ctk.CTkToplevel(self)
        dialogo.title("Abrir enlaces")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color=COLORES["fondo"])
        dialogo.transient(self)
        self.update_idletasks()
        ancho, alto = 480, 200
        x = self.winfo_rootx() + max(0, (self.winfo_width() - ancho) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - alto) // 2)
        dialogo.geometry(f"{ancho}x{alto}+{x}+{y}")
        ctk.CTkLabel(
            dialogo,
            text=f"Vas a abrir {len(enlaces)} enlaces.",
            text_color=COLORES["texto"],
            font=self.fuente_titulo,
        ).pack(anchor="w", padx=24, pady=(22, 16))
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
            text="Abrir",
            width=110,
            height=36,
            corner_radius=8,
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            text_color=COLORES["texto_boton"],
            command=lambda: self._aceptar_abrir_todos(enlaces, dialogo),
        ).pack(side="left")
        dialogo.protocol("WM_DELETE_WINDOW", dialogo.destroy)
        dialogo.bind("<Escape>", lambda _evento: dialogo.destroy())
        dialogo.after(50, dialogo.lift)
        dialogo.grab_set()

    def _aceptar_abrir_todos(self, enlaces: list[dict], dialogo: ctk.CTkToplevel) -> None:
        try:
            dialogo.destroy()
        except Exception:
            pass
        self._abrir_enlaces(enlaces)

    def _abrir_en_navegador(self, enlace: dict) -> bool:
        try:
            return bool(webbrowser.open(str(enlace.get("url") or "")))
        except Exception:
            return False

    def _abrir_enlaces(self, enlaces: list[dict]) -> None:
        abiertos = 0
        for enlace in enlaces:
            if not self._sigue_en_lista(enlace):
                continue
            if self._abrir_en_navegador(enlace):
                enlace["visitado"] = True
                abiertos += 1
        try:
            self._guardar()
        except OSError as exc:
            self.aviso.configure(text=_mensaje_permiso(exc, "No se pudo guardar el enlace."))
            return
        if abiertos == 0:
            self.aviso.configure(text="No se pudo abrir ninguno.")
        elif abiertos == 1:
            self.aviso.configure(text="Se abrió 1 enlace.")
        else:
            self.aviso.configure(text=f"Se abrieron {abiertos} enlaces.")
        self.refrescar_lista()

    def nueva_categoria(self) -> None:
        self._pedir_nombre("Nueva categoría", "", self._crear_desde_dialogo)

    def renombrar_categoria(self, nombre: str) -> None:
        self._pedir_nombre(
            "Renombrar categoría",
            nombre,
            lambda texto: self._renombrar_desde_dialogo(nombre, texto),
        )

    def _crear_desde_dialogo(self, texto: str) -> str | None:
        try:
            datos.crear_categoria(self.coleccion, texto)
            self._guardar()
        except datos.ErrorCategoria as exc:
            return str(exc)
        except OSError as exc:
            self.coleccion["categorias"].pop()
            return _mensaje_permiso(exc, "No se pudo guardar.")
        return None

    def _renombrar_desde_dialogo(self, anterior: str, texto: str) -> str | None:
        try:
            datos.renombrar_categoria(self.coleccion, anterior, texto)
            self._guardar()
        except datos.ErrorCategoria as exc:
            return str(exc)
        except OSError as exc:
            try:
                datos.renombrar_categoria(self.coleccion, texto, anterior)
            except datos.ErrorCategoria:
                pass
            return _mensaje_permiso(exc, "No se pudo guardar.")
        nuevo = texto.strip()
        if self._seccion is not None and self._seccion.casefold() == anterior.strip().casefold():
            self._seccion = nuevo
            self.titulo_seccion.configure(text=nuevo)
        if self._filtro_categoria.casefold() == anterior.strip().casefold():
            self._filtro_categoria = nuevo
        if self._categoria_alta.casefold() == anterior.strip().casefold():
            self._categoria_alta = nuevo
        return None

    def _pedir_nombre(self, titulo: str, inicial: str, aplicar) -> None:
        dialogo = ctk.CTkToplevel(self)
        dialogo.title(titulo)
        dialogo.resizable(False, False)
        dialogo.configure(fg_color=COLORES["fondo"])
        dialogo.transient(self)
        self.update_idletasks()
        ancho, alto = 460, 230
        x = self.winfo_rootx() + max(0, (self.winfo_width() - ancho) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - alto) // 2)
        dialogo.geometry(f"{ancho}x{alto}+{x}+{y}")
        ctk.CTkLabel(
            dialogo,
            text=titulo,
            anchor="w",
            text_color=COLORES["texto"],
            font=self.fuente_titulo,
        ).pack(fill="x", padx=24, pady=(20, 8))
        campo = ctk.CTkEntry(
            dialogo,
            height=36,
            corner_radius=10,
            border_width=1,
            border_color=COLORES["borde"],
            fg_color=COLORES["barra"],
            text_color=COLORES["texto"],
            font=self.fuente_url,
        )
        campo.pack(fill="x", padx=24)
        campo.insert(0, inicial)
        aviso = ctk.CTkLabel(
            dialogo,
            text="",
            anchor="w",
            text_color=COLORES["aviso"],
            font=self.fuente_detalle,
        )
        aviso.pack(fill="x", padx=24, pady=(8, 0))

        def guardar() -> None:
            error = aplicar(campo.get())
            if error:
                aviso.configure(text=error)
                return
            try:
                dialogo.destroy()
            except Exception:
                pass
            self._aplicar_vista()
            self.refrescar_lista()

        acciones = ctk.CTkFrame(dialogo, fg_color="transparent")
        acciones.pack(anchor="e", padx=24, pady=(12, 20))
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
            command=guardar,
        ).pack(side="left")
        dialogo.protocol("WM_DELETE_WINDOW", dialogo.destroy)
        dialogo.bind("<Escape>", lambda _evento: dialogo.destroy())
        dialogo.bind("<Return>", lambda _evento: guardar())
        dialogo.after(50, dialogo.lift)
        dialogo.after(50, campo.focus)
        dialogo.grab_set()

    def confirmar_eliminar_categoria(self, nombre: str) -> None:
        dialogo = ctk.CTkToplevel(self)
        dialogo.title("Eliminar categoría")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color=COLORES["fondo"])
        dialogo.transient(self)
        self.update_idletasks()
        ancho, alto = 520, 280
        x = self.winfo_rootx() + max(0, (self.winfo_width() - ancho) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - alto) // 2)
        dialogo.geometry(f"{ancho}x{alto}+{x}+{y}")
        cantidad = len(self._enlaces_de(nombre))
        ctk.CTkLabel(
            dialogo,
            text=f"Eliminar {nombre}",
            anchor="w",
            text_color=COLORES["texto"],
            font=self.fuente_titulo,
        ).pack(fill="x", padx=24, pady=(20, 6))
        ctk.CTkLabel(
            dialogo,
            text=f"Tiene {_palabra(cantidad, 'enlace', 'enlaces')}.",
            anchor="w",
            text_color=COLORES["secundario"],
            font=self.fuente_url,
        ).pack(fill="x", padx=24, pady=(0, 10))
        eleccion = ctk.StringVar(value="mover")
        ctk.CTkRadioButton(
            dialogo,
            text="Mover los enlaces a Sin categoría",
            variable=eleccion,
            value="mover",
            text_color=COLORES["texto"],
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            font=self.fuente_url,
        ).pack(anchor="w", padx=24, pady=4)
        ctk.CTkRadioButton(
            dialogo,
            text="Eliminar también los enlaces",
            variable=eleccion,
            value="borrar",
            text_color=COLORES["texto"],
            fg_color=COLORES["acento"],
            hover_color=COLORES["acento_hover"],
            font=self.fuente_url,
        ).pack(anchor="w", padx=24, pady=(4, 12))
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
            command=lambda: self._eliminar_categoria(nombre, eleccion.get() == "borrar", dialogo),
        ).pack(side="left")
        dialogo.protocol("WM_DELETE_WINDOW", dialogo.destroy)
        dialogo.bind("<Escape>", lambda _evento: dialogo.destroy())
        dialogo.after(50, dialogo.lift)
        dialogo.grab_set()

    def _eliminar_categoria(self, nombre: str, borrar_enlaces: bool, dialogo: ctk.CTkToplevel) -> None:
        try:
            dialogo.destroy()
        except Exception:
            pass
        categorias_previas = list(self.coleccion["categorias"])
        enlaces_previos = list(self.enlaces)
        textos = [
            (enlace, enlace.get("categoria"))
            for enlace in enlaces_previos
            if isinstance(enlace, dict)
        ]
        try:
            datos.eliminar_categoria(self.coleccion, nombre, borrar_enlaces)
            self._guardar()
        except datos.ErrorCategoria as exc:
            self.aviso.configure(text=str(exc))
            return
        except OSError as exc:
            self.coleccion["categorias"] = categorias_previas
            self.enlaces = enlaces_previos
            for enlace, categoria in textos:
                enlace["categoria"] = categoria
            self.aviso.configure(text=_mensaje_permiso(exc, "No se pudo guardar el enlace."))
            return
        self.aviso.configure(text="")
        if self._filtro_categoria.casefold() == nombre.strip().casefold():
            self._filtro_categoria = "todas"
        if self._categoria_alta.casefold() == nombre.strip().casefold():
            self._categoria_alta = ETIQUETA_SIN_CATEGORIA
        if self._seccion is not None and self._seccion.casefold() == nombre.strip().casefold():
            self._volver_tarjetas()
            return
        self.refrescar_lista()

    def editar(self, enlace: dict) -> None:
        """Pide título, categoría y notas. No toca la URL ni el estado."""
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
        self._titulo_obtenido = None
        dialogo.title("Editar enlace")
        dialogo.resizable(False, False)
        dialogo.configure(fg_color=COLORES["fondo"])
        dialogo.transient(self)
        self.update_idletasks()
        ancho, alto = 520, 620
        x = self.winfo_rootx() + max(0, (self.winfo_width() - ancho) // 2)
        y = self.winfo_rooty() + max(0, (self.winfo_height() - alto) // 2)
        dialogo.geometry(f"{ancho}x{alto}+{x}+{y}")

        ctk.CTkLabel(
            dialogo,
            text="Título",
            anchor="w",
            text_color=COLORES["texto"],
            font=self.fuente_detalle,
        ).pack(fill="x", padx=24, pady=(20, 6))
        titulo = ctk.CTkEntry(
            dialogo,
            height=36,
            corner_radius=10,
            border_width=1,
            border_color=COLORES["borde"],
            fg_color=COLORES["barra"],
            text_color=COLORES["texto"],
            font=self.fuente_url,
        )
        titulo.pack(fill="x", padx=24)
        titulo.insert(0, str(enlace.get("titulo") or ""))
        self._campo_titulo = titulo
        self._boton_titulo = ctk.CTkButton(
            dialogo,
            text="Obtener título de nuevo",
            width=220,
            height=36,
            corner_radius=8,
            fg_color=COLORES["barra"],
            hover_color=COLORES["borde"],
            text_color=COLORES["texto"],
            command=lambda: self._pedir_titulo(enlace, dialogo),
        )
        self._boton_titulo.pack(anchor="w", padx=24, pady=(10, 0))

        ctk.CTkLabel(
            dialogo,
            text="Categoría",
            anchor="w",
            text_color=COLORES["texto"],
            font=self.fuente_detalle,
        ).pack(fill="x", padx=24, pady=(14, 6))
        opciones = ["Sin categoría", *self._nombres_categoria()]
        actual = str(enlace.get("categoria") or "").strip()
        if actual and all(actual.casefold() != item.casefold() for item in opciones):
            opciones.append(actual)
        opciones.append("Nueva categoría")
        self._menu_categoria_edicion = ctk.CTkOptionMenu(
            dialogo,
            values=opciones,
            command=self._al_elegir_categoria_edicion,
            height=36,
            corner_radius=10,
            fg_color=COLORES["barra"],
            button_color=COLORES["borde"],
            button_hover_color=COLORES["acento"],
            dropdown_fg_color=COLORES["barra"],
            dropdown_hover_color=COLORES["borde"],
            dropdown_text_color=COLORES["texto"],
            text_color=COLORES["texto"],
            font=self.fuente_url,
            dropdown_font=self.fuente_detalle,
        )
        self._menu_categoria_edicion.pack(fill="x", padx=24)
        if not actual:
            self._menu_categoria_edicion.set("Sin categoría")
        else:
            elegido = next(
                (item for item in opciones if item.casefold() == actual.casefold()),
                actual,
            )
            self._menu_categoria_edicion.set(elegido)
        self._entrada_categoria_nueva = ctk.CTkEntry(
            dialogo,
            height=36,
            corner_radius=10,
            border_width=1,
            border_color=COLORES["borde"],
            fg_color=COLORES["barra"],
            text_color=COLORES["texto"],
            placeholder_text="Nombre de la categoría",
            font=self.fuente_url,
        )
        self._aviso_categoria = ctk.CTkLabel(
            dialogo,
            text="",
            anchor="w",
            text_color=COLORES["aviso"],
            font=self.fuente_detalle,
        )

        self._ancla_notas = ctk.CTkLabel(
            dialogo,
            text="Notas",
            anchor="w",
            text_color=COLORES["texto"],
            font=self.fuente_detalle,
        )
        self._ancla_notas.pack(fill="x", padx=24, pady=(14, 6))
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
            command=lambda: self._cerrar_edicion(dialogo),
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
            command=lambda: self._guardar_edicion(enlace, titulo, notas, dialogo),
        ).pack(side="left")

        dialogo.protocol("WM_DELETE_WINDOW", lambda: self._cerrar_edicion(dialogo))
        dialogo.bind("<Escape>", lambda _evento: self._cerrar_edicion(dialogo))
        dialogo.after(50, dialogo.lift)
        dialogo.after(50, titulo.focus)
        dialogo.grab_set()

    def _cerrar_edicion(self, dialogo: ctk.CTkToplevel) -> None:
        self._campo_titulo = None
        self._boton_titulo = None
        self._titulo_obtenido = None
        self._menu_categoria_edicion = None
        self._entrada_categoria_nueva = None
        self._aviso_categoria = None
        self._ancla_notas = None
        if getattr(self, "_dialogo_editar", None) is dialogo:
            self._dialogo_editar = None
        try:
            dialogo.destroy()
        except Exception:
            pass

    def _pedir_titulo(self, enlace: dict, dialogo: ctk.CTkToplevel) -> None:
        """Pide el título en segundo plano y lo deja en el campo al volver."""
        boton = self._boton_titulo
        if boton is None or self._cerrando:
            return
        self._token_titulo += 1
        token = self._token_titulo
        boton.configure(state="disabled", text="Obteniendo título...")
        try:
            self._ejecutor.submit(
                self._obtener_titulo_en_segundo_plano,
                str(enlace.get("url") or ""),
                id(dialogo),
                token,
            )
        except RuntimeError:
            boton.configure(state="normal", text="Obtener título de nuevo")

    def _obtener_titulo_en_segundo_plano(self, url: str, dialogo_id: int, token: int) -> None:
        """Corre fuera del hilo principal. No toca widgets."""
        try:
            _estado, _codigo, titulo = verificador.verificar_url(url)
            texto = titulo.strip() or verificador.titulo_descriptivo(url)
        except Exception:
            texto = verificador.titulo_descriptivo(url)
        self._resultados.put(("titulo_dialogo", dialogo_id, token, texto))

    def _aplicar_titulo_dialogo(self, dialogo_id: int, token: int, texto: str) -> None:
        if token != self._token_titulo:
            return
        dialogo = getattr(self, "_dialogo_editar", None)
        if dialogo is None or id(dialogo) != dialogo_id:
            return
        campo = self._campo_titulo
        boton = self._boton_titulo
        if campo is None:
            return
        try:
            if not campo.winfo_exists():
                return
            campo.delete(0, "end")
            campo.insert(0, texto)
            self._titulo_obtenido = texto
            if boton is not None and boton.winfo_exists():
                boton.configure(state="normal", text="Obtener título de nuevo")
        except Exception:
            return

    def _al_elegir_categoria_edicion(self, valor: str) -> None:
        entrada = self._entrada_categoria_nueva
        aviso = self._aviso_categoria
        if entrada is None:
            return
        if valor == "Nueva categoría":
            ancla = self._ancla_notas
            entrada.pack(fill="x", padx=24, pady=(8, 0), before=ancla)
            if aviso is not None:
                aviso.pack(fill="x", padx=24, pady=(4, 0), before=ancla)
            entrada.focus()
            return
        entrada.pack_forget()
        if aviso is not None:
            aviso.pack_forget()

    def _guardar_edicion(
        self,
        enlace: dict,
        titulo: ctk.CTkEntry,
        notas: ctk.CTkTextbox,
        dialogo: ctk.CTkToplevel,
    ) -> None:
        if not self._sigue_en_lista(enlace):
            self._cerrar_edicion(dialogo)
            return
        anterior_titulo = enlace.get("titulo")
        anterior_manual = enlace.get("titulo_manual")
        anterior_categoria = enlace.get("categoria")
        anterior_notas = enlace.get("notas")
        categorias_previas = list(self.coleccion["categorias"])
        menu = self._menu_categoria_edicion
        if menu is None:
            return
        elegido = menu.get()
        try:
            if elegido == "Nueva categoría":
                campo = self._entrada_categoria_nueva
                creada = datos.crear_categoria(
                    self.coleccion,
                    "" if campo is None else campo.get(),
                )
                categoria = str(creada.get("nombre") or "")
            elif elegido == "Sin categoría":
                categoria = ""
            else:
                categoria = elegido
        except datos.ErrorCategoria as exc:
            if self._aviso_categoria is not None:
                self._aviso_categoria.configure(text=str(exc))
                self._aviso_categoria.pack(fill="x", padx=24, pady=(4, 0))
            return
        decision = datos.resolver_edicion_titulo(
            str(anterior_titulo or ""),
            titulo.get(),
            self._titulo_obtenido,
            verificador.titulo_descriptivo(str(enlace.get("url") or "")),
        )
        if decision is not None:
            enlace["titulo"], enlace["titulo_manual"] = decision
        enlace["categoria"] = categoria
        enlace["notas"] = notas.get("1.0", "end-1c").strip()
        try:
            self._guardar()
        except OSError as exc:
            enlace["titulo"] = anterior_titulo
            enlace["titulo_manual"] = anterior_manual
            enlace["categoria"] = anterior_categoria
            enlace["notas"] = anterior_notas
            self.coleccion["categorias"] = categorias_previas
            self.aviso.configure(text=_mensaje_permiso(exc, "No se pudo guardar el enlace."))
            return
        self._cerrar_edicion(dialogo)
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
        except OSError as exc:
            registro.anotar("No se pudo exportar el CSV.", exc)
            self.aviso.configure(text=_mensaje_permiso(exc, "No se pudo exportar el CSV."))
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
        except ValueError as exc:
            registro.anotar(str(exc))
            self.aviso.configure(text=str(exc))
            return
        except OSError as exc:
            registro.anotar("No se pudo leer el CSV.", exc)
            self.aviso.configure(text=_mensaje_permiso(exc, "No se pudo leer el CSV."))
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
        self._iniciar_verificacion(seleccion, "Todavía no hay enlaces para verificar.", con_barra=True)

    def reintentar_caidos(self) -> None:
        """Vuelve a comprobar los caídos, también los que el filtro oculta."""
        seleccion = [
            enlace
            for enlace in self.enlaces
            if isinstance(enlace, dict) and str(enlace.get("estado") or "") == "caído"
        ]
        self._iniciar_verificacion(seleccion, "No hay enlaces caídos.", con_barra=True)

    def _iniciar_verificacion(
        self,
        seleccion: list,
        aviso_vacio: str,
        con_barra: bool = True,
        categoria: str | None = None,
    ) -> None:
        """Encola una tanda. Como máximo hay 8 hilos, compartidos con Añadir.

        con_barra es la verificación de toda la lista. Una categoría gira
        el botón y no muestra la barra.
        """
        if self._verificacion_masiva or self._cerrando:
            return
        if not seleccion:
            self.aviso.configure(text=aviso_vacio)
            return

        self._lote += 1
        self._sin_conexion = False
        lote = self._lote
        cancelar = threading.Event()
        self._cancelar_lote = cancelar
        self._verificacion_masiva = True
        self._con_barra = con_barra
        self._nombre_lote = categoria
        self._fallo_al_guardar = False
        self._hechos_lote = 0
        self._total_lote = len(seleccion)
        self._pendientes_lote = len(seleccion)
        self._desactivar_globales()
        if con_barra:
            self._mostrar_progreso()
        self._sincronizar_carga()
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

    def _desactivar_globales(self) -> None:
        for boton in (
            self.boton_verificar,
            self.boton_verificar_tarjetas,
            self.boton_reintentar,
        ):
            boton.configure(state="disabled", fg_color=COLORES["borde"])

    def _reactivar_globales(self) -> None:
        for boton in (
            self.boton_verificar,
            self.boton_verificar_tarjetas,
            self.boton_reintentar,
        ):
            boton.configure(state="normal", fg_color=COLORES["acento"])

    def _mostrar_progreso(self) -> None:
        self._mostrar_fila_progreso()
        self.barra_progreso.set(0)
        self.texto_progreso.configure(text=texto_progreso(0, self._total_lote))
        self.boton_cancelar.configure(state="normal")
        self.barra_progreso.grid(row=0, column=1, sticky="ew", padx=(14, 12))
        self.texto_progreso.grid(row=0, column=2, padx=(0, 12))
        self.boton_cancelar.grid(row=0, column=3)

    def _ocultar_progreso(self) -> None:
        self.barra_progreso.grid_remove()
        self.texto_progreso.grid_remove()
        self.boton_cancelar.grid_remove()
        self._reactivar_globales()
        if self._mostrando_tarjetas() or self._seccion is not None:
            self._ocultar_boton_progreso()
        self._sincronizar_carga()

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
        if self._con_barra:
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
        self._sincronizar_carga()
        self.boton_cancelar.configure(state="disabled")
        if fallo:
            self.aviso.configure(text="No se pudo guardar el resultado de la verificación.")
        elif self._sin_conexion:
            self.aviso.configure(
                text="No hay conexión a internet. Los enlaces que no respondieron quedan como caídos."
            )
        elif cancelado:
            self.aviso.configure(
                text=f"Verificación cancelada. {hechos} de {total} comprobados."
            )
        else:
            self.aviso.configure(text=f"Verificación terminada. {hechos} de {total}.")
        if not self._con_barra:
            self._reactivar_globales()
            return
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

    def _botones_en_carga(self) -> list[tuple[ctk.CTkButton, bool]]:
        """Botones que deben girar. El segundo valor distingue la cabecera."""
        if not self._verificacion_masiva:
            return []
        botones: list[tuple[ctk.CTkButton, bool]] = []
        if self._con_barra:
            if self._seccion is not None:
                botones.append((self.boton_verificar_categoria, True))
            botones.extend((boton, False) for boton in self._botones_tarjeta.values())
            return botones
        if self._seccion == self._nombre_lote:
            botones.append((self.boton_verificar_categoria, True))
        tarjeta = self._botones_tarjeta.get(self._nombre_lote or "")
        if self._nombre_lote is not None and tarjeta is not None:
            botones.append((tarjeta, False))
        return botones

    def _aplicar_fotograma(self, boton: ctk.CTkButton, cabecera: bool) -> None:
        if not self._fotogramas_carga:
            return
        try:
            if not boton.winfo_exists():
                return
        except Exception:
            return
        imagen = self._fotogramas_carga[self._indice_carga % len(self._fotogramas_carga)]
        if cabecera:
            boton.configure(
                text="Verificando...",
                image=imagen,
                state="disabled",
                fg_color=COLORES["acento"],
            )
            return
        boton.configure(image=imagen, state="disabled")

    def _restaurar_boton_categoria(self, boton: ctk.CTkButton, cabecera: bool, ocupado: bool) -> None:
        try:
            if not boton.winfo_exists():
                return
        except Exception:
            return
        if cabecera:
            boton.configure(
                text="Verificar categoría",
                image=self.iconos["verificar"],
                state="disabled" if ocupado else "normal",
                fg_color=COLORES["borde"] if ocupado else COLORES["acento"],
            )
            return
        boton.configure(
            image=self.iconos["verificar"],
            state="disabled" if ocupado else "normal",
        )

    def _sincronizar_carga(self) -> None:
        """Gira solo los botones de la tanda en curso y cancela el after si no hay."""
        activos = self._botones_en_carga()
        vistos = {id(boton) for boton, _cabecera in activos}
        ocupado = self._verificacion_masiva
        if id(self.boton_verificar_categoria) not in vistos:
            self._restaurar_boton_categoria(self.boton_verificar_categoria, True, ocupado)
        for boton in self._botones_tarjeta.values():
            if id(boton) not in vistos:
                self._restaurar_boton_categoria(boton, False, ocupado)
        for boton, cabecera in activos:
            self._aplicar_fotograma(boton, cabecera)
        if not activos or self._cerrando:
            self._cancelar_after_carga()
            return
        if self._after_carga is None:
            self._after_carga = self.after(INTERVALO_CARGA_MS, self._avanzar_carga)

    def _avanzar_carga(self) -> None:
        self._after_carga = None
        if self._cerrando or not self._fotogramas_carga:
            return
        self._indice_carga = (self._indice_carga + 1) % len(self._fotogramas_carga)
        self._sincronizar_carga()

    def _cancelar_after_carga(self) -> None:
        if self._after_carga is None:
            return
        try:
            self.after_cancel(self._after_carga)
        except Exception:
            pass
        self._after_carga = None

    def _al_cerrar(self) -> None:
        """Cierra la ventana sin esperar a la red. Lo ya encolado no arranca."""
        self._cerrando = True
        if self._cancelar_lote is not None:
            self._cancelar_lote.set()
        for identificador in (
            self._after_resultados,
            self._after_ocultar,
            self._after_redimension,
            self._after_carga,
            self._after_repintado,
            self._after_busqueda,
        ):
            if identificador is None:
                continue
            try:
                self.after_cancel(identificador)
            except Exception:
                pass
        self._after_resultados = None
        self._after_ocultar = None
        self._after_redimension = None
        self._after_carga = None
        self._after_repintado = None
        self._after_busqueda = None
        self._vista_sucia = False
        self._repintado_enlaces = []
        self._ejecutor.shutdown(wait=False, cancel_futures=True)
        self._guardar_al_cerrar()
        self.destroy()

    def _guardar_al_cerrar(self) -> None:
        """Escribe la tanda que seguía en la cola o que no llegó al disco."""
        try:
            self._vaciar_cola()
        except Exception:
            pass
        if not self._guardado_pendiente:
            return
        try:
            self._guardar()
            self._guardado_pendiente = False
        except OSError:
            pass

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
        motivo: str = "",
        lote: int | None = None,
    ) -> bool:
        """Aplica el resultado al diccionario. No guarda ni pinta.

        True si el enlace cambió. El guardado y el pintado van una vez
        por pasada, en _recoger_resultados.
        """
        try:
            if not self.winfo_exists():
                return False
        except Exception:
            return False
        if not self._sigue_en_lista(enlace):
            return False
        if self._token_por_enlace.get(id(enlace)) != token:
            return False

        enlace["estado"] = estado
        enlace["codigo_http"] = codigo
        decision = datos.resolver_titulo(
            enlace,
            titulo,
            verificador.titulo_descriptivo(str(enlace.get("url") or "")),
        )
        if decision is not None:
            enlace["titulo"], enlace["titulo_manual"] = decision
        enlace["ultima_verificacion"] = momento
        self._guardado_pendiente = True
        if motivo == verificador.MOTIVO_SIN_CONEXION:
            if lote is None:
                self._sin_conexion_suelto = True
            else:
                self._sin_conexion = True
        return True

    def _presentacion(self, enlace: dict) -> tuple[str, str, str]:
        estado = str(enlace.get("estado") or "pendiente")
        color = COLORES_ESTADO.get(estado, COLORES_ESTADO["pendiente"])
        titulo = str(enlace.get("titulo") or "").strip() or datos.TITULO_RELLENO
        detalle = estado
        categoria = str(enlace.get("categoria") or "").strip()
        if categoria:
            detalle = f"{estado}  ·  {categoria}"
        return titulo, detalle, color

    def _pintar_fila(self, enlace: dict) -> None:
        """Retoca la fila si sigue a la vista. No reconstruye la lista."""
        info = self._filas.get(id(enlace))
        if not info or not self._fila_en_pantalla(enlace):
            return
        titulo, detalle, color = self._presentacion(enlace)
        info["punto"].configure(fg_color=color)
        self._actualizar_recorte(info["titulo"], titulo)
        self._actualizar_recorte(info["detalle"], detalle)
        info["detalle"].configure(text_color=color)
        self._pintar_fecha(info.get("fecha"), texto_ultima_verificacion(enlace))

    def _pintar_fecha(self, etiqueta: ctk.CTkLabel | None, texto: str) -> None:
        """Muestra la fecha bajo el estado. Sin texto, no ocupa sitio."""
        if etiqueta is None:
            return
        try:
            if not etiqueta.winfo_exists():
                return
        except Exception:
            return
        self._actualizar_recorte(etiqueta, texto)
        if texto:
            if not etiqueta.winfo_ismapped():
                etiqueta.pack(fill="x", pady=(2, 0))
            return
        etiqueta.pack_forget()

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
        self._recortes = []
        self._botones_tarjeta = {}
        for hijo in self.lista.winfo_children():
            hijo.destroy()
        self._rehacer_menu_alta()
        if self._mostrando_tarjetas():
            self._pintar_tarjetas()
            self._pintar_resumen()
            self._restaurar_scroll(fraccion)
            return
        self._asegurar_filtro_categoria()
        consulta = self._categoria_consulta()
        visibles = [
            enlace
            for enlace in self.enlaces
            if isinstance(enlace, dict)
            and coincide(enlace, self._filtro, self._texto_busqueda(), consulta)
        ]
        if self._seccion is not None and not self._enlaces_de(self._seccion):
            mensaje = "Esta categoría no tiene enlaces."
        elif not self.enlaces:
            mensaje = "Todavía no hay enlaces."
        elif not visibles:
            mensaje = "Ningún enlace coincide con la búsqueda."
        else:
            mensaje = ""
        if mensaje:
            self._columnas = self._columnas_actuales(0)
            ctk.CTkLabel(
                self.lista,
                text=mensaje,
                text_color=COLORES["secundario"],
                font=self.fuente_url,
                fg_color="transparent",
            ).pack(anchor="w", padx=8, pady=28)
        else:
            self._pintar_rejilla_enlaces(visibles)
        self._pintar_resumen()
        self._rehacer_menu_categoria()
        self._restaurar_scroll(fraccion)
        if conservar_foco:
            self.busqueda.focus_set()
        self._sincronizar_carga()

    def _restaurar_scroll(self, fraccion: float) -> None:
        """Deja el scroll en la fracción guardada, ya con el alto nuevo.

        En Linux el canvas avanza de 30 en 30 px. Si la fracción se aplica
        antes de recalcular la región, Tk conserva el desplazamiento del
        alto anterior y la vista salta.
        """
        try:
            canvas = self.lista._parent_canvas
            self.update_idletasks()
            caja = canvas.bbox("all")
            if caja is not None:
                canvas.configure(scrollregion=caja)
            canvas.yview_moveto(fraccion)
        except Exception:
            return

    def abrir(self, enlace: dict) -> None:
        """Abre la URL en el navegador y, si arranca, marca el enlace como visitado."""
        if not self._sigue_en_lista(enlace):
            return
        if not self._abrir_en_navegador(enlace):
            self.aviso.configure(text="No se pudo abrir el enlace.")
            return

        self.aviso.configure(text="")
        enlace["visitado"] = True
        try:
            self._guardar()
        except OSError as exc:
            self.aviso.configure(text=_mensaje_permiso(exc, "No se pudo guardar el enlace."))
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
            self._guardar()
        except OSError as exc:
            self.aviso.configure(text=_mensaje_permiso(exc, "No se pudo guardar el enlace."))
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

    def _ancho_contenedor(self) -> int:
        try:
            return int(self.lista._parent_canvas.winfo_width())
        except Exception:
            return 0

    def _columnas_actuales(self, cantidad: int) -> int:
        maximo = MAX_COLUMNAS_TARJETAS if self._mostrando_tarjetas() else MAX_COLUMNAS_ENLACES
        calculadas = columnas_para_ancho(
            self._ancho_contenedor(),
            ANCHO_MINIMO_COLUMNA,
            maximo,
        )
        if cantidad > 0:
            return min(calculadas, cantidad)
        return calculadas

    def _cantidad_celdas(self) -> int:
        if self._mostrando_tarjetas():
            return 1 + len(self._nombres_categoria())
        consulta = self._categoria_consulta()
        return sum(
            1
            for enlace in self.enlaces
            if isinstance(enlace, dict)
            and coincide(enlace, self._filtro, self._texto_busqueda(), consulta)
        )

    def _al_redimensionar_lista(self, evento) -> None:
        if self._cerrando or evento.widget is not self.lista._parent_canvas:
            return
        ancho = int(evento.width)
        if ancho <= 1 or ancho == self._ancho_lista:
            return
        self._ancho_lista = ancho
        if self._after_redimension is not None:
            try:
                self.after_cancel(self._after_redimension)
            except Exception:
                pass
        self._after_redimension = self.after(DEBOUNCE_REDIMENSION_MS, self._aplicar_columnas)

    def _aplicar_columnas(self) -> None:
        """Rehace la rejilla solo si cambia el número de columnas."""
        self._after_redimension = None
        if self._cerrando:
            return
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        nuevas = self._columnas_actuales(self._cantidad_celdas())
        if nuevas != self._columnas:
            self.refrescar_lista()
            return
        self._recortar_textos()

    def _rejilla(self, columnas: int) -> ctk.CTkFrame:
        rejilla = ctk.CTkFrame(self.lista, fg_color="transparent")
        rejilla.pack(fill="x", padx=4, pady=4)
        for indice in range(max(1, columnas)):
            rejilla.grid_columnconfigure(indice, weight=1, uniform="columnas")
        return rejilla

    def _pintar_rejilla_enlaces(self, visibles: list[dict]) -> None:
        columnas = self._columnas_actuales(len(visibles))
        self._columnas = columnas
        rejilla = self._rejilla(columnas)
        for indice, enlace in enumerate(visibles):
            self._crear_fila(rejilla, enlace, indice // columnas, indice % columnas)

    def _medir(self, fuente: ctk.CTkFont):
        escala = float(self._get_window_scaling() or 1)
        familia, tamano, _estilo = fuente.create_scaled_tuple(escala)
        peso = fuente.cget("weight")
        clave = (familia, tamano, peso)
        medida = self._fuentes_medida.get(clave)
        if medida is None:
            medida = FuenteTk(family=familia, size=tamano, weight=peso)
            self._fuentes_medida[clave] = medida
        return medida.measure

    def _presupuesto(self, reserva: int) -> int:
        columnas = max(1, self._columnas)
        ancho = self._ancho_contenedor()
        escala = float(self._get_window_scaling() or 1)
        return max(0, ancho // columnas - int(reserva * escala))

    def _registrar_recorte(
        self,
        etiqueta: ctk.CTkLabel,
        texto: str,
        fuente: ctk.CTkFont,
        reserva: int,
        envolver: bool = False,
    ) -> None:
        self._recortes.append(
            {
                "etiqueta": etiqueta,
                "texto": texto,
                "fuente": fuente,
                "reserva": reserva,
                "envolver": envolver,
            }
        )
        self._aplicar_recorte(self._recortes[-1])

    def _actualizar_recorte(self, etiqueta: ctk.CTkLabel, texto: str) -> None:
        for item in self._recortes:
            if item["etiqueta"] is etiqueta:
                item["texto"] = texto
                self._aplicar_recorte(item)
                return
        etiqueta.configure(text=texto)

    def _aplicar_recorte(self, item: dict) -> None:
        presupuesto = self._presupuesto(item["reserva"])
        if item["envolver"]:
            item["etiqueta"].configure(wraplength=max(80, presupuesto))
            item["etiqueta"].configure(text=item["texto"])
            return
        item["etiqueta"].configure(
            text=recortar_texto(item["texto"], self._medir(item["fuente"]), presupuesto)
        )

    def _recortar_textos(self) -> None:
        for item in self._recortes:
            try:
                if not item["etiqueta"].winfo_exists():
                    continue
            except Exception:
                continue
            self._aplicar_recorte(item)

    def _crear_fila(self, padre: ctk.CTkFrame, enlace: dict, fila_grid: int, columna: int) -> None:
        titulo, detalle, color = self._presentacion(enlace)

        fila = ctk.CTkFrame(padre, fg_color=COLORES["fila"], corner_radius=12)
        fila.grid(row=fila_grid, column=columna, sticky="nsew", padx=8, pady=6)
        fila.grid_columnconfigure(1, weight=1)
        fila.grid_columnconfigure(2, minsize=28)

        punto = ctk.CTkFrame(fila, width=12, height=12, corner_radius=6, fg_color=color)
        punto.grid(row=0, column=0, padx=(16, 12), pady=16)
        punto.grid_propagate(False)

        textos = ctk.CTkFrame(fila, fg_color="transparent")
        textos.grid(row=0, column=1, sticky="ew", pady=14, padx=(0, 8))

        etiqueta_titulo = ctk.CTkLabel(
            textos,
            text="",
            anchor="w",
            justify="left",
            text_color=COLORES["texto"],
            font=self.fuente_titulo,
            fg_color="transparent",
        )
        etiqueta_titulo.pack(fill="x")
        self._registrar_recorte(etiqueta_titulo, titulo, self.fuente_titulo, RESERVA_TEXTO_FILA)
        url = str(enlace.get("url") or "")
        etiqueta_url = ctk.CTkLabel(
            textos,
            text="",
            anchor="w",
            justify="left",
            text_color=COLORES["secundario"],
            font=self.fuente_url,
            fg_color="transparent",
        )
        etiqueta_url.pack(fill="x", pady=(2, 0))
        self._registrar_recorte(etiqueta_url, url, self.fuente_url, RESERVA_TEXTO_FILA)

        notas = str(enlace.get("notas") or "").strip()
        if notas:
            primera = notas.splitlines()[0].strip()
            etiqueta_notas = ctk.CTkLabel(
                textos,
                text="",
                anchor="w",
                justify="left",
                text_color=COLORES["secundario"],
                font=self.fuente_detalle,
                fg_color="transparent",
            )
            etiqueta_notas.pack(fill="x", pady=(2, 0))
            self._registrar_recorte(etiqueta_notas, primera, self.fuente_detalle, RESERVA_TEXTO_FILA)

        etiqueta_detalle = ctk.CTkLabel(
            textos,
            text="",
            anchor="w",
            text_color=color,
            font=self.fuente_detalle,
            fg_color="transparent",
        )
        etiqueta_detalle.pack(fill="x", pady=(4, 0))
        self._registrar_recorte(etiqueta_detalle, detalle, self.fuente_detalle, RESERVA_TEXTO_FILA)
        fecha = texto_ultima_verificacion(enlace)
        etiqueta_fecha = ctk.CTkLabel(
            textos,
            text="",
            anchor="w",
            text_color=COLORES["secundario"],
            font=self.fuente_detalle,
            fg_color="transparent",
        )
        self._registrar_recorte(etiqueta_fecha, fecha, self.fuente_detalle, RESERVA_TEXTO_FILA)
        if fecha:
            etiqueta_fecha.pack(fill="x", pady=(2, 0))
        self._filas[id(enlace)] = {
            "punto": punto,
            "titulo": etiqueta_titulo,
            "detalle": etiqueta_detalle,
            "fecha": etiqueta_fecha,
        }

        marca = ctk.CTkLabel(
            fila,
            text="",
            width=28,
            fg_color="transparent",
        )
        if enlace.get("visitado"):
            marca.configure(image=self.iconos["check"])
        marca.grid(row=0, column=2, padx=(4, 8), pady=16)

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


def report_callback_exception(self, tipo, valor, traza) -> None:
        """Un fallo de un botón se anota. La ventana sigue abierta."""
        registro.anotar("Error en la ventana.", valor if isinstance(valor, BaseException) else None)
        try:
            self.aviso.configure(
                text="Ocurrió un error. El detalle está en gestor.log, junto a los datos."
            )
        except Exception:
            pass


Aplicacion.report_callback_exception = report_callback_exception


def _instalar_ganchos() -> None:
    """Manda al registro lo que, si no, saldría como traceback."""

    def _sistema(tipo, valor, traza) -> None:
        if issubclass(tipo, KeyboardInterrupt):
            sys.__excepthook__(tipo, valor, traza)
            return
        registro.anotar("Error no esperado.", valor if isinstance(valor, BaseException) else None)

    def _hilo(args: threading.ExceptHookArgs) -> None:
        if args.exc_type is SystemExit:
            return
        registro.anotar(
            "Error en un hilo.",
            args.exc_value if isinstance(args.exc_value, BaseException) else None,
        )

    sys.excepthook = _sistema
    threading.excepthook = _hilo


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
    """Abre la ventana. Un fallo de arranque se explica, no se muestra el traceback."""
    ctk.set_appearance_mode("dark")
    try:
        destino = ruta if ruta is not None else datos.ruta_datos()
        registro.iniciar(destino.parent)
    except OSError as exc:
        registro.anotar("No se pudo abrir el registro.", exc)
        _mostrar_error("No se puede escribir en la carpeta de datos. Revisa los permisos.")
        return
    _instalar_ganchos()
    try:
        iconos = cargar_iconos()
    except FileNotFoundError as exc:
        registro.anotar(str(exc), exc)
        _mostrar_error(str(exc))
        return
    except Exception as exc:
        registro.anotar("No se pudieron cargar los iconos.", exc)
        _mostrar_error(
            "No se pudo abrir la ventana. El detalle está en gestor.log, junto a los datos."
        )
        return
    try:
        aplicacion = Aplicacion(ruta=destino, iconos=iconos)
        aplicacion.mainloop()
    except Exception as exc:
        registro.anotar("No se pudo abrir la ventana.", exc)
        _mostrar_error(
            "No se pudo abrir la ventana. El detalle está en gestor.log, junto a los datos."
        )
