AUTOMATED MTA MONITORING — UPLOAD PATHS MATTER

Upload to the REPOSITORY ROOT (not docs):
  .github/workflows/monitor-realtime.yml
  scripts/monitor_realtime.py

Upload to docs/:
  data-dashboard.html  (replaces existing)
  realtime-dashboard.js (new)

Create docs/data/ directory if it does not exist. The workflow writes JSON there automatically.
GitHub web UI can create each nested path with Add file > Create new file, or upload the package using GitHub Desktop, which preserves folders. Uploading everything into docs/ WILL BREAK THE WORKFLOW.

Prerequisite: Settings > Secrets and variables > Actions > Repository secrets:
  SWIFTLY_API_KEY  (already set if you configured it earlier)

GitHub Actions > Monitor MTA real-time service > Run workflow.
Then confirm the job is green and docs/data/realtime-status.json exists.

The schedule runs about every 15 minutes (GitHub may delay scheduled runs).
Raw .pb snapshots are saved as workflow artifacts for 30 days. Public JSON has prediction observations and trip/stop IDs; not GPS coordinates or rider details.

WARNING: This is a prediction sampler, NOT a validated arrival or missed-bus detector. The dashboard must not represent forecast lateness as confirmed lateness.

If the job reports HTTP 401/403, check the key and access entitlement. If git push fails with 403, enable Settings > Actions > General > Workflow permissions > Read and write permissions (where permitted).

If you already have a collector workflow, this adds a second workflow; monitor API quotas and avoid duplicate requests.
