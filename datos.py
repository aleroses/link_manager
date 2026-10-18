"""Persistencia de los enlaces en un archivo JSON.

El archivo vive junto a este módulo cuando la carpeta se puede escribir.
Si el script está en una ruta de solo lectura, se usa la carpeta de
configuración del usuario.
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

NOMBRE_ARCHIVO = "enlaces.json"
_SONDA = ".sonda_escritura"


def directorio_escribible(ruta: Path) -> bool:
    """Comprueba si se puede crear y borrar un archivo dentro de ruta."""
    if not ruta.is_dir():
        return False
    sonda = ruta / _SONDA
    try:
        sonda.write_text("", encoding="utf-8")
    except OSError:
        return False
    finally:
        try:
            if sonda.exists():
                sonda.unlink()
        except OSError:
            pass
    return True


def directorio_configuracion() -> Path:
    """Carpeta de configuración del usuario, elegida de forma portable.

    Windows usa APPDATA. En el resto de sistemas se respeta
    XDG_CONFIG_HOME y, si no existe, ~/.config.
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA")
        if base:
            return Path(base) / "GestorDeEnlaces"
        return Path.home() / "AppData" / "Roaming" / "GestorDeEnlaces"

    configuracion = os.environ.get("XDG_CONFIG_HOME")
    if configuracion:
        return Path(configuracion) / "gestor-de-enlaces"
    return Path.home() / ".config" / "gestor-de-enlaces"


def ruta_datos(
    base: Path | None = None,
    carpeta_config: Path | None = None,
) -> Path:
    """Devuelve la ruta de enlaces.json sin crearlo.

    base permite probar con una carpeta temporal. carpeta_config solo
    se usa cuando base no es escribible, para no tocar la configuración
    real durante las pruebas.
    """
    if base is None:
        base = Path(__file__).resolve().parent
    if directorio_escribible(base):
        return base / NOMBRE_ARCHIVO

    destino = carpeta_config if carpeta_config is not None else directorio_configuracion()
    destino.mkdir(parents=True, exist_ok=True)
    return destino / NOMBRE_ARCHIVO


def enlace_nuevo(url: str) -> dict:
    """Registro vacío, listo para guardarse. La verificación llega después."""
    return {
        "url": url,
        "titulo": "",
        "estado": "pendiente",
        "codigo_http": None,
        "visitado": False,
        "categoria": "",
        "notas": "",
        "fecha_añadido": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ultima_verificacion": None,
    }


def _ruta_respaldo(ruta: Path) -> Path:
    """enlaces.json.bak, o un nombre con marca de tiempo si ese ya existe."""
    candidato = ruta.with_name(ruta.name + ".bak")
    if not candidato.exists():
        return candidato
    marca = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return ruta.with_name(f"{ruta.name}.{marca}.bak")


def _respaldar(ruta: Path) -> bool:
    """Copia el archivo tal cual. Devuelve False si no se pudo copiar."""
    if not ruta.is_file():
        return False
    try:
        shutil.copy2(ruta, _ruta_respaldo(ruta))
    except OSError:
        return False
    return True


def cargar_enlaces(ruta: Path | None = None) -> list:
    """Lee la lista de enlaces.

    Si el archivo no existe, lo crea vacío. Si el JSON no se puede leer
    o no es una lista, guarda una copia .bak y deja el archivo en [].
    """
    if ruta is None:
        ruta = ruta_datos()
    if not ruta.exists():
        guardar_enlaces([], ruta)
        return []

    try:
        texto = ruta.read_text(encoding="utf-8")
    except (OSError, UnicodeError):
        if _respaldar(ruta):
            guardar_enlaces([], ruta)
        return []

    try:
        if not texto.strip():
            raise ValueError("archivo vacío")
        datos = json.loads(texto)
        if not isinstance(datos, list):
            raise ValueError("el contenido no es una lista")
    except (json.JSONDecodeError, ValueError):
        if _respaldar(ruta):
            guardar_enlaces([], ruta)
        return []
    return datos


def guardar_enlaces(enlaces: list, ruta: Path | None = None) -> None:
    """Escribe la lista de forma atómica: temporal y después renombre.

    Si el renombre falla, se borra el temporal para no dejar basura.
    """
    if ruta is None:
        ruta = ruta_datos()
    ruta.parent.mkdir(parents=True, exist_ok=True)
    temporal = ruta.with_name(ruta.name + ".tmp")
    contenido = json.dumps(enlaces, ensure_ascii=False, indent=2) + "\n"
    try:
        temporal.write_text(contenido, encoding="utf-8")
        temporal.replace(ruta)
    except Exception:
        try:
            if temporal.exists():
                temporal.unlink()
        except OSError:
            pass
        raise
