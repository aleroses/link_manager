# Gestor de Enlaces

Aplicación de escritorio para guardar enlaces web, comprobar si responden y abrirlos en el navegador. La ventana permite añadir un enlace, ver su estado, abrirlo, copiar la dirección y eliminarlo.

## Requisitos

- Python 3.10 o superior.
- Conexión a internet para las pruebas de red del verificador.
- En Debian, paquetes del sistema: `python3`, `python3-venv`, `python3-pip` y `python3-tk`.

`python3-tk` hace falta para abrir la ventana. CustomTkinter se apoya en Tk, que no viene dentro de `pip`.

Las dependencias de Python van con versión fijada en `requirements.txt`:

- `customtkinter==6.0.0` (ventana)
- `requests==2.34.2` (verificación de enlaces)
- `pillow==12.3.0` (iconos)

Pillow 13 exige Python 3.11. La versión 12.3.0 mantiene el soporte de Python 3.10.

## Instalación en Windows (PowerShell)

Abre PowerShell en la carpeta del proyecto y ejecuta:

```powershell
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Si PowerShell rechaza `Activate.ps1` por la directiva de ejecución, usa una de estas dos opciones:

```powershell
# Opción A: permitir scripts solo en esta ventana, luego activar
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\venv\Scripts\Activate.ps1

# Opción B: no activar nada y llamar directo al Python del entorno
.\venv\Scripts\python.exe main.py
```

La opción A solo afecta a esa ventana. Después de activar, `python main.py` abre la aplicación. La opción B abre la aplicación sin activar el entorno.

## Instalación en Debian (bash)

```bash
sudo apt install python3 python3-venv python3-pip python3-tk
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Ejecutar la aplicación

Con el entorno virtual activado, en la carpeta del proyecto:

```powershell
python main.py
```

En Debian el comando es el mismo (`python main.py`) después de `source venv/bin/activate`.

Se abre la ventana "Gestor de Enlaces". Pega una dirección en el campo y pulsa Añadir (o Enter). El enlace aparece al momento como pendiente y, unos segundos después, cambia de color cuando termina la comprobación. La ventana sigue respondiendo mientras tanto.

En cada fila hay cuatro botones de icono: Editar, Abrir (también vale el doble clic sobre el texto), Copiar URL y Eliminar. Editar cambia el título, la categoría y las notas. Obtener título de nuevo vuelve a leer el título de la página. Abrir lanza el navegador predeterminado y marca el enlace como visitado. Copiar cambia el icono a una marca de verificación durante un segundo. Eliminar pide confirmación. Si pegas el mismo enlace con otra forma (`example.com` y `https://example.com/`), la aplicación avisa y no lo añade otra vez. Si pegas varias líneas, cada línea es un enlace: las vacías se saltan, las que no son http o https se cuentan y las repetidas no se guardan.

El botón Verificar todos comprueba la lista entera, también los enlaces que el filtro oculta. Aparecen una barra, el texto "8 de 25 (32%)" y el botón Cancelar. Como máximo hay 8 comprobaciones a la vez, y se puede seguir usando la ventana. Cancelar no corta lo que ya salió a la red: eso termina y se anota. El resto no se inicia.

Debajo hay un buscador y dos menús. El buscador mira título, URL, notas y categoría en cada tecla, sin distinguir mayúsculas. El primer menú deja ver todos, un estado (pendiente, activo, error o caído) o si el enlace está visitado. El segundo filtra por categoría: Todas, Sin categoría o una de las que ya hay. Las tres condiciones se aplican a la vez. La barra inferior cuenta toda la colección, por ejemplo "12 activos, 3 caídos, 2 errores, 5 pendientes". Ahí también están Importar, Exportar y Reintentar caídos. Exportar escribe un CSV con todos los enlaces, no solo los que se ven. Importar añade los nuevos y conserva los que ya estaban. El formato del archivo está en la sección "Formato del CSV".

Sin activar el entorno:

