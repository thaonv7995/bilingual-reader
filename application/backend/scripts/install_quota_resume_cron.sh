#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "Usage: $0 /absolute/path/to/books/<slug>/work/quota_resume/install-cron.txt"
  exit 1
fi

CRON_FILE="$1"

if [[ ! -f "$CRON_FILE" ]]; then
  echo "Missing cron template: $CRON_FILE"
  exit 1
fi

TMP_CRON="$(mktemp)"
crontab -l 2>/dev/null > "$TMP_CRON" || true

if ! grep -Fqx "$(tail -n 1 "$CRON_FILE")" "$TMP_CRON"; then
  {
    echo ""
    echo "# Books HTML quota-resume"
    tail -n 1 "$CRON_FILE"
  } >> "$TMP_CRON"
fi

crontab "$TMP_CRON"
rm -f "$TMP_CRON"
echo "Installed cron entry from $CRON_FILE"
