"""Ventana del Gestor de Enlaces.

Tema oscuro, campo para añadir una URL y lista con el estado de cada
enlace. La comprobación de red ocurre en un hilo. Ese hilo no toca
widgets: deja el resultado en una cola y el hilo principal lo aplica
con after().
"""

from __future__ import annotations

import queue
import threading
from datetime import datetime, timezone
from pathlib import Path

import customtkinter as ctk
from PIL import Image

import datos
import verificador

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
        self._resultados: queue.Queue[tuple[int, str, int | None, str, str]] = queue.Queue()
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

        self.aviso = ctk.CTkLabel(
            barra,
            text="",
            height=22,
            anchor="w",
            text_color=COLORES["aviso"],
            font=self.fuente_detalle,
        )
        self.aviso.pack(fill="x", padx=22, pady=(0, 12))

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
        self.after(100, self._recoger_resultados)

    def anadir(self) -> None:
        """Normaliza la URL, la guarda como pendiente y verifica en segundo plano."""
        try:
            url = verificador.normalizar_url(self.entrada.get())
        except ValueError:
            self.aviso.configure(text="Ese enlace no es válido. Usa una dirección http o https.")
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

        indice = len(self.enlaces) - 1
        self.entrada.delete(0, "end")
        self.refrescar_lista()
        hilo = threading.Thread(
            target=self._verificar_en_segundo_plano,
            args=(indice, url),
            daemon=True,
        )
        hilo.start()

    def _verificar_en_segundo_plano(self, indice: int, url: str) -> None:
        estado, codigo, titulo = verificador.verificar_url(url)
        momento = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._resultados.put((indice, estado, codigo, titulo, momento))

    def _recoger_resultados(self) -> None:
        """Aplica lo que el hilo de red ya termino. Corre en el hilo principal."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        try:
            while True:
                indice, estado, codigo, titulo, momento = self._resultados.get_nowait()
                self._aplicar_verificacion(indice, estado, codigo, titulo, momento)
        except queue.Empty:
            pass
        self.after(100, self._recoger_resultados)

    def _aplicar_verificacion(
        self,
        indice: int,
        estado: str,
        codigo: int | None,
        titulo: str,
        momento: str,
    ) -> None:
        """Escribe el resultado en la lista. Solo se llama desde el hilo principal."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        if indice < 0 or indice >= len(self.enlaces):
            return

        enlace = self.enlaces[indice]
        enlace["estado"] = estado
        enlace["codigo_http"] = codigo
        enlace["titulo"] = titulo
        enlace["ultima_verificacion"] = momento
        try:
            datos.guardar_enlaces(self.enlaces, self.ruta)
        except OSError:
            self.aviso.configure(text="No se pudo guardar el resultado de la verificación.")
        self.refrescar_lista()

    def refrescar_lista(self) -> None:
        for hijo in self.lista.winfo_children():
            hijo.destroy()
        if not self.enlaces:
            ctk.CTkLabel(
                self.lista,
                text="Todavía no hay enlaces.",
                text_color=COLORES["secundario"],
                font=self.fuente_url,
                fg_color="transparent",
            ).pack(anchor="w", padx=8, pady=28)
            return
        for enlace in self.enlaces:
            self._crear_fila(enlace)

    def _crear_fila(self, enlace: dict) -> None:
        estado = str(enlace.get("estado") or "pendiente")
        color = COLORES_ESTADO.get(estado, COLORES_ESTADO["pendiente"])
        titulo = str(enlace.get("titulo") or "").strip() or "Sin título"

        fila = ctk.CTkFrame(self.lista, fg_color=COLORES["fila"], corner_radius=12)
        fila.pack(fill="x", pady=6, padx=4)
        fila.grid_columnconfigure(1, weight=1)

        punto = ctk.CTkFrame(fila, width=12, height=12, corner_radius=6, fg_color=color)
        punto.grid(row=0, column=0, padx=(16, 12), pady=16)
        punto.grid_propagate(False)

        textos = ctk.CTkFrame(fila, fg_color="transparent")
        textos.grid(row=0, column=1, sticky="ew", pady=14, padx=(0, 8))

        ctk.CTkLabel(
            textos,
            text=titulo,
            anchor="w",
            justify="left",
            text_color=COLORES["texto"],
            font=self.fuente_titulo,
            fg_color="transparent",
        ).pack(fill="x")
        ctk.CTkLabel(
            textos,
            text=str(enlace.get("url") or ""),
            anchor="w",
            justify="left",
            wraplength=560,
            text_color=COLORES["secundario"],
            font=self.fuente_url,
            fg_color="transparent",
        ).pack(fill="x", pady=(2, 0))

        detalle = estado
        categoria = str(enlace.get("categoria") or "").strip()
        if categoria:
            detalle = f"{estado}  ·  {categoria}"
        ctk.CTkLabel(
            textos,
            text=detalle,
            anchor="w",
            text_color=color,
            font=self.fuente_detalle,
            fg_color="transparent",
        ).pack(fill="x", pady=(4, 0))

        if enlace.get("visitado"):
            ctk.CTkLabel(
                fila,
                text="",
                image=self.iconos["check"],
                fg_color="transparent",
            ).grid(row=0, column=2, padx=(4, 16), pady=16)


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
