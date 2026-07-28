#!/usr/bin/env bash
# Проверка архитектурного канона UI (Full Event Sourcing).
#
# Применяется ко всему `apps/*/ui` без исключений: все сервисы должны быть
# мигрированы под единый event-driven канон.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if ! command -v rg >/dev/null 2>&1; then
    echo "check_ui_canon: нужен ripgrep (rg)" >&2
    exit 1
fi

ERR=0
fail() { echo "check_ui_canon: $1" >&2; ERR=1; }

# 0. Motion canon: единый core motion layer вместо разрозненных transition: all.
MOTION_GLOBS=( apps/*/ui core/frontend/static -g '*.js' -g '*.css' --glob '!**/*.min.js' )
if rg -q 'transition:\s*all\b' "${MOTION_GLOBS[@]}"; then
    fail "transition: all запрещён — используйте --motion-transition-interactive или явный список compositor-friendly свойств"
    rg -n 'transition:\s*all\b' "${MOTION_GLOBS[@]}" >&2 || true
fi

# 1. Только PlatformElement / PlatformApp / PlatformPage наследование.
if rg -q 'extends LitElement' apps -g '*.js'; then
    fail "запрещено extends LitElement в apps/**/*.js"
    rg 'extends LitElement' apps -g '*.js' >&2 || true
fi
while IFS= read -r platform_app_file; do
    if ! rg -q 'static platformAssistant\s*=' "$platform_app_file"; then
        fail "$platform_app_file: каждый PlatformApp обязан задать static platformAssistant"
    fi
done < <(rg -l 'extends PlatformApp\b' apps -g '*-app.js')

# 2. Импорты core lib только через @platform/lib/...
if rg -q "from ['\"]/static/core/lib" apps -g '*.js'; then
    fail "импорты из /static/core/lib обходят import map; используйте @platform/lib/..."
    rg "from ['\"]/static/core/lib" apps -g '*.js' >&2 || true
fi

# 3. Запрещённые импорты старого канона (модулей нет — но проверяем чтобы не вернулись).
if rg -q "from ['\"]@platform/lib/services/(BaseService|ServiceRegistry|platform-services-bootstrap)" apps -g '*.js'; then
    fail "ServiceRegistry/BaseService запрещены в apps/**"
    rg "from ['\"]@platform/lib/services/" apps -g '*.js' >&2 || true
fi
if rg -q "from ['\"]@platform/lib/store/" apps -g '*.js'; then
    fail "BaseStore запрещён в apps/**"
    rg "from ['\"]@platform/lib/store/" apps -g '*.js' >&2 || true
fi
if rg -q "from ['\"]@platform/services/" apps -g '*.js'; then
    fail "старые сервисы (auth/icon/theme/...) удалены — используйте dispatch/select"
    rg "from ['\"]@platform/services/" apps -g '*.js' >&2 || true
fi
if rg -q "from ['\"]@platform/lib/utils/(use-store|types)\.js" apps -g '*.js'; then
    fail "use-store / AppEvents удалены"
    rg "from ['\"]@platform/lib/utils/(use-store|types)\.js" apps -g '*.js' >&2 || true
fi
if rg -q "from ['\"]@platform/lib/router/" apps -g '*.js'; then
    fail "Router.js удалён — маршрутизация через router.effect"
    rg "from ['\"]@platform/lib/router/" apps -g '*.js' >&2 || true
fi

# 4. Запрещённые имена в коде.
if rg -q '\bServiceRegistry\b' apps -g '*.js'; then
    fail "ServiceRegistry не существует"
    rg '\bServiceRegistry\b' apps -g '*.js' >&2 || true
fi
if rg -q '\bBaseStore\b' apps -g '*.js'; then
    fail "BaseStore не существует"
    rg '\bBaseStore\b' apps -g '*.js' >&2 || true
fi
if rg -q '\bAppEvents\b' apps -g '*.js'; then
    fail "AppEvents удалены — CoreEvents / <svc>Events"
    rg '\bAppEvents\b' apps -g '*.js' >&2 || true
fi

# 5. new CustomEvent в apps — запрещено (в core разрешено для composition).
if rg -q 'new CustomEvent\(' apps -g '*.js'; then
    fail "new CustomEvent в apps/** запрещено; используйте this.dispatch(...)"
    rg 'new CustomEvent\(' apps -g '*.js' >&2 || true
fi

# 6. Доступ к старым геттерам PlatformElement.
#    `icon` удалён из списка: это — реактивное property Lit-компонентов
#    (`<dashboard-stat-tile icon="..."/>`, `<sidebar-nav-item icon="..."/>`),
#    а не IconService-геттер (его в платформе нет). Для иконок в компонентах
#    используется `<platform-icon name="...">` в рендере.
if rg -q 'this\.(services|auth|notify|theme|companies|calendarApi|filesApi|fileTypes|team|a2a|syncWs|syncApi|crmApi|ragApi)\b' apps -g '*.js'; then
    fail "this.services / this.auth / this.theme / ... удалены — используйте dispatch/select"
    rg 'this\.(services|auth|notify|theme|companies|calendarApi|filesApi|fileTypes|team|a2a|syncWs|syncApi|crmApi|ragApi)\b' apps -g '*.js' >&2 || true
fi

# 7. fetch / axios в компонентах — только в effects/.
if rg -q '\bfetch\(' apps -g '*.js' --glob '!apps/*/ui/events/effects/**'; then
    fail "fetch вне events/effects/** запрещён"
    rg '\bfetch\(' apps -g '*.js' --glob '!apps/*/ui/events/effects/**' >&2 || true
fi

# 8. Запрещены каталоги старого канона.
for svc in apps/*/ui; do
    [ -d "$svc/services" ] && fail "$svc/services запрещён — HTTP в events/effects"
    [ -d "$svc/store" ] && fail "$svc/store запрещён — данные в events/reducers"
    [ -d "$svc/stores" ] && fail "$svc/stores запрещён — данные в events/reducers"
done

# 9. Modal canon: открытие модалок только через dispatch UI_MODAL_OPEN.
#    Запрещены createElement('*-modal') и appendChild на body для модалок.
MOD_GLOBS=( apps -g '*.js' --glob '!apps/*/ui/assets/**' --glob '!**/*.min.js' )
if rg -q "createElement\(\s*['\"][a-z0-9_-]*-modal['\"]" "${MOD_GLOBS[@]}"; then
    fail "createElement('*-modal') запрещён — открывайте модалку через dispatch(CoreEvents.UI_MODAL_OPEN, { kind, props })"
    rg -n "createElement\(\s*['\"][a-z0-9_-]*-modal['\"]" "${MOD_GLOBS[@]}" >&2 || true
fi
# Прямая мутация .open на модалке — запрещена; стек управляет открытием.
BAD_OPEN="$(rg -n "\.open\s*=\s*(true|false)\b" "${MOD_GLOBS[@]}" --glob '!apps/*/ui/events/**' || true)"
if [ -n "$BAD_OPEN" ]; then
    fail "прямое .open=true/false на модалке запрещено — dispatch UI_MODAL_OPEN/CLOSE"
    echo "$BAD_OPEN" >&2
fi
# document.body.appendChild для модалок — запрещён.
if rg -q "document\.body\.appendChild\(\s*[a-zA-Z_]+-?[a-zA-Z_]*[Mm]odal" "${MOD_GLOBS[@]}"; then
    fail "document.body.appendChild для модалок запрещён — модалки рендерятся platform-modal-stack"
    rg -n "document\.body\.appendChild\(\s*[a-zA-Z_]+-?[a-zA-Z_]*[Mm]odal" "${MOD_GLOBS[@]}" >&2 || true
fi

# 10. Запрет легаси window-событий sidebar/breadcrumbs/office-list — переехало на bus.
LEGACY_WINDOW_EVENTS=(
    'platform-sidebar-open'
    'platform-sidebar-mobile-change'
    'office-documents-list-reload'
)
LEGACY_GLOBS=(
    apps -g '*.js' --glob '!apps/*/ui/assets/**' --glob '!**/*.min.js'
    core/frontend/static -g '*.js' --glob '!**/*.min.js'
)
for ev in "${LEGACY_WINDOW_EVENTS[@]}"; do
    if rg -q "window\.(addEventListener|dispatchEvent)\(\s*['\"]?${ev}\b|new CustomEvent\(\s*['\"]${ev}['\"]" "${LEGACY_GLOBS[@]}"; then
        fail "легаси window-событие '${ev}' — переехало на bus (CoreEvents)"
        rg -n "window\.(addEventListener|dispatchEvent)\(\s*['\"]?${ev}\b|new CustomEvent\(\s*['\"]${ev}['\"]" "${LEGACY_GLOBS[@]}" >&2 || true
    fi
done
# CustomEvent('navigate') в роутинге — теперь dispatch ROUTER_NAVIGATE_REQUESTED.
if rg -q "new CustomEvent\(\s*['\"]navigate['\"]" "${LEGACY_GLOBS[@]}"; then
    fail "CustomEvent('navigate') запрещён — dispatch CoreEvents.ROUTER_NAVIGATE_REQUESTED"
    rg -n "new CustomEvent\(\s*['\"]navigate['\"]" "${LEGACY_GLOBS[@]}" >&2 || true
fi

# 11. Запрет старых геттеров в core/frontend/static/lib (кроме standalone chat-surface —
#     у platform-chat свой бутстрап, а `theme` — его reactive property/attribute,
#     контракт embed-виджета, не ThemeService).
#     `icon` удалён из списка: reactive property Lit-компонентов
#     (`<sidebar-nav-item icon="...">`, `<platform-panel icon="...">`), а не
#     IconService (его нет).
CORE_LIB_GLOBS=( core/frontend/static/lib -g '*.js' --glob '!core/frontend/static/lib/chat/platform-chat.js' )
if rg -q 'this\.(services|auth|notify|theme|companies|calendarApi|filesApi|fileTypes|team|a2a|syncWs|syncApi|crmApi|ragApi)\b' "${CORE_LIB_GLOBS[@]}"; then
    fail "this.services/this.calendarApi/... в core/lib — используйте dispatch(<SLICE_EVENTS>) и select"
    rg -n 'this\.(services|auth|notify|theme|companies|calendarApi|filesApi|fileTypes|team|a2a|syncWs|syncApi|crmApi|ragApi)\b' "${CORE_LIB_GLOBS[@]}" >&2 || true
fi

# 12. Имена событий: this.dispatch('<scope>/<entity>/<verb>') — snake_case, >= 3 сегмента.
BAD_DISPATCH="$(rg -nU "this\.dispatch\(\s*['\"]([^'\"]+)['\"]" apps -g '*.js' \
    | grep -vE "this\.dispatch\(\s*['\"][a-z][a-z0-9_]*(/[a-z][a-z0-9_]*){2,}['\"]" || true)"
if [ -n "$BAD_DISPATCH" ]; then
    fail "dispatch с именем не по контракту scope/entity/verb (snake_case, >= 3)"
    echo "$BAD_DISPATCH" >&2
fi

# 13. Factory canon — pages и modals в мигрированных сервисах не лезут в фабрики/контроллеры/CoreEvents напрямую.
#     Canon: единственная точка входа — helpers PlatformElement (useResource/useOp/useForm/useCursorList/useFacets/useSlice,
#     openModal/closeModal/toast/copyToClipboard/navigate). I18nNs не нужен — namespace резолвится через
#     static i18nNamespace или PlatformApp.defaultI18nNamespace.
FACTORY_CANON_SERVICES=( frontend crm rag sync office flows provider_litserve voice wiki )
for svc in "${FACTORY_CANON_SERVICES[@]}"; do
    # rg падает с error если ни одной из переданных директорий нет; игнорируем
    # отсутствующие (например, у provider_litserve нет модалок).
    PG_DIRS=()
    [ -d "apps/${svc}/ui/pages" ] && PG_DIRS+=("apps/${svc}/ui/pages")
    [ -d "apps/${svc}/ui/modals" ] && PG_DIRS+=("apps/${svc}/ui/modals")
    if [ "${#PG_DIRS[@]}" -eq 0 ]; then
        continue
    fi
    PG_GLOBS=( "${PG_DIRS[@]}" -g '*.js' )

    if rg -q "from ['\"]@platform/lib/events/controllers/" "${PG_GLOBS[@]}"; then
        fail "${svc}: pages/modals не импортируют контроллеры напрямую — используйте this.useResource/useOp/..."
        rg -n "from ['\"]@platform/lib/events/controllers/" "${PG_GLOBS[@]}" >&2 || true
    fi
    if rg -q "from ['\"]@platform/lib/utils/i18n-namespace\.js['\"]" "${PG_GLOBS[@]}"; then
        fail "${svc}: I18nNs в pages/modals запрещён — namespace резолвится автоматически или строкой"
        rg -n "from ['\"]@platform/lib/utils/i18n-namespace\.js['\"]" "${PG_GLOBS[@]}" >&2 || true
    fi
    if rg -q "from ['\"]\.\./events/resources/[^'\"]+['\"]" "${PG_GLOBS[@]}"; then
        fail "${svc}: pages/modals не импортируют resource-объекты напрямую — используйте this.useResource('<svc>/<name>')"
        rg -n "from ['\"]\.\./events/resources/[^'\"]+['\"]" "${PG_GLOBS[@]}" >&2 || true
    fi
    if rg -q "from ['\"]\.\./\.\./events/resources/[^'\"]+['\"]" "${PG_GLOBS[@]}"; then
        fail "${svc}: pages/modals не импортируют resource-объекты напрямую — используйте this.useResource('<svc>/<name>')"
        rg -n "from ['\"]\.\./\.\./events/resources/[^'\"]+['\"]" "${PG_GLOBS[@]}" >&2 || true
    fi
    if rg -q "new (ResourceController|OpController|FormController|CursorListController|FacetsController|SliceController)\b" "${PG_GLOBS[@]}"; then
        fail "${svc}: ручное new <X>Controller в pages/modals запрещено — this.useResource/useOp/useForm/useCursorList/useFacets/useSlice"
        rg -n "new (ResourceController|OpController|FormController|CursorListController|FacetsController|SliceController)\b" "${PG_GLOBS[@]}" >&2 || true
    fi
    if rg -q "this\.dispatch\(\s*CoreEvents\.(UI_TOAST_SHOW|UI_MODAL_OPEN|UI_MODAL_CLOSE|UI_CLIPBOARD_COPY_REQUESTED|ROUTER_NAVIGATE_REQUESTED)\b" "${PG_GLOBS[@]}"; then
        fail "${svc}: прямой dispatch CoreEvents.UI_*/ROUTER_NAVIGATE_REQUESTED в pages/modals — используйте this.toast/openModal/closeModal/copyToClipboard/navigate"
        rg -n "this\.dispatch\(\s*CoreEvents\.(UI_TOAST_SHOW|UI_MODAL_OPEN|UI_MODAL_CLOSE|UI_CLIPBOARD_COPY_REQUESTED|ROUTER_NAVIGATE_REQUESTED)\b" "${PG_GLOBS[@]}" >&2 || true
    fi
    if [ -d "apps/${svc}/ui/events/effects" ]; then
        fail "${svc}: apps/${svc}/ui/events/effects/ удалена — вся side-effect логика в фабриках events/resources/*"
    fi
done

# 14. Анти-паттерны рантайма для МИГРИРОВАННЫХ сервисов и core/frontend/static/lib/**:
#     - super.showModal()                           — у GlassModal нет showModal(); открывайте через openModal()
#     - this.bus.getState() в компонентах          — читайте состояние через this.select(...)
#     - 'await (this.dispatch(...))' / fake await  — диспатч fire-and-forget, ответы — через useEvent
#     - this.i18n.getCurrentLocale() / this.i18n.t — i18n только через this.t(...) и this.select(s => s.i18n.locale)
RUNTIME_ANTI_GLOBS=(
    apps -g '*.js'
    --glob '!apps/*/ui/events/**'
    --glob '!apps/*/ui/assets/**'
    --glob '!**/*.min.js'
    core/frontend/static/lib -g '*.js'
    --glob '!core/frontend/static/lib/platform-element/**'
    --glob '!core/frontend/static/lib/events/**'
)
if rg -q 'super\.showModal\s*\(' "${RUNTIME_ANTI_GLOBS[@]}"; then
    fail "super.showModal() запрещено — у GlassModal нет showModal(), открывайте через openModal('<kind>')"
    rg -n 'super\.showModal\s*\(' "${RUNTIME_ANTI_GLOBS[@]}" >&2 || true
fi
if rg -q 'this\.bus\.getState\s*\(' "${RUNTIME_ANTI_GLOBS[@]}"; then
    fail "this.bus.getState() запрещён в компонентах — используйте this.select(s => ...)"
    rg -n 'this\.bus\.getState\s*\(' "${RUNTIME_ANTI_GLOBS[@]}" >&2 || true
fi
if rg -q 'await\s*\(\s*\(?\s*this\.dispatch\s*\(' "${RUNTIME_ANTI_GLOBS[@]}"; then
    fail "fake await на this.dispatch(...) запрещён — диспатч fire-and-forget; ответ ловите через useEvent(*_COMPLETED/*_FAILED)"
    rg -n 'await\s*\(\s*\(?\s*this\.dispatch\s*\(' "${RUNTIME_ANTI_GLOBS[@]}" >&2 || true
fi
if rg -q 'this\.i18n\.(getCurrentLocale|t)\s*\(' "${RUNTIME_ANTI_GLOBS[@]}"; then
    fail "this.i18n.* запрещено — используйте this.t(key) и this.select(s => s.i18n.locale)"
    rg -n 'this\.i18n\.(getCurrentLocale|t)\s*\(' "${RUNTIME_ANTI_GLOBS[@]}" >&2 || true
fi

# 15. Запрет фолбеков `|| [] / || {} / || null / || ''` в events/resources/**
#     (zero-fallback канон фабрик; дефолты — только в initialSlice / extraInitial).
RESOURCES_FALLBACK_PATTERN='\|\|\s*\[\]|\|\|\s*\{\}|\|\|\s*null\b|\|\|\s*['\''"]\s*['\''"]'
if rg -q "${RESOURCES_FALLBACK_PATTERN}" apps -g '*.resource.js'; then
    fail "фолбеки '|| [] / || {} / || null / ' в apps/**/events/resources/**.resource.js запрещены — нормализуйте через _normalize<X> или initialSlice"
    rg -n "${RESOURCES_FALLBACK_PATTERN}" apps -g '*.resource.js' >&2 || true
fi
# Запрет `?? []` / `?? {}` / `?? null` / `?? '—'` в events/resources/** — та же
# логика фолбеков, но через nullish coalescing.
RESOURCES_NULLISH_PATTERN='\?\?\s*\[\]|\?\?\s*\{\}|\?\?\s*null\b|\?\?\s*['\''"]'
if rg -q "${RESOURCES_NULLISH_PATTERN}" apps -g '*.resource.js'; then
    fail "фолбеки '?? [] / ?? {} / ?? null / ?? \"\"' в apps/**/events/resources/**.resource.js запрещены"
    rg -n "${RESOURCES_NULLISH_PATTERN}" apps -g '*.resource.js' >&2 || true
fi

# 16. Field canon (raw <input>/<textarea>/<select>) — отдельный детектор
#     scripts/check_field_canon.sh (make check-field-canon). Здесь: п.17 (.form-*/.field-pill*
#     CSS в apps/<svc>/ui/**) и 18 (импорт glass-input/glass-textarea).

# 17. Локальные .form-* / .field-pill* CSS правила в apps/<svc>/ui/** запрещены —
#     стили только в core/frontend/static/lib/styles/shared/field-pill.styles.js;
#     кастомизация — токены --field-pill-* в core/frontend/static/assets/css/tokens.css.
PILL_CSS_PATTERN='\.(form-(input|textarea|select|group|label)|field-pill(-(input|textarea|select|label|empty|readonly-text|readonly-muted|readonly-inline)|--(textarea|tags))?)\s*[\{,]'
if rg -nP "${PILL_CSS_PATTERN}" apps -g '*.js' >/dev/null 2>&1; then
    fail "локальные .form-*/.field-pill* CSS правила в apps/<svc>/ui/**.js запрещены — стили только в core/frontend/static/lib/styles/shared/field-pill.styles.js (токены --field-pill-* в tokens.css)"
    rg -nP "${PILL_CSS_PATTERN}" apps -g '*.js' >&2 || true
fi

# 18. Импорт удалённых glass-input / glass-textarea — запрещён.
GLASS_INPUT_PATTERN="from\s+['\"]@platform/lib/components/glass-(input|textarea)\.js['\"]"
if rg -nP "${GLASS_INPUT_PATTERN}" apps core -g '*.js' >/dev/null 2>&1; then
    fail "импорт @platform/lib/components/glass-(input|textarea).js запрещён — компоненты удалены в PHASE 1.5; используйте <platform-field type='string|text' input-type='...'>"
    rg -nP "${GLASS_INPUT_PATTERN}" apps core -g '*.js' >&2 || true
fi

# 19. Utility canon: локальные дубли core форматтеров / валидаторов / escape / hash в apps/<svc>/ui/**.
#     Вся «общая» утильность (formatFileSize / formatDuration / formatPlatformNumber /
#     formatPlatformDate / escapeHtml / hashString31 / EMAIL_RE / digitsOnly /
#     placeholder-storage-keys) живёт в core/frontend/static/lib/utils/.
#     Локальная копия — нарушение DRY и канона.
APPS_UI_GLOBS=( apps -g '*.js' --glob 'apps/*/ui/**' )

# 19a. Hardcoded 'ru-RU' в Intl.* / toLocaleString / toLocaleDateString.
RUHARDCODE_PATTERN="Intl\.(NumberFormat|DateTimeFormat)\(\s*['\"]ru-RU['\"]|toLocale(Date|Time)?String\(\s*['\"]ru-RU['\"]"
if rg -nP "${RUHARDCODE_PATTERN}" "${APPS_UI_GLOBS[@]}" >/dev/null 2>&1; then
    fail "hardcoded 'ru-RU' в Intl.* / toLocaleString запрещён — используйте core/utils/format-platform-{number,date}.js с локалью из state.i18n"
    rg -nP "${RUHARDCODE_PATTERN}" "${APPS_UI_GLOBS[@]}" >&2 || true
fi

# 19b. Локальный EMAIL regex / digitsOnly / phone проверка.
EMAIL_RE_PATTERN="\bEMAIL_RE\b\s*=\s*/|\b_digitsOnly\s*\(|/\^\[\^\\\\s@\]\+@"
if rg -nP "${EMAIL_RE_PATTERN}" "${APPS_UI_GLOBS[@]}" >/dev/null 2>&1; then
    fail "локальный EMAIL_RE / _digitsOnly / email regex запрещён — используйте core/utils/validators.js (isValidEmail, digitsOnly, isValidPhone, EMAIL_RE)"
    rg -nP "${EMAIL_RE_PATTERN}" "${APPS_UI_GLOBS[@]}" >&2 || true
fi

# 19c. Локальный escapeHtml.
ESCAPE_HTML_PATTERN="function\s+escapeHtml\s*\(|const\s+escapeHtml\s*=\s*function|const\s+escapeHtml\s*=\s*\("
if rg -nP "${ESCAPE_HTML_PATTERN}" "${APPS_UI_GLOBS[@]}" >/dev/null 2>&1; then
    fail "локальный escapeHtml запрещён — используйте core/utils/escape-html.js"
    rg -nP "${ESCAPE_HTML_PATTERN}" "${APPS_UI_GLOBS[@]}" >&2 || true
fi

# 19d. Локальный hash*31 цикл вне core/.
LOCAL_HASH_PATTERN="h\s*=\s*\(\s*h\s*\*\s*31\s*\+\s*[a-zA-Z_]+\.charCodeAt"
if rg -nP "${LOCAL_HASH_PATTERN}" "${APPS_UI_GLOBS[@]}" >/dev/null 2>&1; then
    fail "локальный hash*31 цикл запрещён — используйте core/utils/hash-string.js (hashString31, hueFromString, indexFromSeed)"
    rg -nP "${LOCAL_HASH_PATTERN}" "${APPS_UI_GLOBS[@]}" >&2 || true
fi

# 20. Mobile shell 2026 canon: гамбургер в apps/<svc>/ui/** запрещён.
#     - Старые компоненты *-mobile-app-header — удалены, новые такие имена запрещены.
#     - this.openSidebar() в apps/<svc>/ui/{pages,modals,components}/** — антипаттерн.
#     - <platform-bottom-nav> / <platform-bottom-sheet-stack> / <platform-top-bar> рендерит только PlatformApp (core).
MOBILE_HEADER_PATTERN="customElements\.define\(\s*['\"][a-z0-9_-]*-mobile-app-header['\"]"
if rg -nP "${MOBILE_HEADER_PATTERN}" "${APPS_UI_GLOBS[@]}" >/dev/null 2>&1; then
    fail "компонент *-mobile-app-header запрещён — mobile shell делает <platform-bottom-nav> + <platform-top-bar> (см. frontend.mdc)"
    rg -nP "${MOBILE_HEADER_PATTERN}" "${APPS_UI_GLOBS[@]}" >&2 || true
fi
MOBILE_HEADER_IMPORT_PATTERN="from\s+['\"][^'\"]*mobile-app-header[^'\"]*['\"]"
if rg -nP "${MOBILE_HEADER_IMPORT_PATTERN}" "${APPS_UI_GLOBS[@]}" >/dev/null 2>&1; then
    fail "импорт *-mobile-app-header запрещён — используйте mobile shell платформы (bottom-nav / top-bar)"
    rg -nP "${MOBILE_HEADER_IMPORT_PATTERN}" "${APPS_UI_GLOBS[@]}" >&2 || true
fi

# Локальная вёрстка <platform-bottom-nav> / <platform-bottom-sheet-stack> / <platform-top-bar>
# в сервисных приложениях запрещена — её делает PlatformApp.render().
BOTTOM_NAV_LOCAL_PATTERN="<platform-bottom-(nav|sheet-stack)\b|<platform-top-bar\b"
if rg -nP "${BOTTOM_NAV_LOCAL_PATTERN}" "${APPS_UI_GLOBS[@]}" >/dev/null 2>&1; then
    fail "рендер <platform-bottom-nav>/<platform-bottom-sheet-stack>/<platform-top-bar> в apps/**/ui запрещён — их монтирует PlatformApp.render() (см. frontend.mdc)"
    rg -nP "${BOTTOM_NAV_LOCAL_PATTERN}" "${APPS_UI_GLOBS[@]}" >&2 || true
fi

# this.openSidebar() в pages/modals/components — антипаттерн mobile shell 2026.
# Допускается только в sidebar-компонентах core (там — desktop-канон).
OPEN_SIDEBAR_PATTERN="this\.openSidebar\s*\("
if rg -nP "${OPEN_SIDEBAR_PATTERN}" apps -g '*.js' --glob '!apps/*/ui/components/*sidebar*.js' >/dev/null 2>&1; then
    fail "this.openSidebar() в apps/<svc>/ui/{pages,modals,components}/** запрещён — на мобиле используйте <platform-bottom-nav> + bottom-sheet, на десктопе sidebar и так виден"
    rg -nP "${OPEN_SIDEBAR_PATTERN}" apps -g '*.js' --glob '!apps/*/ui/components/*sidebar*.js' >&2 || true
fi

# 21. Bottom-sheet canon: kind строго '<scope>.<entity>', регистрация через registerBottomSheetKind.
BOTTOM_SHEET_KIND_PATTERN="static\s+bottomSheetKind\s*=\s*['\"]([^'\"]+)['\"]"
BOTTOM_SHEET_KIND_BAD="$(rg -noP "${BOTTOM_SHEET_KIND_PATTERN}" apps core -g '*.js' \
    | grep -vE "static\s+bottomSheetKind\s*=\s*['\"][a-z][a-z0-9_]*\.[a-z][a-z0-9_]*['\"]" || true)"
if [ -n "$BOTTOM_SHEET_KIND_BAD" ]; then
    fail "bottomSheetKind должен быть '<scope>.<entity>' (snake_case)"
    echo "$BOTTOM_SHEET_KIND_BAD" >&2
fi

# 22. Запрещённые мёртвые vendor-артефакты (удалены из репозитория).
DEAD_ASSET_PATHS=(
    core/frontend/static/assets/js/zustand-bundle.js
    core/frontend/static/assets/js/livekit/livekit-client.umd.js
    core/frontend/static/assets/js/livekit/livekit-client.e2ee.worker.js
    core/frontend/static/assets/js/livekit/livekit-client.e2ee.worker.mjs
)
for dead_asset in "${DEAD_ASSET_PATHS[@]}"; do
    if [ -f "$dead_asset" ]; then
        fail "мёртвый vendor-артефакт не должен возвращаться в репозиторий: $dead_asset"
    fi
done
if rg -q 'zustand-bundle\.js' core/frontend/pwa/sw.js; then
    fail "zustand-bundle.js запрещён в SW precache"
fi

# 23. Flows UI: hardcoded hex/rgba в JS запрещены (Design System tokens only).
FLOWS_HEX_HITS="$(rg -n '#[0-9a-fA-F]{3,8}|rgba?\(' apps/flows/ui -g '*.js' \
    --glob '!apps/flows/ui/components/flow-canvas/**' \
    --glob '!apps/flows/ui/constants/flow-cover-gradients.js' || true)"
if [ -n "$FLOWS_HEX_HITS" ]; then
    fail "apps/flows/ui/**/*.js: hardcoded hex/rgba запрещены — используйте tokens.css (--flows-*, --accent, --glass-*)"
    echo "$FLOWS_HEX_HITS" >&2
fi

# 24. Flows UI: raw <button в apps/flows/ui/**/*.js запрещён — action chrome только <platform-button>.
#     Selectable cards / list rows — <article role="button" tabindex="0"> + keyboard (Enter/Space).
#     Resize handles — role="separator" + pointer handlers, не <button>.
FLOWS_BUTTON_HITS="$(rg -n '<button' apps/flows/ui -g '*.js' || true)"
if [ -n "$FLOWS_BUTTON_HITS" ]; then
    fail "apps/flows/ui/**/*.js: raw <button запрещён — используйте <platform-button> или <article role=\"button\">"
    echo "$FLOWS_BUTTON_HITS" >&2
fi

# 25. Flows UI: legacy action-button CSS class definitions запрещены — удалять в том же PR, что и миграция на platform-button.
FLOWS_LEGACY_BTN_CSS_PATTERN='\.(action-btn|icon-btn|ghost-btn|mini-btn|add-btn|mcp-preset)\s*[\{,]'
if rg -nP "${FLOWS_LEGACY_BTN_CSS_PATTERN}" apps/flows/ui -g '*.js' >/dev/null 2>&1; then
    fail "apps/flows/ui/**/*.js: legacy .action-btn/.icon-btn/.ghost-btn/.mini-btn/.add-btn/.mcp-preset CSS запрещены — удаляйте вместе с миграцией на <platform-button>"
    rg -nP "${FLOWS_LEGACY_BTN_CSS_PATTERN}" apps/flows/ui -g '*.js' >&2 || true
fi

# 26. Flows UI: glass-button запрещён — используйте <platform-button>.
FLOWS_GLASS_BUTTON_HITS="$(rg -n '<glass-button|glass-button\.js' apps/flows/ui -g '*.js' || true)"
if [ -n "$FLOWS_GLASS_BUTTON_HITS" ]; then
    fail "apps/flows/ui/**/*.js: <glass-button> запрещён — используйте <platform-button>"
    echo "$FLOWS_GLASS_BUTTON_HITS" >&2
fi

# 27. Flows UI: literal --platform-button-icon-size px overrides запрещены — density props или var(--flows-*).
FLOWS_ICON_SIZE_HITS="$(rg -n 'platform-button-icon-size:\s*[0-9]' apps/flows/ui -g '*.js' \
    --glob '!apps/flows/ui/components/flow-canvas/**' || true)"
if [ -n "$FLOWS_ICON_SIZE_HITS" ]; then
    fail "apps/flows/ui/**/*.js: literal --platform-button-icon-size запрещён — используйте density=\"compact|dense\" или var(--flows-*)"
    echo "$FLOWS_ICON_SIZE_HITS" >&2
fi

# 28. Flows UI: inline glass panel triplet (--glass-solid-subtle + --glass-border-subtle) — glassStyles/panelShellStyles.
FLOWS_GLASS_TRIPLET_MAX=4
FLOWS_GLASS_TRIPLET_COUNT=0
while IFS= read -r glass_file; do
    [ -z "$glass_file" ] && continue
    if rg -q 'glass-border-subtle' "$glass_file"; then
        FLOWS_GLASS_TRIPLET_COUNT=$((FLOWS_GLASS_TRIPLET_COUNT + 1))
    fi
done < <(rg -l 'glass-solid-subtle' apps/flows/ui -g '*.js' --glob '!apps/flows/ui/components/flow-canvas/**' || true)
if [ "$FLOWS_GLASS_TRIPLET_COUNT" -gt "$FLOWS_GLASS_TRIPLET_MAX" ]; then
    fail "apps/flows/ui: inline glass triplet в ${FLOWS_GLASS_TRIPLET_COUNT} файлах (max ${FLOWS_GLASS_TRIPLET_MAX}) — импортируйте glassStyles/panelShellStyles"
    rg -l 'glass-solid-subtle' apps/flows/ui -g '*.js' --glob '!apps/flows/ui/components/flow-canvas/**' | while IFS= read -r glass_file; do
        rg -q 'glass-border-subtle' "$glass_file" && echo "  $glass_file" >&2
    done
fi

# 29. Flows i18n: action_cancel только в flows.common.*
FLOWS_I18N_DUP_ACTION_CANCEL="$(uv run python - <<'PY'
import json
import sys
from pathlib import Path

root = Path("core/i18n/translations")
errors = []
for lang in ("en", "ru"):
    path = root / lang / "flows.json"
    data = json.loads(path.read_text(encoding="utf-8"))

    def walk(obj, prefix=""):
        if not isinstance(obj, dict):
            return
        if prefix != "common" and "action_cancel" in obj:
            errors.append(f"{lang}:{prefix or '<root>'}.action_cancel")
        for key, value in obj.items():
            walk(value, f"{prefix}.{key}" if prefix else key)

    walk(data)
print("\n".join(errors))
PY
)"
if [ -n "$FLOWS_I18N_DUP_ACTION_CANCEL" ]; then
    fail "flows.json: action_cancel дублируется вне common — используйте flows.common.action_cancel"
    echo "$FLOWS_I18N_DUP_ACTION_CANCEL" >&2
