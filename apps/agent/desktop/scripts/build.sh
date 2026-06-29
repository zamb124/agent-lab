#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/../../.." && pwd)"
VENDOR_DIR="${ROOT_DIR}/vendor/goose"
GOOSE_UI_DIR="${VENDOR_DIR}/ui"
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
    diagnose_desktop_build_state
    echo "electron-forge did not create ${DESKTOP_DIR}/out" >&2
    exit 1
  fi
}

require_desktop_make_dir() {
  require_desktop_out_dir
  if [[ ! -d "${DESKTOP_DIR}/out/make" ]]; then
    diagnose_desktop_build_state
    echo "electron-forge did not create ${DESKTOP_DIR}/out/make" >&2
    exit 1
  fi
}

install_desktop_node_modules() {
  if [[ ! -f "${GOOSE_UI_DIR}/pnpm-lock.yaml" ]]; then
    echo "Goose UI lockfile missing: ${GOOSE_UI_DIR}/pnpm-lock.yaml" >&2
    exit 1
  fi
  # Единый install для всех платформ из корня Goose UI monorepo: только так
  # отрабатывает postinstall electron (onlyBuiltDependencies в ui/package.json)
  # и в node_modules/electron/dist оказывается реальный бинарь, а не только locales.
  pushd "${GOOSE_UI_DIR}" >/dev/null
  pnpm install --frozen-lockfile
  popd >/dev/null
  require_electron_dist
  case "${PLATFORM}" in
    windows|linux-deb|linux-rpm|linux-appimage)
      # Makers wix/appimage отсутствуют в lockfile Goose; добавляем их после
      # frozen-install, когда electron уже корректно собран и не будет затронут.
      pushd "${DESKTOP_DIR}" >/dev/null
      pnpm add -D @electron-forge/maker-wix@^7.11.1 @reforged/maker-appimage@^5.2.0
      popd >/dev/null
      require_electron_dist
      ;;
  esac
}

electron_dist_marker() {
  case "${PLATFORM}" in
    macos-arm64|macos-x64) echo "Electron.app" ;;
    windows) echo "electron.exe" ;;
    linux-deb|linux-rpm|linux-appimage) echo "electron" ;;
    *)
      echo "Unsupported platform for electron dist check: ${PLATFORM}" >&2
      exit 1
      ;;
  esac
}

require_electron_dist() {
  local dist_dir=""
  dist_dir="$(find "${GOOSE_UI_DIR}" -path "*/node_modules/electron/dist" -type d 2>/dev/null | head -n 1)"
  if [[ -z "${dist_dir}" ]]; then
    echo "electron dist missing after pnpm install under ${GOOSE_UI_DIR}" >&2
    diagnose_desktop_build_state
    exit 1
  fi
  local marker
  marker="$(electron_dist_marker)"
  if [[ ! -e "${dist_dir}/${marker}" ]]; then
    echo "electron dist present but ${marker} missing in ${dist_dir}" >&2
    ls -la "${dist_dir}" >&2 || true
    exit 1
  fi
  echo "electron dist ready: ${dist_dir}/${marker}"
}

run_desktop_i18n_compile() {
  pushd "${DESKTOP_DIR}" >/dev/null
  pnpm run i18n:compile
  popd >/dev/null
}

