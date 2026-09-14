#!/usr/bin/env bash
# Create the source-only IFI delivery archive from an immutable Git revision.
set -euo pipefail

VERSION="${VERSION:-1.0.0-rc.1}"
REF="${REF:-HEAD}"
OUT_DIR="${OUT_DIR:-artifacts}"

if [[ ! "$VERSION" =~ ^[0-9A-Za-z][0-9A-Za-z._-]*$ ]]; then
  echo "Invalid VERSION: $VERSION" >&2
  exit 2
fi

COMMIT="$(git rev-parse --verify "${REF}^{commit}")"
if [[ "$REF" == "HEAD" ]] && ! git diff --quiet HEAD --; then
  echo "Working tree has tracked changes; commit them or package an explicit tag/ref." >&2
  exit 2
fi

mkdir -p "$OUT_DIR"
ARCHIVE="$OUT_DIR/cyberguard-${VERSION}-source.tar.gz"
MANIFEST="$OUT_DIR/cyberguard-${VERSION}-manifest.txt"

git archive --format=tar --prefix="cyberguard-${VERSION}/" "$COMMIT" \
  | gzip -n > "$ARCHIVE"

if command -v sha256sum >/dev/null 2>&1; then
  SHA256="$(sha256sum "$ARCHIVE" | awk '{print $1}')"
else
  SHA256="$(shasum -a 256 "$ARCHIVE" | awk '{print $1}')"
fi

{
  printf 'CyberGuard source delivery\n'
  printf 'Version: %s\n' "$VERSION"
  printf 'Git ref: %s\n' "$REF"
  printf 'Git commit: %s\n' "$COMMIT"
  printf 'Archive: %s\n' "$(basename "$ARCHIVE")"
  printf 'SHA-256: %s\n' "$SHA256"
  printf 'Generated (UTC): %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  printf 'Distribution model: source archive; operators build Docker images locally.\n'
} > "$MANIFEST"

printf '%s  %s\n' "$SHA256" "$(basename "$ARCHIVE")" > "${ARCHIVE}.sha256"
printf 'Created %s\nCreated %s\nCreated %s\n' "$ARCHIVE" "${ARCHIVE}.sha256" "$MANIFEST"
