#!/usr/bin/env bash
# Validate M7 packaging skeleton without requiring Developer ID or notarization.
# Exit 0 when config is coherent; non-zero on missing required files.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

fail=0
ok() { echo "  OK  $*"; }
bad() { echo "  BAD $*"; fail=1; }

echo "== CyberGuard pack:check (dry-run, no certs) =="

[[ -f electron-builder.yml ]] && ok "electron-builder.yml" || bad "electron-builder.yml missing"
[[ -f entitlements/release.plist ]] && ok "entitlements/release.plist" || bad "release.plist missing"
[[ -f entitlements/dev.plist ]] && ok "entitlements/dev.plist" || bad "dev.plist missing"
[[ -f scripts/notarize.cjs ]] && ok "scripts/notarize.cjs" || bad "notarize.cjs missing"
[[ -f electron/main.cjs ]] && ok "electron/main.cjs" || bad "main.cjs missing"
[[ -f electron/preload.cjs ]] && ok "electron/preload.cjs" || bad "preload.cjs missing"
[[ -f package.json ]] && ok "package.json" || bad "package.json missing"

# YAML essentials
if grep -q 'appId: com.cyberguard.desktop' electron-builder.yml; then
  ok "appId com.cyberguard.desktop"
else
  bad "appId mismatch"
fi
if grep -q 'afterSign: scripts/notarize.cjs' electron-builder.yml; then
  ok "afterSign → notarize.cjs"
else
  bad "afterSign not wired"
fi
if grep -q 'hardenedRuntime: true' electron-builder.yml; then
  ok "hardenedRuntime"
else
  bad "hardenedRuntime not set"
fi

# notarize hook must not claim success without credentials
if grep -q 'DRY-RUN' scripts/notarize.cjs && grep -q 'INV-38' scripts/notarize.cjs; then
  ok "notarize dry-run + INV-38 wording"
else
  bad "notarize.cjs missing dry-run / INV-38 guard"
fi

# optional sidecar payload
if [[ -d build/sidecar ]] && [[ -n "$(ls -A build/sidecar 2>/dev/null || true)" ]]; then
  ok "build/sidecar present (extraResources)"
else
  echo "  WARN build/sidecar empty or missing — GA bundle must add PyInstaller onedir later"
fi

# node syntax check on notarize hook
if command -v node >/dev/null 2>&1; then
  node --check scripts/notarize.cjs && ok "notarize.cjs syntax" || bad "notarize.cjs syntax"
else
  echo "  WARN node not on PATH — skip syntax check"
fi

# Simulate dry-run invoke of afterSign without electron-builder
if command -v node >/dev/null 2>&1; then
  CYBERGUARD_NOTARIZE_DRY_RUN=1 node -e '
    const n = require("./scripts/notarize.cjs");
    n.default({
      electronPlatformName: "darwin",
      appOutDir: "/tmp/cg-pack-check-missing",
      packager: { appInfo: { productFilename: "CyberGuard" } },
    }).then(() => process.exit(0)).catch((e) => { console.error(e); process.exit(1); });
  ' && ok "notarize hook dry-run exits 0 without certs" || bad "notarize dry-run failed"
fi

echo
if [[ "$fail" -ne 0 ]]; then
  echo "pack:check FAILED"
  exit 1
fi
echo "pack:check PASSED (not notarized — correct for unsigned/dev builds)"
exit 0