fi

# 30. Flows UI: literal color: white запрещён — используйте semantic tokens (--text-inverse, --flows-avatar-text).
FLOWS_COLOR_WHITE_HITS="$(rg -n 'color:\s*white\b' apps/flows/ui -g '*.js' || true)"
if [ -n "$FLOWS_COLOR_WHITE_HITS" ]; then
    fail "apps/flows/ui/**/*.js: color: white запрещён — используйте var(--text-inverse) или var(--flows-avatar-text)"
    echo "$FLOWS_COLOR_WHITE_HITS" >&2
fi

# 31. Flows UI: local .form-field CSS запрещён — используйте formStyles (.form-group) из core.
FLOWS_FORM_FIELD_CSS_HITS="$(rg -n '\.form-field\s*\{' apps/flows/ui/{pages,modals,components} -g '*.js' || true)"
if [ -n "$FLOWS_FORM_FIELD_CSS_HITS" ]; then
    fail "apps/flows/ui: local .form-field CSS запрещён — импортируйте formStyles и используйте .form-group"
    echo "$FLOWS_FORM_FIELD_CSS_HITS" >&2
fi

# 32. Flows UI: raw checkbox/radio запрещены — platform-field boolean / platform-segmented-control.
FLOWS_CHECKBOX_RADIO_HITS="$(rg -n 'type="checkbox"|type="radio"' apps/flows/ui/{pages,modals,components} -g '*.js' || true)"
if [ -n "$FLOWS_CHECKBOX_RADIO_HITS" ]; then
    fail "apps/flows/ui: raw checkbox/radio запрещены — используйте platform-field type=\"boolean\" или platform-segmented-control"
    echo "$FLOWS_CHECKBOX_RADIO_HITS" >&2
