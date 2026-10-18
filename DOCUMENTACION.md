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

## 2026-10-17 — Fase 3: Ventana base

### Qué se hizo

La aplicación abre una ventana oscura. Se puede pegar una URL, pulsar Añadir y ver el enlace en una lista con un punto de color según su estado. Al añadir, el registro se guarda como pendiente y un hilo llama a `verificar_url`. El hilo principal recoge el resultado con `after()`, actualiza la fila y vuelve a guardar. `python main.py` abre la ventana. `python main.py --probar` conserva las pruebas de consola.

Los iconos de Lucide 0.469.0 (licencia ISC) están en `assets/icons/`: el SVG original y un PNG a 20 px y otro a 40 px. La interfaz carga el de 40 px con `CTkImage` a tamaño 20, para que una pantalla HiDPI tenga píxeles de sobra.

### Decisiones técnicas y por qué

- La ventana vive en `interfaz.py`. `main.py` solo elige entre la ventana y las pruebas, para no mezclar Tk con el bloque de consola.
- Paleta fija en el código: fondo `#14171C`, barras `#1C2128`, filas `#242A33`, un solo acento `#4C8DFF`. Los estados son verde `#3DDC97`, rojo `#E85D4C`, naranja `#E8A04C` y gris `#8B9098`. El nombre del estado acompaña al punto para que el color no sea la única pista.
- Se fijó Lucide 0.469.0 porque en `main` ya no existen `trash-2` ni `filter`, y en esa etiqueta sí están, junto con `triangle-alert`.
- Pillow no rasteriza SVG. Los PNG se generaron una vez en el desarrollo (trazo claro `#E7E5E4` sobre fondo transparente) y quedan en el repositorio. Quien clone el proyecto no necesita Cairo ni Inkscape, ni en Windows ni en Debian.
- Si falta un PNG de 40 px, la aplicación muestra el nombre del archivo y no construye la lista a medias.
- La verificación al añadir no espera en el hilo de la interfaz. El hilo de red solo deposita el resultado en una cola. Un `after()` del hilo principal lo escribe en la fila. Llamar a `after()` desde el otro hilo no es fiable: Tk responde que el hilo principal no está en su bucle y el estado se quedaría en pendiente. "Verificar todos", la barra de progreso y la cancelación siguen siendo la fase 5. Abrir, copiar, editar, borrar y los duplicados siguen siendo la fase 4: los iconos ya están guardados, pero esos botones no se muestran todavía.
- Una URL vacía o que no sea http/https no se guarda. El aviso queda en la barra superior.
- El bloque de PowerShell (directiva solo de esa ventana, o llamar a `python.exe` sin activar) está en la instalación de Windows. El fallo ocurre al activar el entorno, antes de llegar a "Problemas comunes".

### Archivos creados o modificados

- `assets/icons/*.svg`, `assets/icons/*-20.png`, `assets/icons/*-40.png`
- `interfaz.py`
- `main.py`
- `README.md`
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

`renderPM` de ReportLab, usado solo para fabricar los PNG, pasó a depender de cairocffi en cuanto esa librería estuvo instalada, y cairocffi no encontraba la DLL de Cairo. Se desinstaló cairocffi para que el render usara pycairo, se generaron los PNG y después se quitaron esas herramientas del entorno. No forman parte de `requirements.txt`.

### Pendientes

- Abrir enlaces con `webbrowser`, copiar, borrar y duplicados (fase 4).
- Verificación de todos con barra de progreso y cancelar (fase 5).
- Filtros, búsqueda, categorías editables, CSV y contadores (fase 6).
- Pulido y notas de PyInstaller (fase 7).
- Crear la rama `debian` al validar en Linux.

## 2026-10-17 — Fase 4: Abrir, copiar, eliminar y duplicados

### Qué se hizo

Cada fila tiene tres botones de icono: Abrir, Copiar URL y Eliminar. Abrir usa `webbrowser` y, si el navegador arranca, pone `visitado` en verdadero y muestra el icono check. El doble clic sobre el texto de la fila hace lo mismo. Copiar deja la URL en el portapapeles y cambia el icono a check durante un segundo. Eliminar abre un diálogo oscuro con Cancelar y Eliminar. Un enlace repetido no se guarda: el aviso dice que ya está en la lista.

### Decisiones técnicas y por qué