run_desktop_forge() {
  local forge_subcommand="$1"
  shift
  local forge_log="${DESKTOP_DIR}/forge-${forge_subcommand}.log"
  run_desktop_i18n_compile
  local forge_exit=0
  pushd "${DESKTOP_DIR}" >/dev/null
  set +e
  DEBUG="${FORGE_DEBUG:-electron-forge:*,electron-packager,@electron/universal,@electron/osx-sign,@reforged/*}" \
    pnpm exec electron-forge "${forge_subcommand}" "$@" >"${forge_log}" 2>&1
  forge_exit=$?
  set -e
  popd >/dev/null
  cat "${forge_log}"
  if [[ "${forge_exit}" -ne 0 ]]; then
    echo "electron-forge ${forge_subcommand} failed with exit code ${forge_exit}; log: ${forge_log}" >&2
    if [[ -f "${forge_log}" ]]; then
      echo "Last 200 lines of ${forge_log}:" >&2
      tail -n 200 "${forge_log}" >&2 || true
    fi
    diagnose_desktop_build_state
    exit "${forge_exit}"
  fi
  if [[ ! -d "${DESKTOP_DIR}/out" ]]; then
    echo "electron-forge ${forge_subcommand} returned exit ${forge_exit} but ${DESKTOP_DIR}/out was not created" >&2
    echo "Searching for out/ directories under workspace:" >&2
    find "${GOOSE_UI_DIR}" -maxdepth 3 -name out -type d 2>/dev/null >&2 || true
    if [[ -f "${forge_log}" ]]; then
      echo "Last 200 lines of ${forge_log}:" >&2
      tail -n 200 "${forge_log}" >&2 || true
    fi
    diagnose_desktop_build_state
    exit 1
  fi
}

run_desktop_forge_make() {
  local forge_target="$1"
  shift
  run_desktop_forge make --targets="${forge_target}" "$@"
}

run_desktop_forge_macos_zip() {
  local package_arch="$1"
  if [[ "${package_arch}" == "x64" ]]; then
    export ELECTRON_ARCH=x64
    run_desktop_forge make --targets="@electron-forge/maker-zip" --arch x64
  else
    run_desktop_forge make --targets="@electron-forge/maker-zip" --arch arm64
  fi
}

macos_package_arch() {
  if [[ "${PLATFORM}" == "macos-x64" ]]; then
    echo "x64"
  else
    echo "arm64"
  fi
}

diagnose_desktop_build_state() {
  echo "Desktop build diagnostics (${PLATFORM}):" >&2
  echo "  disk usage:" >&2
  df -h "${DESKTOP_DIR}" >&2 2>/dev/null || df -h >&2 2>/dev/null || true
  if [[ -d "${DESKTOP_DIR}" ]]; then
    ls -la "${DESKTOP_DIR}" >&2 || true
  else
    echo "  missing desktop dir: ${DESKTOP_DIR}" >&2
  fi
  if [[ -d "${DESKTOP_DIR}/src/bin" ]]; then
    echo "  src/bin:" >&2
    ls -la "${DESKTOP_DIR}/src/bin" >&2 || true
    if [[ -f "${DESKTOP_DIR}/src/bin/goosed" ]]; then
      file "${DESKTOP_DIR}/src/bin/goosed" >&2 || true
      if command -v codesign >/dev/null 2>&1; then
        codesign -dv --verbose=4 "${DESKTOP_DIR}/src/bin/goosed" >&2 || true
      fi
    fi
  else
    echo "  missing src/bin" >&2
  fi
  if [[ -d "${DESKTOP_DIR}/out" ]]; then
    echo "  out:" >&2
    ls -la "${DESKTOP_DIR}/out" >&2 || true
  else
    echo "  missing out/" >&2
  fi
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
  # macos-x64 собирается на arm64-раннере (macos-14): Intel-раннер macos-13
  # недоступен/висит в очереди. Под x86_64 нужен явный target и кросс-сборка;
  # macos-arm64/linux/windows остаются нативной сборкой в target/release.
  local cargo_target=""
  if [[ "${PLATFORM}" == "macos-x64" ]]; then
    cargo_target="x86_64-apple-darwin"
  fi
  pushd "${VENDOR_DIR}" >/dev/null
  if [[ -n "${cargo_target}" ]]; then
    rustup target add "${cargo_target}"
    cargo build --release -p goose-server --target "${cargo_target}"
  else
    cargo build --release -p goose-server
  fi
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
    local goosed_release_dir="${VENDOR_DIR}/target/release"
    if [[ -n "${cargo_target}" ]]; then
      goosed_release_dir="${VENDOR_DIR}/target/${cargo_target}/release"
    fi
    local goosed_bin="${goosed_release_dir}/goosed"
    if [[ ! -f "${goosed_bin}" ]]; then
      echo "Rust build did not produce goosed: ${goosed_bin}" >&2
      exit 1
    fi
    cp "${goosed_bin}" "${DESKTOP_DIR}/src/bin/"
    chmod +x "${DESKTOP_DIR}/src/bin/goosed"
  fi
}

