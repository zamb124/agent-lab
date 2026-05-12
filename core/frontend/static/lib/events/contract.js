/**
 * Платформенный контракт событий.
 *
 * Событие = единица входа в систему. Любое действие — клик, ответ HTTP,
 * фрейм WebSocket, тик таймера, смена URL — становится событием в EventBus.
 * State обновляется ТОЛЬКО редьюсерами от событий; side-эффекты живут
 * в effects, которые тоже общаются с миром через события.
 *
 * Имя события: `<scope>/<entity>/<verb>` — нижний регистр, snake_case
 *   scope:  ui | auth | theme | i18n | router | network | crm | flows | sync | rag | office | frontend | <service>
 *   entity: домен (toast, modal, session, document, channel, ...)
 *   verb:   глагол прошедшего (created, opened, closed, requested, succeeded, failed) или императив для команд (open, close)
 *
 * Контракт сериализации:
 *   {
 *     id:           string  - монотонный ULID-подобный id
 *     type:         string  - имя события
 *     payload:      unknown - тело события (валидируется поверх по domain)
 *     meta: {
 *       ts:             number  - epoch ms при создании
 *       source:         'local' | 'ws' | 'http' | 'router' | 'storage' | 'timer' | 'system'
 *       causation_id:   string|null - id события, породившего это
 *       correlation_id: string|null - id запроса/потока для связки
 *       trace_id:       string|null - OTEL trace id (если есть)
 *     }
 *   }
 */

const EVENT_TYPE_PATTERN = /^[a-z][a-z0-9_]*(\/[a-z][a-z0-9_]*){2,}$/;
const EVENT_SOURCE_VALUES = new Set(['local', 'ws', 'http', 'router', 'storage', 'timer', 'system']);

let _seq = 0;

function _generateId() {
    const ts = Date.now().toString(36);
    _seq = (_seq + 1) & 0xffffffff;
    const rnd = Math.floor(Math.random() * 0xffffff).toString(36);
    return `e_${ts}_${_seq.toString(36)}_${rnd}`;
}

/**
 * Проверить и нормализовать имя события.
 * Бросает Error при нарушении формата.
 */
export function assertEventType(type) {
    if (typeof type !== 'string' || type.length === 0) {
        throw new Error(`Event type must be non-empty string, got: ${typeof type}`);
    }
    if (!EVENT_TYPE_PATTERN.test(type)) {
        throw new Error(
            `Event type "${type}" violates contract. Expected scope/entity/verb (lowercase, snake_case, >= 3 segments).`,
        );
    }
    return type;
}

/**
 * Создать событие. Все поля meta опциональны; недостающие подставит EventBus.
 *
 * @param {string} type
 * @param {unknown} [payload]
 * @param {{causation_id?: string, correlation_id?: string, trace_id?: string, source?: string, ts?: number}} [meta]
 * @returns {{id: string, type: string, payload: unknown, meta: object}}
 */
export function createEvent(type, payload, meta) {
    assertEventType(type);
    const m = meta || {};
    const source = m.source || 'local';
    if (!EVENT_SOURCE_VALUES.has(source)) {
        throw new Error(`Invalid event source "${source}". Allowed: ${[...EVENT_SOURCE_VALUES].join(', ')}`);
    }
    return {
        id: _generateId(),
        type,
        payload: payload === undefined ? null : payload,
        meta: {
            ts: typeof m.ts === 'number' ? m.ts : Date.now(),
            source,
            causation_id: m.causation_id || null,
            correlation_id: m.correlation_id || null,
            trace_id: m.trace_id || null,
        },
    };
}

/**
 * Базовые scope'ы платформенного ядра. Не запрещает другие — это якорь для документации.
 */
export const CORE_SCOPES = Object.freeze({
    UI: 'ui',
    AUTH: 'auth',
    THEME: 'theme',
    I18N: 'i18n',
    ROUTER: 'router',
    NETWORK: 'network',
    NOTIFY: 'notify',
    MODAL: 'modal',
    PWA: 'pwa',
    STORAGE: 'storage',
    HTTP: 'http',
    WS: 'ws',
});

/**
 * Реестр core-событий — единственный источник правды для платформенных типов.
 * Сервисные scope'ы (crm/, flows/, sync/, ...) объявляются в apps/<svc>/ui/events/<svc>-events.js.
 */
