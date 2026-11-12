# INGECON SUN STORAGE 1Play — read-only profile

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

- loads only the `sensor` and `binary_sensor` platforms; it creates no number,
  switch, select or time entity, never reads holding registers and refuses
  writes in the coordinator;
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

## Not covered yet

- Energy counters are integrated from SSE power, as for the ISS; no 1Play
  device counter has been identified.
- No write support. Controls would need a confirmed 1Play holding map
  (address, bit, range, scale and meaning) per field and physical validation.
- Three-phase 1Play installations: the per-phase sum is implemented but only
  a single-phase system has been observed.