macos_signing_enabled() {
  if [[ -z "${APPLE_TEAM_ID:-}" ]]; then
    return 1
  fi
  return 0
}

macos_notarize_mode() {
  echo "${AGENT_MACOS_NOTARIZE:-0}"
}

macos_notarize_sync_enabled() {
  if ! macos_signing_enabled; then
    return 1
  fi
  if [[ "$(macos_notarize_mode)" != "1" ]]; then
    return 1
  fi
  return 0
}

macos_notarize_submit_only_enabled() {
  if ! macos_signing_enabled; then
    return 1
  fi
  if [[ "$(macos_notarize_mode)" != "submit-only" ]]; then
    return 1
  fi
  return 0
}

macos_notarization_enabled() {
  macos_notarize_sync_enabled || macos_notarize_submit_only_enabled
}

resolve_macos_signing_identity() {
  if [[ -z "${KEYCHAIN_PATH:-}" ]]; then
    echo "KEYCHAIN_PATH is required for macOS signing" >&2
    exit 1
  fi
  local signing_identity=""
  signing_identity="$(security find-identity -v -p codesigning "${KEYCHAIN_PATH}" \
    | awk -F'"' '/Developer ID Application/ { print $2; exit }')"
  if [[ -z "${signing_identity}" ]]; then
    echo "Developer ID Application identity not found in keychain ${KEYCHAIN_PATH}" >&2
    security find-identity -v -p codesigning "${KEYCHAIN_PATH}" >&2 || true
    exit 1
  fi
  echo "${signing_identity}"
}

verify_macos_goosed_arch() {
  local goosed_bin="${DESKTOP_DIR}/src/bin/goosed"
  if [[ ! -f "${goosed_bin}" ]]; then
    echo "goosed binary missing for arch verification: ${goosed_bin}" >&2
    exit 1
  fi
  if ! command -v file >/dev/null 2>&1; then
    echo "file command is required for macOS goosed arch verification" >&2
    exit 1
  fi
  local file_output=""
  file_output="$(file "${goosed_bin}")"
  echo "goosed arch check: ${file_output}"
  case "${PLATFORM}" in
    macos-x64)
      if ! grep -q 'x86_64' <<<"${file_output}"; then
        echo "macos-x64 build requires x86_64 goosed binary, got: ${file_output}" >&2
        exit 1
      fi
      ;;
    macos-arm64)
      if ! grep -q 'arm64' <<<"${file_output}"; then
        echo "macos-arm64 build requires arm64 goosed binary, got: ${file_output}" >&2
        exit 1
      fi
      ;;
    *)
      echo "Unsupported macOS platform for goosed arch verification: ${PLATFORM}" >&2
      exit 1
      ;;
  esac
}

sign_macos_goosed_binary() {
  if ! macos_signing_enabled; then
    echo "macOS signing disabled — skipping goosed pre-sign"
    return 0
  fi
  local goosed_bin="${DESKTOP_DIR}/src/bin/goosed"
  local entitlements_path="${ROOT_DIR}/distro/goosed.entitlements.plist"
  if [[ ! -f "${goosed_bin}" ]]; then
    echo "goosed binary missing before pre-sign: ${goosed_bin}" >&2
    exit 1
  fi
  if [[ ! -f "${entitlements_path}" ]]; then
    echo "entitlements.plist missing: ${entitlements_path}" >&2
    exit 1
  fi
  verify_macos_goosed_arch
  local signing_identity=""
  signing_identity="$(resolve_macos_signing_identity)"
  echo "Pre-signing goosed with identity: ${signing_identity}"
  codesign --force --sign "${signing_identity}" \
    --options runtime --timestamp \
    --entitlements "${entitlements_path}" \
    "${goosed_bin}"
  codesign --verify --deep --strict "${goosed_bin}"
  echo "goosed pre-sign complete"
}

