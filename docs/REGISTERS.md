# Referencia HTTP / Modbus — ISS 0.4.0

Mapa de referencia: API 102, web 6.1.0, HwType ABH0101. Las direcciones HR son
**desde cero**, como las utilizadas por el portal; no se añade 40001.

La integración utiliza HTTP para lecturas y escrituras. Esta tabla documenta la
correspondencia Modbus; no significa que el componente incluya un cliente Modbus.
En la instalación de referencia, las escrituras HTTP aplican los parámetros EMS
probados; algunas escrituras Modbus solo actualizan el valor almacenado.
No se ha identificado ni se presupone un registro Modbus universal de aplicación.

## Controles

| Entidad | Clave estable | Plataforma | Registro | startbit HTTP |
|---|---|---|---|---|
| Corriente máxima de carga BMS | `bms_max_charge_current` | number | HR86 | 0 |
| Corriente máxima de descarga BMS en On-Grid | `bms_max_on_grid_discharge_current` | number | HR142 | 0 |
| Potencia máxima de carga desde red o generador | `max_grid_charge_power` | number | HR128 | 0 |
| Potencia máxima de excedente FV a red | `max_surplus_grid_power` | number | HR129 | 0 |
| Potencia máxima de batería a red | `max_battery_grid_injection_power` | number | HR58 | 0 |
| SOC máximo | `soc_max` | number | HR123 | 0 |
| SOC de recuperación | `soc_recovery` | number | HR130 | 0 |
| SOC mínimo | `soc_min` | number | HR125 | 0 |
| SOC Descx | `soc_descx` | number | HR126 | 0 |
| SOC Recx | `soc_recx` | number | HR127 | 0 |
| SOC de carga desde red 1 | `soc_grid_1` | number | HR119 | 0 |
| SOC de carga desde red 2 | `soc_grid_2` | number | HR63 | 0 |
| SOC mínimo de descarga programada 1 | `soc_discharge_1` | number | HR59 | 0 |
| SOC mínimo de descarga programada 2 | `soc_discharge_2` | number | HR60 | 0 |
| Calibración del SOC cuando lo necesita el BMS | `bms_soc_calibration` | switch | HR132 | 0 |
| Priorizar inyección a red antes que batería | `prioritize_grid_export` | switch | HR132 | 12 |
| Peak shaving | `peak_shaving` | switch | HR132 | 14 |
| Uso de batería programado 1 | `schedule_1_battery_use` | select | HR133 | 11 |
| Uso de batería programado 2 | `schedule_2_battery_use` | select | HR133 | 12 |
| Modo de carga desde red 1 | `grid_charge_schedule_1_mode` | select | HR100 | 5 |
| Modo de carga desde red 2 | `grid_charge_schedule_2_mode` | select | HR133 | 1 |
| Modo de descarga de batería 1 | `battery_discharge_schedule_1_mode` | select | HR100 | 10 |
| Modo de descarga de batería 2 | `battery_discharge_schedule_2_mode` | select | HR100 | 12 |
| Inicio de carga desde red 1 | `grid_charge_schedule_1_start` | time | HR117 | 0=minuto, 8=hora |
| Fin de carga desde red 1 | `grid_charge_schedule_1_end` | time | HR118 | 0=minuto, 8=hora |
| Inicio de carga desde red 2 | `grid_charge_schedule_2_start` | time | HR61 | 0=minuto, 8=hora |
| Fin de carga desde red 2 | `grid_charge_schedule_2_end` | time | HR62 | 0=minuto, 8=hora |
| Inicio de descarga de batería 1 | `battery_discharge_schedule_1_start` | time | HR120 | 0=minuto, 8=hora |
| Fin de descarga de batería 1 | `battery_discharge_schedule_1_end` | time | HR121 | 0=minuto, 8=hora |
| Inicio de descarga de batería 2 | `battery_discharge_schedule_2_start` | time | HR64 | 0=minuto, 8=hora |
| Fin de descarga de batería 2 | `battery_discharge_schedule_2_end` | time | HR65 | 0=minuto, 8=hora |

