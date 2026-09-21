# Security policy

## Reporting a vulnerability

Please do not publish inverter credentials, authorization headers, unredacted
diagnostics, HAR files, serial numbers or private network details in an issue.

For a suspected vulnerability that can be described without sensitive data,
open an issue with the minimum reproduction details and mark it clearly as a
security report. If sensitive information is required, contact the repository
owner privately before sharing it.

The integration communicates with the inverter over local HTTP Basic
authentication. That transport does not encrypt credentials; use it only on a
trusted LAN and never expose the inverter HTTP service directly to the Internet.