assert_macos_app_ready_for_notarization() {
  local app_path="$1"
  if ! command -v codesign >/dev/null 2>&1; then
    echo "codesign is required before macOS notarization" >&2
    exit 1
  fi
  echo "Verifying ${app_path} signature before notarization"
  codesign --verify --deep --strict "${app_path}"
  local goosed_in_app="${app_path}/Contents/Resources/bin/goosed"
  if [[ ! -f "${goosed_in_app}" ]]; then
    echo "goosed missing in app bundle before notarization: ${goosed_in_app}" >&2
    exit 1
  fi
  codesign --verify --deep --strict "${goosed_in_app}"
}

macos_app_bundle_asset_name() {
  uv run python - "${DISTRO_JSON}" "${PLATFORM}" "${VERSION_SHA}" "${REPO_ROOT}" <<'PY'
import sys
from pathlib import Path

distro_path = Path(sys.argv[1])
platform_name = sys.argv[2]
version_sha = sys.argv[3]
repo_root = Path(sys.argv[4])
sys.path.insert(0, str(repo_root))
from apps.agent.desktop.build_contract import load_distro_config, macos_app_bundle_asset_filename

distro = load_distro_config(distro_path)
print(macos_app_bundle_asset_filename(platform_name, version_sha, distro.bundle_name))
PY
}

macos_notarize_fragment_name() {
  uv run python - "${DISTRO_JSON}" "${PLATFORM}" "${VERSION_SHA}" "${REPO_ROOT}" <<'PY'
import sys
from pathlib import Path

distro_path = Path(sys.argv[1])
platform_name = sys.argv[2]
version_sha = sys.argv[3]
repo_root = Path(sys.argv[4])
sys.path.insert(0, str(repo_root))
from apps.agent.desktop.build_contract import load_distro_config, macos_notarize_fragment_filename

distro = load_distro_config(distro_path)
print(macos_notarize_fragment_filename(platform_name, version_sha, distro.bundle_name))
PY
}

export_macos_app_bundle_zip() {
  local app_path="$1"
  local zip_path="$2"
  ditto -c -k --keepParent "${app_path}" "${zip_path}"
}

package_macos_dmg() {
  local app_path="$1"
  local dmg_path="$2"
  local volume_name="$3"
  if ! command -v hdiutil >/dev/null 2>&1; then
    echo "hdiutil is required to pack ${volume_name}.app into .dmg" >&2
    exit 1
  fi
  rm -f "${dmg_path}"
  local dmg_staging=""
  dmg_staging="$(mktemp -d)"
  cp -R "${app_path}" "${dmg_staging}/"
  ln -s /Applications "${dmg_staging}/Applications"
  hdiutil create \
    -volname "${volume_name}" \
    -srcfolder "${dmg_staging}" \
    -ov \
    -format UDZO \
    "${dmg_path}"
  rm -rf "${dmg_staging}"
}

