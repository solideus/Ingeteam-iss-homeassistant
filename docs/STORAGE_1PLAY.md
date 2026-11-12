# INGECON SUN STORAGE 1Play profile

Status: **experimental, monitoring only.** Reported in issue #7 and validated on
one installation (single-phase, with battery):

| Item | Value |
|---|---|
| Inverter | INGECON SUN STORAGE 1Play |
| Comms card | `HwType` AAX0077, `CommsVersion` ACO1200_A, `ApiVersion` 102 |
| Comms firmware | AAX1055DC (dated 2026-10-13; apparently a remote update) |
| Inverter map | `compatible.firmware` = **ABH1002AL** |
| Modbus document | ABH2010IMB02_K (rev. K, 19/02/2021), *Input Registers* |

## Why a separate profile

The 1Play map is a different, older generation from the ISS 6TL reference
(ABH1007AE). Many addresses exist in both maps with different meanings, so
**the ISS controls must never be used on a 1Play**. A few examples from the
maps:

- `pv_2_power` reads online 36, which on the 1Play is *Grid/Genset Frequency*
  (50.01 Hz → `5001`). Online 33 (`pv_1_power`) does not exist.
- ISS alarm addresses 12, 14 and 28 are *Inverter Status*, *Battery Voltage*
  and *AC Loads Frequency* on the 1Play, which produced 17 false alarms.
- Several holding addresses used by ISS controls are other settings on the
  1Play (digital output voltage threshold, absorption time, minimum-voltage
  stop time).

The profile therefore:

- loads `sensor`, `binary_sensor` and `number` only, and creates just the
  controls listed in its `control_keys` (see *Settings* below); it reads only
  those holding registers;
- removes, at setup, entities a previous ISS-profile entry left behind
  (controls and `pv_1_power`/`pv_2_power`);
- reads every online register the device map declares and decodes alarms and
  states with the labels of that map.

## Telemetry (SSE)

`/ems/sse/phases` only has phases 1–3 (no aggregate phase 4) and different
field names. Per event, summing phases 1–3:

| Value | Source |
|---|---|
| Grid power (+ import) | Σ `W` |
| PV power | Σ `PdcPVStorage` (equals `PacPV` of `/ems/sse/stream`) |
| Household load | Σ `PacPVBatt` + Σ `W` |
| Battery charge / discharge | Σ `PacCharge` / Σ `PacDischarge` |
| SOC / battery voltage | `EMS_SOC` / `EMS_VBAT` |

`/ems/sse/stream` provides `StatusBat` (battery status type of the map:
1 discharging, 2 constant-current charging, 7 not configured) and `StatusCode`
(3 with `"Status": "On-grid"`); they are merged into the next phase sample.
A missing value in any phase yields `None`, never zero.

Cross-checked against an independent Modbus TCP reading (Node-RED): load and
PV agree within the sampling offset (e.g. PV 2528 vs 2681 W, load 1501 vs
1465 W with passing clouds).

## Online registers

HTTP online address = Modbus input register − 30001. Value = raw × `sc` /
100000, where `sc` comes from the map (identical to the units of the Modbus
document).

| HTTP | Modbus | Entity | Scale |
|---|---|---|---|
| 6 | 30007 | Operating time (h) | ×1 |
| 8, 9, 55 | 30009, 30010, 30056 | Inverter codes 1–3 → alarms | bits |
| 10 | 30011 | Inverter alarms → alarms | bits (32-bit) |
| 12 | 30013 | Inverter state; bit 0 = connected to grid | enum/bits |
| 15 | 30016 | Battery current | /100 A |
| 18 | 30019 | Battery SOH | % |
| 19, 20 | 30020, 30021 | Battery max. charge/discharge current | /100 A |
| 21 | 30022 | Battery state | enum |
| 22 | 30023 | Battery temperature | /10 °C |
| 23–25 | 30024–30026 | PV voltage, current (/100), power | |
| 26–30 | 30027–30031 | AC loads voltage, current (/100), frequency (/100), power, reactive | |
| 34–38 | 30035–30039 | Grid voltage, current (/100), frequency (/100), active, reactive | |
| 39 | 30040 | DC bus voltage | V |
| 40–42 | 30041–30043 | Heatsink, electronics, PT100 temperature | /10 °C |
| 43, 44 | 30044, 30045 | Isolation resistance +/− | kΩ |
| 47 | 30048 | Battery BMS alarms → alarms | bits |
| 48 | 30049 | Residual current | mA |
| 52, 53 | 30053, 30054 | Battery charging/discharging voltage | /10 V |
| 54 | 30055 | Grid power factor | /1000 |
| 59 | 30060 | Power reduction reason (non-zero → binary sensor) | enum |
| 60 | 30061 | Power reduction ratio | /10 % |

Registers 30032–30034 (inverter cos φ, active and reactive power) are in the
Modbus document but not in the HTTP map, so they are not read.

## Settings

| Holding | Map entry | Entity | Range | Validation |
|---|---|---|---|---|
| 123 | *SOCmax: Maximum charge limit of renewable source (%)* | `number` `soc_max` | 0–100 % | 95 → 96 → 95 |
| 124 | *SOCgrid: Maximum charge limit from the grid/genset (%)* | `number` `soc_grid` | 0–100 % | 0 → 1 → 0 |
| 125 | *SOCmin: Minimum limit for switching to standby (%)* | `number` `soc_min` | 0–100 % | 5 → 6 → 5 |
| 128 | *Maximum battery charging power from the grid/genset (W)* | `number` `max_grid_charge_power` | 0–6000 W | 3000 → 2900 → 3000 |
| 129 | *Maximum power injected to the grid (W)* | `number` `max_grid_injection_power` | −6000–6000 W | 6000 → 5900 → 6000 |
| 116 | *Maximum Charge Current* (BMS) | `number` `bms_max_charge_current` | 0–50 A | 50 → 49 → 50 |
| 132 bit 4 | *Battery Charging Priority* | `select` `battery_charge_priority` | PV then grid / grid only | there and back |
| 132 bit 1 | *Battery-Backup Function: Mode* | `switch` `battery_backup` | on/off | on → off → on |

All entries have `sc` 1 and the range shown in the map. Each was validated on
a real 1Play through the integration: the write was confirmed, the immediate
readback and the next poll returned the new value, and the original value
was restored the same way. While a bit of register 132 changed, the other
exposed bit did not. SOCmax, SOCmin and the grid charging power use the same
addresses and meanings as the ISS; the other settings live elsewhere on the
1Play. The holding read of the profile is limited to these registers.

Deliberately not exposed: operation mode (122), SOCdescx/SOCrecx (126/127,
shutdown thresholds), the generator schedule (100.2, 110–113) and every grid
protection, regulation, battery type and grid-quality setting.

Full test record (in Spanish): [1Play validation](VALIDATION_STORAGE_1PLAY.md).

## Not covered yet

- Energy counters are integrated from SSE power, as for the ISS; no 1Play
  device counter has been identified.
- Other settings. Each one needs its 1Play map entry (address, bit, range,
  scale and meaning) and a write/readback on a real inverter before it is
  added to `control_keys`. Grid protection, regulation, country, battery type
  and grid-quality algorithms are installer settings and stay out of scope.
- Three-phase 1Play installations: the per-phase sum is implemented but only
  a single-phase system has been observed.
