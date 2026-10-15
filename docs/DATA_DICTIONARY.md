[DATA_DICTIONARY.md](https://github.com/user-attachments/files/33508371/DATA_DICTIONARY.md)
# Data dictionary

## Rider report columns
- report_id: random non-identifying unique ID
- incident_date: local YYYY-MM-DD
- route_id, stop_id: GTFS IDs; keep exact stop private for minor-related reports
- scheduled_time_local, observed_time_local: HH:MM or blank
- incident_type: late / no_show_reported / pass_by_reported / canceled_reported
- verification_status: unverified / corroborated / disputed
- work_hours_missed: nonnegative decimal
- documented_wages_lost_usd: dollars, actual wage loss only
- paid_leave_hours_used: hours, not automatically fiscal expenditure
- extra_transport_cost_usd: dollars
- school_minutes_missed: minutes
- evidence_reference: private file ID, not public URL
- notes_private: restricted narrative; no public export

Do not place minors' names, addresses, or phone numbers in CSV fields.