write_macos_notarize_fragment() {
  local submission_id="$1"
  local app_bundle_asset="$2"
  local dmg_asset="$3"
  local fragment_path=""
  fragment_path="${OUTPUT_DIR}/$(macos_notarize_fragment_name)"
  uv run python - "${fragment_path}" "${PLATFORM}" "${VERSION_SHA}" "${submission_id}" "${app_bundle_asset}" "${dmg_asset}" "${REPO_ROOT}" <<'PY'
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

fragment_path = Path(sys.argv[1])
platform_name = sys.argv[2]
version_sha = sys.argv[3]
submission_id = sys.argv[4]
app_bundle_asset = sys.argv[5]
dmg_asset = sys.argv[6]
repo_root = Path(sys.argv[7])
sys.path.insert(0, str(repo_root))
from apps.agent.desktop.macos_notarize import MacosNotarizeFragment, MacosNotarizeStatus

submitted_at = datetime.now(tz=UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
fragment = MacosNotarizeFragment(
    platform=platform_name,
    version_sha=version_sha,
    submission_id=submission_id,
    submitted_at=submitted_at,
    status=MacosNotarizeStatus.PENDING,
    app_bundle_asset=app_bundle_asset,
    dmg_asset=dmg_asset,
)
fragment_path.parent.mkdir(parents=True, exist_ok=True)
fragment_path.write_text(json.dumps(fragment.model_dump(mode="json"), indent=2) + "\n", encoding="utf-8")
print(fragment_path)
PY
}

submit_macos_notarization() {
  local app_path="$1"
  assert_macos_app_ready_for_notarization "${app_path}"
  local zip_path=""
  local zip_bytes=""
  zip_path="$(mktemp -t humanitec-agent-notarize-XXXXXX).zip"
  ditto -c -k --keepParent "${app_path}" "${zip_path}"
  zip_bytes="$(wc -c <"${zip_path}" | tr -d ' ')"
  echo "Notarization zip ready: ${zip_path} (${zip_bytes} bytes)"
  echo "Submitting ${app_path} for notarization"

  local submission_id=""
  local submit_attempt=1
  local submit_max_attempts="${NOTARY_SUBMIT_MAX_ATTEMPTS:-3}"
  while [[ "${submit_attempt}" -le "${submit_max_attempts}" ]]; do
    local submit_json=""
    local submit_stderr=""
    submit_json="$(mktemp -t humanitec-notary-submit-XXXXXX.json)"
    submit_stderr="$(mktemp -t humanitec-notary-submit-XXXXXX.err)"
    set +e
    xcrun notarytool submit "${zip_path}" \
      --apple-id "${APPLE_ID}" \
      --password "${APPLE_ID_PASSWORD}" \
      --team-id "${APPLE_TEAM_ID}" \
      --output-format json >"${submit_json}" 2>"${submit_stderr}"
    local submit_exit=$?
    set -e
    if [[ "${submit_exit}" -eq 0 ]]; then
      submission_id="$(uv run python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["id"])' "${submit_json}")"
      rm -f "${submit_json}" "${submit_stderr}"
      echo "Notarization submission id: ${submission_id}"
      rm -f "${zip_path}"
      echo "${submission_id}"
      return 0
    fi
    cat "${submit_stderr}" >&2 || true
    cat "${submit_json}" >&2 || true
    rm -f "${submit_json}" "${submit_stderr}"
    if [[ "${submit_attempt}" -eq "${submit_max_attempts}" ]]; then
      echo "notarytool submit failed after ${submit_max_attempts} attempts" >&2
      rm -f "${zip_path}"
      exit 1
    fi
    local submit_backoff=$((submit_attempt * 30))
    echo "notarytool submit failed (attempt ${submit_attempt}/${submit_max_attempts}); retrying in ${submit_backoff}s..." >&2
    sleep "${submit_backoff}"
    submit_attempt=$((submit_attempt + 1))
  done
}

handle_macos_notarization() {
  local app_path="$1"
  local dmg_asset="$2"
  if macos_notarize_submit_only_enabled; then
    if [[ -z "${APPLE_ID:-}" ]]; then
      echo "APPLE_ID is required for macOS submit-only notarization" >&2
      exit 1
    fi
    if [[ -z "${APPLE_ID_PASSWORD:-}" ]]; then
      echo "APPLE_ID_PASSWORD is required for macOS submit-only notarization" >&2
      exit 1
    fi
    local app_bundle_asset=""
    app_bundle_asset="$(macos_app_bundle_asset_name)"
    local app_bundle_zip="${OUTPUT_DIR}/${app_bundle_asset}"
    export_macos_app_bundle_zip "${app_path}" "${app_bundle_zip}"
    echo "Stored app bundle for async notarization: ${app_bundle_zip}"
    local submission_id=""
    submission_id="$(submit_macos_notarization "${app_path}")"
    write_macos_notarize_fragment "${submission_id}" "${app_bundle_asset}" "${dmg_asset}"
    return 0
  fi
  if macos_notarize_sync_enabled; then
    notarize_macos_app_bundle_sync "${app_path}"
    return 0
  fi
  echo "macOS notarization skipped (AGENT_MACOS_NOTARIZE=${AGENT_MACOS_NOTARIZE:-0})."
}

poll_notary_submission_until_complete() {
  local submission_id="$1"
  local max_wait_seconds="${NOTARY_MAX_WAIT_SECONDS:-5400}"
  local poll_interval="${NOTARY_POLL_INTERVAL_SECONDS:-60}"
  local elapsed=0
  while [[ "${elapsed}" -lt "${max_wait_seconds}" ]]; do
    local info_json=""
    info_json="$(mktemp -t humanitec-notary-info-XXXXXX.json)"
    local info_stderr=""
    info_stderr="$(mktemp -t humanitec-notary-info-XXXXXX.err)"
    set +e
    xcrun notarytool info "${submission_id}" \
      --apple-id "${APPLE_ID}" \
      --password "${APPLE_ID_PASSWORD}" \
      --team-id "${APPLE_TEAM_ID}" \
      --output-format json >"${info_json}" 2>"${info_stderr}"
    local info_exit=$?
    set -e
    if [[ "${info_exit}" -ne 0 ]]; then
      cat "${info_stderr}" >&2 || true
      rm -f "${info_json}" "${info_stderr}"
      echo "notarytool info failed for ${submission_id} (network?), retrying in ${poll_interval}s..." >&2
      sleep "${poll_interval}"
      elapsed=$((elapsed + poll_interval))
      continue
    fi
    rm -f "${info_stderr}"
    local notary_status=""
    notary_status="$(uv run python -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["status"])' "${info_json}")"
    rm -f "${info_json}"
    echo "Notarization status for ${submission_id}: ${notary_status} (elapsed ${elapsed}s / max ${max_wait_seconds}s)"
    case "${notary_status}" in
      Accepted)
        return 0
        ;;
      Invalid|Rejected)
        echo "Notarization rejected for ${submission_id}" >&2
        xcrun notarytool log "${submission_id}" \
          --apple-id "${APPLE_ID}" \
          --password "${APPLE_ID_PASSWORD}" \
          --team-id "${APPLE_TEAM_ID}" >&2 || true
        exit 1
        ;;
      "In Progress")
        sleep "${poll_interval}"
        elapsed=$((elapsed + poll_interval))
        ;;
      *)
        echo "Unexpected notary status '${notary_status}' for ${submission_id}" >&2
        exit 1
        ;;
    esac
  done
  echo "Notarization timed out after ${max_wait_seconds}s for ${submission_id}" >&2
  xcrun notarytool log "${submission_id}" \
    --apple-id "${APPLE_ID}" \
    --password "${APPLE_ID_PASSWORD}" \
    --team-id "${APPLE_TEAM_ID}" >&2 || true
  exit 1
}

