#!/usr/bin/env bash
# Gestor de Enlaces. Licencia GPL-3.0. El texto está en LICENSE.
# Arranca main.py con el Python del entorno, esté donde esté la terminal.

carpeta="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
python="$carpeta/venv/bin/python"

if [[ ! -x "$python" ]]; then
    echo "No se encontró el entorno virtual en:" >&2
    echo "  $carpeta/venv" >&2
    echo "Créalo una sola vez, dentro de esa carpeta:" >&2
    echo "  python3 -m venv venv" >&2
    echo "  source venv/bin/activate" >&2
    echo "  python -m pip install --upgrade pip" >&2
    echo "  pip install -r requirements.txt" >&2
    echo "En Debian también hace falta: sudo apt install python3 python3-venv python3-pip python3-tk" >&2
    exit 1
fi

exec "$python" "$carpeta/main.py" "$@"
