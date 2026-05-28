/**
 * PlatformElement — канонический Event Sourcing базовый класс.
 *
 * Принципы:
 *   - Никаких прямых сервис-вызовов: любое действие = `dispatch(type, payload)`.
 *   - Никакого setState / прямой записи в стор: чтение — только через `select()`.
 *   - Никаких произвольных CustomEvent для межкомпонентного обмена: только bus.
 *   - Никаких импортов CoreEvents/I18nNs/контроллеров/resource-объектов
 *     в pages/modals — всё доступно как методы базового класса.
 *
 * API:
 *   this.dispatch(type, payload?, meta?)              — отправить событие в EventBus
 *   this.select(selector, opts?)                       — реактивная подписка на срез state
 *   this.useEvent(type, handler)                       — подписка на отдельный тип события
 *   this.t(key, vars?, namespace?)                     — перевод по state.i18n
 *   this.useResource(name, opts?)                      — ResourceController по имени фабрики
 *   this.useOp(name)                                   — OpController по имени фабрики
 *   this.useForm(name)                                 — FormController по имени фабрики
 *   this.useКурсорList(name, opts?)                    — КурсорListController по имени фабрики
 *   this.useFacets(name)                               — FacetsController по имени фабрики
 *   this.useSlice(name)                                — SliceController по имени фабрики
 *   this.toast(i18n_key, {type?, vars?, duration?})    — toast через UI_TOAST_SHOW
 *   this.openFile(fileOrId, options?)                  — глобальный OnlyOffice viewer для FileRecord
 *   this.openModal(kindOrClass, props?)                — UI_MODAL_OPEN
 *   this.closeModal(kind?)                             — UI_MODAL_CLOSE
 *   this.openSidebar()                                 — UI_SIDEBAR_OPEN_REQUESTED
 *   this.closeSidebar()                                — UI_SIDEBAR_CLOSE_REQUESTED
 *   this.openBottomSheet(kind, props?)                 — UI_BOTTOM_SHEET_OPEN_REQUESTED
 *   this.closeBottomSheet(targetOrUndefined)           — UI_BOTTOM_SHEET_CLOSE_REQUESTED
 *   this.getCurrentRouteKey()                          — state.router.routeKey | null
 *   this.navigate(routeKey, params?, navigationOptions?) — ROUTER_NAVIGATE_REQUESTED (options.search: ?query)
 *   this.copyToClipboard(text, {success_i18n_key, error_i18n_key}) — UI_CLIPBOARD_COPY_REQUESTED
 *   this.setLocale(locale)                              — I18N_LOCALE_REQUESTED
 *   this.setTheme(name)                                 — THEME_SET_REQUESTED
 *   this.switchCompany(company_id)                      — AUTH_COMPANY_SWITCH_REQUESTED
 *   this.startOAuth(provider, { returnPath?, plan? })   — auth/oauth/start_requested
 */

import { LitElement } from '../../assets/js/lit/lit.min.js';
import { StyleCache } from '../utils/style-cache.js';
import { baseStyles } from './styles.js';
import { glassStyles } from '../styles/shared/glass.styles.js';
import { formStyles } from '../styles/shared/form.styles.js';
import { buttonStyles, iconButtonStyles } from '../styles/shared/button.styles.js';
import { motionStyles } from '../styles/shared/motion.styles.js';
import { getPlatformBus } from '../events/bus-singleton.js';
import { SelectController } from '../events/select-controller.js';
// Не использовать ../events/index.js: barrel подтягивает модули с bare import `lit` (ложится на автономный embed).
import { CoreEvents, assertEventType } from '../events/contract.js';
import { CoreAuthEvents } from '../events/effects/auth.effect.js';
import { FILES_EVENTS } from '../events/reducers/files.js';
import { translate } from '../events/effects/i18n.effect.js';
import { getFactory } from '../events/factory-registry.js';
import { getDefaultI18nNamespace } from '../utils/i18n-namespace.js';
import {
    ResourceController,
    OpController,
    FormController,
    CursorListController,
    FacetsController,
    SliceController,
} from '../base/use-resource.js';
import { PLATFORM_MOBILE_VIEWPORT_CONTENT } from '../utils/platform-viewport-meta.js';
import { isStandaloneOrNativeAppShell } from '../utils/native-app-shell.js';
const ZOOM_BLOCKED_KEYBOARD_KEYS = new Set(['+', '-', '=', '_', '0']);
const ZOOM_BLOCKED_KEYBOARD_CODES = new Set(['NumpadAdd', 'NumpadSubtract', 'Digit0', 'Equal', 'Minus']);