fi

# 33. Platform typography: единый Inter + JetBrains Mono через tokens.css / platform-fonts.css.
if ! uv run python scripts/check_platform_typography.py; then
    fail "platform typography canon — см. scripts/check_platform_typography.py и frontend.mdc Typography canon"
fi

# 34. Единый спиннер: собственные CSS-спиннеры в apps/** запрещены — используйте <platform-spinner>.
SPINNER_KEYFRAMES_HITS="$(rg -n '@keyframes\s+spin\b' apps/*/ui -g '*.js' || true)"
if [ -n "$SPINNER_KEYFRAMES_HITS" ]; then
    fail "apps/**/ui: собственный @keyframes spin запрещён — используйте <platform-spinner>"
    echo "$SPINNER_KEYFRAMES_HITS" >&2
fi

# 35. Boot shell: запрещён текст имени сервиса в :not(:defined)::after — только platform-boot-spinner.css.
BOOT_TEXT_HITS="$(rg -n ":not\\(:defined\\)::after\\s*\\{[^}]*content:\\s*['\"]" apps/*/ui/index.html || true)"
if [ -n "$BOOT_TEXT_HITS" ]; then
    fail "apps/*/ui/index.html: текстовый boot content запрещён — подключите platform-boot-spinner.css"
    echo "$BOOT_TEXT_HITS" >&2
fi
MISSING_BOOT_CSS="$(rg -L 'platform-boot-spinner\\.css' apps/*/ui/index.html || true)"
if [ -n "$MISSING_BOOT_CSS" ]; then
    fail "apps/*/ui/index.html: отсутствует link на platform-boot-spinner.css"
    echo "$MISSING_BOOT_CSS" >&2
fi

# 36. Long-text editor canon: только platform-markdown-editor (prompt-editor удалён).
if rg -q "prompt-editor|PromptEditor|prompt_editor\.js" apps core/frontend tests -g '*.js' -g '*.py' -g '*.html' 2>/dev/null; then
    fail "prompt-editor запрещён — используйте <platform-markdown-editor> (ui_components.mdc)"
    rg -n "prompt-editor|PromptEditor|prompt_editor\.js" apps core/frontend tests -g '*.js' -g '*.py' -g '*.html' >&2 || true
fi
if [ -f core/frontend/static/lib/components/prompt-editor.js ]; then
    fail "core/.../prompt-editor.js должен быть удалён — логика в platform-markdown-editor.js"
fi

# 37. Подвал сайдбара: колокольчик живёт внутри <platform-user> в слоте user-toolbar.
#     Рядом с блоком пользователя он повисает отдельной кнопкой и ломает ряд футера.
STRAY_NOTIF=$(rg -l "platform-notification-manager" apps/*/ui/components/*-sidebar.js 2>/dev/null | while read -r file; do
    if rg -q "<platform-notification-manager(?![^>]*slot=\"user-toolbar\")" -P "$file" 2>/dev/null; then
        echo "$file"
    fi
done)
if [ -n "$STRAY_NOTIF" ]; then
    fail "sidebar footer: <platform-notification-manager> обязан идти slot=\"user-toolbar\" внутри <platform-user> (ui_components.mdc)"
    echo "$STRAY_NOTIF" >&2
fi

if [ "$ERR" -ne 0 ]; then
    exit 1
fi

echo "check_ui_canon: OK"
