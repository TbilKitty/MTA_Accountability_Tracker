# Methodology and definitions

## Units
Use a unique observation key `(service_date, trip_id, stop_id, scheduled_time)`; include direction, route, and source feed version. Account for GTFS times beyond 24:00 and the America/New_York timezone, DST transitions, service calendars, and exceptions. Do not conflate vehicle observations with passenger boardings.

## Thresholds
- Official MTA local-bus OTP benchmark: generally -2 to +7 minutes at scheduled timepoints (check current definition).
- Project significant-delay threshold: >30 minutes. This is an analytical threshold, not a legal standard.
- `confirmed_cancellation`: explicit provider trip cancellation or independently authenticated operational record.
- `suspected_no_show`: rider report or inference requiring verification; never infer solely from missing GPS, predictions, or alerts.
- `confirmed_pass_by`: corroborated passenger/stop evidence; vehicle GPS alone cannot prove boarding denial.
- `data_unavailable`: feed outage, stale timestamps, failed API request, unmatched trip or vehicle; not a service failure.

## Economic impacts
Report separately: (1) observed passenger-delay minutes where supported; (2) modeled time value, using explicit assumptions and sensitivity intervals; (3) self-reported work hours; (4) corroborated lost earnings; (5) accrued leave value; (6) additional actual expenditures; (7) employer incremental costs if documented. Never add overlapping valuations or assume all riders are employed. Avoid extrapolating from a convenience sample to all MTA riders without representative sampling.

## Quality controls
Keep feed snapshot timestamps, checksums, original timezone, query parameters, provider response codes, schema versions, matched trip/stop IDs, observer identity in private records only, and any corrections. Track denominator: scheduled trips, successfully observed trips, and coverage hours. Publish methodology and confidence classification with every statistic.
