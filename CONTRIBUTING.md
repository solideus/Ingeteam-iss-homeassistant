# Contributing

Report bugs and proposals through the repository Issues.
Include the Home Assistant and integration versions, inverter model/API version,
steps to reproduce and sanitized logs. Compatibility is currently grounded in
one ISS register map (API 102 / web 6.1.0).

Use Python 3.14.2 or later and install `requirements-test.txt` in a virtual
environment. Run `python -m pytest -q`. Tests use real Home Assistant Core 2026.3.0
with an isolated HTTP/SSE inverter simulator; they never access a physical inverter.
They verify registration, translation loading, service calls, field writes and
readback, current limits, schedule handling and unavailable telemetry.
The expanded suite also covers complete SSE framing, real operating captures,
watchdog behavior, reconnection, energy gaps and persistence across reloads.
The minimum Core is pinned in requirements; CI also tests Core 2026.9.3.

Translations live in `custom_components/ingeteam_iss/translations/*.json`.
Keep identical keys in every language and never translate stable entity keys,
unique IDs or selector state values. `en.json` is the English fallback.
Use complete strings, not Home Assistant Core build-time placeholders.
Keep `strings.json` aligned with `translations/en.json`. The 0.4.0 translation
update script documents the new strings across all eight languages.

Changes to writable registers need a confirmed map entry (address, bit, range,
scale and meaning). Preserve other fields in shared registers and existing
entity unique IDs. Keep installation and polling read-only.
Do not add a second source of the same energy to the Energy dashboard, or
silently import/replace existing MQTT history. Document measurement boundaries
and discrepancies, and break energy time anchors on missing/invalid telemetry.

The code uses the included Apache License 2.0. Ingeteam names and existing brand
assets identify the supported equipment; this project is an unofficial integration.