- `verificador.clave_url` compara sin distinguir mayúsculas en el esquema y el host, sin la barra final y sin el fragmento. La query se conserva, porque `?id=1` y `?id=2` son páginas distintas. La URL que se guarda sigue siendo la de `normalizar_url`; las ya guardadas no se reescriben.
- El diálogo es un `CTkToplevel` con los colores de la aplicación. Un `messagebox` del sistema se vería distinto en Windows y en Debian.
- El hilo de red ya no devuelve la posición del enlace. Devuelve el diccionario. Si ese objeto ya no está en la lista (porque se eliminó), el resultado se descarta. Así borrar el de arriba no escribe el estado en el de abajo. `list.remove` compara por contenido, no por identidad, así que la baja se hace filtrando con `is`.
- El portapapeles usa `clipboard_clear` y `clipboard_append`, y después `update_idletasks()`, para que en Debian la copia siga disponible al salir de la ventana.
- Si la lista se redibuja antes de que pase el segundo del check (por ejemplo, porque llega la verificación), el callback comprueba que el botón siga existiendo.

### Archivos creados o modificados

- `verificador.py`
- `interfaz.py`
- `main.py` (pruebas de `clave_url`)
- `README.md`
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

Ninguno de ejecución distinto del diseño anterior: programar `after()` desde el hilo de red ya se había descartado en la fase 3, y aquí la cola solo cambia el dato que transporta.

### Pendientes

- Verificación de todos con barra de progreso y cancelar (fase 5).
- Filtros, búsqueda, categorías editables, notas, CSV y contadores (fase 6).
- Pulido y notas de PyInstaller (fase 7).
- Crear la rama `debian` al validar en Linux.

## 2026-10-17 — Fase 5: Verificación masiva

### Qué se hizo

El botón Verificar todos comprueba la lista con un `ThreadPoolExecutor` de 8 hilos. Mientras corre, la barra superior muestra la barra de progreso, el contador "8 de 25 (32%)" y Cancelar. Al terminar, el aviso dice cuántos se comprobaron. Cancelar no abre más conexiones: lo que ya está en la red termina y se guarda; el resto se omite y conserva su estado.

Añadir un enlace usa el mismo grupo de hilos, así que nunca hay más de 8 comprobaciones a la vez aunque se pulse Verificar todos y se añada otro enlace.

### Decisiones técnicas y por qué

- El hilo de red no llama a `after()` ni toca widgets. En la fase 3 eso fallaba: Tk responde que el hilo principal no está en su bucle y el estado se quedaba en pendiente. El trabajador deja el resultado en una cola. Un `after()` del hilo principal, cada 100 ms, escribe el estado, guarda el JSON y pinta la fila y la barra.
- El contador y la barra cuentan comprobaciones que salieron a la red, no los enlaces omitidos por Cancelar. Por eso, al cancelar, el texto puede quedarse en "8 de 25 (32%)" y el aviso repite esa cifra. El porcentaje es entero (`hechos * 100 // total`) para no mostrar 100% antes del último.
- Cada envío lleva un token. Si el enlace se borró, o si llegó un resultado más viejo que el último envío, no se escribe. Borrar el de arriba no cambia el de abajo.
- La fila se actualiza en su sitio (punto, título y estado). Redibujar toda la lista en cada resultado haría saltar el scroll y cortaría el segundo del icono de copiar.
- Cancelar usa un `Event` distinto en cada pulsación. No se reutiliza uno ya activado: si no, un lote nuevo podría heredar la cancelación del anterior.
- Al cerrar la ventana se cancela lo pendiente y `shutdown(wait=False, cancel_futures=True)` no espera. Los hilos del grupo no son demonios (así es `ThreadPoolExecutor` en la biblioteca estándar, también en Python 3.10). Una comprobación ya empezada puede retener el proceso hasta su límite de 8 segundos. La ventana sí se cierra al momento.
- La barra permanece unos 700 ms en el valor final para que se pueda leer, y después se oculta. Verificar todos vuelve a poder pulsarse entonces. Mientras tanto el botón se atenúa: sigue a la vista, pero no acepta otra tanda.
- Al cerrar la ventana se cancelan los `after()` propios. Si no, Tk intenta pintar una ventana que ya no existe.

### Archivos creados o modificados

- `interfaz.py`
- `README.md`
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

Ninguno de ejecución. El reparto se comprobó con un verificador falso: 25 enlaces, nunca más de 8 hilos dentro de la función, el contador en "8 de 25 (32%)", Cancelar dejando sin empezar los que aún estaban en la cola, y el estado sin cambiar hasta que el `after()` del hilo principal recogía la cola.

