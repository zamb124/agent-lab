#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENDOR_DIR="${ROOT_DIR}/vendor/goose"
PATCH_DIR="${ROOT_DIR}/patches"
BASE_PATCH="${PATCH_DIR}/goose-vendor-base.patch"
OVERLAY_PATCH="${PATCH_DIR}/goose-vendor-overlay.patch"
UPSTREAM_SHA="4f7bf8c1e281863932b42b65577b4d7be04214b0"

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

apply_base_patch() {
  local sentinel="${VENDOR_DIR}/ui/desktop/src/humanitecDistro.ts"
  if [[ -f "${sentinel}" ]]; then
    echo "Goose vendor base patch already present"
    return
  fi

  local head_sha
  head_sha="$(git -C "${VENDOR_DIR}" rev-parse HEAD)"
  if [[ "${head_sha}" != "${UPSTREAM_SHA}" ]]; then
    echo "Goose vendor base must be ${UPSTREAM_SHA}, got ${head_sha}" >&2
    exit 1
  fi

  git -C "${VENDOR_DIR}" apply --check "${BASE_PATCH}"
  git -C "${VENDOR_DIR}" apply "${BASE_PATCH}"
  echo "Applied Goose vendor base patch"
}

apply_overlay_patch() {
  if git -C "${VENDOR_DIR}" apply --reverse --check "${OVERLAY_PATCH}" >/dev/null 2>&1; then
    echo "Goose vendor overlay already present"
    return
  fi

  git -C "${VENDOR_DIR}" apply --check "${OVERLAY_PATCH}"
  git -C "${VENDOR_DIR}" apply "${OVERLAY_PATCH}"
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
    "${ROOT_DIR}/scripts/apply_branding.sh"
    apply_overlay_patch
    ;;
  *)
    echo "Usage: $0 [pre|post|all]" >&2
    exit 2
    ;;
esac
