#!/usr/bin/env bash
# Record local image IDs and, after docker push, registry immutable digests.
set -euo pipefail

OUT="${1:-artifacts/release-digests.md}"
IMAGES=(
  cyberguard-api:1.0.0-rc.1
  cyberguard-tool-runner:1.0.0-rc.1
  cyberguard-webui:1.0.0-rc.1
)

mkdir -p "$(dirname "$OUT")"
{
  echo "# Release image digests"
  echo
  echo "Generated (UTC): $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo
  echo "Local IDs identify the image on this machine. Registry digests"
  echo "(\`repo@sha256:...\`) are immutable only after \`docker push\`."
  echo
  echo "| Image | Local ID | Registry digest |"
  echo "|---|---|---|"
  for image in "${IMAGES[@]}"; do
    id="$(docker image inspect "$image" --format '{{.Id}}')"
    digest="$(docker image inspect "$image" --format '{{if .RepoDigests}}{{index .RepoDigests 0}}{{else}}not-pushed{{end}}')"
    # Local bake writes a RepoDigest without a registry host; that is not a
    # published immutable digest.
    if [[ "$digest" != */* ]]; then
      digest=not-pushed
    fi
    echo "| \`$image\` | \`$id\` | \`$digest\` |"
  done
  echo
  echo "After publishing:"
  echo
  echo '```bash'
  echo "REGISTRY=<registry>/  # e.g. ghcr.io/pz1130/"
  echo "for image in ${IMAGES[*]}; do"
  echo '  docker tag "$image" "${REGISTRY}${image}"'
  echo '  docker push "${REGISTRY}${image}"'
  echo '  docker buildx imagetools inspect "${REGISTRY}${image}" --format "{{json .Manifest.Digest}}"'
  echo "done"
  echo '```'
} | tee "$OUT"