export const CoreEvents = Object.freeze({
    UI_TOAST_SHOW:        'ui/toast/show',
    UI_TOAST_DISMISS:     'ui/toast/dismiss',
    UI_TOAST_CLEAR:       'ui/toast/clear',
    UI_MODAL_OPEN:        'ui/modal/open',
    UI_MODAL_CLOSE:       'ui/modal/close',
    UI_MODAL_CLOSED:      'ui/modal/closed',
    UI_NAVIGATE:          'ui/navigate/requested',
    UI_SIDEBAR_OPEN_REQUESTED:  'ui/sidebar/open_requested',
    UI_SIDEBAR_CLOSE_REQUESTED: 'ui/sidebar/close_requested',
    UI_SIDEBAR_MOBILE_CHANGED:  'ui/sidebar/mobile_changed',
    UI_SIDEBAR_COLLAPSE_CHANGED:'ui/sidebar/collapse_changed',
    UI_BOTTOM_SHEET_OPEN_REQUESTED:  'ui/bottom_sheet/open_requested',
    UI_BOTTOM_SHEET_OPENED:          'ui/bottom_sheet/opened',
    UI_BOTTOM_SHEET_CLOSE_REQUESTED: 'ui/bottom_sheet/close_requested',
    UI_BOTTOM_SHEET_CLOSED:          'ui/bottom_sheet/closed',
    UI_NAMESPACE_SELECT_REQUESTED: 'ui/namespace/select_requested',
    UI_NAMESPACE_CHANGED:          'ui/namespace/changed',
    UI_DOCUMENTS_RELOAD_REQUESTED: 'ui/documents/reload_requested',
    UI_CLIPBOARD_COPY_REQUESTED:   'ui/clipboard/copy_requested',
    UI_CLIPBOARD_COPIED:           'ui/clipboard/copied',
    UI_CLIPBOARD_COPY_FAILED:      'ui/clipboard/copy_failed',

    AUTH_LOGIN_REQUESTED: 'auth/session/login_requested',
    AUTH_LOGIN_SUCCEEDED: 'auth/session/login_succeeded',
    AUTH_LOGIN_FAILED:    'auth/session/login_failed',
    AUTH_LOGOUT_REQUESTED:'auth/session/logout_requested',
    AUTH_LOGGED_OUT:      'auth/session/logged_out',
    AUTH_VALIDATED:       'auth/session/validated',
    AUTH_UNAUTHORIZED:    'auth/session/unauthorized',
    AUTH_ASSUMED_ANONYMOUS: 'auth/session/assumed_anonymous',
    AUTH_USER_LOADED:     'auth/user/loaded',
    AUTH_USER_FAILED:     'auth/user/failed',
    AUTH_COMPANY_SWITCH_REQUESTED: 'auth/company/switch_requested',
    AUTH_COMPANY_SWITCHED:         'auth/company/switched',

    THEME_TOGGLE_REQUESTED: 'theme/preference/toggle_requested',
    THEME_SET_REQUESTED:    'theme/preference/set_requested',
    THEME_CHANGED:          'theme/preference/changed',
    THEME_SYSTEM_CHANGED:   'theme/system/changed',

    I18N_LOCALE_REQUESTED: 'i18n/locale/set_requested',
    I18N_LOCALE_LOADED:    'i18n/locale/loaded',
    I18N_LOCALE_FAILED:    'i18n/locale/failed',
    I18N_LOCALE_CHANGED:   'i18n/locale/changed',

    ROUTER_NAVIGATE_REQUESTED: 'router/route/navigate_requested',
    ROUTER_ROUTE_CHANGED:      'router/route/changed',
    ROUTER_NOT_FOUND:          'router/route/not_found',
    ROUTER_ROUTES_REGISTERED:  'router/routes/registered',

    NETWORK_ONLINE:  'network/connectivity/online',
    NETWORK_OFFLINE: 'network/connectivity/offline',

    HTTP_REQUEST_STARTED:  'http/request/started',
    HTTP_REQUEST_SUCCEEDED:'http/request/succeeded',
    HTTP_REQUEST_FAILED:   'http/request/failed',

    WS_CONNECT_REQUESTED:  'ws/connection/connect_requested',
    WS_CONNECTED:          'ws/connection/connected',
    WS_DISCONNECTED:       'ws/connection/disconnected',
    WS_FRAME_RECEIVED:     'ws/frame/received',
    WS_SEND_REQUESTED:     'ws/frame/send_requested',
    WS_SEND_FAILED:        'ws/frame/send_failed',

    STORAGE_LOAD_REQUESTED: 'storage/value/load_requested',
    STORAGE_LOADED:         'storage/value/loaded',
    STORAGE_PERSIST_REQUESTED: 'storage/value/persist_requested',

    PWA_PUSH_PERMISSION_REQUESTED: 'pwa/push/permission_requested',
    PWA_PUSH_REGISTERED:           'pwa/push/registered',
    PWA_INSTALL_AVAILABLE:         'pwa/install/available',
    PWA_INSTALLED:                 'pwa/install/installed',
    PWA_UPDATE_AVAILABLE:          'pwa/update/available',

    APP_BOOTSTRAP_STARTED:   'ui/app/bootstrap_started',
    APP_BOOTSTRAP_COMPLETED: 'ui/app/bootstrap_completed',
});
