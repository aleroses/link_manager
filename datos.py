"""Persistencia de los enlaces en un archivo JSON.

El archivo vive junto a este módulo cuando la carpeta se puede escribir.
Si el script está en una ruta de solo lectura, se usa la carpeta de
configuración del usuario.
"""

from __future__ import annotations

import csv
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


# Texto que la lista muestra si el título aún está vacío. No se guarda.
TITULO_RELLENO = "Sin título"


def enlace_nuevo(url: str) -> dict:
    """Registro vacío, listo para guardarse. La verificación llega después."""
    return {
        "url": url,
        "titulo": "",
        "titulo_manual": False,
        "estado": "pendiente",
        "codigo_http": None,
        "visitado": False,
        "categoria": "",
        "notas": "",
        "fecha_añadido": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "ultima_verificacion": None,
    }


def resolver_titulo(
    enlace: dict,
    titulo_html: str,
    descriptivo: str,
) -> tuple[str, bool] | None:
    """Decide el título tras una verificación.

    Devuelve (titulo, titulo_manual) cuando hay que escribirlo. None
    conserva el que ya está: un título editado a mano no se pisa. El
    texto "Sin título" sí se sustituye, aunque la marca estuviera puesta.
    """
    actual = str(enlace.get("titulo") or "").strip()
    if bool(enlace.get("titulo_manual")) and actual != TITULO_RELLENO:
        return None
    return (titulo_html.strip() or descriptivo, False)


def resolver_edicion_titulo(
    anterior: str,
    nuevo: str,
    obtenido: str | None,
    descriptivo: str,
) -> tuple[str, bool] | None:
    """Decide el título al guardar el diálogo.

    None deja el título y la marca como estaban. Una cadena vacía o
    "Sin título" pasa al título descriptivo y queda como automática.
    """
    texto = nuevo.strip()
    if not texto or texto == TITULO_RELLENO:
        return (descriptivo, False)
    if obtenido is not None and texto == obtenido.strip():
        return (texto, False)
    if texto != str(anterior or "").strip():
        return (texto, True)
    return None


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


COLUMNAS_CSV = (
    "url",
    "titulo",
    "estado",
    "codigo_http",
    "visitado",
    "categoria",
    "notas",
    "fecha_añadido",
    "ultima_verificacion",
)
ESTADOS_CONOCIDOS = {"pendiente", "activo", "error", "caído"}
_VISITADO_SI = {"si", "sí", "true", "1"}


def _texto_visitado(valor: object) -> str:
    return "si" if bool(valor) else "no"


def _leer_visitado(valor: str) -> bool:
    return valor.strip().casefold() in _VISITADO_SI


def _leer_codigo(valor: str) -> int | None:
    limpio = valor.strip()
    if not limpio:
        return None
    try:
        return int(limpio)
    except ValueError:
        return None


def escribir_csv(enlaces: list, ruta: Path) -> None:
    """Escribe la colección en UTF-8 con BOM. visitado queda en si o no."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.DictWriter(
            archivo,
            fieldnames=COLUMNAS_CSV,
            extrasaction="ignore",
            lineterminator="\n",
        )
        escritor.writeheader()
        for enlace in enlaces:
            if not isinstance(enlace, dict):
                continue
            codigo = enlace.get("codigo_http")
            ultima = enlace.get("ultima_verificacion")
            escritor.writerow(
                {
                    "url": enlace.get("url") or "",
                    "titulo": enlace.get("titulo") or "",
                    "estado": enlace.get("estado") or "",
                    "codigo_http": "" if codigo is None else codigo,
                    "visitado": _texto_visitado(enlace.get("visitado")),
                    "categoria": enlace.get("categoria") or "",
                    "notas": enlace.get("notas") or "",
                    "fecha_añadido": enlace.get("fecha_añadido") or "",
                    "ultima_verificacion": "" if not ultima else ultima,
                }
            )


def leer_csv(ruta: Path) -> tuple[list[dict], int, list[dict]]:
    """Lee enlaces de un CSV.

    Devuelve (enlaces, filas_sin_url, por_verificar). por_verificar son
    los mismos dicts cuyo estado no era conocido: quedan en pendiente
    para que la ventana los compruebe. Un título no vacío, distinto de
    "Sin título", queda marcado como manual. Lanza ValueError si falta
    la columna url.
    """
    with ruta.open("r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        nombres = [str(nombre or "").strip() for nombre in (lector.fieldnames or [])]
        if "url" not in nombres:
            raise ValueError("el CSV no tiene la columna url")
        enlaces: list[dict] = []
        sin_url = 0
        por_verificar: list[dict] = []
        for fila in lector:
            if not fila or not any(str(valor or "").strip() for valor in fila.values()):
                continue
            url = str(fila.get("url") or "").strip()
            if not url:
                sin_url += 1
                continue
            enlace = enlace_nuevo(url)
            titulo = str(fila.get("titulo") or "")
            if titulo.strip() and titulo.strip() != TITULO_RELLENO:
                enlace["titulo"] = titulo
                enlace["titulo_manual"] = True
            else:
                enlace["titulo"] = ""
                enlace["titulo_manual"] = False
            enlace["categoria"] = str(fila.get("categoria") or "").strip()
            enlace["notas"] = str(fila.get("notas") or "")
            estado = str(fila.get("estado") or "").strip()
            if estado in ESTADOS_CONOCIDOS:
                enlace["estado"] = estado
            else:
                enlace["estado"] = "pendiente"
                por_verificar.append(enlace)
            enlace["codigo_http"] = _leer_codigo(str(fila.get("codigo_http") or ""))
            enlace["visitado"] = _leer_visitado(str(fila.get("visitado") or ""))
            fecha = str(fila.get("fecha_añadido") or "").strip()
            if fecha:
                enlace["fecha_añadido"] = fecha
            ultima = str(fila.get("ultima_verificacion") or "").strip()
            enlace["ultima_verificacion"] = ultima or None
            enlaces.append(enlace)
    return enlaces, sin_url, por_verificar