### Pendientes

- Filtros, búsqueda, categorías editables, notas, CSV y contadores (fase 6).
- Pulido y notas de PyInstaller (fase 7).
- Crear la rama `debian` al validar en Linux.

## 2026-10-17 — Fase 6A: Filtro, búsqueda y reintento

### Qué se hizo

La ventana filtra la lista y la busca al escribir. El menú ofrece Todos, Pendiente, Activo, Error, Caído, Visitado y No visitado. El texto se compara, sin distinguir mayúsculas, con el título, la URL, las notas y la categoría. Las dos condiciones se aplican a la vez. La barra inferior cuenta toda la colección, también lo que el filtro oculta: "12 activos, 3 caídos, 2 errores, 5 pendientes", con singular cuando el número es 1. Reintentar caídos vuelve a comprobar solo ese estado y usa el mismo grupo de 8 hilos, la misma barra y el mismo Cancelar.

### Decisiones técnicas y por qué

- El filtro y el texto no se guardan en el JSON. Son de la sesión. Al volver a abrir, la lista sale completa.
- Visitado y No visitado miran el campo `visitado`, que no es un estado. Un enlace activo puede estar visitado o no.
- El resumen incluye los errores aunque el ejemplo de partida no los citara. Si no, ese estado desaparecería del recuento.
- Verificar todos y Reintentar caídos comparten `_iniciar_verificacion`. El botón solo elige la selección. Reintentar incluye caídos ocultos por el filtro: el botón habla del estado, no de lo que se ve.
- Si una fila oculta recibe un resultado y sigue sin cumplir el filtro, no se redibuja la lista. Solo cambia el resumen. Si entra o sale del filtro, ahí sí se vuelve a pintar. Así un resultado no salta el scroll ni escribe el título en otra fila.
- Si el enlace recién añadido no pasa el filtro, el aviso lo dice. Sigue guardado.

### Archivos creados o modificados

- `interfaz.py`
- `README.md`
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

Ninguno de ejecución. Con un verificador falso se vio el filtro junto con el texto, el resumen en singular y con errores, el reintento limitado a los caídos, y un enlace que pasa a activo y sale de la vista sin cambiar el título del que sigue caído.

### Pendientes

- Editar notas y categoría, pegar varios enlaces y CSV (resto de la fase 6).
- Pulido y notas de PyInstaller (fase 7).
- Crear la rama `debian` al validar en Linux.

## 2026-10-17 — Fase 6B: Categorías, notas, pegado y CSV

### Qué se hizo

Cada fila se puede editar: categoría y notas, sin tocar la URL ni el estado. Si hay notas, la primera línea se ve en la fila. Un segundo menú filtra por Todas, Sin categoría o una categoría ya guardada, junto con el filtro de estado y el buscador. Pegar varias líneas añade un enlace por línea. Importar y Exportar leen y escriben un CSV con las columnas del registro.

### Decisiones técnicas y por qué

- El CSV vive en `datos.py`. Así `python main.py --probar` lo comprueba sin abrir Tk. Va en UTF-8 con BOM: Excel en Windows enseña bien `cañón` y `caído`. `visitado` se escribe `si` o `no`; al leer también valen `true`, `false`, `1` y `0`.
- Importar une por la misma clave que los duplicados. No borra ni reescribe un enlace que ya está. Si el estado del archivo no es pendiente, activo, error o caído, queda pendiente y se verifica. Un estado válido se conserva y no sale a la red.
- El campo de arriba sigue siendo de una línea. Solo un pegado con varias líneas se reparte. Una línea sola entra en el campo, como antes.
- Todas y Sin categoría son opciones fijas del menú. El resto sale de las categorías guardadas, sin distinguir mayúsculas: se muestra la primera forma. Si la categoría elegida desaparece, el menú vuelve a Todas.
- Editar guarda una sola vez y vuelve a pintar la lista. La verificación en segundo plano no cambia notas ni categoría.

### Archivos creados o modificados

- `datos.py`
- `main.py`
- `interfaz.py`
- `README.md`
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

Ninguno de ejecución. La consola cubre el ida y vuelta con tildes, una fila sin URL y un estado desconocido. La ventana cubre el filtro de categoría, el guardado de notas, el pegado de tres líneas y un import que no pisa un enlace ya guardado.

### Pendientes

