[DEPLOYMENT.md](https://github.com/user-attachments/files/33508378/DEPLOYMENT.md)
# Deployment checklist

1. Create a GitHub repository and keep it **private** while collecting and validating data.
2. Upload files, never `.env`, private rider reports, or raw feeds containing restricted or identifying content.
3. Install dependencies and run `pytest -q`.
4. Run `python -m src.collect --static --alerts` locally.
5. Locate stops in `data/processed/stops.csv`, then run `python -m src.schedule --date YYYY-MM-DD --stop STOP_ID`.
6. Request authorized Swiftly real-time access; implement and test adapter after confirming endpoint and authentication documentation.
7. Optionally run `.github/workflows/archive.yml` manually or on its daily schedule to archive public schedules and alerts as workflow artifacts (retention limited by GitHub; arrange durable independent storage).
8. Populate private rider report CSV, run `python -m src.report`, inspect aggregate disclosure risk, then publish only `docs/` on GitHub Pages if desired.
9. Keep automatic social posting **disabled** until verified classification, human review, correction handling, platform API authorization, and rate limits are implemented.
10. For litigation readiness, use independent immutable backups and a written evidence retention policy; GitHub Actions artifacts are not permanent evidence storage.