- Windows: `.\venv\Scripts\python.exe main.py`
- Debian: `./venv/bin/python main.py`

## Ejecutar las pruebas de consola

```powershell
python main.py --probar
```

En Debian, el mismo comando con el entorno activado. Escribe líneas `OK` o `FALLO` y termina con un resumen. El código de salida es 0 solo cuando todas las pruebas pasan. No abre la ventana. Las tres pruebas de red necesitan internet.

## Estructura del proyecto

```text
link_manager/
  main.py             Abre la ventana; con --probar lanza las pruebas
  interfaz.py         Ventana oscura, lista, filtro y resumen
  datos.py            Carga y guardado de enlaces.json y CSV
  verificador.py      Normalización de URL y comprobación HTTP
  requirements.txt    Dependencias con versión fijada
  README.md           Esta guía
  DOCUMENTACION.md    Diario de decisiones por fase
  .gitignore
  assets/icons/       SVG Lucide y PNG a 20 px y 40 px
  venv/               Entorno local; no se versiona
```

## Dónde se guardan los enlaces

`enlaces.json` (UTF-8, indentado) se crea junto a los scripts si esa carpeta se puede escribir. Si el programa está en una ruta de solo lectura, el archivo pasa a:

- Windows: `%APPDATA%\GestorDeEnlaces\enlaces.json`
- Debian: `$XDG_CONFIG_HOME/gestor-de-enlaces/enlaces.json`, o `~/.config/gestor-de-enlaces/enlaces.json`

Al abrir la ventana, si todavía no existe el archivo, se crea `enlaces.json` vacío. Las pruebas de `python main.py --probar` usan una carpeta temporal y no escriben ese archivo en el proyecto.

Cada enlace tendrá: `url`, `titulo`, `titulo_manual`, `estado`, `codigo_http`, `visitado`, `categoria`, `notas`, `fecha_añadido`, `ultima_verificacion`.

`titulo_manual` queda en verdadero cuando el título se escribe en el diálogo. Mientras lo esté, una verificación posterior lo conserva. Si es falso, o si el título guardado es `Sin título`, la siguiente comprobación escribe el de la página. Si la página no lo trae, el título queda formado por el dominio sin `www` y, cuando la ruta tiene partes, la última con los guiones convertidos en espacios: `example.com / articulo sobre python`.

Estados del enlace: `pendiente`, `activo` (HTTP 200-399), `error` (HTTP 4xx/5xx o URL no válida), `caído` (timeout, DNS, SSL o sin conexión). `visitado` es independiente del estado.

## Formato del CSV

Importar y exportar usan las mismas columnas, en UTF-8 con BOM. La única obligatoria es `url`. Si esa columna no está, el archivo se rechaza y la lista sigue igual. Las demás pueden omitirse:

- `titulo`
- `estado`
- `codigo_http`
- `visitado`
- `categoria`
- `notas`
- `fecha_añadido`
- `ultima_verificacion`

Una fila vacía, o con la `url` vacía, se omite. Un `estado` distinto de `pendiente`, `activo`, `error` o `caído` queda en `pendiente` y el enlace se verifica. Un estado conocido se conserva. `visitado` se escribe `si` o `no`; al leer también valen `true`, `false`, `1` y `0`. Un título no vacío, distinto de `Sin título`, se conserva en las verificaciones siguientes. La celda vacía o el texto `Sin título` se sustituye la próxima vez que se comprueba el enlace.

## Funcionalidades disponibles

Hasta esta fase:

