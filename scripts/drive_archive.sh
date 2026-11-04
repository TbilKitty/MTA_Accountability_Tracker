#!/usr/bin/env bash
# Copies files into the project's Google Drive archive with rclone, then confirms
# Drive holds identical copies (rclone compares checksums).
#
#   scripts/drive_archive.sh test                      # upload a small test file
#   scripts/drive_archive.sh <subfolder> <file>...     # e.g. 2026/11 a.tar.gz a.manifest.csv
#
# Needs the RCLONE_CONF secret: the output of `rclone config show gdrive`, for a
# remote named "gdrive" with scope drive.file (it can only touch files it created).
# See SETUP_GOOGLE_DRIVE_ARCHIVE.md.
set -euo pipefail

ARCHIVE="gdrive:MTA Tracker Archive"
mode="${1:-}"

if [ -z "${RCLONE_CONF:-}" ]; then
  if [ "$mode" = "test" ]; then
    echo "::error::The RCLONE_CONF secret is missing. Add it under Settings > Secrets and variables > Actions (see SETUP_GOOGLE_DRIVE_ARCHIVE.md)."
    exit 1
  fi
  echo "::warning::RCLONE_CONF secret not set yet, so nothing was sent to Google Drive. The GitHub backup copy still has the files."
  exit 0
fi

if ! command -v rclone > /dev/null; then
  sudo apt-get install -y -qq rclone > /dev/null 2>&1 \
    || curl -fsSL https://rclone.org/install.sh | sudo bash > /dev/null
fi

conf="${RUNNER_TEMP:-/tmp}/rclone.conf"
printf '%s\n' "$RCLONE_CONF" > "$conf"
chmod 600 "$conf"
export RCLONE_CONFIG="$conf"

if [ "$mode" = "test" ]; then
  f="${RUNNER_TEMP:-/tmp}/connection-test.txt"
  echo "MTA tracker connection test at $(date -u +%FT%TZ)" > "$f"
  set -- _connection-test "$f"
fi

dest="$ARCHIVE/$1"
shift
for f in "$@"; do
  rclone copy "$f" "$dest" --retries 5 --low-level-retries 10
  rclone check "$(dirname "$f")" "$dest" --include "/$(basename "$f")" --one-way
done
echo "Saved $# file(s) to Google Drive: $dest"