Los dos controles de corriente BMS usan enteros de 0–66 A (escala 1 A).
HR132 bit 0 es un permiso booleano de calibración cuando la solicita el BMS.
No equivale a una orden instantánea de recalibrado.

Los modos de carga/descarga son campos de 2 bits: 0 desactivado, 1 toda la
semana, 2 lunes a viernes, 3 sábado y domingo. Los selectores de uso de batería
son de 1 bit: 0 autoconsumo, 1 inyección a red. En un horario, el byte bajo es
el minuto y el alto la hora; el valor Modbus bruto es `hora * 256 + minuto`.
Para Modbus, cualquier escritura de un registro compartido debe preservar sus
otros bits. El `startbit` de la API identifica el campo ya decodificado.

## Peticiones HTTP

Autenticación HTTP Basic con las credenciales configuradas. Nodo configurable,
por defecto 1. No se necesita un servicio intermedio ni MQTT.

- `GET /system/info/device`: identificación de la tarjeta de comunicación.
- `GET /system/events/sse/stream`: telemetría rápida; evento `/ems/sse/phases`.
- `POST /inverter/holding/read/{id}`: ajustes.
- `POST /inverter/online/read/{id}`: FV1, FV2 y corriente de batería.
- `POST /inverter/holding/write/{id}`: escritura de los campos seleccionados.

El cuerpo POST es texto JSON con cabecera
`Content-Type: application/x-www-form-urlencoded`, como en el portal observado.
Ejemplo de lectura de los dos límites BMS:

```json
[{"address":86,"length":1},{"address":142,"length":1}]
```

Ejemplo ilustrativo de escritura de un límite (el valor es un ejemplo, no una
recomendación para una instalación):

```json
{
  "Values":[{"address":86,"startbit":0,"value":20}],
  "metadata":{"user":"USUARIO_CONFIGURADO","host":"home-assistant"}
}
```

Para el permiso BMS se usa `address:132`, `startbit:0`, `value:0` o `1`.
Una hora envía dos elementos `Values` con la misma dirección y startbit 0 y 8.
No se demuestra atomicidad interna por agrupar ambos campos en una petición.
La confirmación es una lista `result` con `success:true`. Después se releen y
comparan los campos; un resultado distinto genera error y se muestra el valor
recibido, sin asumir el solicitado. Una confirmación de valor almacenado no
certifica por sí sola la respuesta física del equipo.

## Sensores

La tabla siguiente conserva la referencia de las direcciones online. En 0.4.0
solo se leen por este endpoint las direcciones 18 y 33–36. Los demás sensores
usan el [modelo SSE documentado](TELEMETRY_ENERGY.md), preservando sus claves.
La antigua suma FV1 + FV2 deja de ser el origen del sensor FV total: ahora es `pv`.

Las direcciones siguientes pertenecen a la vista **online**, no a los holding
registers. No debe trasladarse automáticamente la misma dirección a HR.

| Sensor | Dirección online | Conversión |
|---|---|---|
| SOC batería | 20 | Valor directo, % |
| Potencia batería | 19 | Valor directo, W |
| Tensión batería | 17 | Valor / 10, V |
| Corriente batería | 18 | Valor / 100, A |
| Potencia FV1 | 33 | Valor directo, W |
| Potencia FV2 | 36 | Valor directo, W |
| Potencia FV total | 33 + 36 | Suma de ambos valores, W |
| Potencia red | 71 | Valor directo, W |
| Potencia de cargas totales | 78 | Valor directo, W |

Esta conversión solo se refiere al endpoint online. En `/properties/read/{id}`,
los campos `Vbatt`, `Ibatt`, `Pdc1` y `Pdc2` de la respuesta aportada ya están
decodificados; no se dividen otra vez por la escala. La respuesta de propiedades
sirve como evidencia del mapa, no sustituye al endpoint online en esta versión.

Las lecturas se identifican por dirección y `startbit`, nunca por `Data[n]`.
Se descartan los campos inconsistentes o con `success: false`. No se usa
`PacGrid` como intercambio con la red pública; la magnitud SSE elegida es `W`.
