# Version 0.5.0: operation and validation

## Upgrade

Update through HACS and restart Home Assistant. Do not remove the integration.
All 0.4.0 entity IDs and the energy storage key are retained. Entry schema v1 is
migrated to v2 automatically. New counters begin when 0.5.0 first receives valid
samples; they do not reconstruct the previous part of a day/month from Recorder.
Back up Home Assistant before upgrading; restoring that backup is the reliable
way to roll back the configuration schema and persistent counters together.

## Connection and publication

The integration menu **Reconfigure** changes host/IP, HTTP port, username,
password, inverter ID and publication cadence. Empty password preserves the
existing password. The new credentials and selected node are read before saving.
A different reported serial is rejected to avoid mixing two devices' history.
The node ID changes HTTP targeting; SSE remains the installation aggregate
`Phase = 4`. Multi-inverter selection is not claimed by this version.

**Configure** offers the same cadence plus the independent HTTP polling interval
and valid-SSE timeout. Cadences: **Real time — SSE (inverter cadence)**, **5**,
**10**, **30 seconds**. SSE is the default and does not promise exactly 1 Hz.
The connection stays open for every cadence. All valid samples reach energy
calculations and the watchdog. Slow cadence delays telemetry states and their
automations, but does not reduce inverter event traffic or HTTP polling. Existing
lifetime energy sensors retain their separate 30-second publication limit.
HTTP settings writes and confirmation do not wait for the SSE publication gate.

Invalid authentication starts reauthentication. Successful reconfiguration
reloads the entry, closes its old stream and restores the same stored counters.

## Energy and hourly netting

New keys:

| Key | Meaning |
|---|---|
| `load_energy_daily`, `load_energy_monthly` | Household consumption by local day/month |
| `net_import_energy`, `net_export_energy` | Lifetime settled hourly net energy |
| `hourly_net_balance` | Current hour: export minus import; positive means surplus |
| `net_import_energy_daily`, `net_export_energy_daily` | Settled net energy for this local day |
| `net_import_energy_monthly`, `net_export_energy_monthly` | Settled net energy for this local month |

For each hour, compute import minus export. A positive result increments net
import; a negative result increments net export by its absolute value. Lifetime
net counters never reset. Calendar counters reset at the local date/month change.
Use the two lifetime net counters as grid import/export in the Energy dashboard
if you want hourly netting; do not add both gross and net counters for the same
flow. Existing dashboard selections are never changed automatically. Selecting
new sensors does not transfer old statistics from existing sensors.

Integration uses the previous valid power over the actual monotonic interval.
Intervals crossing an hour are split at the boundary. UTC hour identifiers avoid
duplicating the repeated local hour in Spain's autumn DST change. Local dates
use Home Assistant's time zone. Netting uses fixed 60-minute UTC-aligned hours
(matching Spain's civil hours); zones offset by fractional hours are not yet
supported for civil-hour netting.

A new valid sample closes the old bucket at the hour boundary. If no sample
arrives, a five-second maintenance timer settles the observed subtotal once at
least five seconds past the boundary. It never estimates the missing time. This
differs deliberately from early finalization: the last seconds of valid data
are included. The algorithm is original; only the documented netting behaviour
of [ha-balance-neto](https://github.com/miguelangellv/ha-balance-neto) was consulted.

Samples more than five seconds apart, invalid channels, interruptions, restarts
and significant wall-clock jumps are not bridged. Current bucket and totals are
saved together, every 60 seconds and on orderly unload/stop. Abrupt power loss
can lose changes since the last save. These are estimates, not fiscal meters.

## Automation states and alarms

Grid flow: importing/exporting/balanced. Battery flow: charging/discharging/idle/
not available. A ±10 W deadband avoids switching states around zero. PV active
means more than 10 W. `StatusBat = 7` means battery unavailable. Grid-connected
state is true for reported states 3/4/8, false for 2/11, otherwise unavailable;
it describes the reported operating mode, not an independent mains detector.
Power reduction uses online register 41 (reason), not the inconsistent
`ReductionReason` properties alias observed at address 57.

The alarm count has an `alarms` list and `raw_codes` attributes. Each entry has
category, address, bit, mask, description and `documented`. Labels come from
the connected inverter's map. Generic `Bit N` and reserved labels are considered
undocumented. In particular BMS fields 73–76 do not supply meaningful labels in
the reference map. No Pylontech-specific meaning is inferred.

Event `ingeteam_iss_alarm` contains the same fields plus `active` and `entry_id`.
Changes follow HTTP polling; failed/missing reads do not emit a false clearing.
An active code found on startup emits an activation event. A zero count means
no codes in the successfully read categories; inspect `missing_categories` for
coverage. The alarm binary sensor is unavailable if no categories can be read.

## Capabilities, diagnostics and firmware

ABH1007AE (portal firmware) is the tested reference. Earlier firmware may work
with incompatibilities; future firmware is not automatically certified.
The optional `/inverter/map/{id}` determines available holding fields and online
addresses. Unsupported controls are omitted and writes are checked. If the map
is unavailable, retain the curated 0.4.0 reads; missing fields are unavailable.
Internal map firmware identifiers such as ABH1006AC are not compared to the
portal firmware as if they were the same component.

Optional SSE diagnostics include last received event, last valid sample,
elapsed time without data, moving mean interval, reconnect attempts, valid,
discarded and incomplete frames, missing fields, timeout and last failure type.
Other event types count as discarded because they are intentionally unconsumed.
A missing battery field can legitimately count as incomplete when disconnected.
Counters are session-local. Downloadable diagnostics expose only allow-listed
technical fields; credentials, host and serial are excluded.

## Roadmap after 0.5.0

- Medium priority: multi-inverter support, write audit trail, automation blueprints.
- Lower priority: energy consistency, peak demand, self-consumption/autonomy ratios,
  and advanced battery metrics.

## Release validation

Automated tests use real Home Assistant Core and a synthetic HTTP/SSE server.
They cover existing controls and IDs, calendar boundaries, both Spain DST changes,
netting and persistence, gaps, publication cadence, authentication/reconfiguration,
capability filtering, alarm edges and diagnostic privacy. CI runs the supported
minimum Core 2026.3.0 and Core 2026.9.3, plus HACS and Hassfest validation.
These checks do not replace testing 0.5.0 on a physical inverter.
