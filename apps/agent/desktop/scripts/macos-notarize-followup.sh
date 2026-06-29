#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/../../.." && pwd)"

usage() {
  echo "Usage: $0 --repo OWNER/REPO [--release-tag TAG] [--version-sha SHA] [--all-pending]" >&2
  echo "Requires: APPLE_ID, APPLE_ID_PASSWORD, APPLE_TEAM_ID, gh CLI" >&2
}

REPO=""
RELEASE_TAG=""
VERSION_SHA=""
ALL_PENDING="0"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo)
      REPO="$2"
      shift 2
      ;;
    --release-tag)
      RELEASE_TAG="$2"
      shift 2
      ;;
    --version-sha)
      VERSION_SHA="$2"
      shift 2
      ;;
    --all-pending)
      ALL_PENDING="1"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ -z "${REPO}" ]]; then
  echo "repo is required" >&2
  usage
  exit 1
fi

for required in APPLE_ID APPLE_ID_PASSWORD APPLE_TEAM_ID; do
  if [[ -z "${!required:-}" ]]; then
    echo "Missing env: ${required}" >&2
    exit 1
  fi
done

pushd "${REPO_ROOT}" >/dev/null
if [[ "${ALL_PENDING}" == "1" ]]; then
  uv run python scripts/agent_build.py notarize-followup \
    --repo "${REPO}" \
    --all-pending
else
  if [[ -z "${RELEASE_TAG}" ]]; then
    echo "--release-tag is required unless --all-pending is set" >&2
    exit 1
  fi
  followup_args=(
    notarize-followup
    --repo "${REPO}"
    --release-tag "${RELEASE_TAG}"
  )
  if [[ -n "${VERSION_SHA}" ]]; then
    followup_args+=(--version-sha "${VERSION_SHA}")
  fi
  uv run python scripts/agent_build.py "${followup_args[@]}"
fi
popd >/dev/null