notarize_macos_app_bundle_sync() {
  local app_path="$1"
  if [[ -z "${APPLE_ID:-}" ]]; then
    echo "APPLE_ID is required for macOS notarization" >&2
    exit 1
  fi
  if [[ -z "${APPLE_ID_PASSWORD:-}" ]]; then
    echo "APPLE_ID_PASSWORD is required for macOS notarization" >&2
    exit 1
  fi
  if [[ ! -d "${app_path}" ]]; then
    echo "macOS app bundle missing for notarization: ${app_path}" >&2
    exit 1
  fi
  local submission_id=""
  submission_id="$(submit_macos_notarization "${app_path}")"
  poll_notary_submission_until_complete "${submission_id}"
  xcrun stapler staple "${app_path}"
  echo "Notarization and stapling complete for ${app_path}"
  if [[ "${AGENT_VERIFY_MACOS_NOTARIZED:-0}" == "1" ]]; then
    if ! command -v spctl >/dev/null 2>&1; then
      echo "spctl is required when AGENT_VERIFY_MACOS_NOTARIZED=1" >&2
      exit 1
    fi
    spctl -a -vv "${app_path}"
  fi
}

notarize_macos_app_bundle() {
  local app_path="$1"
  notarize_macos_app_bundle_sync "${app_path}"
}

