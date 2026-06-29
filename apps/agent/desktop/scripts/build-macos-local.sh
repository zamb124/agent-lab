#!/usr/bin/env bash
# Локальная macOS-сборка HumanitecAgent: sign + notarize + DMG.
# Notarization не гоняется в CI (AGENT_MACOS_NOTARIZE=0) — только на Mac разработчика.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/../../.." && pwd)"

usage() {
  echo "Usage: $0 [--platform macos-arm64|macos-x64] [--version-sha SHA]" >&2
  echo "Requires: Developer ID in keychain, APPLE_ID, APPLE_ID_PASSWORD, APPLE_TEAM_ID" >&2
}

PLATFORM=""
VERSION_SHA="$(git -C "${REPO_ROOT}" rev-parse HEAD 2>/dev/null || echo local)"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)
      PLATFORM="$2"
      shift 2
      ;;
    --version-sha)
      VERSION_SHA="$2"
      shift 2
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

if [[ "$(uname -s)" != "Darwin" ]]; then
  echo "macOS local build requires Darwin host" >&2
  exit 1
fi

if [[ -z "${PLATFORM}" ]]; then
  case "$(uname -m)" in
    arm64) PLATFORM="macos-arm64" ;;
    x86_64) PLATFORM="macos-x64" ;;
    *)
      echo "Unsupported machine: $(uname -m)" >&2
      exit 1
      ;;
  esac
  echo "Auto-detected platform: ${PLATFORM}"
fi

case "${PLATFORM}" in
  macos-arm64|macos-x64) ;;
  *)
    echo "Unsupported platform: ${PLATFORM}" >&2
    usage
    exit 1
    ;;
esac

for required in APPLE_ID APPLE_ID_PASSWORD APPLE_TEAM_ID; do
  if [[ -z "${!required:-}" ]]; then
    echo "Missing env: ${required}" >&2
    exit 1
  fi
done

if [[ -z "${KEYCHAIN_PATH:-}" ]]; then
  KEYCHAIN_PATH="${HOME}/Library/Keychains/login.keychain-db"
  export KEYCHAIN_PATH
  echo "Using login keychain: ${KEYCHAIN_PATH}"
fi

if ! security find-identity -v -p codesigning "${KEYCHAIN_PATH}" \
  | grep -q 'Developer ID Application'; then
  echo "Developer ID Application not found in ${KEYCHAIN_PATH}" >&2
  echo "Import .p12: security import cert.p12 -k login.keychain -P 'password' -T /usr/bin/codesign" >&2
  exit 1
fi

export AGENT_MACOS_NOTARIZE=1
export AGENT_VERIFY_CODESIGN=1
export AGENT_VERIFY_MACOS_NOTARIZED=1
export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-12.0}"

echo "Building ${PLATFORM} (version ${VERSION_SHA}) with notarization..."
"${ROOT_DIR}/scripts/build.sh" \
  --platform "${PLATFORM}" \
  --artifact-mode release \
  --version-sha "${VERSION_SHA}"

DIST_DIR="${ROOT_DIR}/dist"
echo "Artifact:"
ls -la "${DIST_DIR}/"*"${PLATFORM}"*.dmg 2>/dev/null || ls -la "${DIST_DIR}/"

echo "Verify locally:"
echo "  hdiutil attach ${DIST_DIR}/HumanitecAgent-${PLATFORM}-${VERSION_SHA}.dmg"
echo "  spctl -a -vv /Volumes/HumanitecAgent/HumanitecAgent.app"
