# GitHub and HACS publication

This repository contains the stable 0.5.3 release. Its manifest points
to `solideus/Ingeteam-iss-homeassistant` and identifies `@solideus` as code owner.

1. Keep the integration at `custom_components/ingeteam_iss/`; only one
   integration may exist below `custom_components/`.
2. Keep Issues enabled and use the repository topics `home-assistant`, `hacs`,
   `ingeteam`, `solar`, `battery` and `custom-integration`.
3. Require the integration tests and validation workflow to pass before merging.
4. Create a tag matching `manifest.json`, currently `v0.5.3`, and publish it as a
   stable release after validation. HACS installs from the repository layout;
   this `hacs.json` does not enable ZIP-release installation.
5. The integration is included in the HACS default catalogue. Verify upgrades
   through HACS and keep the release notes and translated documentation current.

Repository publication remains separate from physical testing on the reference inverter.
The map and current limits target the reference ISS firmware; reports from other
models must be checked before claiming broad compatibility. Several inverter
nodes behind one communication board are not yet a supported configuration:
identity currently follows the board serial number, as in 0.1.0 and 0.2.0.

Before public release, test SSE through the intended LAN environment, normal
reload/restart persistence, Energy sources and the Installer account permissions.
Do not upload HAR files, credentials, personal IPs or unredacted device logs.
The included operating fixtures contain measurements only, without credentials.

Inclusion in Home Assistant Core is another process with its own review and
quality requirements. Version 1.0 is not automatic approval by Ingeteam or HA.

References:
- [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/)
- [HACS publication](https://www.hacs.xyz/docs/publish/start/)
- [Home Assistant manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
