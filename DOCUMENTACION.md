# Documentación del Gestor de Enlaces

Diario acumulativo del proyecto. Cada fase añade una entrada. Las entradas anteriores se conservan.

## 2026-10-17 — Fase 0: Preparación

### Qué se hizo

Se creó el esqueleto del proyecto para poder desarrollar igual en Windows 10/11 y en Debian 12 o superior: dependencias fijadas, entorno virtual ignorado por Git, guía de instalación y repositorio en la rama `windows`.

### Decisiones técnicas y por qué

- Las versiones quedan fijadas en `requirements.txt`: `customtkinter==6.0.0`, `requests==2.34.2` y `pillow==12.3.0`. Pillow 13.0.0 exige Python 3.11; 12.3.0 es la última línea que sigue admitiendo Python 3.10, que es el mínimo del proyecto.
- CustomTkinter y Pillow se instalan desde esta fase aunque la ventana y los iconos lleguen después, para que el entorno de quien clone el repo ya esté completo.
- `assets/icons/` se crea vacía (con `.gitkeep` para que Git la conserve). Los SVG de Lucide se añadirán en la fase 3.
- El repositorio se inicializa en la rama `windows`. `master` se crea en el primer commit, en el mismo punto, y a partir de ahí el trabajo sigue en `windows`. Fusionar a `master` queda para cuando se confirme.
- No se hace ningún commit automático: quien valida el resultado ejecuta el commit.

### Archivos creados o modificados

- `requirements.txt`
- `.gitignore` (`venv/`, `__pycache__/`, `enlaces.json`, `*.bak`, `*.tmp`)
- `README.md`
- `DOCUMENTACION.md`
- `assets/icons/.gitkeep`
- `venv/` en local, sin versionar

### Problemas encontrados y cómo se resolvieron

Ninguno durante la preparación. La elección de Pillow 12.3.0 evita un fallo de instalación en Python 3.10. En este equipo (Windows, Python 3.14.6) las tres librerías se instalaron desde ruedas y se importan: CustomTkinter 6.0.0, requests 2.34.2 y Pillow 12.3.0.

### Pendientes

- Persistencia JSON (fase 1).
- Verificador de URLs y pruebas de consola (fase 2).
- Ventana, iconos y el resto de funciones de las fases 3 a 7.
- Rama `debian`, cuando se valide en Linux.

## 2026-10-17 — Fase 1: Persistencia

### Qué se hizo

`datos.py` carga y guarda la lista de enlaces. Si `enlaces.json` no existe, lo crea como `[]`. Si el contenido no es JSON, está vacío o no es una lista, copia el original a un `.bak` y, solo si la copia sale bien, reescribe el archivo de trabajo como lista vacía. El guardado escribe `enlaces.json.tmp` y después lo renombra encima del archivo final.

### Decisiones técnicas y por qué

- La ruta usa `pathlib`. No hay separadores escritos a mano.
- Para saber si la carpeta del script sirve, se crea y se borra un archivo sonda. Es una prueba real de escritura y funciona igual en Windows y en Linux, sin llamadas exclusivas de un sistema.
- Si esa carpeta no es escribible, el destino es `%APPDATA%/GestorDeEnlaces` en Windows y `$XDG_CONFIG_HOME/gestor-de-enlaces` (o `~/.config/gestor-de-enlaces`) en el resto. `sys.platform` y las variables de entorno forman parte de la biblioteca estándar.
- `ruta_datos()` acepta una carpeta base y una carpeta de configuración opcionales. Las pruebas pasan un temporal y no crean archivos en AppData ni junto al script.
- El respaldo se llama `enlaces.json.bak`. Si ya existe, el siguiente lleva marca de tiempo con microsegundos (`enlaces.json.AAAAMMDDTHHMMSSFFFFFFZ.bak`) para no destruir la copia anterior. El patrón `*.bak` del `.gitignore` cubre los dos nombres.
- Si no se puede hacer la copia `.bak`, el archivo corrupto no se pisa. Perder el original sería peor que dejarlo para un intento posterior. La función igual devuelve `[]` y no lanza la excepción de JSON.
- Después de un respaldo correcto sí se reescribe `[]`. Si no, cada arranque volvería a ver el mismo archivo dañado.
- `Path.replace` es el renombre atómico en el mismo disco, en Windows y en Linux. Si falla, se borra el `.tmp`.
- El JSON se escribe en UTF-8, `ensure_ascii=False` e `indent=2`, para que las tildes de `caído` y `fecha_añadido` se lean en el archivo.
- `enlace_nuevo()` deja el registro completo en `pendiente`, con `visitado` en falso. Verificar y marcar visitado son responsabilidades de otras fases.

