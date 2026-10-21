# Fase 13: investigación de rendimiento de la interfaz

Solo medición. El código del programa no se ha cambiado. No hay commit ni push.

La sensación de que cada acción recarga la ventana es cierta en casi todos los gestos. Hay una excepción importante: en la lista, un resultado de verificación que no entra ni sale del filtro ya actualiza esa fila. En las tarjetas, que es la vista inicial, cada resultado destruye y vuelve a crear todas las tarjetas. Con 50 categorías, 30 resultados seguidos ocupan unos 108 segundos. Con 100 enlaces en Todos los enlaces, borrar uno tarda unos 10 segundos. El objetivo de 50 ms queda unas 200 veces por debajo de lo medido.

## Entorno

Medido el 20 de octubre de 2026 en Debian 12 (bookworm), Python 3.11.2, CustomTkinter 6.0.0, Tk 8.6.13, sobre Xwayland (`DISPLAY=:1`). CPU Intel Core i5-10400F, 8 GB de RAM. La ventana es la del programa: 1000×680.

El canvas de la lista midió 951 px. La segunda columna pide 960 px (`ANCHO_MINIMO_COLUMNA` 480, el doble). En esta geometría todo se pintó en una columna. Pasar a dos columnas no bajaría el número de widgets: `refrescar_lista` crea todas las filas visibles igual.

La aplicación real estaba abierta en la misma sesión. El tope de pixmaps de más abajo es de esa sesión, con las dos ventanas a la vez.

Los datos de prueba se escribieron en `/tmp`, con `Aplicacion(ruta=...)`. `data/enlaces.json`, `data/enlaces.csv` y `data/gestor.log` quedaron con el mismo tamaño y la misma fecha que antes de medir. El script está en `/tmp/medir_rendimiento_fase13.py` y no forma parte del repositorio.

Cada fila de prueba iba sin notas, en estado pendiente, repartida entre categorías con nombre. Los tiempos son una muestra por caso, con `time.perf_counter`, incluyendo el `update()` que vacía la cola de dibujo. `refrescar_lista` ya llama a `update_idletasks` al restaurar el scroll.

## Qué reconstruye la interfaz

Hay un solo camino de reconstrucción: `refrescar_lista` en `interfaz.py`. Borra `_filas`, `_recortes` y `_botones_tarjeta`, hace `destroy()` de todos los hijos de la lista y vuelve a crear tarjetas o filas. Después restaura la fracción de scroll.

`_filas` ya es un diccionario de `id(enlace)` a los widgets de esa fila (punto, título, detalle y fecha). Solo lo usa `_pintar_fila`, y solo cuando la vista es una lista y la fila sigue visible. La marca de visitado no está en ese diccionario. La clave no es la URL: el objeto del enlace ya es la identidad que usa la cola de resultados. Conviene conservarla. Un campo `padre` futuro no tiene por qué cambiar el objeto.

