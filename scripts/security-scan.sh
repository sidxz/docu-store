#!/usr/bin/env bash
# Trivy release gate: the component's lockfile + secrets, then the image CI
# publishes from it. Fails on any fixable HIGH/CRITICAL finding.
#
#   ./scripts/security-scan.sh services|web|cli
#
# release.sh runs this before it bumps anything; never tag over a red scan.
# Fix the dependency or base image. Add an id to .trivyignore (with the
# reason) only when the fix can't run here or is a scheduled major.
set -euo pipefail

component="${1:?usage: $0 services|web|cli}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

command -v trivy >/dev/null || { echo "trivy is not installed: brew install trivy" >&2; exit 1; }

gate=(--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 --ignorefile "$ROOT/.trivyignore")

trivy fs --scanners vuln,secret "${gate[@]}" \
  --skip-dirs "**/node_modules,**/.venv,**/.next,**/dist,blobs,evaluation" \
  "$ROOT/$component"

# cli ships to npm, not as an image.
[[ "$component" == cli ]] && exit 0

image="docu-store-$component:scan"
docker build -t "$image" "$ROOT/$component"
trivy image --scanners vuln "${gate[@]}" "$image"