- Pulido y notas de PyInstaller (fase 7).
- Crear la rama `debian` al validar en Linux.

## 2026-10-18 — Fase 7A: Títulos descriptivos y editables

### Qué se hizo

Si HEAD responde y el contenido parece HTML, un GET parcial de como máximo 64 KB lee el `<title>` y cierra la conexión. El código HTTP sigue siendo el del HEAD. Si no hay título, el enlace guarda uno formado con el dominio, sin `www`, y la última parte legible de la ruta. El diálogo de edición incluye el título y el botón Obtener título de nuevo. Un título escrito a mano no se pisa en la siguiente verificación. El texto `Sin título`, si quedó guardado, sí se sustituye.

### Decisiones técnicas y por qué

- El GET de título usa `stream=True`, lee como máximo 64 KB y cierra la respuesta. El tiempo límite sigue en 8 segundos por petición. Si ese GET falla, se conserva el estado que ya dio el HEAD.
- Un `Content-Type` vacío, o que contenga `html` o `xml`, se trata como HTML. Otro tipo, por ejemplo un PDF, no descarga el cuerpo.
- `verificar_url` sigue devolviendo cadena vacía cuando no hay `<title>`. Así la prueba de un dominio caído no cambia. Quien guarda el enlace, en `_escribir_resultado`, elige el título de la página o `titulo_descriptivo`.
- `titulo_manual` vive en el JSON. Falso en un enlace nuevo y en los registros viejos que no traen el campo. Verdadero solo cuando el diálogo guarda un texto distinto del que había y distinto del que acaba de traer el botón. Vaciar el campo, o dejar `Sin título`, guarda el descriptivo y deja la marca en falso.
- Obtener título de nuevo corre en el mismo grupo de 8 hilos. El resultado entra por la cola y el hilo principal lo escribe en el campo. No cambia el estado ni el código hasta Guardar. Cancelar, Escape o cerrar el diálogo descartan ese resultado.
- El CSV no gana una columna. Al importar, un título no vacío y distinto de `Sin título` entra con `titulo_manual` en verdadero, para que la verificación posterior lo conserve. Vacío o `Sin título` entra automático.
- La lista sigue mostrando `Sin título` solo como texto de pantalla mientras el campo guardado esté vacío. Ese texto no se escribe en el JSON.

### Archivos creados o modificados

- `verificador.py`
- `datos.py`
- `interfaz.py`
- `main.py`
- `README.md`
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

Ninguno de ejecución. `python main.py --probar` terminó con 37 pruebas correctas y 0 fallos: título descriptivo, sustitución de `Sin título`, respeto de un título manual, GET parcial tras un HEAD HTML y un PDF al que no se le pide el cuerpo. El diálogo, abierto aparte, guardó el título traído por el botón como automático, el campo vacío como título descriptivo y un texto nuevo como manual.

### Pendientes

- Resto del pulido y notas de PyInstaller (fase 7).
- Crear la rama `debian` al validar en Linux.

## 2026-10-18 — Fase 7B: Categorías como secciones

### Qué se hizo

`enlaces.json` pasa a ser un documento version 2 con `categorias` y `enlaces`. La pantalla abre en tarjetas. Un control alterna con la lista de todos los enlaces. Cada tarjeta muestra el nombre, la cantidad y el recuento de estados, y permite abrir todos, verificar, renombrar y eliminar. Sin categoría es fija. Al entrar en una tarjeta se ven sus enlaces, con las acciones de siempre, y se comprueban en segundo plano. Importar un CSV crea las categorías que falten. El diálogo Editar elige la categoría en un menú.

### Decisiones técnicas y por qué

