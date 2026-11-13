# Validación en un INGECON SUN STORAGE 1Play real

Registro de las comprobaciones hechas con el perfil `storage_1play` en una
instalación real. Complementa a [STORAGE 1Play](STORAGE_1PLAY.md), donde se
describe el perfil, y a la [validación general](VALIDATION.md).

## Equipo y entorno

| Elemento | Valor |
|---|---|
| Inversor | INGECON SUN STORAGE 1Play **6TL**, generación TL sin M (1 MPPT), monofásico, con batería (Pylontech Force H1/H2 por BMS) |
| Cableado | Toda la vivienda conectada a la salida de cargas (*AC Loads*) del inversor |
| Tarjeta de comunicaciones | `HwType` AAX0077, `CommsVersion` ACO1200_A, `ApiVersion` 102 |
| Firmware de comunicaciones | AAX1055DC (fecha 2026-10-13) |
| Mapa del inversor | `compatible.firmware` = ABH1002AL |
| Modo de operación | *Self-Consumption managed by ISS1Play* (holding 122 = 3) |
| Normativa | RD+UNE206007 Insular (España) |
| Home Assistant | Core 2026.11.1, integración desde la rama del perfil 1Play |
| Usuario del portal | Usuario local dedicado a Home Assistant |
| Referencias | Mapa propio `/inverter/map/1` y documento Modbus ABH2010IMB02_K (*Input Registers*, rev. K) |

Fecha de las pruebas: 10 a 12 de noviembre de 2026.

## Método para los ajustes

Cada ajuste se probó por separado, siempre a través de la integración, con la
misma entidad y el mismo servicio que usaría un usuario:

1. Leer el valor actual.
2. Escribir un valor de prueba cercano, elegido para no alterar el
   funcionamiento: por ejemplo, un SOC de carga desde red del 1 % cuando la
   batería estaba por encima del 30 %.
3. Comprobar la confirmación del inversor y la relectura inmediata que hace
   la integración tras escribir.
4. Esperar al siguiente sondeo HTTP (unos 18 s) y comprobar que el inversor
   sigue devolviendo el valor de prueba.
5. Restaurar el valor original de la misma forma y repetir las
   comprobaciones 3 y 4.
6. En los bits del registro 132, comprobar que el otro bit expuesto no
   cambia.

Si una comprobación fallaba, la prueba se detenía antes de pasar al
siguiente ajuste. No falló ninguna.

**Alcance:** estas pruebas confirman que el inversor acepta el valor, lo
devuelve y lo conserva, y que se restaura igual. No demuestran todo su efecto
operativo; por ejemplo, no se esperó a que la batería llegara a un límite de
SOC. Por eso los controles están deshabilitados por defecto.

## Ajustes validados

| Entidad | Holding | Entrada del mapa | Rango | Original | Prueba | Resultado |
|---|---|---|---|---|---|---|
| `number.soc_max` | 123 | *SOCmax: Maximum charge limit of renewable source (%)* | 0–100 % | 95 | 95 → 96 → 95 | ✅ |
| `number.soc_grid` | 124 | *SOCgrid: Maximum charge limit from the grid/genset (%)* | 0–100 % | 0 | 0 → 1 → 0 | ✅ |
| `number.soc_min` | 125 | *SOCmin: Minimum limit for switching to standby (%)* | 0–100 % | 5 | 5 → 6 → 5 | ✅ |
| `number.max_grid_charge_power` | 128 | *Maximum battery charging power from the grid/genset (W)* | 0–6000 W | 3000 | 3000 → 2900 → 3000 | ✅ |
| `number.max_grid_injection_power` | 129 | *Maximum power injected to the grid (W)* | −6000–6000 W | 6000 | 6000 → 5900 → 6000 | ✅ |
| `number.bms_max_charge_current` | 116 | *Maximum Charge Current* (BMS) | 0–50 A | 50 | 50 → 49 → 50 | ✅ |
| `select.battery_charge_priority` | 132 bit 4 | *Battery Charging Priority* | `pv_then_grid` / `grid_only` | `pv_then_grid` | ida y vuelta | ✅ |
| `switch.battery_backup` | 132 bit 1 | *Battery-Backup Function: Mode* | on/off | on | on → off → on | ✅ |

Detalles de cada prueba:

- Todas las escrituras devolvieron HTTP 200 y confirmación del inversor. En
  todos los casos, la relectura inmediata y el sondeo siguiente dieron el
  valor de prueba, y después del original.
