#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "${ROOT_DIR}/../../.." && pwd)"
VENDOR_DIR="${ROOT_DIR}/vendor/goose"
PATCH_DIR="${ROOT_DIR}/patches"
BASE_PATCH="${PATCH_DIR}/goose-vendor-base.patch"
OVERLAY_PATCH="${PATCH_DIR}/goose-vendor-overlay.patch"
UPSTREAM_SHA="4f7bf8c1e281863932b42b65577b4d7be04214b0"
OVERLAY_MARKER="super::routes::agent::call_tool,"

# Файлы без trailing newline в upstream blob. Windows checkout/autocrlf часто
# дописывает \n — тогда git apply падает с "patch does not apply".
NO_EOF_NL_PATHS=(
  "crates/goose/src/prompts/tiny_model_system.md"
  "ui/desktop/forge.deb.desktop"
  "ui/desktop/forge.rpm.desktop"
)

require_inputs() {
  if [[ ! -d "${VENDOR_DIR}/.git" && ! -f "${VENDOR_DIR}/.git" ]]; then
    echo "Goose vendor checkout missing: ${VENDOR_DIR}" >&2
    exit 1
  fi
  for patch_path in "${BASE_PATCH}" "${OVERLAY_PATCH}"; do
    if [[ ! -s "${patch_path}" ]]; then
      echo "Goose vendor patch missing or empty: ${patch_path}" >&2
      exit 1
    fi
  done
}

vendor_git() {
  # Без CRLF/eol-конверсии: патчи собраны на точных upstream blob.
  git -C "${VENDOR_DIR}" -c core.autocrlf=false -c core.eol=lf "$@"
}

restore_exact_blobs() {
  local rel
  for rel in "${NO_EOF_NL_PATHS[@]}"; do
    vendor_git cat-file blob "HEAD:${rel}" > "${VENDOR_DIR}/${rel}"
  done
}

reset_vendor_to_upstream() {
  local head_sha
  head_sha="$(vendor_git rev-parse HEAD)"
  if [[ "${head_sha}" != "${UPSTREAM_SHA}" ]]; then
    echo "Goose vendor HEAD must be ${UPSTREAM_SHA}, got ${head_sha}" >&2
    exit 1
  fi
  vendor_git reset --hard "${UPSTREAM_SHA}"
  vendor_git clean -fd
  vendor_git checkout-index --force --all
  # checkout-index --force -c core.autocrlf=false/core.eol=lf на Windows-
  # раннере GitHub Actions эмпирически не гарантирует LF на диске (checkout-
  # machinery Git for Windows ведёт себя иначе, чем на macOS/Linux, где то же
  # решение работает) — LF-based base-патч не матчился ни по одному файлу.
  # Детерминированно нормализуем CRLF->LF по всем tracked-файлам напрямую,
  # без зависимости от платформенного поведения checkout/reset.
  (cd "${REPO_ROOT}" && vendor_git ls-files -z | uv run python "${ROOT_DIR}/scripts/normalize_vendor_line_endings.py" "${VENDOR_DIR}")
  restore_exact_blobs
}

apply_base_patch() {
  # Каждый pre начинается с чистого upstream: иначе branding ломает overlay.
  reset_vendor_to_upstream
  vendor_git apply --check --whitespace=nowarn "${BASE_PATCH}"
  vendor_git apply --whitespace=nowarn "${BASE_PATCH}"
  echo "Applied Goose vendor base patch"
}

overlay_already_present() {
  local openapi_path="${VENDOR_DIR}/crates/goose-server/src/openapi.rs"
  if [[ ! -f "${openapi_path}" ]]; then
    return 1
  fi
  grep -Fq "${OVERLAY_MARKER}" "${openapi_path}"
}

apply_overlay_patch() {
  # Marker устойчив к последующему branding (иконки/имена branding не трогает openapi.rs).
  if overlay_already_present; then
    echo "Goose vendor overlay already present"
    return
  fi

  vendor_git apply --check --whitespace=nowarn "${OVERLAY_PATCH}"
  vendor_git apply --whitespace=nowarn "${OVERLAY_PATCH}"
  echo "Applied Goose vendor overlay"
}

require_inputs
case "${1:-all}" in
  pre)
    apply_base_patch
    ;;
  post)
    apply_overlay_patch
    ;;
  all)
    apply_base_patch
    apply_overlay_patch
    "${ROOT_DIR}/scripts/apply_branding.sh"
    ;;
  *)
    echo "Usage: $0 [pre|post|all]" >&2
    exit 2
    ;;
esac
