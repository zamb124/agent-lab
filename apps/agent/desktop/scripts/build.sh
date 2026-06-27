#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/../../.." && pwd)"
VENDOR_DIR="${ROOT_DIR}/vendor/goose"
DISTRO_JSON="${ROOT_DIR}/distro/humanitec.json"
OUTPUT_DIR="${AGENT_OUTPUT_DIR:-${ROOT_DIR}/dist}"
DESKTOP_DIR="${VENDOR_DIR}/ui/desktop"

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

is_windows_host() {
  case "$(uname -s)" in
    MINGW*|MSYS*|CYGWIN*) return 0 ;;
    *) return 1 ;;
  esac
}

require_desktop_out_dir() {
  if [[ ! -d "${DESKTOP_DIR}/out" ]]; then
    echo "electron-forge did not create ${DESKTOP_DIR}/out" >&2
    exit 1
  fi
}

require_desktop_make_dir() {
  require_desktop_out_dir
  if [[ ! -d "${DESKTOP_DIR}/out/make" ]]; then
    echo "electron-forge did not create ${DESKTOP_DIR}/out/make" >&2
    exit 1
  fi
}

install_desktop_node_modules() {
  pushd "${DESKTOP_DIR}" >/dev/null
  pnpm add -D @electron-forge/maker-wix@^7.11.1 @reforged/maker-appimage@^5.2.0
  pnpm install
  popd >/dev/null
}

prepare_desktop_binaries() {
  pushd "${DESKTOP_DIR}" >/dev/null
  node scripts/prepare-platform-binaries.js
  popd >/dev/null
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
  mkdir -p "${DESKTOP_DIR}/src/bin"
  if is_windows_host; then
    local goosed_exe="${VENDOR_DIR}/target/release/goosed.exe"
    if [[ ! -f "${goosed_exe}" ]]; then
      echo "Rust build did not produce goosed.exe: ${goosed_exe}" >&2
      exit 1
    fi
    cp "${goosed_exe}" "${DESKTOP_DIR}/src/bin/"
    shopt -s nullglob
    local dll_path
    for dll_path in "${VENDOR_DIR}/target/release/"*.dll; do
      cp "${dll_path}" "${DESKTOP_DIR}/src/bin/"
    done
    shopt -u nullglob
  else
    local goosed_bin="${VENDOR_DIR}/target/release/goosed"
    if [[ ! -f "${goosed_bin}" ]]; then
      echo "Rust build did not produce goosed: ${goosed_bin}" >&2
      exit 1
    fi
    cp "${goosed_bin}" "${DESKTOP_DIR}/src/bin/"
  fi
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
      install_desktop_node_modules
      prepare_desktop_binaries
      pushd "${DESKTOP_DIR}" >/dev/null
      if [[ "${PLATFORM}" == "macos-x64" ]]; then
        export ELECTRON_ARCH=x64
        pnpm run make -- --targets=@electron-forge/maker-zip --arch=x64
      else
        pnpm run make -- --targets=@electron-forge/maker-zip
      fi
      popd >/dev/null
      require_desktop_out_dir
      built_dmg_path="$(find "${DESKTOP_DIR}/out" -name "*.dmg" -type f | head -n 1)"
      if [[ -n "${built_dmg_path}" ]]; then
        cp "${built_dmg_path}" "${OUTPUT_DIR}/${filename}"
      else
        app_path="$(find "${DESKTOP_DIR}/out" -name "${GOOSE_BUNDLE_NAME}.app" -type d | head -n 1)"
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
      install_desktop_node_modules
      prepare_desktop_binaries
      pushd "${DESKTOP_DIR}" >/dev/null
      case "${PLATFORM}" in
        linux-deb) pnpm run make -- --targets=@electron-forge/maker-deb ;;
        linux-rpm) pnpm run make -- --targets=@electron-forge/maker-rpm ;;
        linux-appimage) pnpm run make -- --targets=@reforged/maker-appimage ;;
      esac
      popd >/dev/null
      require_desktop_make_dir
      built_artifact_path="$(find "${DESKTOP_DIR}/out/make" -type f \( -name "*.deb" -o -name "*.rpm" -o -name "*.AppImage" \) | head -n 1)"
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
      install_desktop_node_modules
      prepare_desktop_binaries
      pushd "${DESKTOP_DIR}" >/dev/null
      pnpm run make -- --targets=@electron-forge/maker-wix
      popd >/dev/null
      require_desktop_make_dir
      built_msi_path="$(find "${DESKTOP_DIR}/out/make" -name "*.msi" -type f | head -n 1)"
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
