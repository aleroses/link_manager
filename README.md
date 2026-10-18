# Gestor de Enlaces

Aplicación de escritorio para guardar enlaces web, comprobar si responden y abrirlos más tarde en el navegador. La ventana gráfica todavía no está construida. En este punto el proyecto incluye la persistencia en JSON y el verificador de URLs, y se comprueban los dos con pruebas de consola.

## Requisitos

- Python 3.10 o superior.
- Conexión a internet para las pruebas de red del verificador.
- En Debian, paquetes del sistema: `python3`, `python3-venv`, `python3-pip` y `python3-tk`.

`python3-tk` hace falta para la ventana (fases posteriores). Conviene instalarlo ya para que el entorno quede completo.

Las dependencias de Python van con versión fijada en `requirements.txt`:

- `customtkinter==6.0.0` (interfaz; aún no se usa)
- `requests==2.34.2` (verificación de enlaces)
- `pillow==12.3.0` (iconos; aún no se usa)

Pillow 13 exige Python 3.11. La versión 12.3.0 mantiene el soporte de Python 3.10.

## Instalación en Windows (PowerShell)

Abre PowerShell en la carpeta del proyecto y ejecuta:

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Instalación en Debian (bash)

```bash
sudo apt install python3 python3-venv python3-pip python3-tk
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Ejecutar las pruebas

Con el entorno virtual activado, en la carpeta del proyecto:

```powershell
python main.py
```

En Debian el comando es el mismo (`python main.py`) después de `source venv/bin/activate`.

El programa no abre una ventana. Escribe en la consola líneas `OK` o `FALLO` y termina con un resumen. El código de salida es 0 solo cuando todas las pruebas pasan.

Sin activar el entorno también puedes usar el intérprete del virtualenv:

- Windows: `.\venv\Scripts\python.exe main.py`
- Debian: `./venv/bin/python main.py`

## Estructura del proyecto

```text
link_manager/
  main.py             Pruebas de consola (punto de entrada provisional)
  datos.py            Carga y guardado de enlaces.json
  verificador.py      Normalización de URL y comprobación HTTP
  requirements.txt    Dependencias con versión fijada
  README.md           Esta guía
  DOCUMENTACION.md    Diario de decisiones por fase
  .gitignore
  assets/icons/       Reservada para los iconos (fase 3)
  venv/               Entorno local; no se versiona
```

Cuando la interfaz crezca, la ventana irá en `interfaz.py` y `main.py` pasará a abrirla.

## Dónde se guardan los enlaces

`enlaces.json` (UTF-8, indentado) se crea junto a los scripts si esa carpeta se puede escribir. Si el programa está en una ruta de solo lectura, el archivo pasa a:

- Windows: `%APPDATA%\GestorDeEnlaces\enlaces.json`
- Debian: `$XDG_CONFIG_HOME/gestor-de-enlaces/enlaces.json`, o `~/.config/gestor-de-enlaces/enlaces.json`

Las pruebas de `main.py` usan una carpeta temporal y no crean `enlaces.json` en el proyecto.

Cada enlace tendrá: `url`, `titulo`, `estado`, `codigo_http`, `visitado`, `categoria`, `notas`, `fecha_añadido`, `ultima_verificacion`.

Estados del enlace: `pendiente`, `activo` (HTTP 200-399), `error` (HTTP 4xx/5xx o URL no válida), `caído` (timeout, DNS, SSL o sin conexión). `visitado` es independiente del estado.

## Funcionalidades disponibles

Hasta esta fase:

- Crear un registro de enlace con todos los campos.
- Cargar y guardar la lista en JSON. Si el archivo no existe, se crea vacío. Si está corrupto, se copia a un `.bak` y el archivo de trabajo queda en `[]`.
- Escritura atómica: se escribe un temporal y después se renombra.
- Normalizar una URL (se antepone `https://` si falta el esquema).
- Verificar una URL con tiempo límite de 8 segundos: primero HEAD y, si falla, GET. El título se lee del HTML cuando la petición es GET.

Todavía no hay ventana, botones, filtros ni apertura en el navegador.

## Ramas

- `master`: rama estable. Solo recibe cambios cuando se confirma una fusión.
- `windows`: rama de desarrollo y de prueba en Windows. Todo el trabajo diario va aquí.
- `debian`: se creará más adelante para validar el mismo código en Linux. Aún no existe.

Estás en `windows` para desarrollar. `master` aparece en el primer commit, apuntando a ese mismo punto, y no se vuelve a tocar hasta que pidas la fusión:

```bash
git checkout master
git merge windows
git checkout windows
```

## Problemas comunes

**PowerShell no deja activar el entorno.** El mensaje habla de la directiva de ejecución. En esa ventana:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1
```

Eso solo afecta a la ventana actual. Si prefieres no cambiar la directiva, ejecuta `.\venv\Scripts\python.exe main.py`.

**`python3 -m venv` falla en Debian.** Falta el paquete `python3-venv`. Instálalo con el comando `apt` de la sección de Debian y vuelve a crear el entorno.

**La ventana futura no arranca en Debian.** Falta `python3-tk`. CustomTkinter se apoya en Tk, que no viene dentro de `pip`.

**Las pruebas de "Red" salen FALLO y el resto OK.** Esas tres necesitan internet y que `example.com` responda. Revisa la conexión y vuelve a lanzar `python main.py`. Un dominio `.invalid` debe quedar como `caído`; si una red corporativa responde por él, esa prueba concreta puede fallar.

**Aparece un archivo `.bak`.** El JSON no se pudo leer. La copia conserva el contenido anterior. El archivo de trabajo se reescribe como lista vacía para que el programa pueda seguir. No borres el `.bak` hasta recuperar lo que te interese.
