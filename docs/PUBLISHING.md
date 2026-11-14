# GitHub and HACS publication

This branch prepares **0.6.0**, a profile refactor with only the existing TL M
profile. The published baseline is **v0.5.3**; do not describe this branch as a
stable release before validation and publication. Its manifest points to
`solideus/Ingeteam-iss-homeassistant` and identifies `@solideus` as code owner.
See [0.6.0 scope](VERSION_0.6.0.md) and [profile contributions](PROFILES.md).

1. Keep the integration at `custom_components/ingeteam_iss/`; only one
   integration may exist below `custom_components/`.
2. Keep Issues enabled and use the repository topics `home-assistant`, `hacs`,
   `ingeteam`, `solar`, `battery` and `custom-integration`.
3. Require the integration tests and validation workflow to pass before merging.
4. Before a release, confirm the validated commit is the merged and tagged
   content. Keep manifest, tag and release notes on the same version; use
   `v0.6.0` only for the validated 0.6.0 content. HACS installs from the repository layout;
   this `hacs.json` does not enable ZIP-release installation.
5. The integration is included in the HACS default catalogue. Verify upgrades
   through HACS and keep the release notes and translated documentation current.

Repository publication remains separate from physical testing on the reference inverter.
The map and current limits target the reference ISS firmware; reports from other
models must be checked before claiming broad compatibility. Several inverter
nodes behind one communication board are not yet a supported configuration:
identity currently follows the board serial number, as in 0.1.0 and 0.2.0.

Before the stable 0.6.0 release, complete the TL M equivalence checks against
v0.5.3 and the physical checks described in VERSION_0.6.0.md. Test SSE through the
intended LAN environment, normal reload/restart persistence, known controls and
schedules, Energy sources and the Installer account permissions. Simulator tests
and previously reported physical validation do not establish that the refactor
has passed these checks.
Do not upload HAR files, credentials, personal IPs or unredacted device logs.
The included operating fixtures contain measurements only, without credentials.

Inclusion in Home Assistant Core is another process with its own review and
quality requirements. Version 1.0 is not automatic approval by Ingeteam or HA.

References:
- [HACS integration requirements](https://www.hacs.xyz/docs/publish/integration/)
- [HACS publication](https://www.hacs.xyz/docs/publish/start/)
- [Home Assistant manifest](https://developers.home-assistant.io/docs/creating_integration_manifest/)