| Acción | Qué ocurre | ¿Bastaría tocar una parte? |
| --- | --- | --- |
| Añadir un enlace | `refrescar_lista` | Sí. En la lista, una fila nueva. En tarjetas, el resumen de una tarjeta. |
| Pegar varias líneas, o importar | Un `refrescar_lista` al guardar el lote. Luego, cada verificación sigue el camino de abajo. | El alta del lote puede reconstruir una vez. Cada verificación, no. |
| Eliminar un enlace | `refrescar_lista` | Sí. Quitar esa fila y reacomodar la rejilla. |
| Editar título, categoría o notas | `refrescar_lista` | Sí, si el enlace sigue en el filtro. Si cambia de filtro, basta quitarlo o moverlo. |
| Abrir un enlace, o abrir todos | `refrescar_lista`, para pintar la marca de visitado | Sí. El icono de esas filas. |
| Cada tecla del buscador | `refrescar_lista` en `<KeyRelease>`, sin espera | Hay que refiltrar. No hace falta en cada tecla, ni rehacer las filas que siguen. |
| Filtro de estado o de categoría | `refrescar_lista` | El conjunto visible cambia. Sigue costando todas las filas que quedan a la vista. |
| Redimensionar | Espera 150 ms. Reconstruye solo si cambia el número de columnas. Si no, recorta textos. | El recorte ya es parcial. En esta ventana el ancho no cruzó las dos columnas, así que un redimensionado de ese tipo no reconstruyó. |
| Entrar en una categoría, volver, o pasar a Todos los enlaces | `refrescar_lista` | Hace falta pintar la vista nueva. No hace falta crear filas que quedan fuera de la pantalla. |
| Crear, renombrar o eliminar una categoría | `refrescar_lista` al cerrar el diálogo | Cambian las tarjetas. No cada fila de las otras categorías. |
| Resultado de verificación, en la lista, si la fila sigue visible | `_pintar_fila` cambia color, título, detalle y fecha. No llama a `refrescar_lista`. | Ya es parcial. |
| Resultado de verificación, en la lista, si entra o sale del filtro | `refrescar_lista` | Basta insertar o quitar esa fila. |
| Resultado de verificación, en tarjetas | `refrescar_lista` por cada resultado | Basta el resumen de esa tarjeta. |
| Copiar | No reconstruye. Cambia el icono del botón un segundo. | Ya es parcial. |

## La cola de resultados y el disco

`_recoger_resultados` se reprograma con `after(100)`: como mucho 10 pasadas por segundo. En cada pasada vacía la cola entera. No agrupa el dibujo. Cada ítem pasa por `_escribir_resultado`, que escribe el JSON completo (`guardar_enlaces`, temporal y renombre, con indentación) y luego `_pintar_fila`.

El número de reconstrucciones no está limitado a 10 por segundo. Es una por resultado. Si 30 resultados están ya en la cola, una sola pasada hace 30 reconstrucciones en las tarjetas y 30 escrituras a disco, y solo después pide el siguiente `after(100)`.

La animación de carga (`after` cada 80 ms) solo cambia el icono del botón. No reconstruye la lista. En las tarjetas el resultado sí destruye esos botones, y `_sincronizar_carga` vuelve a enganchar el icono en los botones nuevos.

En la lista, con el filtro en Todos, la ráfaga de 30 no llamó a `refrescar_lista` ninguna vez. El coste fue el de 30 retoques de fila más 30 escrituras. En las tarjetas, las 30 llamadas reconstruyeron la vista entera.

Un intento de espaciar 30 altas cada 60 ms solo se cumplió en la lista, donde no hay reconstrucción: llegaron en unos 2,1 s, en 18 pasadas, casi siempre de dos en dos. En las tarjetas cada reconstrucción ocupaba el hilo de la interfaz más de 60 ms, los `after` se retrasaron y el reloj acabó sumando las 30 reconstrucciones. En el programa de verdad los hilos de red sí pueden encolar mientras la interfaz pinta: la cola es thread-safe y no toca widgets. Esos ítems entran en el mismo `while` y cada uno sigue llamando a `refrescar_lista`. El número de reconstrucciones sigue siendo el de resultados. La prueba que lo muestra sin ese retraso es la ráfaga instantánea: 30 ítems ya encolados, una pasada, 30 reconstrucciones.

## Números

Widgets bajo la lista, contando `winfo_children` de forma recursiva. Una fila son 31 widgets: 4 `CTkFrame`, 5 `CTkLabel`, 4 `CTkButton`, 9 `CTkCanvas` y 9 `Label` internos de CustomTkinter. La rejilla suma 1. Cincuenta filas son 1551 widgets; 100 filas, 3101; 120 filas, 3721. El resto de la ventana son unos 107 widgets y no crece con la lista.

Una tarjeta ronda los 27 widgets. Seis tarjetas (Sin categoría más 5) son 157. Veintiuna son 562. Cincuenta y una son 1372. El número de enlaces, de 50 a 1000, no cambió ese conteo.

