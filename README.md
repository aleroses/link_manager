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

Se abre la ventana "Gestor de Enlaces" en la vista de categorías. Cada tarjeta muestra el nombre, cuántos enlaces tiene y el recuento de estados. La primera es Sin categoría. Un control arriba alterna con Todos los enlaces, que es la lista completa. Al pulsar una tarjeta se ven sus enlaces y empieza su comprobación. Pega una dirección en el campo, elige la categoría en el menú de al lado y pulsa Añadir (o Enter). El menú lista Sin categoría, las categorías ya guardadas y Nueva categoría..., que abre el diálogo de creación y deja seleccionada la nueva. Dentro de una categoría, el menú viene con esa. En las tarjetas y en Todos los enlaces, viene en Sin categoría. El enlace nuevo se guarda en la categoría elegida. Aparece al momento como pendiente y, unos segundos después, cambia de color cuando termina la comprobación. La ventana sigue respondiendo mientras tanto.

En cada fila hay cuatro botones de icono: Editar, Abrir (también vale el doble clic sobre el texto), Copiar URL y Eliminar. Editar cambia el título, la categoría y las notas. La categoría se elige en un menú, y desde ahí también se puede crear una nueva. Obtener título de nuevo vuelve a leer el título de la página. Abrir lanza el navegador predeterminado y marca el enlace como visitado. Copiar cambia el icono a una marca de verificación durante un segundo. Eliminar pide confirmación. Si pegas el mismo enlace con otra forma (`example.com` y `https://example.com/`), la aplicación avisa y no lo añade otra vez. Si pegas varias líneas, cada línea es un enlace y todas quedan en la categoría elegida en el menú: las vacías se saltan, las que no son http o https se cuentan y las repetidas no se guardan.

El botón Verificar todos comprueba la lista entera, también los enlaces que el filtro oculta. Aparecen una barra, el texto "8 de 25 (32%)" y el botón Cancelar. Como máximo hay 8 comprobaciones a la vez, y se puede seguir usando la ventana. Cancelar no corta lo que ya salió a la red: eso termina y se anota. El resto no se inicia.

En la vista de tarjetas, Nueva categoría pide un nombre. Uno vacío, repetido o igual a Sin categoría, Todas, Nueva categoría o Nueva categoría... no se guarda. Cada tarjeta tiene botones de icono: Abrir todos, Verificar categoría, Renombrar y Eliminar. Sin categoría no se renombra ni se elimina. Abrir todos pide confirmación si hay más de 5 enlaces, y marca como visitados los que el navegador abre. Verificar categoría comprueba solo esos enlaces. Eliminar pregunta si los enlaces pasan a Sin categoría, que es la opción marcada al abrir, o si se borran también.

En Todos los enlaces, y también dentro de una categoría, hay un buscador y menús. El buscador mira título, URL, notas y categoría en cada tecla, sin distinguir mayúsculas. El primer menú deja ver todos, un estado (pendiente, activo, error o caído) o si el enlace está visitado. En Todos los enlaces, el segundo filtra por categoría: Todas, Sin categoría o una de las guardadas, aunque todavía no tenga enlaces. Dentro de una categoría ese menú no aparece, porque la sección ya la eligió, y un botón vuelve a las tarjetas. La barra inferior cuenta toda la colección, por ejemplo "12 activos, 3 caídos, 2 errores, 5 pendientes". Ahí también están Importar, Exportar y Reintentar caídos. Exportar escribe un CSV con todos los enlaces, no solo los que se ven. Importar añade los nuevos, conserva los que ya estaban y crea las categorías que falten. El formato del archivo está en la sección "Formato del CSV".

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
  datos.py            Carga y guardado de data/enlaces.json y CSV
  verificador.py      Normalización de URL y comprobación HTTP
  requirements.txt    Dependencias con versión fijada
  README.md           Esta guía
  DOCUMENTACION.md    Diario de decisiones por fase
  .gitignore
  assets/icons/       SVG Lucide y PNG a 20 px y 40 px
  data/               enlaces.json local; no se versiona
  venv/               Entorno local; no se versiona
