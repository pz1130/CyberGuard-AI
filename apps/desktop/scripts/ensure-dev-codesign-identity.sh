#!/usr/bin/env bash
# Create a stable self-signed codesign identity for CyberGuard Desktop dev builds.
# TCC binds to (bundle id + signing identity) — ad-hoc rebuilds lose Full Disk Access.
#
# Usage:
#   ./scripts/ensure-dev-codesign-identity.sh
#   IDENTITY_CN="CyberGuard Dev" ./scripts/ensure-dev-codesign-identity.sh
#
# Does NOT require Apple Developer Program. May prompt once for Keychain access.
set -euo pipefail

IDENTITY_CN="${IDENTITY_CN:-CyberGuard Dev}"
KEYCHAIN="${KEYCHAIN:-$HOME/Library/Keychains/login.keychain-db}"
if [[ ! -f "$KEYCHAIN" ]]; then
  # Older macOS
  KEYCHAIN="$HOME/Library/Keychains/login.keychain"
fi

echo "== ensure codesign identity: $IDENTITY_CN =="

identity_present() {
  # include untrusted matches (CSSMERR_TP_NOT_TRUSTED still usable for local codesign)
  security find-identity -p codesigning 2>/dev/null | grep -F "\"$IDENTITY_CN\"" >/dev/null
}

identity_valid() {
  security find-identity -v -p codesigning 2>/dev/null | grep -F "\"$IDENTITY_CN\"" >/dev/null
}

if identity_present; then
  echo "OK: identity already present"
  security find-identity -p codesigning 2>/dev/null | grep -F "\"$IDENTITY_CN\"" || true
  if ! identity_valid; then
    echo
    echo "NOTE: identity is present but not yet 'trusted' for code signing."
    echo "If codesign fails, open Keychain Access → My Certificates → '$IDENTITY_CN'"
    echo "  → Get Info → Trust → Code Signing → Always Trust"
  fi
  exit 0
fi

TMP="$(mktemp -d "${TMPDIR:-/tmp}/cg-codesign.XXXXXX")"
cleanup() { rm -rf "$TMP"; }
trap cleanup EXIT

# OpenSSL config: codeSigning EKU required by codesign
cat >"$TMP/openssl.cnf" <<EOF
[ req ]
distinguished_name = req_distinguished_name
x509_extensions = v3_codesign
prompt = no

[ req_distinguished_name ]
CN = ${IDENTITY_CN}
O = CyberGuard
C = US

[ v3_codesign ]
basicConstraints = critical,CA:false
keyUsage = critical,digitalSignature
extendedKeyUsage = critical,codeSigning
subjectKeyIdentifier = hash
EOF

openssl req -new -newkey rsa:2048 -nodes \
  -keyout "$TMP/key.pem" \
  -out "$TMP/csr.pem" \
  -config "$TMP/openssl.cnf" \
  >/dev/null 2>&1

openssl x509 -req -days 3650 \
  -in "$TMP/csr.pem" \
  -signkey "$TMP/key.pem" \
  -out "$TMP/cert.pem" \
  -extfile "$TMP/openssl.cnf" \
  -extensions v3_codesign \
  >/dev/null 2>&1

# macOS security import needs legacy PKCS#12 (OpenSSL 3 default MAC fails)
EXPORT_PASS="cg-dev-temp"
if ! openssl pkcs12 -export -legacy \
  -inkey "$TMP/key.pem" \
  -in "$TMP/cert.pem" \
  -out "$TMP/cert.p12" \
  -name "$IDENTITY_CN" \
  -passout "pass:$EXPORT_PASS" \
  >/dev/null 2>&1; then
  # fallback without -legacy (LibreSSL)
  openssl pkcs12 -export \
    -inkey "$TMP/key.pem" \
    -in "$TMP/cert.pem" \
    -out "$TMP/cert.p12" \
    -name "$IDENTITY_CN" \
    -passout "pass:$EXPORT_PASS" \
    -macalg sha1 -certpbe PBE-SHA1-3DES -keypbe PBE-SHA1-3DES \
    >/dev/null 2>&1
fi

set +e
security import "$TMP/cert.p12" \
  -k "$KEYCHAIN" \
  -P "$EXPORT_PASS" \
  -T /usr/bin/codesign \
  -T /usr/bin/security \
  -T /usr/bin/productsign \
  2>"$TMP/import.err"
IMP_RC=$?
set -e

if [[ $IMP_RC -ne 0 ]]; then
  echo "WARN: security import failed (rc=$IMP_RC)."
  cat "$TMP/import.err" || true
  echo "Create the certificate manually (Keychain Access → Certificate Assistant"
  echo "  → Create a Certificate → name '$IDENTITY_CN' → Code Signing) and re-run."
  exit 1
fi

set +e
security set-key-partition-list -S apple-tool:,apple:,codesign: -s -k "" "$KEYCHAIN" >/dev/null 2>&1
security add-trusted-cert -d -r trustRoot -p codeSign -k "$KEYCHAIN" "$TMP/cert.pem" >/dev/null 2>&1
set -e

# Smoke: can codesign use the identity?
echo "test" >"$TMP/blob"
if codesign --force --sign "$IDENTITY_CN" --timestamp=none "$TMP/blob" 2>"$TMP/cs.err"; then
  echo "OK: created identity '$IDENTITY_CN' and codesign can use it"
else
  echo "OK: imported identity '$IDENTITY_CN' (codesign smoke may need Trust UI once)"
  cat "$TMP/cs.err" || true
  echo
  echo "If needed: Keychain Access → My Certificates → '$IDENTITY_CN'"
  echo "  → Get Info → Trust → Code Signing → Always Trust"
fi

security find-identity -p codesigning 2>/dev/null | grep -F "\"$IDENTITY_CN\"" || true
echo
echo "Next: npm run codesign:dev"
echo "Then grant Full Disk Access once to the signed Electron.app."
exit 0
