#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# release.sh — Interactive release helper for docu-store monorepo
#
# Bumps the version in the appropriate file, commits, tags, and
# optionally pushes.  Works for services (BE), web (FE), and CLI.
#
# Usage:
#   ./scripts/release.sh               # interactive prompts
#   ./scripts/release.sh services patch # non-interactive
#   ./scripts/release.sh web minor
#   ./scripts/release.sh cli major
# ──────────────────────────────────────────────────────────────
set -euo pipefail

# ── Paths (relative to repo root) ────────────────────────────
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

SERVICES_VERSION_FILE="$REPO_ROOT/services/pyproject.toml"
WEB_VERSION_FILE="$REPO_ROOT/web/apps/portal/package.json"
CLI_VERSION_FILE="$REPO_ROOT/cli/package.json"

# ── Color helpers ─────────────────────────────────────────────
BOLD='\033[1m'
DIM='\033[2m'
GREEN='\033[0;32m'
YELLOW='\033[0;33m'
CYAN='\033[0;36m'
RED='\033[0;31m'
NC='\033[0m' # reset

info()  { echo -e "${CYAN}${BOLD}>>>${NC} $*"; }
ok()    { echo -e "${GREEN}${BOLD} ok${NC} $*"; }
warn()  { echo -e "${YELLOW}${BOLD}warn${NC} $*"; }
err()   { echo -e "${RED}${BOLD}err${NC} $*" >&2; }

# ── Version readers ───────────────────────────────────────────
read_services_version() {
  grep -m1 '^version' "$SERVICES_VERSION_FILE" | sed 's/.*"\(.*\)".*/\1/'
}

read_json_version() {
  node -e "process.stdout.write(JSON.parse(require('fs').readFileSync('$1','utf8')).version)"
}

# ── Version writers ───────────────────────────────────────────
write_services_version() {
  local new_ver="$1"
  # macOS + GNU compatible sed
  if sed --version 2>/dev/null | grep -q GNU; then
    sed -i "s/^version = \".*\"/version = \"$new_ver\"/" "$SERVICES_VERSION_FILE"
  else
    sed -i '' "s/^version = \".*\"/version = \"$new_ver\"/" "$SERVICES_VERSION_FILE"
  fi
}

write_json_version() {
  local file="$1" new_ver="$2"
  # Use node to preserve formatting
  node -e "
    const fs = require('fs');
    const raw = fs.readFileSync('$file', 'utf8');
    const updated = raw.replace(/\"version\": \"[^\"]+\"/, '\"version\": \"$new_ver\"');
    fs.writeFileSync('$file', updated);
  "
}

# ── Semver bump ───────────────────────────────────────────────
bump_version() {
  local cur="$1" part="$2"
  IFS='.' read -r major minor patch <<< "$cur"
  case "$part" in
    major) echo "$((major + 1)).0.0" ;;
    minor) echo "$major.$((minor + 1)).0" ;;
    patch) echo "$major.$minor.$((patch + 1))" ;;
    *) err "Unknown bump type: $part"; exit 1 ;;
  esac
}

# ── Show current versions ────────────────────────────────────
show_versions() {
  local svc web cli
  svc=$(read_services_version)
  web=$(read_json_version "$WEB_VERSION_FILE")
  cli=$(read_json_version "$CLI_VERSION_FILE")

  echo ""
  echo -e "  ${DIM}Component        Version     Last Tag${NC}"
  echo -e "  ───────────────  ──────────  ─────────────────"
  printf "  ${BOLD}services (BE)${NC}    %-11s %s\n" "$svc" "$(git tag -l 'services-v*' --sort=-v:refname | head -1)"
  printf "  ${BOLD}web (FE)${NC}         %-11s %s\n" "$web" "$(git tag -l 'web-v*' --sort=-v:refname | head -1)"
  printf "  ${BOLD}cli${NC}              %-11s %s\n" "$cli" "$(git tag -l 'cli-v*' --sort=-v:refname | head -1)"
  echo ""
}

# ── Pre-flight checks ────────────────────────────────────────
preflight() {
  # Must be on main
  local branch
  branch=$(git -C "$REPO_ROOT" rev-parse --abbrev-ref HEAD)
  if [[ "$branch" != "main" ]]; then
    warn "You are on branch ${BOLD}$branch${NC}, not main."
    read -rp "  Continue anyway? [y/N] " yn
    [[ "$yn" =~ ^[Yy]$ ]] || exit 0
  fi

  # Must be clean
  if [[ -n "$(git -C "$REPO_ROOT" status --porcelain)" ]]; then
    warn "Working tree has uncommitted changes."
    read -rp "  Continue anyway? [y/N] " yn
    [[ "$yn" =~ ^[Yy]$ ]] || exit 0
  fi
}

