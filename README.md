# Ingeteam ISS for Home Assistant — 0.5.0

[Español](README.es.md) · [Testing](docs/VALIDATION.md) · [Telemetry and energy](docs/TELEMETRY_ENERGY.md) · [Publishing](docs/PUBLISHING.md)

Unofficial local integration for the Ingeteam INGECON SUN STORAGE ISS 6TL.
Version 0.5.0 retains the working controls, schedules, groups and entity identities
from 0.4.0, adding hourly net energy, calendar consumption and reconfiguration.
No cloud, MQTT broker or Node-RED is required. Setup never writes inverter settings.

## Requirements

- Home Assistant Core **2026.3.0 or later**.
- Tested reference firmware **ABH1007AE** on the ISS installation:
  API 102, web 6.1.0, communication board ABH0101.
- Local HTTP access, normally port 80.
- **Create a dedicated Home Assistant user in the inverter configuration portal.
  Installer permissions are mandatory.** This separates Home Assistant changes
  from other users' portal changes. Lower permission levels cannot write some
  settings.

`ABH1007AE` is the portal firmware reference. `ABH1006AC` identifies the internal
map/firmware layer and is not treated as the portal version. Older firmware may
be tried with possible incompatibilities; future firmware is not automatically
certified. The integration uses the connected device's capability map, without
blocking installation solely because of a firmware version string.

HTTP Basic credentials are not encrypted in transit. Use a trusted LAN and
never expose the inverter HTTP port to the Internet. Remove credentials and
identifiers from reports and logs.

## Included

Up to 70 registered entities in 6 devices/groups, retaining all 53 existing unique IDs:

| Group | Contents |
|---|---|
| Main inverter | Power/battery sensors, grid/battery flow states, alarms and SSE diagnostics |
| Battery management | 5 SOC settings, 2 BMS current limits, BMS-requested SOC calibration permission |
| Scheduled grid charging | Maximum power, 2 SOC targets, 2 schedule modes, 4 times |
| Scheduled discharging | Maximum battery export, 2 SOC limits, 2 battery-use modes, 2 schedule modes, 4 times |
| Grid and surplus | Maximum PV export, priority and peak-shaving controls |
| Energy | 6 existing lifetime counters, daily/monthly consumption, hourly net balance and net counters |

## New in 0.5.0

- **Real time — SSE**, **5 s**, **10 s** or **30 s** publication cadence. The
  inverter sets SSE timing; all samples still feed energy calculations.
- **Reconfigure** connection details and cadence without deleting the entry.
  Reauthentication and automatic migration retain identities and stored energy.
- Daily/monthly household consumption and persistent hourly net import/export.
  Net lifetime totals never reset; separate daily/monthly net meters are included.
- Automation states, map-based alarm descriptions and activation/clearing events.
- Downloadable diagnostics and an optional detailed SSE diagnostic entity.
- Capability-based reads/controls, retaining unknown alarm codes explicitly.

See [0.5.0 operation, upgrade and limitations](docs/VERSION_0.5.0.md). New calendar
and net counters begin at upgrade; they do not reconstruct earlier history.
For hourly netting in the Energy dashboard select **Net imported energy** and
**Net exported energy** in place of gross grid counters, not in addition to them.

BMS maximum charge current (HR86) and maximum on-grid discharge current (HR142)
now use **sliders: 0–66 A, step 1 A**. The range is not a recommendation for the
connected battery. Existing BMS and inverter protections still apply.
The HR132 bit 0 switch permits SOC calibration when requested by the BMS; it
does not trigger immediate forced calibration.

All writes retain per-field payloads, serialization, immediate readback and
comparison. No unrelated packed-register bits are changed. A matching readback
confirms the returned setting, not independently verified physical behavior.

## Hybrid telemetry

A single authenticated connection to `/system/events/sse/stream` reads complete
SSE events. Only `/ems/sse/phases`, aggregate `Phase = 4`, supplies sensors.
Other event types and excessive fields are not exposed.

| Measurement | Source |
|---|---|
| Total PV power | SSE `pv` |
| Household consumption | SSE `cons`, not `total_cons` |
| Net grid power | SSE `W`: positive import, negative export |
| Grid import/export | `max(W, 0)` / `max(-W, 0)` |
| Battery SOC/voltage | SSE `soc` / `vbat`, already decoded |
| Net battery power | `PacDischarge - PacCharge`, positive discharge |
| Battery charge/discharge | SSE `PacCharge` / `PacDischarge` |
| PV1/PV2/battery current | HTTP online registers 33/36/18; current divided by 100 |