- Sigue habiendo un solo archivo. No se crea `categorias.json`. Una ficha guarda `nombre` y `fecha_creacion`. El enlace conserva `categoria` como texto, y el vacío significa Sin categoría.
- No hay migración. Una lista antigua, un JSON ilegible o un objeto que no sea version 2 se copia a `.bak` y el archivo de trabajo queda vacío. Los datos que había eran de prueba.
- Crear, renombrar, eliminar y asegurar viven en `datos.py`, así las pruebas no abren Tk. Los nombres se comparan sin distinguir mayúsculas. `Sin categoría`, `Todas` y `Nueva categoría` están reservados porque son etiquetas de la ventana. Renombrar conserva la fecha y actualiza los enlaces.
- Eliminar ofrece dos caminos. El marcado al abrir mueve los enlaces a Sin categoría. El otro los borra. El resto de la colección no cambia.
- La vista de tarjetas y la de todos los enlaces comparten el marco con scroll, la barra de progreso y el grupo de 8 hilos. Entrar en una categoría llama a la misma verificación masiva, solo con esos enlaces. Si ya hay una tanda en curso, no se inicia otra. Una sección vacía no lanza la tanda.
- Añadir desde dentro de una categoría deja el enlace en ella. Desde las tarjetas o desde Todos los enlaces queda en Sin categoría.
- Abrir todos reutiliza la apertura de un enlace. A partir de 6 pide confirmación. Se guarda una vez, al terminar, y solo quedan visitados los que el navegador llegó a abrir.
- El CSV no gana columnas. `asegurar_categoria` crea la ficha que falte y, si el nombre ya existe con otra grafía, el enlace usa la que ya estaba guardada.
- Los iconos nuevos son Lucide 0.469.0: `folder`, `folder-plus`, `arrow-left`, `layout-grid` y `list`, en SVG y en PNG a 20 y 40 px. La herramienta que los rasterizó no forma parte de `requirements.txt`.

### Archivos creados o modificados

- `datos.py`
- `interfaz.py`
- `main.py`
- `assets/icons/folder.svg`, `folder-plus.svg`, `arrow-left.svg`, `layout-grid.svg`, `list.svg` y sus PNG
- `README.md`
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

Ninguno de ejecución. `python main.py --probar` terminó con 43 pruebas correctas y 0 fallos: documento version 2, lista antigua archivada en `.bak`, rechazo de nombres, renombre y los dos modos de borrado. La ventana, abierta aparte, mostró las tarjetas, la sección con el botón de volver y el menú de categoría del diálogo Editar.

### Pendientes

- Resto del pulido y notas de PyInstaller (fase 7).
- Crear la rama `debian` al validar en Linux.

## 2026-10-18 — Fase 7B.1: Categoría al añadir y carpeta de datos

### Qué se hizo

Junto al campo de URL hay un menú Categoría. Lista Sin categoría, las categorías guardadas y Nueva categoría..., que abre el diálogo de creación y deja seleccionada la nueva. Dentro de una sección el menú viene con esa. En las tarjetas y en Todos los enlaces viene en Sin categoría. Añadir y el pegado múltiple guardan los enlaces nuevos en la categoría elegida. Los duplicados siguen sin guardarse.

`enlaces.json` pasa a `data/enlaces.json`. La carpeta se crea si no existe. Si `data/` no se puede escribir, el archivo sigue yendo a la carpeta de configuración del usuario. Un `enlaces.json` antiguo en la raíz no se migra ni se borra: la consola avisa que se ignora.

### Decisiones técnicas y por qué

- El menú de alta y el filtro de Todos los enlaces son controles distintos. Cambiar la categoría del alta no cambia el filtro. La vista solo fija el valor por defecto al entrar o salir. Un cambio manual se conserva hasta el siguiente cambio de vista.
- Nueva categoría... reutiliza el diálogo de las tarjetas. Al elegirla, el menú vuelve enseguida a la selección anterior, porque CustomTkinter cambia el texto antes de avisar. Si se cancela, esa selección sigue. Si se guarda, el menú queda en la categoría nueva. El diálogo Editar no cambia: sigue con el campo inline y el texto Nueva categoría.
- `Nueva categoría...` queda reservado, igual que Sin categoría, Todas y Nueva categoría, para que el nombre de la acción no pueda ser una categoría.
- `nuevos_enlaces` vive en `datos.py` y es lo que usan el botón Añadir y el pegado. Normaliza, cuenta inválidos y repetidos (también el repetido dentro del mismo pegado) y no modifica la colección ni crea categorías. Así la prueba no abre Tk. Importar CSV no pasa por esa función: sigue creando las categorías que falten en el archivo.
- La ruta de trabajo es `data/enlaces.json`. `ruta_datos` crea la carpeta y comprueba que se puede escribir, pero no crea el JSON: eso lo sigue haciendo `cargar_enlaces`. La escritura atómica y el `.bak` quedan junto al archivo que esté en uso.
- Si la carpeta del proyecto no admite `data/`, el destino sigue siendo `%APPDATA%\GestorDeEnlaces\enlaces.json` en Windows y `$XDG_CONFIG_HOME/gestor-de-enlaces/enlaces.json` (o `~/.config/gestor-de-enlaces/enlaces.json`) en el resto.
- No hay migración. El `enlaces.json` de la raíz puede ser de prueba o de una versión anterior. Copiarlo solo podría mezclar una lista antigua con el documento version 2. Se deja en su sitio y `ruta_datos` escribe en stderr que se ignora.
- `.gitignore` ignora `data/` entera. La línea `enlaces.json` se queda para el archivo viejo de la raíz. `*.bak` y `*.tmp` siguen cubriendo copias fuera de `data/`.

