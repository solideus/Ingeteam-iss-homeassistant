# 0.5.3 — Correcciones de balance horario y robustez

## Actualización

Actualizar desde HACS y reiniciar Home Assistant conservando la integración.
Se mantienen los identificadores, unidades, horarios, ajustes, acumulados y
almacén energético. No es necesario volver a configurar el panel de Energía.
Guardar una copia de seguridad antes de actualizar permite restaurar también
los datos persistidos si fuese necesario volver a una versión anterior.

Esta versión corrige las futuras publicaciones; no desplaza automáticamente las
estadísticas antiguas que ya quedaron asignadas a la hora siguiente.

## Cierre neto a HH:59:55

La publicación a HH:00:00 de 0.5.0–0.5.2 hacía que el incremento neto quedase
fechado en la siguiente hora estadística. Desde 0.5.3, los periodos de 60 minutos
cierran cinco segundos antes de la hora, como el comportamiento de referencia.
Por ejemplo, el incremento publicado a 12:59:55 queda en la hora 12:00–13:00.

Un temporizador UTC dedicado cierra y publica el saldo observado aunque no
llegue una muestra SSE en ese instante. Las muestras también pueden provocar
el cierre al cruzar el corte. Ambos caminos comparten la identidad de periodo,
evitando liquidaciones duplicadas. El temporizador se cancela al descargar.
Los cierres no esperan al límite de publicación de energía de 30 s ni a las
frecuencias configurables de 5, 10 o 30 s. Las potencias conservan su frecuencia.

Los últimos cinco segundos alimentan el siguiente balance. Un intervalo válido
que llegue después de cerrar también se conserva en el periodo abierto, sin
reabrir ni modificar un balance ya publicado. Por ello el orden de recepción y
temporizador puede mover ese intervalo en tránsito al periodo siguiente.
Se siguen descartando los huecos superiores a cinco segundos y no se extrapola
la última potencia durante una caída. El margen de publicación no garantiza
puntualidad si Home Assistant está detenido o su bucle de eventos está bloqueado.

Los días y meses de consumo siguen el calendario local real, no se adelantan
cinco segundos. Se mantienen las identidades UTC de las ventanas netas para
evitar duplicar la hora repetida del cambio de horario de Madrid. Continúa el
alcance de horas civiles para zonas con desfase UTC de horas enteras; no se
añade soporte de balance civil para zonas de media hora o cuarto de hora.

## Restauración y alarmas

Al arrancar se restauran los subtotales y las entidades los publican antes de
procesar cierres y reinicios pendientes. Así Recorder observa los incrementos
finales y los ceros explícitos en el orden correcto. No se restauran anclas de
potencia ni tiempo. Un cierre recuperado tras una parada se publica con la fecha
del reinicio: se conserva su incremento, pero no se reconstruye la hora histórica
durante la que Home Assistant estuvo apagado.

Una lectura parcial de alarmas conserva los códigos activos de categorías que
no se han podido volver a leer. Solo una lectura válida de la categoría puede
confirmar su desaparición y emitir el evento de desactivación. Las entidades
exponen `coverage_complete`, `missing_categories` y `stale_categories`; los
códigos conservados incluyen `stale: true`. Si no hay alarmas conocidas y falta
cobertura, el indicador/recuento queda no disponible en lugar de confirmar cero.

## Lecturas y configuración

Números, modos, bits y horarios requieren valores finitos, enteros y dentro del
rango correspondiente. No se aceptan índices negativos, fracciones truncadas,
booleanos o cadenas como ajustes leídos. Los registros afectados quedan no
disponibles; los controles válidos siguen actualizando.

Las respuestas de registros validan la lista `Data`, bloques, direcciones,
bits y valores. Los elementos defectuosos se aíslan y las estructuras generales
inválidas generan errores de API controlados. Un fallo de online no deshabilita
los controles cuya lectura holding es válida. Mapas de alarmas incompletos
conservan los códigos como no documentados sin bloquear los controles.

La construcción del cliente durante el alta queda dentro del bloque de gestión
de errores. Usuarios con `:` o credenciales fuera de Latin-1 vuelven al formulario
con `invalid_connection_settings`; el mensaje explica estas restricciones en
los ocho idiomas. Se conserva la resolución asíncrona de zona horaria de 0.5.1.

## Validación

Validación local completada: **142 pruebas superadas** en Home Assistant Core
**2026.3.0** y **2026.9.3**, con Python 3.14.9. Ruff (análisis y formato),
compilación Python y comprobación del paquete instalable correctos.

- Home Assistant Core real en las dos versiones de la matriz CI.
- Recorder real con SQLite: escritura de estados, compilación de estadísticas
  de cinco minutos y agregación horaria, para importación y exportación netas.
  El incremento queda en la hora de cierre y no vuelve a sumarse en la siguiente.
- Corte anticipado con las cuatro frecuencias, sin nuevas muestras SSE,
  repetición de temporizador y orden temporizador/SSE. Conservación de la energía
  observada y de las muestras en tránsito posteriores al corte.
- Recarga tras cambio de día y mes: estados restaurados, cierres y ceros;
  las sumas `total_increasing` incluyen el subtotal pendiente una sola vez.
- Lecturas parciales de alarmas, estados de cobertura y confirmación de borrado.
- Campos inválidos, respuestas y mapas incompletos; otros controles siguen vivos.
- Cuatro capturas SSE originales en `tests/fixtures/real_sse_captures.json`, además
  de los cinco escenarios sintéticos anteriores, identificados como tales.
- Regresiones de escrituras/relecturas, identidades, cambios de horario de Madrid,
  reconexión, precisión, persistencia, traducciones y privacidad del diagnóstico.

Las acciones de HACS y Hassfest y los resultados finales se enlazan en la release.
Las pruebas no sustituyen la comprobación prolongada en el inversor físico ni
convierten estos acumuladores calculados en contadores fiscales.
