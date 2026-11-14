# Ingeteam ISS maintenance

Read the current code, related tests, README files and version notes before changing behavior. Check the branch and working tree; preserve unrelated edits. Use focused branches and describe the actual tested revision.

## Scope and profiles

- The production reference is **INGECON SUN STORAGE 1Play 6TL M — 2 MPPT**, portal firmware **ABH1007AE**, board ABH0101, API 102. ABH1006AC is an internal map reference, not the portal requirement.
- Version 0.6.0 separates the existing behavior into profile `tl_m`. The earlier **1Play TL without M — 1 MPPT** is not supported by this refactor. PR #8 is preserved as research for a later profile.
- Put model-specific entity definitions, registers, telemetry decoding and operating-state interpretation in that model's profile. Generic platforms must not gain model-name conditionals.
- Adding a profile normally changes its directory, explicit registry registration, tests, translations and documentation. Review changes to shared communications, entities or energy separately and run the existing profile's regression suite.
- Shared infrastructure means isolation is not absolute. Do not promise no regressions from file separation alone. See [profile contribution guide](docs/PROFILES.md).

## Stable behavior

- Preserve domain, config-entry identity, entity unique IDs, user names, automations, device grouping and the energy storage key. Do not delete or recreate entries or entities to implement a refactor.
- Setup and ordinary reads never write inverter settings. Serialize writes, send only requested fields, preserve shared-register bits, confirm by readback and report rejection or mismatch.
- Keep HTTP controls independent of SSE availability. A failed auxiliary online read must not disable valid holding controls.
- For the TL M, process complete `/ems/sse/phases` events, select one `Phase = 4`, invalidate missing values and renew freshness for unchanged valid samples. Heartbeats, unrelated events and invalid JSON do not renew the telemetry watchdog.
- Preserve the documented power sources and signs. Do not replace `pv`, `cons`, `W` or `PacDischarge` with apparently equivalent internal flows without evidence.
- Energy uses every valid sample, full internal precision and monotonic intervals up to five seconds. Restore totals, never temporal anchors; do not bridge invalid data, outages or restarts.
- Preserve the ordinary 30-second energy publication gate, periodic persistence and immediate `HH:59:55` net closures. Check Recorder's statistical hour as well as the amount. Keep local day/month boundaries and Madrid DST behavior.
- Resolve time zones asynchronously. Do not change sensor classes, units or reset semantics without checking statistics and migration consequences.

## Evidence and publication

- Run Ruff and the appropriate tests with the supported Core versions. Keep tests of the original profile; new tests must verify observable behavior and meaningful failure cases.
- Distinguish simulator results, reported physical observations and new physical validation. A matching readback confirms a returned value, not its complete physical effect.
- Keep the eight translations coherent. Never translate entity keys, unique IDs or internal selector values.
- Never commit credentials, personal addresses, serials, unredacted HAR files or private logs. Keep existing icons, logos and Apache-2.0 notices.
- Do not purge Recorder, edit SQL or reconstruct statistics implicitly. The integration is already in HACS defaults; do not reopen its catalogue submission.
- Follow [publishing](docs/PUBLISHING.md) for a release, including matching validated content, manifest, tag and notes. Do not publish or merge based on roadmap text alone; follow the user's authorized task scope.

## Pending work

Use [ROADMAP.md](docs/ROADMAP.md) for priorities. The `via_device` deprecation is a separate pending compatibility change, not part of the 0.6.0 profile extraction.
