"""Registro de errores en gestor.log, junto a los datos.

El archivo rota al llegar a un tamaño fijo. Así se puede diagnosticar
un fallo sin mostrar un traceback en la ventana.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

NOMBRE = "gestor.log"
MAX_BYTES = 256 * 1024
COPIAS = 2

_registro = logging.getLogger("gestor")
_registro.setLevel(logging.INFO)
_registro.propagate = False


def iniciar(carpeta: Path) -> None:
    """Abre el registro en carpeta. Si ya está abierto, no hace nada."""
    if _registro.handlers:
        return
    carpeta.mkdir(parents=True, exist_ok=True)
    manejador = RotatingFileHandler(
        carpeta / NOMBRE,
        maxBytes=MAX_BYTES,
        backupCount=COPIAS,
        encoding="utf-8",
    )
    manejador.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    _registro.addHandler(manejador)


def cerrar() -> None:
    """Cierra el archivo. Lo usan las pruebas para no dejarlo abierto."""
    for manejador in list(_registro.handlers):
        manejador.close()
        _registro.removeHandler(manejador)


def anotar(mensaje: str, exc: BaseException | None = None) -> None:
    """Escribe mensaje en el registro. Sin manejador, no hace nada."""
    if not _registro.handlers:
        return
    if exc is None:
        _registro.error(mensaje)
    else:
        _registro.error(mensaje, exc_info=(type(exc), exc, exc.__traceback__))
    for manejador in _registro.handlers:
        manejador.flush()
