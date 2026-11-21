# Contributing

Report bugs and proposals through the repository Issues.
Include the Home Assistant and integration versions, inverter model/API version,
steps to reproduce and sanitized logs. Compatibility is grounded in the
INGECON SUN STORAGE 1Play **6TL M — 2 MPPT**, reference portal firmware
**ABH1007AE**, board ABH0101 (API 102 / web 6.1.0).

Version 0.6.0 prepares a profile architecture with `tl_m` as the only production
profile. Before adding a model, read [the profile contribution guide](docs/PROFILES.md)
and [AGENTS.md](AGENTS.md). Put model-specific registers, entity descriptions,
telemetry and state interpretation in its own profile directory. Add an explicit
registry entry, tests, translations and documentation; do not edit `tl_m` or add
model-name branches to common platforms. Changes to common infrastructure need
separate review and regression evidence for the existing profile.

The earlier 1Play TL without M is not supported merely by this refactor. PR #8
is retained as research for a later contribution. Keep experimental work and its
physical validation clearly identified; profile separation is not an absolute
no-regression guarantee.

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
