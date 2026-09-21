# Telemetría SSE y modelo energético — 0.4.0

Esta especificación sustituye las hipótesis preliminares por las capturas reales
aportadas durante el desarrollo. Los nombres de MQTT no se reutilizan como
identificadores de la integración.

## Protocolo

- Endpoint local: `GET /system/events/sse/stream`.
- Autenticación: HTTP Basic del usuario de la integración.
- Cabecera: `Accept: text/event-stream`.
- Evento: `/ems/sse/phases`, objeto JSON con lista `Phases`.
- Se selecciona exactamente un agregado con `Phase = 4`. No se suman el
  agregado y las fases individuales; un agregado duplicado se rechaza.
- `/ems/sse/stream` también transporta dispositivos y resúmenes; no se mezcla
  con el evento elegido.
- Lectura por eventos completos, no por fragmentos TCP ni recortes de texto:
  UTF-8 fragmentado, BOM, LF/CRLF/CR, comentarios y múltiples líneas `data:`.
- Límite de tamaño 256 Ki caracteres por evento. Tramas excesivas o UTF-8
  inválido cierran la conexión y activan la reconexión.
- JSON corrupto o sin magnitudes principales válidas no renueva el watchdog.
  No se aceptan booleanos, cadenas, NaN o infinitos como medidas.
- Datos parciales válidos actualizan los campos presentes e invalidan los
  ausentes. No se arrastran campos de una muestra anterior.
- No se solicita reproducción histórica con Last-Event-ID: la fuente de
  energía requiere muestras de tiempo real, no reenvíos potencialmente antiguos.

El alcance es un inversor y un agregado de instalación por tarjeta. La petición
SSE no contiene el ID Modbus: no se anuncia selección de un inversor individual
dentro de una planta de varios nodos.

## Correspondencia de los acumuladores

| Clave estable de energía | Potencia de origen | Unidad final |
|---|---|---|
| `pv_energy` | `pv` | kWh |
| `load_energy` | `cons` | kWh |
| `grid_import_energy` | `max(W, 0)` | kWh |
| `grid_export_energy` | `max(-W, 0)` | kWh |
| `battery_charge_energy` | `PacCharge` | kWh |
| `battery_discharge_energy` | `PacDischarge` | kWh |

Las claves se combinan con el identificador de tarjeta ya utilizado. No se
cambian las claves de los sensores existentes. Cuatro potencias direccionales
nuevas hacen visibles las fuentes del cálculo; no se crean todos los flujos
internos como entidades adicionales.

## Escenarios de referencia

| Escenario | FV | Vivienda | Importación | Exportación | Carga batería | Descarga batería |
|---|---:|---:|---:|---:|---:|---:|
| FV cargando batería | 4739 | 3052 | 12 | 0 | 1699 | 0 |
| Carga FV + red | 4649 | 3062 | 3600 | 0 | 5065 | 0 |
| FV + batería inyectando a red | 4452 | 3103 | 0 | 2864 | 0 | 1510 |
| Batería y FV para vivienda | 1667 | 4048 | 21 | 0 | 0 | 2275 |
| Sin FV y batería desconectada | 0 | 1015 | 1015 | 0 | No disponible | No disponible |

Potencias en W. Los JSON completos están en `tests/fixtures/scenarios.json`.

Conclusiones que las pruebas protegen:

1. `_grid_cons` no es toda la importación: no basta para contabilizar carga
   desde red. En la muestra es 3062 W y `W` es 3600 W.
2. `_pv_grid` no es toda la exportación: faltaría la batería. En la muestra
   1349 + 1515 = 2864 W, coincidiendo con `-W`.
3. `total_cons` no sustituye a `cons`. En carga desde red, 3478 frente a
   3062 W; no son la misma magnitud.
4. `pv` y `pv_total_value` no siempre coinciden: se usa `pv` para conservar
   el origen del sistema MQTT de referencia, no una equivalencia demostrada
   con FV1 + FV2.
5. `PacDischarge` tampoco equivale exactamente a `_sto_cons + _sto_grid`
   en todas las muestras. Las discrepancias quedan visibles, sin corregirlas.
6. `StatusBat = 7` invalida las medidas de batería. No invalida vivienda/red/FV
   ni la lectura de los ajustes almacenados.

No se atribuyen las diferencias a pérdidas, redondeo o asincronía como causa
demostrada. Para evaluar la precisión final hace falta comparar intervalos
equivalentes en la instalación física.

## Regla temporal

Para dos recepciones consecutivas válidas, se añade:

`ΔE [kWh] = P_anterior [W] × Δt [s] / 3 600 000`

Cada canal tiene su propia pareja de muestras. La primera muestra inicializa
el punto temporal pero no suma energía. La segunda permite integrar la primera.
Potencias constantes siguen sumando porque se procesan todas las recepciones,
aunque el valor no cambie.

Se acepta `0 < Δt ≤ 5 s`. Para un hueco mayor se descarta el intervalo completo
y se toma el dato nuevo como nuevo punto de partida. El mismo principio se
aplica a datos inválidos, desconexión y recarga/reinicio. El tiempo es monotónico
del host; la fecha UTC de diagnóstico no interviene en la integral.

No hay temporizador que extienda una última potencia por 30 s hasta el
watchdog. Los 30 s controlan la disponibilidad visual del SSE; los 5 s son un
límite distinto para el cálculo conservador de energía.

## Persistencia y presentación

Los seis totales comparten un almacén versionado por entrada de configuración.
Se restaura el total, nunca el momento de la muestra anterior. Guardado atómico
periódico mientras cambian los totales y al detener/recargar normalmente.

Los cálculos mantienen precisión completa. El estado publicado usa seis
decimales y la precisión de presentación sugerida es tres. Los acumuladores
usan `state_class: total` sin `last_reset` porque son totales de vida útil que
no se reinician por calendario. Son compatibles con estadísticas de energía.
El cálculo usa cada evento, pero los estados de energía se publican cada 30 s
mientras llegan datos y al interrumpirse el SSE. Esto limita el tráfico de
Recorder sin reducir la frecuencia de las muestras de la integral.

No se ofrecen funciones de reinicio, importación de historial ni compensaciones
manuales en esta versión. Los valores se conservan aunque el sensor de potencia
quede no disponible. Por ello un total inmóvil no garantiza conexión:
para automatizaciones de disponibilidad se usa el diagnóstico SSE.

## Referencias

- [Documentación SSE de Ingeteam aportada por el usuario](https://www.ingeras.es/archive/protocols/AAA0060/IMB05/AAA0060IMB05_A.pdf).
- [Actualización por push y coordinadores de Home Assistant](https://developers.home-assistant.io/docs/integration_fetching_data/).
- [Clases de estado de sensores](https://developers.home-assistant.io/docs/core/entity/sensor/).
- [Integración numérica de potencia](https://www.home-assistant.io/integrations/integration/).
