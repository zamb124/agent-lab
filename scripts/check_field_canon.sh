#!/usr/bin/env bash
# Field canon: запрет сырых <input>/<textarea>/<select> в
# apps/<svc>/ui/{pages,modals,components}/**, кроме whitelist и platform-field tree.
#
# Whitelist для сырых тегов (всё остальное поле формы — только <platform-field>):
#   * <input type="file|hidden|range|color|checkbox|radio|search">
#   * атрибут data-canon="composer|mention|inline-edit|search-as-you-type|combobox"
#
# Классы form-input / field-pill-input в приложениях не считаются обёрткой — только whitelist выше или platform-field.
# В check_ui_canon.sh не включён (см. п.16 там).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
    echo "check_field_canon: нужен ripgrep (rg)" >&2
    exit 1
fi

ERR=0
fail() { echo "check_field_canon: $1" >&2; ERR=1; }

FIELD_CANON_DIRS=()
for svc in apps/*/ui; do
    [ -d "$svc/pages" ] && FIELD_CANON_DIRS+=("$svc/pages")
    [ -d "$svc/modals" ] && FIELD_CANON_DIRS+=("$svc/modals")
    [ -d "$svc/components" ] && FIELD_CANON_DIRS+=("$svc/components")
done

if [ "${#FIELD_CANON_DIRS[@]}" -eq 0 ]; then
    echo "check_field_canon: OK (no UI directories)"
    exit 0
fi

BAD_INPUT='<input\b(?![^>]*\btype=["'\''](?:file|hidden|range|color|checkbox|radio|search)["'\''])(?![^>]*\bdata-canon=)[^>]*>'
if rg -nUP --multiline-dotall "${BAD_INPUT}" "${FIELD_CANON_DIRS[@]}" -g '*.js' >/dev/null 2>&1; then
    fail "raw <input> в apps/<svc>/ui/{pages,modals,components}/**: только whitelist type=, либо data-canon, иначе <platform-field> (см. .cursor/rules/data-types.mdc)"
    rg -nUP --multiline-dotall "${BAD_INPUT}" "${FIELD_CANON_DIRS[@]}" -g '*.js' >&2 || true
fi

BAD_TEXTAREA='<textarea\b(?![^>]*\bdata-canon=)[^>]*>'
if rg -nUP --multiline-dotall "${BAD_TEXTAREA}" "${FIELD_CANON_DIRS[@]}" -g '*.js' >/dev/null 2>&1; then
    fail "raw <textarea>: только data-canon или замените на <platform-field type='text'>"
    rg -nUP --multiline-dotall "${BAD_TEXTAREA}" "${FIELD_CANON_DIRS[@]}" -g '*.js' >&2 || true
fi

BAD_SELECT='<select\b(?![^>]*\bdata-canon=)[^>]*>'
if rg -nUP --multiline-dotall "${BAD_SELECT}" "${FIELD_CANON_DIRS[@]}" -g '*.js' >/dev/null 2>&1; then
    fail "raw <select>: только data-canon='combobox' или <platform-field type='enum'>"
    rg -nUP --multiline-dotall "${BAD_SELECT}" "${FIELD_CANON_DIRS[@]}" -g '*.js' >&2 || true
fi

if [ "$ERR" -ne 0 ]; then
    exit 1
fi

echo "check_field_canon: OK"