### Vista de tarjetas

El tiempo depende de cuántas tarjetas hay, no de cuántos enlaces guardan.

| Tarjetas (incluida Sin categoría) | Tiempo de pintado | Widgets |
| --- | --- | --- |
| 6 | 0,39–0,44 s | 157 |
| 21 | 1,28–1,46 s | 562 |
| 51 | 3,19–3,44 s | 1372 |

Un resultado de verificación en esta vista tarda lo mismo que ese pintado, porque llama a `refrescar_lista` una vez. Con 1000 enlaces y 50 categorías, un solo resultado tardó 3,44 s, de los cuales el guardado fueron 8 ms.

### Todos los enlaces, entrar y borrar

| Enlaces visibles | Todos los enlaces | Borrar uno | Una tecla del buscador (siguen todos) | Widgets tras pintar |
| --- | --- | --- | --- | --- |
| 50 | 4,2–4,6 s | 4,1–4,3 s | 4,2–4,4 s | 1551 |
| 100 | 8,4–9,5 s | 9,7–10,3 s | 8,7–9,7 s | 3101 |
| 120 | 11,4 s | 12,0 s | 11,8 s | 3721 |

El buscador y el borrado reconstruyen la lista entera. El guardado de un borrado, con 100 enlaces, fue de unos 2 ms: el tiempo es de crear widgets.

Entrar en una categoría cuesta según los enlaces de esa categoría, con los mismos 31 widgets por fila. Diez enlaces: 1,02 s. Veinte: 1,99 s. Veinticuatro: 2,81 s. Una categoría de un solo enlace: 0,23 s.

Con 100 enlaces, después de marcar 30 como activos, filtrar por Pendiente reconstruyó unas 68 filas en 6,7 s. Un resultado que salía de ese filtro reconstruyó otra vez, en 6,4 s. El atajo parcial no se usa cuando la fila entra o sale del filtro.

### Un resultado en la lista, y una ráfaga de 30

En Todos los enlaces, con el filtro en Todos, un resultado tarda 22–27 ms y no llama a `refrescar_lista`. Treinta resultados ya encolados tardan 0,56–0,67 s, con 0 reconstrucciones. Las 30 escrituras del JSON suman 18–48 ms según el tamaño. Repartidos en unos 2,1 s siguen siendo 0 reconstrucciones, en 18 pasadas de la cola.

En tarjetas, treinta resultados ya encolados:

| Tarjetas | Tiempo de la ráfaga | Reconstrucciones | Mediana de cada una | Las 30 escrituras a disco |
| --- | --- | --- | --- | --- |
| 6 | 11,3–12,6 s | 30 | 0,37–0,41 s | 20–230 ms |
| 21 | 38,5–43,0 s | 30 | 1,27–1,46 s | 24–245 ms |
| 51 | 96–108 s | 30 | 3,16–3,58 s | 26–260 ms |

El extremo de 108 s es 1000 enlaces y 50 categorías: mediana 3,55 s por reconstrucción, y 260 ms de disco en total. El parpadeo es el de las 30 reconstrucciones. El disco, con un JSON de unos 380 KB, no explica ese tiempo.

### Lo que no se pudo pintar

Todos los enlaces con 140, 150 y 200 filas terminó en `BadAlloc` de X al crear pixmaps (`X_CreatePixmap`). Ciento veinte filas sí se crearon. En esta sesión el muro está entre 120 y 140 filas, con la aplicación real también abierta. Por eso no hay un tiempo medido de borrar o de pintar 200, 500 ni 1000 filas.

La proyección, a partir de unos 84 ms por fila entre 50 y 100, y unos 95 ms por fila a 120, sería del orden de 17–19 s para 200 filas, 42–48 s para 500 y 84–95 s para 1000. Es una proyección, no una medida. El fallo de pixmap indica que crear todas las filas puede no llegar a terminar en un servidor gráfico modesto.