### Archivos creados o modificados

- `datos.py`
- `README.md` (ubicación del JSON y comportamiento ante un archivo dañado)
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

Ninguno. La suite de consola cubre archivo nuevo, ida y vuelta con tildes, ausencia de `.tmp`, JSON corrupto, segundo `.bak` sin pisar el primero, carpeta escribible y carpeta de configuración alternativa.

### Pendientes

- Verificador y pruebas de consola (fase 2).
- La interfaz usará `cargar_enlaces()` y `guardar_enlaces()` después de cada cambio.

## 2026-10-17 — Fase 2: Verificador

### Qué se hizo

`verificador.py` normaliza una URL y la clasifica. `main.py` ejecuta pruebas de consola: persistencia en una carpeta temporal, normalización sin red, extracción de título sobre HTML fijo, un servidor local que obliga al camino GET, y tres comprobaciones de internet (`example.com`, una ruta inexistente y un dominio `.invalid`).

### Decisiones técnicas y por qué

- Si falta el esquema se antepone `https://`. `http://` se conserva. `ftp://` y una cadena vacía no salen a la red: el estado es `error` con código `None`, porque no son una caída de conexión.
- Tiempo límite de 8 segundos y un `User-Agent` de navegador, fijo, que no depende del sistema operativo.
- Primero HEAD. Si lanza una excepción de `requests`, o si el código es 405 o 501, se prueba GET. Un 403 es una respuesta del servidor y se queda en `error`. Pasarlo a `activo` a mano será una acción de la interfaz.
- Los códigos 200-399 son `activo`. Cualquier otro código HTTP es `error`. `caído` solo se usa cuando no hay respuesta (timeout, DNS, SSL, conexión).
- El título se obtiene con `html.parser`, de la biblioteca estándar, y solo del cuerpo del GET (como máximo 64 KB). Un HEAD correcto deja el título vacío porque no hay cuerpo. Así no se descarga la página dos veces cuando HEAD basta para saber el estado.
- Las peticiones a `localhost` y `127.0.0.1` ignoran el proxy del sistema. Si no, la prueba local y los futuros enlaces locales saldrían por el proxy y fallarían.
- Las pruebas viven en `main.py` y no en un framework aparte: el requisito es un bloque de consola, y pytest no forma parte del stack. El código de salida es 1 si alguna línea sale `FALLO`.
- La lógica va en `datos.py` y `verificador.py` desde ahora. `main.py` queda libre para convertirse en el lanzador de la ventana en la fase 3, cuando aparezca `interfaz.py`.

### Archivos creados o modificados

- `verificador.py`
- `main.py`
- `README.md` (comando `python main.py` y funcionalidades de esta fase)
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

`python main.py` se ejecutó en Windows con el entorno virtual: 20 pruebas correctas, 0 fallos. `example.com` quedó `activo`, la ruta inexistente quedó `error` y el dominio `.invalid` quedó `caído`. No hizo falta cambiar ninguna URL de prueba.

### Pendientes

- Fase 3: tema oscuro, iconos Lucide en `assets/icons/` y la ventana con campo de URL, botón Añadir y lista.
- Abrir enlaces con `webbrowser`, copiar, borrar y duplicados (fase 4).
- Verificación en segundo plano con barra de progreso (fase 5).
- Filtros, búsqueda, categorías, CSV y contadores (fase 6).
- Pulido y notas de PyInstaller (fase 7).
- Crear la rama `debian` al validar en Linux.
