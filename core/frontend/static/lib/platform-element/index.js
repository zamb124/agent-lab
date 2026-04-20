/**
 * PlatformElement — канонический Event Sourcing базовый класс.
 *
 * Принципы:
 *   - Никаких прямых сервис-вызовов: любое действие = `dispatch(type, payload)`.
 *   - Никакого setState / прямой записи в стор: чтение — только через `select()`.
 *   - Никаких произвольных CustomEvent для cross-component обмена: только bus.
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
 *   this.useCursorList(name, opts?)                    — CursorListController по имени фабрики
 *   this.useFacets(name)                               — FacetsController по имени фабрики
 *   this.useSlice(name)                                — SliceController по имени фабрики
 *   this.toast(i18n_key, {type?, vars?, duration?})    — toast через UI_TOAST_SHOW
 *   this.openModal(kindOrClass, props?)                — UI_MODAL_OPEN
 *   this.closeModal(kind?)                             — UI_MODAL_CLOSE
 *   this.openSidebar()                                 — UI_SIDEBAR_OPEN_REQUESTED
 *   this.closeSidebar()                                — UI_SIDEBAR_CLOSE_REQUESTED
 *   this.navigate(routeKey, params?)                   — ROUTER_NAVIGATE_REQUESTED
 *   this.copyToClipboard(text, {success_i18n_key, error_i18n_key}) — UI_CLIPBOARD_COPY_REQUESTED
 *   this.setLocale(locale)                              — I18N_LOCALE_REQUESTED
 *   this.setTheme(name)                                 — THEME_SET_REQUESTED
 *   this.switchCompany(company_id)                      — AUTH_COMPANY_SWITCH_REQUESTED
 */

import { LitElement } from 'lit';
import { StyleCache } from '../utils/style-cache.js';
import { baseStyles } from './styles.js';
import { glassStyles } from '../styles/shared/glass.styles.js';
import { formStyles } from '../styles/shared/form.styles.js';
import { buttonStyles, iconButtonStyles } from '../styles/shared/button.styles.js';
import { getPlatformBus } from '../events/bus-singleton.js';
import { SelectController } from '../events/select-controller.js';
import { CoreEvents, assertEventType, translate } from '../events/index.js';
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

const PLATFORM_MOBILE_VIEWPORT_CONTENT = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, user-scalable=no, viewport-fit=cover';
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
    static styles = [baseStyles, glassStyles, formStyles, buttonStyles, iconButtonStyles];
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
     * Lit-паттерн child→parent. Запрещено для cross-component / cross-app обмена —
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
     *   ctl.value          // read-only frozen slice (state.syncCallUi)
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

    closeModal(target) {
        let kind = null;
        let id = null;
        if (target === undefined || target === null) {
            // pop topmost
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

    navigate(routeKey, params) {
        if (typeof routeKey !== 'string' || routeKey.length === 0) {
            throw new Error('PlatformElement.navigate: routeKey required (non-empty string)');
        }
        if (params !== undefined && (params === null || typeof params !== 'object')) {
            throw new Error('PlatformElement.navigate: params must be plain object or omitted');
        }
        this.dispatch(CoreEvents.ROUTER_NAVIGATE_REQUESTED, {
            routeKey,
            params: params === undefined ? {} : params,
        });
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
        if (!PlatformElement._isStandalonePwaMode()) return;

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

    static _isStandalonePwaMode() {
        const mediaQuery = window.matchMedia('(display-mode: standalone)');
        const isStandaloneDisplayMode = Boolean(mediaQuery && mediaQuery.matches);
        const isStandaloneIosMode = window.navigator.standalone === true;
        return isStandaloneDisplayMode || isStandaloneIosMode;
    }
}
