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

# 1. Только PlatformElement / PlatformApp / PlatformPage наследование.
if rg -q 'extends LitElement' apps -g '*.js'; then
    fail "запрещено extends LitElement в apps/**/*.js"
    rg 'extends LitElement' apps -g '*.js' >&2 || true
fi

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
if rg -q 'this\.(services|auth|notify|icon|theme|companies|calendarApi|filesApi|fileTypes|team|a2a|syncWs|syncApi|crmApi|ragApi)\b' apps -g '*.js'; then
    fail "this.services / this.auth / this.icon / ... удалены — используйте dispatch/select"
    rg 'this\.(services|auth|notify|icon|theme|companies|calendarApi|filesApi|fileTypes|team|a2a|syncWs|syncApi|crmApi|ragApi)\b' apps -g '*.js' >&2 || true
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
#     Скоуп: и apps, и core (кроме самого embed-chat host-интерфейса).
LEGACY_WINDOW_EVENTS=(
    'platform-sidebar-open'
    'platform-sidebar-mobile-change'
    'office-documents-list-reload'
)
LEGACY_GLOBS=(
    apps -g '*.js' --glob '!apps/*/ui/assets/**' --glob '!**/*.min.js'
    core/frontend/static -g '*.js' --glob '!core/frontend/static/lib/embed-chat/**' --glob '!**/*.min.js'
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

# 11. Запрет старых геттеров в core/frontend/static/lib (кроме embed-chat — у него свой бутстрап).
CORE_LIB_GLOBS=( core/frontend/static/lib -g '*.js' --glob '!core/frontend/static/lib/embed-chat/**' )
if rg -q 'this\.(services|auth|notify|icon|theme|companies|calendarApi|filesApi|fileTypes|team|a2a|syncWs|syncApi|crmApi|ragApi)\b' "${CORE_LIB_GLOBS[@]}"; then
    fail "this.services/this.calendarApi/... в core/lib — используйте dispatch(<SLICE_EVENTS>) и select"
    rg -n 'this\.(services|auth|notify|icon|theme|companies|calendarApi|filesApi|fileTypes|team|a2a|syncWs|syncApi|crmApi|ragApi)\b' "${CORE_LIB_GLOBS[@]}" >&2 || true
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
FACTORY_CANON_SERVICES=( frontend crm rag sync office flows )
for svc in "${FACTORY_CANON_SERVICES[@]}"; do
    PG_GLOBS=( "apps/${svc}/ui/pages" "apps/${svc}/ui/modals" -g '*.js' )

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
    core/frontend/static/lib -g '*.js'
    --glob '!core/frontend/static/lib/embed-chat/**'
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

if [ "$ERR" -ne 0 ]; then
    exit 1
fi

echo "check_ui_canon: OK"