bundle_windows_runtime_dlls() {
  local bin_dir="${DESKTOP_DIR}/src/bin"
  local goosed_exe="${bin_dir}/goosed.exe"
  local bundle_script="${ROOT_DIR}/scripts/bundle_windows_runtime_dlls.ps1"
  if [[ ! -f "${bundle_script}" ]]; then
    echo "Windows runtime bundle script missing: ${bundle_script}" >&2
    exit 1
  fi
  if [[ ! -f "${goosed_exe}" ]]; then
    echo "goosed.exe missing before runtime bundle: ${goosed_exe}" >&2
    exit 1
  fi
  powershell.exe -NoProfile -ExecutionPolicy Bypass \
    -File "${bundle_script}" \
    -DestDir "${bin_dir}" \
    -GoosedExe "${goosed_exe}"
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
      sign_macos_goosed_binary
      install_desktop_node_modules
      prepare_desktop_binaries
      export MACOSX_DEPLOYMENT_TARGET="${MACOSX_DEPLOYMENT_TARGET:-12.0}"
      # Staging electron-packager на том же томе, что out/ (а не системный $TMPDIR
      # на отдельном маленьком томе раннера), вне каталога проекта.
      export ELECTRON_PACKAGER_TMPDIR="${REPO_ROOT}/.electron-packager-tmp"
      mkdir -p "${ELECTRON_PACKAGER_TMPDIR}"
      local package_arch
      package_arch="$(macos_package_arch)"
      run_desktop_forge_macos_zip "${package_arch}"
      require_desktop_out_dir
      local app_dir app_path
      app_dir="${DESKTOP_DIR}/out/${GOOSE_BUNDLE_NAME}-darwin-${package_arch}"
      app_path="${app_dir}/${GOOSE_BUNDLE_NAME}.app"
      if [[ ! -d "${app_path}" ]]; then
        app_path="$(find "${DESKTOP_DIR}/out" -name "${GOOSE_BUNDLE_NAME}.app" -type d | head -n 1)"
      fi
      if [[ -z "${app_path}" || ! -d "${app_path}" ]]; then
        diagnose_desktop_build_state
        echo "Goose desktop package did not produce ${GOOSE_BUNDLE_NAME}.app" >&2
        exit 1
      fi
      handle_macos_notarization "${app_path}" "${filename}"
      package_macos_dmg "${app_path}" "${OUTPUT_DIR}/${filename}" "${GOOSE_BUNDLE_NAME}"
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
      case "${PLATFORM}" in
        linux-deb) run_desktop_forge_make "@electron-forge/maker-deb" ;;
        linux-rpm) run_desktop_forge_make "@electron-forge/maker-rpm" ;;
        linux-appimage) run_desktop_forge_make "@reforged/maker-appimage" ;;
      esac
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
      bundle_windows_runtime_dlls
      install_desktop_node_modules
      prepare_desktop_binaries
      run_desktop_forge_make "@electron-forge/maker-wix"
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
