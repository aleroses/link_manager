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

## Uso diario

Crear el entorno e instalar las dependencias se hace una sola vez, con los pasos de arriba. Cada día basta uno de estos comandos.

### Debian

`source venv/bin/activate` solo afecta a la terminal en la que se ejecuta. Al cerrarla, `python` vuelve a ser el del sistema.

De la más simple a la más avanzada:

```bash
# (a) Con el entorno activado, en la carpeta del proyecto
source venv/bin/activate
python main.py

# (b) Sin activar el entorno, en la carpeta del proyecto
./venv/bin/python main.py

# (c) Desde cualquier carpeta. El script localiza el proyecto solo.
./gestor.sh
```

`./gestor.sh` también acepta los argumentos de `main.py`. Desde otra carpeta hay que llamarlo con su ruta, por ejemplo `/ruta/al/proyecto/gestor.sh`. Si todavía no existe `venv/bin/python`, el script lo dice y recuerda los comandos de instalación.

Lanzador de escritorio (opcional). Se puede añadir una entrada al menú de aplicaciones con un archivo en `~/.local/share/applications/gestor-de-enlaces.desktop`. Las rutas tienen que ser absolutas y las de este ejemplo hay que cambiarlas por las de tu máquina:

```ini
[Desktop Entry]
Type=Application
Name=Gestor de Enlaces
Comment=Guardar enlaces web y comprobar si responden
Exec=/home/ale/Documents/projects/link_manager/gestor.sh
Path=/home/ale/Documents/projects/link_manager
Terminal=false
Categories=Utility;
```

Después, si el menú no lo muestra, `update-desktop-database ~/.local/share/applications` vuelve a leer esa carpeta.

### Windows

La activación con `Activate.ps1` solo dura en esa ventana de PowerShell. Al cerrarla hay que activar otra vez.

```powershell
# (a) Con el entorno activado, en la carpeta del proyecto
.\venv\Scripts\Activate.ps1
python main.py

# (b) Sin activar el entorno. No depende de la política de ejecución.
.\venv\Scripts\python.exe main.py
```

Si PowerShell rechaza `Activate.ps1`, la forma (b) abre la aplicación igual. El detalle de la directiva de ejecución está en "Instalación en Windows".

## Ejecutar la aplicación

Con cualquiera de los comandos de "Uso diario" se abre la ventana "Gestor de Enlaces".

Al entrar ves tus categorías en tarjetas. La primera es Sin categoría. Cada una muestra cuántos enlaces tiene y cuántos están activos, caídos, con error o pendientes. Arriba puedes cambiar a Todos los enlaces para ver la lista completa. Pulsa una tarjeta para entrar en ella.

Para guardar un enlace, pega la dirección, elige la categoría y pulsa Añadir (o Enter). En el menú están Sin categoría, las que ya creaste y Nueva categoría..., que crea una y la deja elegida. Dentro de una categoría el menú empieza en esa. En el resto de la ventana empieza en Sin categoría. El enlace aparece enseguida como pendiente y cambia de color cuando termina la comprobación. Mientras tanto puedes seguir usando la ventana.

En cada fila tienes Editar, Abrir, Copiar y Eliminar. Abrir (o el doble clic) lanza el navegador y marca el enlace como visitado. Copiar muestra una marca de verificación un momento. Eliminar pide confirmación. Editar cambia el título, la categoría y las notas. Desde ahí también puedes crear una categoría, o volver a leer el título de la página. Si el enlace ya estaba, aunque lo pegues de otra forma (`example.com` y `https://example.com/`), la aplicación te avisa. Si pegas varias líneas, cada una se guarda en la categoría elegida: se saltan las vacías, se cuentan las que no son una dirección web y no se repiten las que ya tienes.

Si la ventana es estrecha, la lista va en una columna. Al ensancharla pasa a dos, y las tarjetas pueden llegar a tres. El lugar por donde ibas y los filtros se quedan igual. Si un texto no cabe, se corta con puntos suspensivos. Debajo del estado verás `verificado 18/10/2026`, o `sin verificar` si ese enlace nunca se comprobó.

Verificar todos revisa la colección entera. En las tarjetas está a la izquierda de Nueva categoría. En Todos los enlaces aparece junto a una barra, un contador como "8 de 25 (32%)" y Cancelar. Hay como máximo 8 comprobaciones a la vez. Cancelar deja acabar las que ya empezaron. Dentro de una categoría el botón es Verificar categoría: pasa a decir Verificando... y el icono gira. Puedes salir de esa categoría y la comprobación sigue. Una categoría vacía te avisa y no empieza. Abrir una categoría no comprueba nada por sí sola.

Nueva categoría pide un nombre. Hace falta que no esté vacío, que no se repita y que no sea Sin categoría, Todas, Nueva categoría ni Nueva categoría.... Sin categoría se queda fija. En cada tarjeta puedes abrir todos sus enlaces (si hay más de 5, pide confirmación), verificarlos, renombrar la categoría o eliminarla. Al eliminar puedes dejar los enlaces en Sin categoría, que es la opción marcada, o borrarlos con ella.