### Archivos creados o modificados

- `datos.py`
- `interfaz.py`
- `main.py`
- `.gitignore`
- `README.md`
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

Ninguno de ejecución. `python main.py --probar` terminó con 47 pruebas correctas y 0 fallos: la ruta `data/enlaces.json`, el aviso del JSON de la raíz, el respaldo en la carpeta de configuración y el alta con categoría, duplicados e inválidos. Una ventana abierta sobre un archivo temporal mostró el menú en Sin categoría, lo actualizó al crear Lectura, lo preseleccionó al entrar en esa sección y lo devolvió a Sin categoría al pasar a Todos los enlaces y al volver a las tarjetas.

### Pendientes

- Resto del pulido y notas de PyInstaller (fase 7).
- Crear la rama `debian` al validar en Linux.

## 2026-10-18 — Fase 7C: Diseño adaptable

### Qué se hizo

La lista de Todos los enlaces, la lista dentro de una categoría y la cuadrícula de tarjetas se reparten en columnas según el ancho del contenedor. Una ventana estrecha queda en una columna. Los enlaces pasan a dos cuando el contenedor llega a 960 px, cerca de 1000 px de ventana. Las tarjetas pueden llegar a tres a partir de 1440 px. El título, la URL y la primera línea de notas se cortan con puntos suspensivos, y los botones de cada fila siguen visibles y alineados.

### Decisiones técnicas y por qué

- El número de columnas lo calcula `columnas_para_ancho` con el ancho del canvas de la lista, no con el de la pantalla. El mínimo está en `ANCHO_MINIMO_COLUMNA` (480). Hace falta el doble de ese mínimo para abrir la segunda columna, y el triple para la tercera. `MAX_COLUMNAS_ENLACES` es 2 y `MAX_COLUMNAS_TARJETAS` es 3. Si hay menos elementos que columnas, no se deja una columna vacía: cuatro tarjetas en una pantalla ancha quedan tres y luego una, alineada con la primera.
- En una pantalla de 1366 px el contenedor se queda alrededor de 1320 px, así que las tarjetas llegan a dos columnas. La tercera aparece cuando el contenedor mide al menos 1440 px.
- El `<Configure>` del canvas se enlaza con `add="+"` para no quitar el ajuste de ancho que ya hace el marco con scroll. Si el ancho no cambió, no se hace nada. Si cambió, se espera `DEBOUNCE_REDIMENSION_MS` (150) y solo se reconstruye la rejilla cuando el número de columnas es distinto. Si no, se vuelven a recortar los textos. `_al_cerrar` cancela esa espera.
- `refrescar_lista` sigue guardando la fracción de scroll y no toca el filtro, la búsqueda ni el menú de categoría. El cambio de columnas pasa por ahí.
- Las columnas comparten el ancho con `grid` y `uniform`, el mismo peso en cada una. En la fila, el icono de visitado ocupa su columna aunque no se vea, y los cuatro botones quedan en la siguiente. Así se alinean entre filas en los dos modos.
- El recorte usa la fuente ya escalada de la ventana y un presupuesto que reserva el punto, el hueco de visitado y los botones. El resumen de estados de la tarjeta sigue en varias líneas, con un `wraplength` del ancho de la columna.

### Archivos creados o modificados

- `interfaz.py`
- `main.py`
- `README.md`
- `DOCUMENTACION.md`

### Problemas encontrados y cómo se resolvieron

Ninguno de ejecución. `python main.py --probar` terminó con 53 pruebas correctas y 0 fallos: los límites 959, 960, 1439 y 1440, el recorte con puntos suspensivos, y una ventana temporal en la que las tarjetas y la lista siguen el ancho medido del contenedor. Al ensanchar, el filtro Activo y la fracción de scroll se mantuvieron.

### Pendientes

- Resto del pulido y notas de PyInstaller (fase 7).
- Crear la rama `debian` al validar en Linux.
