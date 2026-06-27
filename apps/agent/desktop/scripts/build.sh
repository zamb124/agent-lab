#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/../../.." && pwd)"
VENDOR_DIR="${ROOT_DIR}/vendor/goose"
DISTRO_JSON="${ROOT_DIR}/distro/humanitec.json"
OUTPUT_DIR="${AGENT_OUTPUT_DIR:-${ROOT_DIR}/dist}"

PLATFORM=""
ARTIFACT_MODE="release"
VERSION_SHA="${GITHUB_SHA:-local}"

usage() {
  echo "Usage: $0 --platform <windows|macos-arm64|macos-x64|linux-deb|linux-rpm|linux-appimage> [--artifact-mode placeholder|release] [--version-sha SHA]" >&2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --platform)
      PLATFORM="$2"
      shift 2
      ;;
    --artifact-mode)
      ARTIFACT_MODE="$2"
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

if [[ -z "${PLATFORM}" ]]; then
  echo "platform is required" >&2
  usage
  exit 1
fi

if [[ ! -f "${DISTRO_JSON}" ]]; then
  echo "Distro config missing: ${DISTRO_JSON}" >&2
  exit 1
fi

read_distro_field() {
  uv run python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))[sys.argv[2]])' "${DISTRO_JSON}" "$1"
}

artifact_filename() {
  uv run python - "${DISTRO_JSON}" "${PLATFORM}" "${VERSION_SHA}" "${REPO_ROOT}" <<'PY'
import sys
from pathlib import Path

distro_path = Path(sys.argv[1])
platform_name = sys.argv[2]
version_sha = sys.argv[3]
repo_root = Path(sys.argv[4])
sys.path.insert(0, str(repo_root))
from apps.agent.desktop.build_contract import artifact_filename, load_distro_config

distro = load_distro_config(distro_path)
print(artifact_filename(platform_name, version_sha, distro.bundle_name))
PY
}

build_placeholder() {
  mkdir -p "${OUTPUT_DIR}"
  local filename
  filename="$(artifact_filename)"
  local display_name protocol_scheme bundle_name
  bundle_name="$(read_distro_field bundle_name)"
  display_name="$(read_distro_field display_name)"
  protocol_scheme="$(read_distro_field protocol_scheme)"
  cat > "${OUTPUT_DIR}/${filename}" <<EOF
HumanitecAgent placeholder for ${PLATFORM} (${VERSION_SHA})
display_name=${display_name}
bundle_name=${bundle_name}
protocol_scheme=${protocol_scheme}
platform=${PLATFORM}
version_sha=${VERSION_SHA}
EOF
  echo "Built placeholder: ${OUTPUT_DIR}/${filename}"
}

build_goosed_binary() {
  pushd "${VENDOR_DIR}" >/dev/null
  cargo build --release -p goose-server
  popd >/dev/null
  mkdir -p "${VENDOR_DIR}/ui/desktop/src/bin"
  cp "${VENDOR_DIR}/target/release/goosed" "${VENDOR_DIR}/ui/desktop/src/bin/"
}