Las tarjetas sí se midieron con 200, 500 y 1000 enlaces. El pintado no creció con los enlaces: 1000 enlaces y 6 tarjetas siguieron en 0,42 s.

## Alternativas

### (a) Actualizar la fila o la tarjeta, y dejar el diccionario que ya existe

`_filas` ya evita la reconstrucción cuando un resultado no cambia de filtro. Falta usarlo al borrar, añadir, editar y abrir, y guardar también el widget de la marca de visitado. En tarjetas hace falta un diccionario del nombre de la categoría al resumen, no un índice de la rejilla.

Mejora esperada: borrar, en la medida de 100 filas, bajaría de unos 10 s hacia el coste de una fila. Un resultado en tarjetas bajaría de 0,4–3,5 s a un cambio de etiqueta. La ráfaga de 30 en 50 categorías dejaría de ser 30 veces 3,5 s.

Riesgo: al quitar una fila en una rejilla de dos columnas hay que reacomodar las siguientes. El scroll, el foco y el recorte con puntos suspensivos hay que conservarlos. Si el filtro o la búsqueda cambian muchas filas a la vez, insertar y quitar de una en una puede no salir más barato que reconstruir; ese caso sigue cubierto por la espera del apartado (b).

Scroll: se puede dejar la fracción, o mejor la posición en píxeles de las filas que siguen. El arreglo de la Fase 7C (aplicar la fracción después de recalcular la región) sigue haciendo falta si aún se reconstruye.

Filtros: un enlace que entra o sale se inserta o se quita. Un cambio de filtro que altera casi toda la lista puede seguir reconstruyendo.

Columnas de la Fase 7C: un cambio de número de columnas sigue justificando `refrescar_lista`. La actualización parcial no puede suponer que siempre hay una columna. En esta ventana había una.

Animación de carga: hoy cada resultado en tarjetas destruye el botón que gira. Actualizar el resumen deja ese botón vivo.

Windows y Debian: es el mismo Tk. No hay API de un solo sistema. El fallo de pixmap visto aquí es de esta sesión Xwayland; el coste de crear los widgets se pagaría igual en Windows.

### (b) Agrupar repintados y guardados cada 100–200 ms

En `_recoger_resultados`, marcar la vista como sucia y pintar una vez al cerrar la pasada, o como mucho cada 150 ms, que es la espera que ya usa el redimensionado. El JSON se escribiría una vez por tanda, no una vez por resultado. La misma espera en `<KeyRelease>` del buscador.

Mejora esperada: 30 resultados ya encolados pasarían de 30 reconstrucciones a 1. Con 50 categorías, la ráfaga bajaría de unos 108 s a unos 3,5 s (un pintado). En la lista, donde ya no hay reconstrucción, el efecto visible es pequeño (la tanda ya cabe en 0,6 s); el efecto claro es pasar de 30 escrituras a 1. Una palabra de varias letras dejaría de reconstruir en cada tecla. Con 100 enlaces, cada tecla cuesta hoy unos 9 s.

Riesgo: la lista puede ir hasta 200 ms por detrás del último resultado. La barra de progreso y el contador pueden seguir actualizándose en cada pasada: son baratos y no reconstruyen la lista. Si el pintado agrupado tarda 3,5 s, el usuario ve un parón único, no treinta parpadeos. No hace rápida la primera apertura de Todos los enlaces.

Scroll, filtros y columnas: una sola reconstrucción al final, con la lógica actual. La animación sobrevive si esa reconstrucción no llega a hacerse porque la fila o la tarjeta se actualizaron en el sitio.

Windows y Debian: `after` se comporta igual. La espera de 150 ms ya está en el código del redimensionado.

### (c) Paginación

Mejora esperada: la primera pintura crearía una página, no las 500 filas. Con el coste actual, una página de 50 filas seguiría rondando los 4 s, y una de 20 rondaría 1,7 s. Ayuda a no chocar con el pixmap de 1000 filas. No deja la apertura por debajo de un segundo salvo que la página sea de muy pocas filas.

