# 0.5.2 — Optimización de sensores de energía

## Problema y solución

`IngeteamCalendarSensor` publicaba en cada notificación del coordinador,
omitiendo el límite de 30 s existente en `IngeteamEnergySensor`. Esto afectaba
especialmente al consumo diario/mensual y al balance de la hora actual.

Se elimina esa sobrescritura y se hereda el límite. Borrarla sin más podría
ocultar a Recorder el último incremento de un contador antes de su reinicio.
Por eso el cálculo de calendario conserva instantáneas del subtotal final y
del cero, además de los valores liquidados en cada cierre horario. El coordinador
entrega esas instantáneas en orden, después de terminar el cálculo, únicamente
a los sensores afectados. Un fallo al publicar no interrumpe la contabilidad.

Los avisos también se entregan desde el temporizador de mantenimiento existente,
aunque no lleguen muestras SSE. No se cambia ese temporizador, la fórmula de
integración, la recepción SSE, el límite de huecos válidos, la persistencia ni
la frecuencia de las potencias. No se añade ninguna tarea de temporización.

Los nueve sensores conservan identificadores, unidades, clases de estado y
precisión. El balance horario mantiene su signo y `measurement`; los otros ocho
mantienen `total_increasing`. El aviso final y el cero permiten conservar las
sumas estadísticas incluso cuando el nuevo subtotal iguala al del período anterior.

## Verificación

- La batería de pruebas usa Home Assistant real y un servidor HTTP/SSE sintético.
- Reloj simulado: 601 muestras en diez minutos, con publicaciones SSE configuradas
  a 0, 5, 10 y 30 s. Después de la muestra inicial hay 20 publicaciones por sensor
  de calendario; cada muestra sigue avanzando los acumuladores sin redondear.
- Comprobación de potencia en cada paso: conserva exactamente la cadencia elegida.
- Cierres de hora, día, mes y año, incluidos los dos cambios de horario de Madrid.
- Publicaciones finales y cero explícito en eventos de estado de Home Assistant,
  incluyendo subtotales idénticos antes/después del reinicio.
- Temporizador antes/después de SSE a medianoche; cierre sin muestras nuevas,
  con SSE conectado o desconectado, sin modificar las actualizaciones de potencia.
- Dos horas de importación/exportación y liquidación única de cada saldo.
- Desconexión, reconexión, recarga, restauración, identidad y atributos estadísticos.
- Regresión de resolución asíncrona de zona horaria: se mantiene `tzinfo`.
- Comparación adicional contra el código de la etiqueta v0.5.1: 86.412 estados
  internos y volcados de persistencia exactamente iguales en doce secuencias
  de dos horas, cruzando todos los límites anteriores y variando el orden del
  temporizador respecto a las muestras. No se copia ese código en la integración.

Ejecutar desde la raíz:

```sh
python -m pip install -r requirements-test.txt
ruff check custom_components tests scripts
python -m pytest -q
```

La matriz CI ejecuta Home Assistant Core 2026.3.0 y 2026.9.3, además de HACS y
Hassfest. Los resultados definitivos y los enlaces se incluyen en la release.

## Efecto esperado y actualización

A una muestra por segundo y con energía cambiante, las publicaciones habituales
pasan de 3.600 a unas 120 por hora y sensor: aproximadamente un 96,7 % menos,
más cierres y desconexiones. Los sensores con un valor constante ya podían evitar
filas nuevas en Recorder. El ahorro total en MariaDB, SQLite o PostgreSQL depende
del conjunto de entidades, filtros y retención configurados; esta validación mide
publicaciones, no el tamaño de una base de datos real.

Actualizar mediante HACS y reiniciar Home Assistant. Se conserva la entrada y
su historial. Esta versión no borra registros antiguos ni compacta la base de
datos. Las gráficas energéticas y las estadísticas de medición del balance horario
tienen menos puntos; las potencias para automatizaciones rápidas no cambian.

Se mantiene íntegra la corrección de zona horaria de 0.5.1 solicitada en
[hacs/default#11154](https://github.com/hacs/default/pull/11154): resolución con
`await dt_util.async_get_time_zone(...)` y paso del objeto `tzinfo` a la contabilidad.
No se crea `ZoneInfo` en el bucle de eventos.

Las limitaciones anteriores continúan: no se estima energía durante huecos sin
muestras válidas; un apagado abrupto puede perder lo ocurrido desde el último
guardado. Las pruebas automatizadas no sustituyen una prueba prolongada del
inversor físico ni convierten los sensores en contadores fiscales.
