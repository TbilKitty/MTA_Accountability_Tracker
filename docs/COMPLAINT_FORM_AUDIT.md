# MTA complaint-form audit protocol

**Status: not yet verified.** Do not publicly assert that a vehicle number is mandatory until tested.

- Record audit date, exact official form URL, browser/device, screenshot filename and SHA-256 digest.
- Note whether vehicle number is present, mandatory, optional, conditionally required, or omitted.
- Test no-show reporting path without submitting a fabricated complaint; document any validation errors.
- Record available fields for route, direction, stop ID, date, scheduled time, description, and supporting evidence.
- Determine whether minors can file, whether anonymous reports are possible, and whether a confirmation number is provided.
- Preserve accessibility observations and language availability; do not infer violations from an informal test.
- Recheck after any form change and retain dated historical versions.

The project rider form must **never require a vehicle number** for a no-show or pass-by report. The vehicle number may be optional for incidents where the rider observed it.