build_release() {
  if [[ ! -d "${VENDOR_DIR}" ]]; then
    echo "Goose vendor tree missing: ${VENDOR_DIR}" >&2
    echo "Run: git submodule update --init apps/agent/desktop/vendor/goose" >&2
    exit 1
  fi

  export GITHUB_OWNER="${GITHUB_OWNER:-zamb124}"
  export GITHUB_REPO="${GITHUB_REPO:-agent-lab}"
  export GOOSE_BUNDLE_NAME
  GOOSE_BUNDLE_NAME="$(read_distro_field bundle_name)"

  chmod +x "${ROOT_DIR}/scripts/apply_branding.sh"
  "${ROOT_DIR}/scripts/apply_branding.sh"

  mkdir -p "${OUTPUT_DIR}"
  local filename
  filename="$(artifact_filename)"

  case "${PLATFORM}" in
    macos-arm64|macos-x64)
      if ! command -v pnpm >/dev/null 2>&1; then
        echo "pnpm is required for macOS Goose desktop build" >&2
        exit 1
      fi
      if ! command -v cargo >/dev/null 2>&1; then
        echo "cargo is required for Goose server build" >&2
        exit 1
      fi
      build_goosed_binary
      pushd "${VENDOR_DIR}/ui/desktop" >/dev/null
      pnpm install --frozen-lockfile
      if [[ "${PLATFORM}" == "macos-x64" ]]; then
        export ELECTRON_ARCH=x64
        pnpm run bundle:intel
      else
        pnpm run bundle:default
      fi
      popd >/dev/null
      built_dmg_path="$(find "${VENDOR_DIR}/ui/desktop/out" -name "*.dmg" -type f | head -n 1)"
      if [[ -n "${built_dmg_path}" ]]; then
        cp "${built_dmg_path}" "${OUTPUT_DIR}/${filename}"
      else
        app_path="$(find "${VENDOR_DIR}/ui/desktop/out" -name "${GOOSE_BUNDLE_NAME}.app" -type d | head -n 1)"
        if [[ -z "${app_path}" ]]; then
          echo "Goose desktop build did not produce .dmg or .app" >&2
          exit 1
        fi
        if ! command -v hdiutil >/dev/null 2>&1; then
          echo "hdiutil is required to pack ${GOOSE_BUNDLE_NAME}.app into .dmg" >&2
          exit 1
        fi
        rm -f "${OUTPUT_DIR}/${filename}"
        hdiutil create \
          -volname "${GOOSE_BUNDLE_NAME}" \
          -srcfolder "${app_path}" \
          -ov \
          -format UDZO \
          "${OUTPUT_DIR}/${filename}"
      fi
      ;;
    linux-deb|linux-rpm|linux-appimage)
      if ! command -v pnpm >/dev/null 2>&1; then
        echo "pnpm is required for Linux Goose desktop build" >&2
        exit 1
      fi
      if ! command -v cargo >/dev/null 2>&1; then
        echo "cargo is required for Goose server build" >&2
        exit 1
      fi
      build_goosed_binary
      pushd "${VENDOR_DIR}/ui/desktop" >/dev/null
      pnpm install --frozen-lockfile
      case "${PLATFORM}" in
        linux-deb) pnpm run make -- --targets=@electron-forge/maker-deb ;;
        linux-rpm) pnpm run make -- --targets=@electron-forge/maker-rpm ;;
        linux-appimage) pnpm run make -- --targets=@electron-forge/maker-appimage ;;
      esac
      popd >/dev/null
      built_artifact_path="$(find "${VENDOR_DIR}/ui/desktop/out/make" -type f \( -name "*.deb" -o -name "*.rpm" -o -name "*.AppImage" \) | head -n 1)"
      if [[ -z "${built_artifact_path}" ]]; then
        echo "Goose desktop build did not produce Linux artifact" >&2
        exit 1
      fi
      cp "${built_artifact_path}" "${OUTPUT_DIR}/${filename}"
      ;;
    windows)
      if ! command -v pnpm >/dev/null 2>&1; then
        echo "pnpm is required for Windows Goose desktop build" >&2
        exit 1
      fi
      if ! command -v cargo >/dev/null 2>&1; then
        echo "cargo is required for Goose server build on Windows" >&2
        exit 1
      fi
      build_goosed_binary
      pushd "${VENDOR_DIR}/ui/desktop" >/dev/null
      pnpm install --frozen-lockfile
      pnpm run make -- --targets=@electron-forge/maker-squirrel
      popd >/dev/null
      built_msi_path="$(find "${VENDOR_DIR}/ui/desktop/out/make" -name "*.msi" -type f | head -n 1)"
      if [[ -z "${built_msi_path}" ]]; then
        echo "Goose desktop build did not produce .msi" >&2
        exit 1
      fi
      cp "${built_msi_path}" "${OUTPUT_DIR}/${filename}"
      ;;
    *)
      echo "Unsupported platform: ${PLATFORM}" >&2
      exit 1
      ;;
  esac

  echo "Built release artifact: ${OUTPUT_DIR}/${filename}"
}

case "${ARTIFACT_MODE}" in
  placeholder)
    build_placeholder
    ;;
  release)
    build_release
    ;;
  *)
    echo "Unsupported artifact mode: ${ARTIFACT_MODE}" >&2
    exit 1
    ;;
esac