Riesgo: la ventana pasa de un scroll continuo a páginas. El lugar por donde iba el usuario, los filtros y la Fase 7C cambian de significado. Hay que decidir qué pasa al añadir un enlace que cae en otra página.

Animación de carga: no depende de la página. Windows y Debian: sin API distinta.

Coste de implementación medio, y el resultado sigue caro por fila.

### (d) Lista virtualizada, solo con las filas visibles

Mejora esperada: abrir Todos los enlaces con 500 o 1000 enlaces costaría lo de las filas que caben en la pantalla, no lo de todas. El número de widgets dejaría de ser 31 por enlace. Es lo que evita el `BadAlloc` al crecer la colección. El scroll recicla filas.

Riesgo alto. `CTkScrollableFrame` no virtualiza. Hay que mantener el alto total, la fila de altura variable (notas y fecha), el reciclaje al hacer scroll, el doble clic, el foco y el recorte. La Fase 7C midió que en Linux el canvas avanza de 30 en 30 px y en Windows de 1 en 1: el reciclaje tiene que usar la posición real, no un paso fijo. Un cambio de columnas reubica las filas visibles.

Filtros: se reconstruye el modelo de filas visibles, no todos los widgets. La animación de las tarjetas no entra aquí. Windows y Debian pueden compartir la lógica si la posición sale del canvas.

Coste alto. Es la fase que ataca la primera pintura y el tope de pixmaps. No es el cambio más barato.

### (e) ttk.Treeview u otro widget denso

Mejora esperada: un árbol nativo aguanta miles de filas y las pinta mucho más rápido que 31 widgets de CustomTkinter por enlace.

Riesgo: se pierde la fila actual (punto de color, iconos, Editar, Abrir, Copiar, Eliminar, notas, fecha con puntos suspensivos). El tema claro u oscuro no coincide entre Windows y Debian. Las columnas de la Fase 7C son una rejilla que salta de una a dos columnas, no columnas de una tabla. La vista de tarjetas no cabe en un Treeview, así que habría dos sistemas de widgets. La animación de carga de las tarjetas no se traslada.

Coste alto en aspecto, menor que escribir un scroll virtual si se acepta otra vista. Queda como reserva si la virtualización de la fila actual no sale.

## Orden recomendado

La optimización no debe guardar el índice de la rejilla como identidad de una fila o de una tarjeta. La fila sigue el `id` del enlace. La tarjeta sigue el nombre de la categoría. Así un `padre` futuro puede cambiar qué tarjetas se muestran sin rehacer el diccionario de otra forma.

1. Agrupar el repintado y el guardado de la cola, y poner al buscador la espera de 150 ms que ya tiene el redimensionado. Es el cambio pequeño de más efecto: la ráfaga de las tarjetas deja de multiplicar el pintado por 30, y cada tecla deja de reconstruir.
2. Actualización parcial de la fila y del resumen de la tarjeta. Cubre borrar, añadir, editar, abrir y el resultado en tarjetas.
3. Virtualizar la lista de enlaces. Entra cuando abrir Todos los enlaces siga costando lo de todas las filas. La paginación es el recambio si la virtualización se atasca, sabiendo que una página grande sigue siendo cara con la fila actual. Treeview queda detrás de las dos, porque cambia la vista.

Criterios para dar por buena cada fase:

