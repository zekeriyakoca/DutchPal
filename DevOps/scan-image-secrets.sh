#!/usr/bin/env bash
# Fails if a built image contains secret-looking values or secret files.
# The image filesystem is exported and scanned on the host, so the scan does
# not depend on tools inside the image.
# Usage: bash DevOps/scan-image-secrets.sh <image> [<image> ...]
set -euo pipefail

PATTERN='sk-(proj-)?[A-Za-z0-9_-]{30,}|sk-[a-f0-9]{32}|gsk_[A-Za-z0-9]{30,}|ntn_[A-Za-z0-9]{30,}|secret_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16}|AccountKey=[A-Za-z0-9+/=]{20,}|SharedAccessKey=[A-Za-z0-9+/=]{20,}|-----BEGIN [A-Z ]*PRIVATE KEY|ghp_[A-Za-z0-9]{30,}|sk_(live|test)_[A-Za-z0-9]{20,}|whsec_[A-Za-z0-9]{20,}|SG\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}|[Pp]assword=[^;"'"'"' $]{4,}'

# Application directories only; OS and third-party packages are skipped.
APP_DIRS=(app src usr/share/nginx/html)

failed=0
for image in "$@"; do
  echo "Scanning $image for secrets..."
  workdir="$(mktemp -d)"
  container="$(docker create "$image")"
  docker export "$container" | tar -x -C "$workdir" "${APP_DIRS[@]}" 2>/dev/null || true
  docker rm "$container" >/dev/null

  files="$(find "$workdir" \( -path '*/node_modules' -o -path '*/site-packages' \) -prune -o \
    \( -name '.env' -o -name '.env.*' -o -name 'secrets.env' -o -name '*.pem' -o -name '*.key' \
       -o -name '*.pfx' -o -name 'appsettings.Development.json' \) -print | sed "s|^$workdir|FILE: |")"
  matches="$(grep -rIlE "$PATTERN" "$workdir" --exclude-dir=node_modules --exclude-dir=site-packages \
    | sed "s|^$workdir|MATCH: |" || true)"
  rm -rf "$workdir"

  if [[ -n "$files$matches" ]]; then
    echo "ERROR: secrets found in $image:" >&2
    printf '%s\n%s\n' "$files" "$matches" | sed '/^$/d' >&2
    failed=1
  else
    echo "  clean"
  fi
done

exit "$failed"