```

## Dónde se guardan los enlaces

`data/enlaces.json` (UTF-8, indentado) se crea en la carpeta `data/`, junto a los scripts, si esa carpeta se puede escribir. El programa crea `data/` si todavía no existe. Si el programa está en una ruta de solo lectura, el archivo pasa a:

- Windows: `%APPDATA%\GestorDeEnlaces\enlaces.json`
- Debian: `$XDG_CONFIG_HOME/gestor-de-enlaces/enlaces.json`, o `~/.config/gestor-de-enlaces/enlaces.json`

Si en la raíz del proyecto queda un `enlaces.json` de una versión anterior, el programa lo deja donde está y escribe en la consola que no lo migra ni lo borra. Los enlaces nuevos van a `data/enlaces.json`.

Al abrir la ventana, si todavía no existe el archivo, se crea un documento vacío:

```json
{ "version": 2, "categorias": [], "enlaces": [] }
```

Una categoría guardada tiene `nombre` y `fecha_creacion`. El nombre conserva las mayúsculas con las que se creó. Cada enlace sigue llevando `categoria`: el texto vacío es Sin categoría. Si el archivo no se puede leer, es una lista antigua o no tiene esa forma, se copia a un `.bak` y el archivo de trabajo queda en el documento vacío. Las pruebas de `python main.py --probar` usan una carpeta temporal y no escriben ese archivo en el proyecto.

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

Una fila vacía, o con la `url` vacía, se omite. Un `estado` distinto de `pendiente`, `activo`, `error` o `caído` queda en `pendiente` y el enlace se verifica. Un estado conocido se conserva. `visitado` se escribe `si` o `no`; al leer también valen `true`, `false`, `1` y `0`. Un título no vacío, distinto de `Sin título`, se conserva en las verificaciones siguientes. La celda vacía o el texto `Sin título` se sustituye la próxima vez que se comprueba el enlace. Si `categoria` trae un nombre que todavía no existe, la importación crea esa categoría.

## Funcionalidades disponibles

Hasta esta fase:

- Crear un registro de enlace con todos los campos.
- Cargar y guardar el documento version 2 en JSON, con `categorias` y `enlaces`. Si el archivo no existe, se crea vacío. Si está corrupto o es una lista antigua, se copia a un `.bak` y el archivo de trabajo queda en el documento vacío.
- Escritura atómica: se escribe un temporal y después se renombra.
- Normalizar una URL (se antepone `https://` si falta el esquema).
- Verificar una URL con tiempo límite de 8 segundos: primero HEAD y, si falla o el servidor responde 405 o 501, GET. Si HEAD responde y el contenido es HTML, un GET parcial de como máximo 64 KB lee el título y se cierra la conexión. El código HTTP sigue siendo el del HEAD. Si no hay título, se guarda uno descriptivo a partir de la URL.
- Ventana oscura y redimensionable, con iconos Lucide.
- Campo de URL, menú de categoría y botón Añadir. Dentro de una categoría el menú viene con esa; en las tarjetas y en Todos los enlaces, con Sin categoría. Nueva categoría... crea una y la deja seleccionada. El enlace se guarda al momento en la categoría elegida y se verifica en segundo plano, sin congelar la ventana.
- Lista con un punto de color: verde activo, rojo caído, naranja error, gris pendiente. Si hay notas, se ve la primera línea.
- Editar el título, la categoría y las notas de un enlace. La categoría sale de un menú y se puede crear una nueva al guardar. Obtener título de nuevo rellena el título desde la página. Un título escrito a mano se conserva al verificar. `Sin título`, si quedó guardado de antes, se sustituye en la siguiente comprobación.
- Ver las categorías como tarjetas, entrar en una y volver. Al entrar se comprueban sus enlaces con la misma barra y el mismo tope de 8 hilos.
- Crear, renombrar y eliminar categorías. Al eliminar, los enlaces pueden pasar a Sin categoría o borrarse con ella.
- Abrir todos los enlaces de una categoría. Con más de 5, pide confirmación. Los que se abren quedan visitados.
- Abrir el enlace en el navegador predeterminado, con el botón o con doble clic. Al abrirlo queda marcado como visitado.
- Copiar la URL al portapapeles. El icono del botón pasa a una marca de verificación durante un segundo.
- Eliminar un enlace, con confirmación.
- Avisar si el enlace ya está en la lista, aunque cambie el esquema, las mayúsculas, la barra final o el fragmento `#...`.
- Pegar varios enlaces de una vez, uno por línea. Todos los nuevos quedan en la categoría elegida en el menú. Los repetidos no se guardan.
- Verificar todos los enlaces, con un máximo de 8 comprobaciones a la vez. El filtro no reduce esa tanda.
- Barra de progreso, contador "8 de 25 (32%)" y botón Cancelar. Los resultados solo se pintan en el hilo principal.
- Buscar por título, URL, notas o categoría, al escribir, sin distinguir mayúsculas.
- Filtrar por estado y, a la vez, por categoría (Todas, Sin categoría o una de las guardadas).
- Resumen fijo de toda la colección: "12 activos, 3 caídos, 2 errores, 5 pendientes".
- Reintentar caídos, con el mismo tope de 8 comprobaciones y la misma barra de progreso.
- Importar y exportar CSV. Exportar incluye toda la colección. Importar añade los nuevos, se salta los repetidos y crea las categorías que falten.

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

**Aparece un archivo `.bak`.** El JSON no se pudo leer. La copia conserva el contenido anterior y queda junto a `data/enlaces.json`. El archivo de trabajo se reescribe como documento vacío para que el programa pueda seguir. No borres el `.bak` hasta recuperar lo que te interese.

**La ventana está vacía y el `enlaces.json` de la raíz sigue ahí.** Esa copia es de una versión anterior. El programa la ignora y usa `data/enlaces.json`. Para recuperar esos enlaces hay que pasarlos a mano al archivo de `data/`.