Para encontrar un enlace, escribe en el buscador: mira el título, la dirección, las notas y la categoría, sin distinguir mayúsculas. Los menús filtran por estado, por si ya lo visitaste y, en Todos los enlaces, por categoría. Abajo, la barra resume toda la colección, por ejemplo "12 activos, 3 caídos, 2 errores, 5 pendientes". Desde ahí puedes importar, exportar o reintentar los caídos. Exportar guarda todos los enlaces. Importar añade los nuevos y crea las categorías que falten. El formato está en "Formato del CSV".

## Ejecutar las pruebas de consola

```powershell
python main.py --probar
```

En Debian, el mismo comando con el entorno activado, o `./gestor.sh --probar`. Escribe líneas `OK` o `FALLO` y termina con un resumen. El código de salida es 0 solo cuando todas las pruebas pasan. No abre la ventana. Las tres pruebas de red necesitan internet.

## Estructura del proyecto

```text
link_manager/
  gestor.sh           Arranque en Debian; localiza el proyecto y usa el Python del venv
  main.py             Abre la ventana; con --probar lanza las pruebas
  interfaz.py         Ventana oscura, lista, filtro y resumen
  datos.py            Carga y guardado de data/enlaces.json y CSV
  verificador.py      Normalización de URL y comprobación HTTP
  registro.py         gestor.log rotativo, junto a los datos
  requirements.txt    Dependencias con versión fijada
  README.md           Esta guía
  DOCUMENTACION.md    Diario de decisiones por fase
  .gitignore
  assets/icons/       SVG Lucide, PNG a 20 px y 40 px, y LICENSE-lucide.txt
  GestorDeEnlaces.spec  Receta de PyInstaller; sí se versiona
  LICENSE             GPL-3.0
  data/               enlaces.json y gestor.log; no se versiona
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

Una categoría guardada tiene `nombre` y `fecha_creacion`. El nombre conserva las mayúsculas con las que se creó. Cada enlace sigue llevando `categoria`: el texto vacío es Sin categoría. Si el archivo no se puede leer, es una lista antigua o no tiene esa forma, se copia a un `.bak`, el archivo de trabajo queda en el documento vacío y la ventana lo dice. Si `data/` no se puede escribir, el aviso indica que los enlaces pasan a la carpeta de configuración. Las pruebas de `python main.py --probar` usan una carpeta temporal y no escriben ese archivo en el proyecto.

Los fallos se anotan en `data/gestor.log` (o junto al JSON, si los datos están en la carpeta de configuración). El archivo rota al llegar a 256 KB y conserva dos copias. Un error inesperado no cierra la ventana con un traceback: queda una frase en español y el detalle en el registro.

Cada enlace tendrá: `url`, `titulo`, `titulo_manual`, `estado`, `codigo_http`, `visitado`, `categoria`, `notas`, `fecha_añadido`, `ultima_verificacion`.

`titulo_manual` queda en verdadero cuando el título se escribe en el diálogo. Mientras lo esté, una verificación posterior lo conserva. Si es falso, o si el título guardado es `Sin título`, la siguiente comprobación escribe el de la página. Si la página no lo trae, el título queda formado por el dominio sin `www` y, cuando la ruta tiene partes, la última con los guiones convertidos en espacios: `example.com / articulo sobre python`.

Estados del enlace: `pendiente`, `activo` (HTTP 200-399), `error` (HTTP 4xx/5xx o URL no válida), `caído` (timeout, DNS, SSL o sin conexión). `visitado` es independiente del estado.

## Formato del CSV

Importar y exportar usan las mismas columnas. La exportación escribe UTF-8 con BOM. La importación acepta también la codificación de Windows (cp1252). Si el archivo no es ninguna de las dos, está mal formado o no tiene la columna `url`, se rechaza con un mensaje y la lista sigue igual. Las demás columnas pueden omitirse:

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
- Lista con un punto de color: verde activo, rojo caído, naranja error, gris pendiente. Si hay notas, se ve la primera línea. Bajo el estado está la fecha de la última verificación, o `sin verificar` si sigue pendiente. En una ventana estrecha la lista va en una columna; a partir de unos 1000 px de ventana, en dos. Las tarjetas llegan hasta tres columnas en un contenedor de unos 1440 px. Título, URL, notas y fecha se cortan con puntos suspensivos. Al redimensionar se conservan el scroll y los filtros.
- Editar el título, la categoría y las notas de un enlace. La categoría sale de un menú y se puede crear una nueva al guardar. Obtener título de nuevo rellena el título desde la página. Un título escrito a mano se conserva al verificar. `Sin título`, si quedó guardado de antes, se sustituye en la siguiente comprobación.
- Ver las categorías como tarjetas, entrar en una y volver. Al entrar se muestran los estados guardados. Verificar todos está a la izquierda de Nueva categoría. En Todos los enlaces, ese botón queda junto a la barra de progreso. Dentro de una categoría no aparece.
- Verificar categoría, en la tarjeta o en la cabecera de la sección, comprueba solo esos enlaces, con el mismo tope de 8 hilos y sin barra. El botón muestra Verificando... y un icono que gira. Al terminar vuelve a su texto.
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
- Importar y exportar CSV. Exportar incluye toda la colección. Importar añade los nuevos, se salta los repetidos y crea las categorías que falten. Un CSV mal formado o en una codificación no reconocida se rechaza sin cambiar la lista.
- Avisos en español cuando no hay conexión a internet, el JSON está dañado, la carpeta de datos no se puede escribir, el CSV no se puede leer o falta un icono en `assets/icons/`. El detalle queda en `data/gestor.log`.

## Ramas

- `master`: línea estable. Está en `v1.0.0`. Todo cambio entra aquí cuando ya está validado.
- `windows` y `debian`: ramas de validación, una por sistema operativo. Contienen `v1.0.0`. Cuando `master` avanza, se actualizan con `git merge master`.

El trabajo nuevo se hace en la rama del sistema donde se está probando. Ahí se valida, se fusiona en `master` y después se actualiza la otra rama.

En Debian:

```bash
git checkout master
git merge debian
git checkout windows
git merge master
git checkout debian
```

En Windows:

```bash
git checkout master
git merge windows
git checkout debian
git merge master
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

