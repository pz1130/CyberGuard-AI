#!/usr/bin/env bash
# Sign the local Electron.app with a stable identity + stable bundle id so TCC
# (Full Disk Access, Files & Folders) survives rebuilds.
#
# Prerequisites:
#   ./scripts/ensure-dev-codesign-identity.sh
#
# Usage (from apps/desktop):
#   ./scripts/codesign-electron-dev.sh
#   IDENTITY_CN="CyberGuard Dev" BUNDLE_ID=com.cyberguard.desktop.dev ./scripts/codesign-electron-dev.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

IDENTITY_CN="${IDENTITY_CN:-CyberGuard Dev}"
BUNDLE_ID="${BUNDLE_ID:-com.cyberguard.desktop.dev}"
ENTITLEMENTS="${ENTITLEMENTS:-$ROOT/entitlements/dev.plist}"
ELECTRON_APP="${ELECTRON_APP:-$ROOT/node_modules/electron/dist/Electron.app}"

if [[ ! -d "$ELECTRON_APP" ]]; then
  echo "ERROR: Electron.app not found at $ELECTRON_APP"
  echo "Run: npm install"
  exit 1
fi

if [[ ! -f "$ENTITLEMENTS" ]]; then
  echo "ERROR: entitlements missing: $ENTITLEMENTS"
  exit 1
fi

if ! security find-identity -p codesigning 2>/dev/null | grep -F "\"$IDENTITY_CN\"" >/dev/null; then
  echo "Identity '$IDENTITY_CN' not found — running ensure-dev-codesign-identity.sh"
  bash "$ROOT/scripts/ensure-dev-codesign-identity.sh"
fi

echo "== codesign Electron for dev =="
echo "  app:        $ELECTRON_APP"
echo "  identity:   $IDENTITY_CN"
echo "  bundle id:  $BUNDLE_ID"

# Stable bundle identifier (TCC key component together with signing cert)
INFO_PLIST="$ELECTRON_APP/Contents/Info.plist"
if [[ -f "$INFO_PLIST" ]]; then
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $BUNDLE_ID" "$INFO_PLIST" 2>/dev/null \
    || /usr/libexec/PlistBuddy -c "Add :CFBundleIdentifier string $BUNDLE_ID" "$INFO_PLIST"
  /usr/libexec/PlistBuddy -c "Set :CFBundleName CyberGuard Desktop" "$INFO_PLIST" 2>/dev/null || true
  echo "  CFBundleIdentifier -> $BUNDLE_ID"
fi

# Also set helper app identifiers under Frameworks (best-effort)
while IFS= read -r -d '' helper_plist; do
  helper_id="${BUNDLE_ID}.helper"
  case "$helper_plist" in
    *"GPU"*) helper_id="${BUNDLE_ID}.helper.gpu" ;;
    *"Plugin"*) helper_id="${BUNDLE_ID}.helper.plugin" ;;
    *"Renderer"*) helper_id="${BUNDLE_ID}.helper.renderer" ;;
  esac
  /usr/libexec/PlistBuddy -c "Set :CFBundleIdentifier $helper_id" "$helper_plist" 2>/dev/null || true
done < <(find "$ELECTRON_APP/Contents/Frameworks" -name Info.plist -print0 2>/dev/null)

sign_one() {
  local target="$1"
  codesign --force --sign "$IDENTITY_CN" \
    --identifier "${BUNDLE_ID}" \
    --entitlements "$ENTITLEMENTS" \
    --options runtime \
    --timestamp=none \
    "$target"
}

# Sign nested code first (deep is discouraged; walk helpers/frameworks)
echo "Signing nested helpers/frameworks..."
# Helpers (apps)
while IFS= read -r -d '' helper; do
  sign_one "$helper" 2>/dev/null || true
done < <(find "$ELECTRON_APP/Contents/Frameworks" -name "*.app" -print0 2>/dev/null)

# Frameworks
while IFS= read -r -d '' fw; do
  sign_one "$fw" 2>/dev/null || true
done < <(find "$ELECTRON_APP/Contents/Frameworks" -name "*.framework" -print0 2>/dev/null)

echo "Signing outer Electron.app..."
codesign --force --deep --sign "$IDENTITY_CN" \
  --identifier "$BUNDLE_ID" \
  --entitlements "$ENTITLEMENTS" \
  --options runtime \
  --timestamp=none \
  "$ELECTRON_APP"

echo
echo "== verify =="
codesign -dv --verbose=2 "$ELECTRON_APP" 2>&1 | grep -E 'Identifier=|Authority=|Signature=|TeamIdentifier=' || codesign -dv "$ELECTRON_APP" 2>&1 | head -20
codesign --verify --deep --strict "$ELECTRON_APP" && echo "verify: OK"

echo
echo "Done. Grant Full Disk Access once to this app:"
echo "  System Settings → Privacy & Security → Full Disk Access"
echo "  → enable Electron / CyberGuard (path: $ELECTRON_APP)"
echo
echo "Dev start (signed binary):"
echo "  npm run dev:signed"
echo
echo "Note: npm install may overwrite Electron.app — re-run this script after install."