# ── Interactive component picker ──────────────────────────────
pick_component() {
  echo -e "  Which component to release?" >&2
  echo -e "    ${BOLD}1)${NC} services (BE)" >&2
  echo -e "    ${BOLD}2)${NC} web (FE)" >&2
  echo -e "    ${BOLD}3)${NC} cli" >&2
  echo "" >&2
  read -rp "  Choice [1/2/3]: " choice
  case "$choice" in
    1) echo "services" ;;
    2) echo "web" ;;
    3) echo "cli" ;;
    *) err "Invalid choice"; exit 1 ;;
  esac
}

# ── Interactive bump picker ───────────────────────────────────
pick_bump() {
  local cur="$1"
  local v_major v_minor v_patch
  v_major=$(bump_version "$cur" major)
  v_minor=$(bump_version "$cur" minor)
  v_patch=$(bump_version "$cur" patch)

  echo -e "  Current version: ${BOLD}$cur${NC}" >&2
  echo -e "    ${BOLD}1)${NC} patch  → $v_patch" >&2
  echo -e "    ${BOLD}2)${NC} minor  → $v_minor" >&2
  echo -e "    ${BOLD}3)${NC} major  → $v_major" >&2
  echo "" >&2
  read -rp "  Bump type [1/2/3]: " choice
  case "$choice" in
    1) echo "patch" ;;
    2) echo "minor" ;;
    3) echo "major" ;;
    *) err "Invalid choice"; exit 1 ;;
  esac
}

# ── Do the release ────────────────────────────────────────────
do_release() {
  local component="$1" bump_type="$2"

  local cur_version new_version tag_prefix version_file write_fn

  case "$component" in
    services)
      cur_version=$(read_services_version)
      tag_prefix="services-v"
      version_file="$SERVICES_VERSION_FILE"
      ;;
    web)
      cur_version=$(read_json_version "$WEB_VERSION_FILE")
      tag_prefix="web-v"
      version_file="$WEB_VERSION_FILE"
      ;;
    cli)
      cur_version=$(read_json_version "$CLI_VERSION_FILE")
      tag_prefix="cli-v"
      version_file="$CLI_VERSION_FILE"
      ;;
  esac

  new_version=$(bump_version "$cur_version" "$bump_type")
  local tag="${tag_prefix}${new_version}"

  # Check tag doesn't already exist
  if git -C "$REPO_ROOT" tag -l "$tag" | grep -q .; then
    err "Tag $tag already exists!"
    exit 1
  fi

  echo ""
  info "Release plan:"
  echo -e "  Component:  ${BOLD}$component${NC}"
  echo -e "  Version:    $cur_version → ${GREEN}${BOLD}$new_version${NC}"
  echo -e "  Tag:        ${BOLD}$tag${NC}"
  echo -e "  File:       ${DIM}$version_file${NC}"
  echo ""
  read -rp "  Proceed? [Y/n] " yn
  [[ "$yn" =~ ^[Nn]$ ]] && { info "Aborted."; exit 0; }

  # 1. Update version file
  case "$component" in
    services)
      write_services_version "$new_version"
      ;;
    web)
      write_json_version "$WEB_VERSION_FILE" "$new_version"
      ;;
    cli)
      write_json_version "$CLI_VERSION_FILE" "$new_version"
      ;;
  esac
  ok "Updated $version_file → $new_version"

  # 2. Commit
  git -C "$REPO_ROOT" add "$version_file"
  git -C "$REPO_ROOT" commit -m "chore($component): bump version to $new_version"
  ok "Committed version bump"

  # 3. Tag
  git -C "$REPO_ROOT" tag -a "$tag" -m "Release $component $new_version"
  ok "Created tag $tag"

  # 4. Push
  echo ""
  read -rp "  Push commit + tag to origin? [Y/n] " yn
  if [[ ! "$yn" =~ ^[Nn]$ ]]; then
    git -C "$REPO_ROOT" push origin HEAD
    git -C "$REPO_ROOT" push origin "$tag"
    ok "Pushed to origin — CI will build and publish"
  else
    info "Skipped push. Run manually:"
    echo "    git push origin HEAD && git push origin $tag"
  fi

  echo ""
  echo -e "  ${GREEN}${BOLD}Done!${NC} $component $new_version released."
}

# ── Main ──────────────────────────────────────────────────────
cd "$REPO_ROOT"

echo ""
echo -e "${BOLD}docu-store release${NC}"
echo ""

show_versions
preflight

# Accept args or prompt
component="${1:-}"
bump_type="${2:-}"

if [[ -z "$component" ]]; then
  component=$(pick_component)
fi

if [[ -z "$bump_type" ]]; then
  case "$component" in
    services) cur=$(read_services_version) ;;
    web)      cur=$(read_json_version "$WEB_VERSION_FILE") ;;
    cli)      cur=$(read_json_version "$CLI_VERSION_FILE") ;;
    *) err "Unknown component: $component"; exit 1 ;;
  esac
  bump_type=$(pick_bump "$cur")
fi

do_release "$component" "$bump_type"