**La ventana dice que no hay conexión.** El equipo no llega a la red. Los enlaces que no respondieron quedan como caídos. Cuando vuelva la conexión, Reintentar caídos los comprueba otra vez. Un sitio concreto que no responde no muestra este aviso.

**La ventana dice que no se puede escribir en la carpeta de datos.** Revisa los permisos de `data/`, o de la carpeta de configuración si el programa ya avisó que guarda ahí. El detalle está en `gestor.log`, en esa misma carpeta.

## Crear un ejecutable

PyInstaller no está en `requirements.txt`: solo hace falta para empaquetar. Con el entorno activado, en la carpeta del proyecto, el comando es el mismo en PowerShell y en bash:

```bash
pip install pyinstaller
```

En Windows el separador de `--add-data` es `;`. Los iconos entran en el paquete y los datos no:

```powershell
pyinstaller --noconfirm --windowed --name GestorDeEnlaces --collect-all customtkinter --collect-all PIL --add-data "assets/icons;assets/icons" main.py
```

En Debian el separador es `:` y el comando es el mismo en lo demás:

```bash
pyinstaller --noconfirm --windowed --name GestorDeEnlaces --collect-all customtkinter --collect-all PIL --add-data "assets/icons:assets/icons" main.py
```

El resultado queda en `dist/GestorDeEnlaces/`. En Windows el programa es `GestorDeEnlaces.exe`. En Debian es `GestorDeEnlaces`, sin extensión. `assets/icons/` viaja dentro del paquete. `data/enlaces.json` y `data/gestor.log` se crean junto al ejecutable la primera vez que se abre, no dentro del paquete: así no se borran al volver a generarlo. Si esa carpeta no se puede escribir, los dos archivos pasan a la carpeta de configuración del usuario, la misma de la sección "Dónde se guardan los enlaces". `--windowed` no abre consola; un fallo de arranque se lee en `gestor.log`.

La copia de Windows regenerada el 18 de octubre de 2026 se hizo con PyInstaller 6.22.3. La carpeta `dist/GestorDeEnlaces/` ocupa unos 47 MB sin contar `data/`, porque esa carpeta aparece al abrir el programa.

La copia de Debian generada el mismo día se hizo con PyInstaller 6.22.3 y Python 3.11.2. La carpeta ocupa 56 MB (635 archivos, 56198544 bytes) sin contar `data/`.

`build/` y `dist/` no se versionan. `GestorDeEnlaces.spec` sí: guarda la receta del ejecutable y no contiene rutas de esta máquina.

## Licencia

Gestor de Enlaces se publica bajo la [GPL-3.0](LICENSE). El texto completo está en ese archivo. Cada módulo `.py` lleva un encabezado que remite a él.

## Créditos y licencias de terceros

Estas licencias se comprobaron en los archivos que instala `pip` y, para Lucide, en la etiqueta 0.469.0 del repositorio. Las cuatro se pueden combinar con la GPL-3.0: son permisivas, o en el caso de Apache-2.0 la Free Software Foundation la considera compatible con la GPL-3.0.

- CustomTkinter 6.0.0, de Tom Schimansky. El archivo `LICENSE` de la rueda es MIT (copyright 2023). En PyPI el campo de licencia dice CC0 y el clasificador dice MIT; manda el texto que viaja con el paquete, que es MIT. https://github.com/TomSchimansky/CustomTkinter
- requests 2.34.2, de Python Software Foundation. Apache-2.0. https://github.com/psf/requests
- Pillow 12.3.0. MIT-CMU, la licencia histórica de PIL: copyright 1997-2011 Secret Labs AB, 1995-2011 Fredrik Lundh, y desde 2010 Jeffrey A. Clark y colaboradores. https://github.com/python-pillow/Pillow
- Iconos Lucide 0.469.0. ISC. Parte del copyright (2013-2022) es de Cole Bemis, por Feather (MIT); el resto (2022) es de Lucide Contributors. El aviso está en `assets/icons/LICENSE-lucide.txt`. https://github.com/lucide-icons/lucide/blob/0.469.0/LICENSE