- Todos los campos tienen `sc` 1, sin escala.
- **Registro 132:** al cambiar la prioridad de carga, el backup siguió
  activado. Al desactivar el backup, la prioridad siguió en `pv_then_grid`.
  La API escribe por campo (`address` + `startbit`).
- **Permisos:** la prioridad de carga declara nivel de usuario 4 (`ur`/`uw`)
  en el mapa. El usuario dedicado pudo escribirla.
- **Igual que en el ISS:** SOCmax (123), SOCmin (125) y la potencia de carga
  desde red (128) tienen la misma dirección y el mismo significado. Los demás
  ajustes del 1Play están en otras direcciones.
- **Estado final:** el inversor quedó con todos sus valores originales.

## Ajustes excluidos a propósito

| Ajuste | Holding | Motivo |
|---|---|---|
| Modo de operación | 122 | Cambia el comportamiento completo del equipo |
| SOCdescx / SOCrecx | 126 / 127 | Umbrales de apagado y de vuelta a dar tensión: un error deja la vivienda sin suministro |
| Horario del generador | 100.2, 110–113 | Está activado (2:00–7:00), pero no se ha confirmado su efecto con el tipo de red *Grid* |
| Protecciones de red, normativa, país | 6–35, 36, 38… | Ajustes de instalador sujetos a normativa |
| Tipo de batería, parámetros de plomo-ácido | 78–93, 89 | Dependen del hardware instalado |
| Algoritmos de calidad de red (Pac/Qac/cos φ, LVRT/HVRT) | 13–16, 146–242 | Ajustes de instalador sujetos a normativa |
| Registros que el ISS usa para otros controles | 58, 59, 60, 63, 86, 119, 130… | En el 1Play significan otra cosa (umbral de una salida digital, tiempo de absorción, tiempo de parada por tensión mínima…) |

Las entidades que el perfil no crea, por ejemplo las de una entrada anterior
con el perfil TL M, no se eliminan: se conservan con sus personalizaciones,
sin ningún control detrás.

## Lecturas validadas

| Comprobación | Resultado |
|---|---|
| Telemetría SSE sin fase 4 | Decodificada; consumo y FV siguen a una lectura Modbus TCP independiente (Node-RED) |
| Energía de un día frente a Node-RED | Importación 13,90 / 14,21 kWh; carga de batería 6,40 / 6,55 kWh; descarga 2,40 / 2,46 kWh. La diferencia coincide con los reinicios de HA durante las pruebas |
| Escala de los registros online | `valor × sc / 100000` coincide con las unidades del documento ABH2010IMB02_K, por ejemplo tensión de batería 1958 → 195,8 V o frecuencia 5001 → 50,01 Hz |
| Correspondencia de direcciones | HTTP = registro Modbus − 30001 en todos los registros del mapa |
| Conectado a red | Bit 0 del estado del inversor (Modbus 30013); valor 11 = *On-grid* |

## Alarmas validadas

| Comprobación | Con las direcciones del ISS | Con el perfil 1Play |
|---|---|---|
| Alarmas activas | 17 falsas: leía estado, tensión de batería y frecuencia | 0 |
| Registros leídos | 12, 14, 28 (otro significado) | 10, 8, 9, 55, 47 |
| Cobertura | Incompleta | Completa: `inverter_alarm`, `inverter_code_1..3`, `battery_bms_alarm` |
| Códigos con descripción | — | 71, con las etiquetas del propio mapa |

Las etiquetas salen del mapa del inversor. En este firmware, la tabla en
español del mapa contiene los mismos textos en inglés.

El sensor binario *Reducción de potencia* se activa con el motivo 7
(*Self-consumption by ISS 1Play*), que es el funcionamiento normal en modo
autoconsumo. No es una avería.

## Pendiente

- Comparar la energía con series simultáneas frente a la lectura Modbus en
  cuatro escenarios (producción solar, descarga nocturna, carga desde red y
  exportación), con los intervalos alineados y los huecos marcados. La
  comparación diaria de arriba no basta para atribuir las diferencias a los
  reinicios.

- Ver una alarma real activarse y resolverse, para validar el evento
  `ingeteam_iss_alarm` de extremo a extremo. Hasta ahora no ha saltado
  ninguna.
- Instalaciones trifásicas del 1Play.
- Cualquier ajuste nuevo debe pasar por el mismo método antes de añadirse a
  `control_keys`.