function preventDefaultAction(event) { event.preventDefault(); }
function preventPinchZoom(event) {
    if (event.touches && event.touches.length > 1) event.preventDefault();
}
function preventCtrlWheelZoom(event) {
    if (event.ctrlKey || event.metaKey) event.preventDefault();
}
function preventKeyboardZoom(event) {
    if (!(event.ctrlKey || event.metaKey)) return;
    if (ZOOM_BLOCKED_KEYBOARD_KEYS.has(event.key) || ZOOM_BLOCKED_KEYBOARD_CODES.has(event.code)) {
        event.preventDefault();
    }
}

const _ALLOWED_TOAST_TYPES = new Set(['success', 'error', 'warning', 'info']);

export class PlatformElement extends LitElement {
    static styles = [baseStyles, glassStyles, formStyles, buttonStyles, iconButtonStyles, motionStyles];
    static _standaloneNoZoomGuardRegistered = false;

    constructor() {
        super();
        this._busTypeUnsubs = [];
        this._i18nSelectController = null;
    }

    get bus() { return getPlatformBus(); }

    dispatch(type, payload, meta) {
        if (typeof type !== 'string' || type.length === 0) {
            throw new Error('PlatformElement.dispatch: type required (non-empty string)');
        }
        if (payload === undefined) {
            throw new Error(`PlatformElement.dispatch: payload required for "${type}" (use null for empty events)`);
        }
        return this.bus.dispatch(type, payload, meta || { source: 'local' });
    }

    select(selector, opts) {
        return new SelectController(this, selector, opts);
    }

    useEvent(type, handler) {
        assertEventType(type);
        const unsub = this.bus.subscribeType(type, handler);
        this._busTypeUnsubs.push(unsub);
        return unsub;
    }

    /**
     * Локальное DOM-событие для непосредственного родителя через slot/composed-boundary.
     * Lit-паттерн child→parent. Запрещено для межкомпонентного / межприложенческого обмена —
     * для этого используй `dispatch(...)` (bus). check_ui_canon разрешает emit/CustomEvent
     * только внутри core/frontend/static/lib (presentational compositions).
     */
    emit(name, detail = null) {
        this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
    }

