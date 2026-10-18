"""Ventana del Gestor de Enlaces.

Tema oscuro, campo para añadir una URL y lista con el estado de cada
enlace. La comprobación de red ocurre en un hilo. Ese hilo no toca
widgets: deja el resultado en una cola y el hilo principal lo aplica
con after().
"""

from __future__ import annotations

import queue
import threading
import webbrowser
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
        # La cola guarda el diccionario, no su posición: si se borra
        # otro enlace, el resultado no se escribe en el de al lado.
        self._resultados: queue.Queue[tuple[dict, str, int | None, str, str]] = queue.Queue()
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
        hilo = threading.Thread(
            target=self._verificar_en_segundo_plano,
            args=(enlace, url),
            daemon=True,
        )
        hilo.start()

    def _es_duplicado(self, url: str) -> bool:
        clave = verificador.clave_url(url)
        for existente in self.enlaces:
            try:
                if verificador.clave_url(str(existente.get("url") or "")) == clave:
                    return True
            except ValueError:
                continue
        return False

    def _verificar_en_segundo_plano(self, enlace: dict, url: str) -> None:
        estado, codigo, titulo = verificador.verificar_url(url)
        momento = datetime.now(timezone.utc).isoformat(timespec="seconds")
        self._resultados.put((enlace, estado, codigo, titulo, momento))

    def _recoger_resultados(self) -> None:
        """Aplica lo que el hilo de red ya termino. Corre en el hilo principal."""
        try:
            if not self.winfo_exists():
                return
        except Exception:
            return
        try:
            while True:
                enlace, estado, codigo, titulo, momento = self._resultados.get_nowait()
                self._aplicar_verificacion(enlace, estado, codigo, titulo, momento)
        except queue.Empty:
            pass
        self.after(100, self._recoger_resultados)

    def _sigue_en_lista(self, enlace: dict) -> bool:
        return any(item is enlace for item in self.enlaces)

    def _aplicar_verificacion(
        self,
        enlace: dict,
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
        if not self._sigue_en_lista(enlace):
            return

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
            wraplength=480,
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
            ).grid(row=0, column=2, padx=(4, 8), pady=16)

        acciones = ctk.CTkFrame(fila, fg_color="transparent")
        acciones.grid(row=0, column=3, padx=(4, 12), pady=12)
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