Total PV changes source from the old string sum to EMS `pv`, preserving its
entity identity. These are not numerically identical in every supplied capture.
No correction factor is applied. Remaining HTTP values are selected by address
and bit, never array index; the already-decoded properties response is not
double-scaled.

HTTP polling (default 15 seconds, configurable 5–300) is independent of SSE.
SSE updates cannot postpone the HTTP timer. HTTP failure does not invalidate
healthy SSE, and SSE failure does not disable working configuration controls.

## Availability and reconnection

The SSE watchdog defaults to **30 seconds**, configurable 10–120 seconds.
Socket errors or EOF invalidate SSE readings immediately; a silent open
connection is detected by the watchdog. Heartbeats, unrelated events and
malformed JSON do not renew it; unchanged valid readings and zeros do.

Automatic retries back off from 1 to 60 seconds. SSE authentication failures
retry every 60 seconds. An enabled connectivity diagnostic tracks valid
telemetry. Last valid event and last interruption timestamps are disabled by
default to avoid high Recorder traffic; enable them in the entity registry if
needed. Reception times use Home Assistant's clock and are session-local.

For the observed `StatusBat = 7` (battery unavailable), battery measurements
become unavailable instead of displaying a false SOC of 0%. PV, household and
grid remain usable. Battery settings remain accessible if their HTTP reads are
valid. SOC=0 or power=0 alone does not indicate disconnection.

## Calculated energy

Six counters integrate PV, household load, grid import/export and battery
charge/discharge. They use the **left Riemann rule**, matching the former YAML
`method: left`, with real monotonic reception intervals. The calculation is
built in; no extra Integral helpers or MQTT sensors are required.

Counters have kWh units, energy device class and `total` state class, without
daily resets. Full internal precision is retained; display precision is 3
decimals. Only valid paired readings up to **5 seconds** apart are integrated.
Energy states are published every 30 seconds while receiving data, and on SSE
interruption, to limit Recorder traffic; accumulation still uses every event.
Missing samples, longer gaps, disconnects and restarts break the corresponding
time anchors. Totals stay visible but frozen during outages; missing energy is
not backfilled or extrapolated.

Totals are saved roughly every 60 seconds while increasing, and on normal
unload/shutdown. An abrupt host power loss may lose increments since the last
save. These are estimated energy values, not billing-grade meters. The
observed disagreement between physical/EMS power fields can affect the balance.

For the Energy dashboard, use PV energy for solar; grid import/export energy
for the two grid directions; battery charge/discharge energy for battery input
and output. Household consumption energy is a separate comparison counter:
do not add it again as an individual load on top of the whole-house balance.

**No automatic history migration:** first-time counters start at zero and do
not import the old MQTT/Integral history. Keep old entities while comparing,
but never select both old and new counters as duplicate Energy sources.
This integration does not edit your dashboard, existing YAML or MQTT entities.

## Install/update

1. Back up Home Assistant and the existing `custom_components/ingeteam_iss`.
2. Copy the archive's `custom_components/ingeteam_iss` into
   `/config/custom_components/ingeteam_iss`, including brand and translations.
3. Restart Home Assistant. Keep the existing integration entry.
4. Check SSE connectivity and follow the [test checklist](docs/VALIDATION.md).
5. Select new Energy sources manually only after comparison.

New setup asks for a host without a URL scheme/path, Installer username,
password, HTTP port and a numeric inverter ID. The ID remains a **typed number
box**, default **1**, range 1–247. Times follow the inverter's local clock.

Customized names and all prior unique IDs are preserved. Spanish, English,
French, German, Italian, Portuguese, Dutch and Polish cover setup, options,
entities, groups and selector labels. Home Assistant's normal translation
behavior applies; changing language does not change entity IDs.

To roll back, restore the previous component directory and restart without
deleting the integration entry or its stored totals. New 0.4.0 entities will
stop updating until the newer version is restored.

## Scope and publication

Five observed operating modes are reproduced with sanitized synthetic fixtures
by the automated suite using actual Home Assistant Core and a localhost
HTTP/SSE simulator. The integration
has also completed an initial extended physical test on the reference inverter.
See [validation details](docs/VALIDATION.md).

Supported scope is one ISS inverter per communication board; aggregate SSE is
not per-node telemetry for multi-inverter installations. Existing board-serial
identity is preserved.

The source tree uses the HACS integration layout and includes automated tests,
issue templates, HACS/Hassfest validation and publication instructions. Until a
tagged release is created, install this development version by adding this
repository to HACS as a custom repository of type **Integration**. Official
Home Assistant Core inclusion will be a separate review, not an automatic
consequence of reaching version 1.0.

[Energy sensor requirements](https://www.home-assistant.io/docs/energy/faq/)
· [Left-rule integration](https://www.home-assistant.io/integrations/integration/)
