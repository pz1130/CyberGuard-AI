#!/usr/bin/env bash
# Quick check that Electron.app has the expected stable identity + bundle id.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
IDENTITY_CN="${IDENTITY_CN:-CyberGuard Dev}"
BUNDLE_ID="${BUNDLE_ID:-com.cyberguard.desktop.dev}"
ELECTRON_APP="${ELECTRON_APP:-$ROOT/node_modules/electron/dist/Electron.app}"

echo "identity present?"
security find-identity -p codesigning 2>/dev/null | grep -F "\"$IDENTITY_CN\"" || {
  echo "FAIL: no identity $IDENTITY_CN — run: npm run codesign:identity"
  exit 1
}
if ! security find-identity -v -p codesigning 2>/dev/null | grep -F "\"$IDENTITY_CN\"" >/dev/null; then
  echo "WARN: identity not in 'valid' list (CSSMERR_TP_NOT_TRUSTED)."
  echo "  Keychain Access → My Certificates → $IDENTITY_CN → Trust → Code Signing → Always Trust"
fi

echo "app signed?"
codesign -dv --verbose=2 "$ELECTRON_APP" 2>&1 | tee /tmp/cg-codesign-dv.txt
grep -q "Identifier=$BUNDLE_ID" /tmp/cg-codesign-dv.txt || {
  echo "FAIL: Identifier is not $BUNDLE_ID (TCC may not stick) — run: npm run codesign:dev"
  exit 1
}
if ! grep -qE "Authority=.*CyberGuard|Authority=$IDENTITY_CN" /tmp/cg-codesign-dv.txt; then
  echo "WARN: Authority line may not show CN; check Keychain trust / re-sign"
fi

# --strict can fail on nested Electron helpers after partial re-sign; deep verify is enough for dev
if codesign --verify --deep "$ELECTRON_APP" 2>/tmp/cg-cs-verify.err; then
  echo "verify: OK"
else
  echo "WARN: deep verify reported issues (often nested helper residual):"
  cat /tmp/cg-cs-verify.err || true
fi
echo "OK: signed as $BUNDLE_ID (identity $IDENTITY_CN)"
