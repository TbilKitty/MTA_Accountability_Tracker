[CHILD_SAFETY_DATA_DICTIONARY.md](https://github.com/user-attachments/files/33508346/CHILD_SAFETY_DATA_DICTIONARY.md)
# Child safety datasets

`child_exposure_reports_template.csv`: voluntary reports of added wait/walk time, without names, school names, exact home addresses, or exact locations. `guardian_verified` refers to confirmation of the reporting guardian, **not** independent confirmation of a bus failure.

`child_safety_official_stats_template.csv`: one row per official aggregate statistic, preserving source, age definition, offense category, geography, period, count, denominator and caveats. Do not add counts across incompatible sources or definitions.

`child_safety_case_links_RESTRICTED_template.csv`: confidential research linkage register. Do not publish or commit completed case-level rows to GitHub, even a private repository. Store encrypted offline or in approved restricted storage. `causal_evidence_status` must default to `not_established`.