- Crear un registro de enlace con todos los campos.
- Cargar y guardar la lista en JSON. Si el archivo no existe, se crea vacío. Si está corrupto, se copia a un `.bak` y el archivo de trabajo queda en `[]`.
- Escritura atómica: se escribe un temporal y después se renombra.
- Normalizar una URL (se antepone `https://` si falta el esquema).
- Verificar una URL con tiempo límite de 8 segundos: primero HEAD y, si falla o el servidor responde 405 o 501, GET. Si HEAD responde y el contenido es HTML, un GET parcial de como máximo 64 KB lee el título y se cierra la conexión. El código HTTP sigue siendo el del HEAD. Si no hay título, se guarda uno descriptivo a partir de la URL.
- Ventana oscura y redimensionable, con iconos Lucide.
- Campo de URL y botón Añadir. El enlace se guarda al momento y se verifica en segundo plano, sin congelar la ventana.
- Lista con un punto de color: verde activo, rojo caído, naranja error, gris pendiente. Si hay notas, se ve la primera línea.
- Editar el título, la categoría y las notas de un enlace. Obtener título de nuevo rellena el título desde la página. Un título escrito a mano se conserva al verificar. `Sin título`, si quedó guardado de antes, se sustituye en la siguiente comprobación.
- Abrir el enlace en el navegador predeterminado, con el botón o con doble clic. Al abrirlo queda marcado como visitado.
- Copiar la URL al portapapeles. El icono del botón pasa a una marca de verificación durante un segundo.
- Eliminar un enlace, con confirmación.
- Avisar si el enlace ya está en la lista, aunque cambie el esquema, las mayúsculas, la barra final o el fragmento `#...`.
- Pegar varios enlaces de una vez, uno por línea.
- Verificar todos los enlaces, con un máximo de 8 comprobaciones a la vez. El filtro no reduce esa tanda.
- Barra de progreso, contador "8 de 25 (32%)" y botón Cancelar. Los resultados solo se pintan en el hilo principal.
- Buscar por título, URL, notas o categoría, al escribir, sin distinguir mayúsculas.
- Filtrar por estado y, a la vez, por categoría (Todas, Sin categoría o una de las guardadas).
- Resumen fijo de toda la colección: "12 activos, 3 caídos, 2 errores, 5 pendientes".
- Reintentar caídos, con el mismo tope de 8 comprobaciones y la misma barra de progreso.
- Importar y exportar CSV. Exportar incluye toda la colección. Importar añade los nuevos y se salta los repetidos.

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

**PowerShell no deja activar el entorno.** Usa la opción A o la opción B de la sección "Instalación en Windows".

**`python3 -m venv` falla en Debian.** Falta el paquete `python3-venv`. Instálalo con el comando `apt` de la sección de Debian y vuelve a crear el entorno.

**La ventana no arranca en Debian.** Falta `python3-tk`. CustomTkinter se apoya en Tk, que no viene dentro de `pip`.

**La ventana dice que faltan iconos.** Tiene que existir cada `nombre-40.png` dentro de `assets/icons/`. No borres esa carpeta.

**Las pruebas de "Red" salen FALLO y el resto OK.** Esas tres necesitan internet y que `example.com` responda. Revisa la conexión y vuelve a lanzar `python main.py --probar`. Un dominio `.invalid` debe quedar como `caído`; si una red corporativa responde por él, esa prueba concreta puede fallar.

**Verificar todos tarda o parece parado.** Cada enlace espera como máximo 8 segundos, y solo 8 van a la vez. Con 25 enlaces lentos puede acercarse al medio minuto. Cancelar deja terminar los que ya empezaron (nunca más de 8) y no inicia los demás.

**Un enlace no aparece después de añadirlo.** El filtro o el buscador lo está ocultando. Elige Todos y Todas, y borra el texto de búsqueda. El enlace sigue guardado: la barra inferior cuenta toda la colección, no solo las filas visibles.

**Excel muestra símbolos raros en el CSV.** Exporta otra vez desde la aplicación. El archivo va en UTF-8 con BOM para que Excel lea las tildes. Si el CSV no tiene una columna `url`, la importación no cambia la lista.

**Aparece un archivo `.bak`.** El JSON no se pudo leer. La copia conserva el contenido anterior. El archivo de trabajo se reescribe como lista vacía para que el programa pueda seguir. No borres el `.bak` hasta recuperar lo que te interese.