    t(key, vars, namespace) {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('PlatformElement.t: key required (non-empty string)');
        }
        const ns = namespace || this.constructor.i18nNamespace || getDefaultI18nNamespace();
        if (!ns) {
            throw new Error(`PlatformElement.t: cannot resolve i18n namespace for key "${key}". Provide explicit namespace, declare static i18nNamespace, or set PlatformApp.defaultI18nNamespace.`);
        }
        return translate(this.bus.getState().i18n, key, vars, ns);
    }

    useResource(name, opts) {
        return new ResourceController(this, getFactory(name, 'resource-collection'), opts);
    }

    useOp(name) {
        return new OpController(this, getFactory(name, 'async-op'));
    }

    useForm(name) {
        return new FormController(this, getFactory(name, 'form'));
    }

    useCursorList(name, opts) {
        return new CursorListController(this, getFactory(name, 'cursor-list'), opts);
    }

    useFacets(name) {
        return new FacetsController(this, getFactory(name, 'facets'));
    }

    /**
     * useSlice(name) — Reactive Controller для `createSlice` фабрики.
     *
     *   const ctl = this.useSlice('sync/call_ui');
     *   ctl.value          // замороженный slice только для чтения (state.syncCallUi)
     *   ctl.<actionMethod>(payload)  // bound из factory.actions
     *
     * Имя фабрики — `<svc>/<entity>` (ровно 2 сегмента, snake_case).
     */
    useSlice(name) {
        return new SliceController(this, getFactory(name, 'slice'));
    }

    toast(i18n_key, options) {
        if (typeof i18n_key !== 'string' || i18n_key.length === 0) {
            throw new Error('PlatformElement.toast: i18n_key required (non-empty string)');
        }
        const opts = options || {};
        const type = opts.type || 'success';
        if (!_ALLOWED_TOAST_TYPES.has(type)) {
            throw new Error(`PlatformElement.toast: invalid type "${type}" (allowed: success|error|warning|info)`);
        }
        const i18n_vars = Object.prototype.hasOwnProperty.call(opts, 'vars') ? opts.vars : null;
        const duration = Object.prototype.hasOwnProperty.call(opts, 'duration') ? opts.duration : null;
        if (duration !== null && typeof duration !== 'number') {
            throw new Error('PlatformElement.toast: duration must be number or omitted');
        }
        const explicitNs = Object.prototype.hasOwnProperty.call(opts, 'namespace') ? opts.namespace : null;
        const ns = explicitNs || this.constructor.i18nNamespace || getDefaultI18nNamespace();
        const qualified_key = i18n_key.includes(':') || !ns ? i18n_key : `${ns}:${i18n_key}`;
        this.dispatch(CoreEvents.UI_TOAST_SHOW, {
            type,
            i18n_key: qualified_key,
            i18n_vars,
            duration,
        });
    }

    openModal(kindOrClass, props) {
        let kind;
        if (typeof kindOrClass === 'string' && kindOrClass.length > 0) {
            kind = kindOrClass;
        } else if (kindOrClass && typeof kindOrClass === 'function') {
            kind = kindOrClass.modalKind;
            if (typeof kind !== 'string' || kind.length === 0) {
                throw new Error('PlatformElement.openModal: modal class missing static modalKind');
            }
        } else {
            throw new Error('PlatformElement.openModal: kind (non-empty string) or modal class required');
        }
        const modalProps = props === undefined ? null : props;
        this.dispatch(CoreEvents.UI_MODAL_OPEN, { kind, props: modalProps });
    }

    openFile(fileOrId, options) {
        let file;
        if (typeof fileOrId === 'string') {
            if (fileOrId.length === 0) {
                throw new Error('PlatformElement.openFile: file id must be non-empty string');
            }
            file = { file_id: fileOrId };
        } else if (fileOrId && typeof fileOrId === 'object') {
            const rawId = fileOrId.file_id || fileOrId.id;
            if (typeof rawId !== 'string' || rawId.length === 0) {
                throw new Error('PlatformElement.openFile: file.file_id or file.id required');
            }
            file = { ...fileOrId, file_id: rawId };
        } else {
            throw new Error('PlatformElement.openFile: file object or file id required');
        }
        const opts = options && typeof options === 'object' ? options : {};
        this.dispatch(FILES_EVENTS.OPEN_REQUESTED, {
            file,
            source: typeof opts.source === 'string' && opts.source.length > 0 ? opts.source : null,
        });
    }

    closeModal(target) {
        let kind = null;
        let id = null;
        if (target === undefined || target === null) {
            // снять верхний элемент
        } else if (typeof target === 'string') {
            if (target.length === 0) {
                throw new Error('PlatformElement.closeModal: kind must be non-empty string');
            }
            kind = target;
        } else if (typeof target === 'object') {
            if (typeof target.id !== 'string' || target.id.length === 0) {
                throw new Error('PlatformElement.closeModal: { id } must contain non-empty string');
            }
            id = target.id;
        } else {
            throw new Error('PlatformElement.closeModal: target must be string kind, { id }, or omitted');
        }
        const payload = { kind };
        if (id !== null) payload.id = id;
        this.dispatch(CoreEvents.UI_MODAL_CLOSE, payload);
    }

    openSidebar() {
        this.dispatch(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, null);
    }

    closeSidebar() {
        this.dispatch(CoreEvents.UI_SIDEBAR_CLOSE_REQUESTED, null);
    }

    /**
     * Открыть нижний экран (bottom-sheet) по зарегистрированному kind'у.
     * Универсальный механизм вторичной мобильной навигации (mobile shell 2026).
     *
     * @param {string} kind — '<scope>.<name>' (snake_case), сheet должен быть зарегистрирован.
     * @param {object|null|undefined} [props] — props компонента листа.
     */
    openBottomSheet(kind, props) {
        if (typeof kind !== 'string' || kind.length === 0) {
            throw new Error('PlatformElement.openBottomSheet: kind required (non-empty string)');
        }
        const sheetProps = props === undefined ? null : props;
        this.dispatch(CoreEvents.UI_BOTTOM_SHEET_OPEN_REQUESTED, { kind, props: sheetProps });
    }

    /**
     * Закрыть нижний экран.
     *   - без аргумента: снять верхний из стека
     *   - строка: закрыть верхний sheet указанного kind
     *   - { id }: закрыть sheet по id
     */
    closeBottomSheet(target) {
        let kind = null;
        let id = null;
        if (target === undefined || target === null) {
            // снять верхний элемент
        } else if (typeof target === 'string') {
            if (target.length === 0) {
                throw new Error('PlatformElement.closeBottomSheet: kind must be non-empty string');
            }
            kind = target;
        } else if (typeof target === 'object') {
            if (typeof target.id !== 'string' || target.id.length === 0) {
                throw new Error('PlatformElement.closeBottomSheet: { id } must contain non-empty string');
            }
            id = target.id;
        } else {
            throw new Error('PlatformElement.closeBottomSheet: target must be string kind, { id }, or omitted');
        }
        const payload = { kind };
        if (id !== null) payload.id = id;
        this.dispatch(CoreEvents.UI_BOTTOM_SHEET_CLOSE_REQUESTED, payload);
    }

    /**
     * Текущий routeKey из state.router. Возвращает null, если bus ещё не поднят
     * или router не успел матчинг (paranoid-чтение без падений).
     * Используется в навигационных компонентах (platform-bottom-nav, platform-top-bar).
     *
     * @returns {string|null}
     */
    getCurrentRouteKey() {
        const state = this.bus.getState();
        const router = state && state.router;
        const key = router && router.routeKey;
        return typeof key === 'string' && key.length > 0 ? key : null;
    }

    navigate(routeKey, params, navigationOptions) {
        if (typeof routeKey !== 'string' || routeKey.length === 0) {
            throw new Error('PlatformElement.navigate: routeKey required (non-empty string)');
        }
        if (params !== undefined && (params === null || typeof params !== 'object')) {
            throw new Error('PlatformElement.navigate: params must be plain object or omitted');
        }
        if (navigationOptions !== undefined && (navigationOptions === null || typeof navigationOptions !== 'object')) {
            throw new Error('PlatformElement.navigate: navigationOptions must be plain object or omitted');
        }
        const payload = {
            routeKey,
            params: params === undefined ? {} : params,
        };
        if (navigationOptions !== undefined && Object.prototype.hasOwnProperty.call(navigationOptions, 'search')) {
            const s = navigationOptions.search;
            if (typeof s !== 'string') {
                throw new Error('PlatformElement.navigate: navigationOptions.search must be a string');
            }
            payload.search = s;
        }
        if (navigationOptions !== undefined && Object.prototype.hasOwnProperty.call(navigationOptions, 'replace')) {
            const r = navigationOptions.replace;
            if (r !== true && r !== false) {
                throw new Error('PlatformElement.navigate: navigationOptions.replace must be boolean');
            }
            if (r === true) {
                payload.replace = true;
            }
        }
        this.dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, payload);
    }

    copyToClipboard(text, options) {
        if (typeof text !== 'string') {
            throw new Error('PlatformElement.copyToClipboard: text required (string)');
        }
        if (!options || typeof options !== 'object') {
            throw new Error('PlatformElement.copyToClipboard: options { success_i18n_key, error_i18n_key } required');
        }
        if (typeof options.success_i18n_key !== 'string' || options.success_i18n_key.length === 0) {
            throw new Error('PlatformElement.copyToClipboard: success_i18n_key required');
        }
        if (typeof options.error_i18n_key !== 'string' || options.error_i18n_key.length === 0) {
            throw new Error('PlatformElement.copyToClipboard: error_i18n_key required');
        }
        this.dispatch(CoreEvents.UI_CLIPBOARD_COPY_REQUESTED, {
            text,
            success_i18n_key: options.success_i18n_key,
            error_i18n_key: options.error_i18n_key,
        });
    }

    setLocale(locale) {
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('PlatformElement.setLocale: locale required (non-empty string)');
        }
        this.dispatch(CoreEvents.I18N_LOCALE_REQUESTED, { locale });
    }

    setTheme(mode) {
        if (mode !== 'dark' && mode !== 'light') {
            throw new Error(`PlatformElement.setTheme: mode must be 'dark' | 'light', got "${mode}"`);
        }
        this.dispatch(CoreEvents.THEME_SET_REQUESTED, { mode });
    }

    switchCompany(company_id) {
        if (typeof company_id !== 'string' || company_id.length === 0) {
            throw new Error('PlatformElement.switchCompany: company_id required (non-empty string)');
        }
        this.dispatch(CoreEvents.AUTH_COMPANY_SWITCH_REQUESTED, { company_id });
    }

    /**
     * Старт OAuth: редирект на провайдера. Тело события совпадает с auth-modal.
     * @param {string} provider — yandex | google | github | apple
     * @param {{ returnPath?: string, plan?: string } | undefined} options
     */
    startOAuth(provider, options) {
        if (typeof provider !== 'string' || provider.length === 0) {
            throw new Error('PlatformElement.startOAuth: provider required (non-empty string)');
        }
        if (options !== undefined && (options === null || typeof options !== 'object')) {
            throw new Error('PlatformElement.startOAuth: options must be a plain object or omitted');
        }
        const opts = options || {};
        let return_path = null;
        if (typeof opts.returnPath === 'string' && opts.returnPath.length > 0) {
            return_path = opts.returnPath;
        }
        let plan = null;
        if (typeof opts.plan === 'string' && opts.plan.length > 0) {
            plan = opts.plan;
        }
        this.dispatch(CoreAuthEvents.OAUTH_START_REQUESTED, {
            provider,
            return_path,
            plan,
        });
    }

    async loadStyles(path) {
        const sheet = await StyleCache.load(path);
        this.shadowRoot.adoptedStyleSheets = [
            ...this.shadowRoot.adoptedStyleSheets,
            sheet,
        ];
    }

    connectedCallback() {
        super.connectedCallback();
        // Реактивность переводов: подписка на сам бандл активной локали.
        // locale сразу проставлен initialState'ом, не меняется при первой загрузке.
        // Меняется только translations[locale] (с undefined на объект) — этого триггера
        // достаточно, чтобы перерендерить любой компонент, использующий this.t(...).
        if (!this._i18nSelectController) {
            this._i18nSelectController = this.select((s) => s.i18n.translations[s.i18n.locale]);
        }
        PlatformElement._registerStandaloneNoZoomGuard();
    }

    disconnectedCallback() {
        for (const unsub of this._busTypeUnsubs) {
            unsub();
        }
        this._busTypeUnsubs = [];
        super.disconnectedCallback();
    }

    static _registerStandaloneNoZoomGuard() {
        if (PlatformElement._standaloneNoZoomGuardRegistered) return;
        if (!isStandaloneOrNativeAppShell()) return;

        const viewportElement = document.querySelector('meta[name="viewport"]');
        if (!viewportElement) {
            throw new Error('PWA shell must define meta viewport');
        }
        viewportElement.setAttribute('content', PLATFORM_MOBILE_VIEWPORT_CONTENT);
        document.documentElement.style.touchAction = 'pan-x pan-y';

        document.addEventListener('gesturestart', preventDefaultAction, { passive: false });
        document.addEventListener('gesturechange', preventDefaultAction, { passive: false });
        document.addEventListener('gestureend', preventDefaultAction, { passive: false });
        document.addEventListener('touchmove', preventPinchZoom, { passive: false });
        window.addEventListener('wheel', preventCtrlWheelZoom, { passive: false });
        window.addEventListener('keydown', preventKeyboardZoom);

        PlatformElement._standaloneNoZoomGuardRegistered = true;
    }
}