- Tras la fase 1: 30 resultados ya en la cola provocan una llamada a `refrescar_lista` en tarjetas, no 30, y una llamada a `guardar_enlaces`, no 30. En la lista, si las filas siguen visibles, siguen siendo cero reconstrucciones, y el guardado también es uno. Con 50 categorías, la ráfaga tiene que quedar en el tiempo de un pintado (unos 3,5 s medidos hoy), no en unos 108 s. Ocho teclas seguidas en el buscador provocan un pintado, no ocho.
- Tras la fase 2: borrar un enlace con 100 enlaces en pantalla queda por debajo de 50 ms. El objetivo original, 500 enlaces, es el mismo: el tiempo no debe crecer con el número de filas. Aquí no se pudo crear la lista de 500. Un resultado en tarjetas no llama a `refrescar_lista`. Abrir un enlace tampoco.
- Tras la fase 3: abrir Todos los enlaces con 500 enlaces en el modelo cuesta lo de las filas visibles (con la fila actual, del orden de 1 s), no la proyección de unos 40 s de las 500. Los widgets de la lista se quedan en esas filas, no en 31 por enlace, y la ventana no depende de poder crear un pixmap por cada enlace de la colección.

## Categorías anidadas (pendiente, posible)

Es una idea opcional. Puede que no se haga. No forma parte de esta fase ni de las tres fases de arriba.

Hoy el documento es la versión 2: `categorias` es una lista plana de `nombre` y `fecha_creacion`. Cada enlace guarda `categoria` como texto, y el texto vacío es Sin categoría. Sin categoría no tiene ficha.

Si algún día se anidan, el cambio de formato más cómodo con el código actual es subir a la versión 3 y añadir `padre` en cada ficha. El texto vacío significa que cuelga de la raíz. El enlace sigue guardando el nombre de su categoría, que sería la hoja donde vive. Un árbol JSON con `hijos` dentro de cada categoría obliga a reescribir el recorrido, el renombrado y el CSV para el mismo resultado.

Ejemplo de la forma plana:

```json
{
  "version": 3,
  "categorias": [
    {"nombre": "Trabajo", "padre": "", "fecha_creacion": "2026-10-20T00:00:00+00:00"},
    {"nombre": "Informes", "padre": "Trabajo", "fecha_creacion": "2026-10-20T00:00:00+00:00"}
  ],
  "enlaces": []
}
```

Al cargar un documento versión 2 se le añadiría `padre` vacío y se guardaría como versión 3. Hasta ese guardado, el lector puede tratar la ausencia de `padre` como raíz, para no romper un archivo a medias. Hay que rechazar ciclos, un padre que no existe, y que Sin categoría tenga padre o hijos. Renombrar un padre tiene que actualizar el `padre` de las hijas, igual que hoy se actualiza `categoria` en los enlaces. La comparación sigue sin distinguir mayúsculas.

En la interfaz, cada nivel mostraría sus tarjetas, no el árbol entero desplegado: 50 tarjetas ya cuestan 3,4 s. Harían falta migas de pan para bajar y subir. Mover un enlace es el cambio de categoría que ya existe. Mover una categoría es cambiar `padre`. Conviene no mostrar a la vez tarjetas anidadas dentro de tarjetas si eso multiplica los widgets que esta medición acaba de contar.

En el CSV haría falta una columna `padre`, opcional. Vacía significa raíz. Al importar, un padre que no existe se crea, como hoy se crea la categoría que falta. Exportar escribiría esa columna. Un nombre repetido en dos ramas no cabe en el modelo actual, que identifica la categoría solo por el nombre: o los nombres siguen siendo únicos en todo el árbol, o más adelante el enlace tendría que guardar el camino. La opción que no cierra la puerta, y no complica la versión 3, es mantener el nombre único.

Al borrar, el diálogo de hoy tiene dos destinos para los enlaces: Sin categoría, o borrarlos con la categoría. Con hijas haría falta un tercero explícito: subir las hijas al padre, pasarlas a Sin categoría, o borrar el subárbol. No debería haber un borrado en cascada silencioso.

La optimización de las fases anteriores deja esa puerta abierta si la fila se busca por el enlace y la tarjeta por el nombre, y si el repintado agrupado vuelve a mirar qué tarjetas están a la vista en lugar de guardar el índice de la rejilla.

## Commit sugerido

No ejecutado:

```bash
git add docs/INVESTIGACION-RENDIMIENTO.md
git commit -m "$(cat <<'EOF'
Phase 13: research UI performance

EOF
)"
```
