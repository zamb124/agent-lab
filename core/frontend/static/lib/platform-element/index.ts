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

import { LitElement } from 'lit';
import type { CSSResultGroup } from 'lit';
import { StyleCache } from '../utils/style-cache.js';
import { baseStyles } from './styles.js';
import { glassStyles } from '../styles/shared/glass.styles.js';
import { formStyles } from '../styles/shared/form.styles.js';
import { buttonStyles, iconButtonStyles } from '../styles/shared/button.styles.js';
import { motionStyles } from '../styles/shared/motion.styles.js';
import { getPlatformBus, hasPlatformBus } from '../events/bus-singleton.js';
import { SelectController } from '../events/select-controller.js';
// Не использовать ../events/index.js: barrel подтягивает модули с bare import `lit` (ложится на автономный embed).
import { CoreEvents, assertEventType } from '../events/contract.js';
import { CoreAuthEvents } from '../events/effects/auth.effect.js';
import { FILES_EVENTS } from '../events/reducers/files.js';
import { translate } from '../events/effects/i18n.effect.js';
import { mergePlatformI18nVars } from '../utils/platform-i18n-vars.js';
import { getFactory } from '../events/factory-registry.js';
import { getDefaultI18nNamespace } from '../utils/i18n-namespace.js';
import {
    ResourceController,
    OpController,
    FormController,
    CursorListController,
    FacetsController,
    SliceController,
    bindActions,
} from '../base/use-resource.js';
import type { CursorListItemOf, OpControllerOf, ResourceControllerOf, SliceControllerOf } from '../base/use-resource.js';
import type { CursorListFactory } from '../events/factories/cursor-list.js';
import { PLATFORM_MOBILE_VIEWPORT_CONTENT } from '../utils/platform-viewport-meta.js';
import { isStandaloneOrNativeAppShell } from '../utils/native-app-shell.js';
import type { EventMetaInput, PlatformEvent } from '../events/contract.js';
import type { PlatformBusLike } from '../events/bus-singleton.js';
import type { PlatformBusState } from '../events/bus-state.js';
import type { FactoryNameOfKind, PlatformFactoryRegistry } from '../events/factory-registry.js';
const ZOOM_BLOCKED_KEYBOARD_KEYS = new Set(['+', '-', '=', '_', '0']);
const ZOOM_BLOCKED_KEYBOARD_CODES = new Set(['NumpadAdd', 'NumpadSubtract', 'Digit0', 'Equal', 'Minus']);

function preventDefaultAction(event: Event): void { event.preventDefault(); }
function preventPinchZoom(event: TouchEvent): void {
    if (event.touches && event.touches.length > 1) event.preventDefault();
}
function preventCtrlWheelZoom(event: WheelEvent): void {
    if (event.ctrlKey || event.metaKey) event.preventDefault();
}
function preventKeyboardZoom(event: KeyboardEvent): void {
    if (!(event.ctrlKey || event.metaKey)) return;
    if (ZOOM_BLOCKED_KEYBOARD_KEYS.has(event.key) || ZOOM_BLOCKED_KEYBOARD_CODES.has(event.code)) {
        event.preventDefault();
    }
}

const _ALLOWED_TOAST_TYPES = new Set(['success', 'error', 'warning', 'info']);

export interface ToastOptions {
    type?: string;
    vars?: Record<string, string | number> | null;
    duration?: number | null;
    namespace?: string | null;
}

function readI18nNamespace(ctor: unknown): string | undefined {
    let current = ctor;
    while (typeof current === 'function') {
        const descriptor = Object.getOwnPropertyDescriptor(current, 'i18nNamespace');
        if (descriptor !== undefined) {
            const value = descriptor.value;
            return typeof value === 'string' && value.length > 0 ? value : undefined;
        }
        current = Object.getPrototypeOf(current);
    }
    return undefined;
}

export class PlatformElement extends LitElement {
    static override styles: CSSResultGroup = [baseStyles, glassStyles, formStyles, buttonStyles, iconButtonStyles, motionStyles];
    static _standaloneNoZoomGuardRegistered = false;

    _busTypeUnsubs: Array<() => void>;
    _i18nSelectController: SelectController<Record<string, unknown> | undefined> | null;

    constructor() {
        super();
        this._busTypeUnsubs = [];
        this._i18nSelectController = null;
    }

    get bus(): PlatformBusLike { return getPlatformBus(); }

    dispatch(type: string, payload: unknown, meta?: EventMetaInput): PlatformEvent | null {
        if (typeof type !== 'string' || type.length === 0) {
            throw new Error('PlatformElement.dispatch: type required (non-empty string)');
        }
        if (payload === undefined) {
            throw new Error(`PlatformElement.dispatch: payload required for "${type}" (use null for empty events)`);
        }
        return this.bus.dispatch(type, payload, meta || { source: 'local' });
    }

    select<V>(selector: (state: Readonly<PlatformBusState>) => V, opts?: { equality?: (a: unknown, b: unknown) => boolean }): SelectController<V> {
        return new SelectController(this, selector, opts);
    }

    useEvent(type: string, handler: (event: PlatformEvent) => void): () => void {
        assertEventType(type);
        const unsub = this.bus.subscribeType(type, handler);
        this._busTypeUnsubs.push(unsub);
        return unsub;
    }

    /**
     * DOM-слушатель на window/document/элемент с авто-снятием на disconnectedCallback.
     * Единственный способ глобальных DOM-подписок: голые addEventListener +
     * removeEventListener-пары и bound-поля под них запрещены ui_canon.
     * Для транзиентных сессий (drag: pointermove/up на время жеста) — снять
     * возвращённым unsub при конце жеста; повторный вызов при disconnect безопасен.
     */
    useDomEvent<E extends Event>(
        target: EventTarget,
        type: string,
        handler: (event: E) => void,
        options?: boolean | AddEventListenerOptions,
    ): () => void {
        const listener: EventListener = (event) => {
            handler(event as E);
        };
        target.addEventListener(type, listener, options);
        const unsub = () => {
            target.removeEventListener(type, listener, options);
        };
        this._busTypeUnsubs.push(unsub);
        return unsub;
    }

    /**
     * Локальное DOM-событие для непосредственного родителя через slot/composed-boundary.
     * Lit-паттерн child→parent. Запрещено для межкомпонентного / межприложенческого обмена —
     * для этого используй `dispatch(...)` (bus). check_ui_canon разрешает emit/CustomEvent
     * только внутри core/frontend/static/lib (presentational compositions).
     */
    emit(name: string, detail: unknown = null): void {
        this.dispatchEvent(new CustomEvent(name, { detail, bubbles: true, composed: true }));
    }

    t(key: string, vars?: Record<string, string | number> | null, namespace?: string): string {
        if (typeof key !== 'string' || key.length === 0) {
            throw new Error('PlatformElement.t: key required (non-empty string)');
        }
        const ns = namespace || readI18nNamespace(this.constructor) || getDefaultI18nNamespace();
        if (!ns) {
            throw new Error(`PlatformElement.t: cannot resolve i18n namespace for key "${key}". Provide explicit namespace, declare static i18nNamespace, or set PlatformApp.defaultI18nNamespace.`);
        }
        const i18nState = this.bus.getState().i18n;
        return translate(i18nState, key, mergePlatformI18nVars(vars), ns);
    }

    useResource<N extends FactoryNameOfKind<'resource-collection'>>(name: N, opts?: { autoload?: boolean; autoloadQuery?: Record<string, unknown> | null }): ResourceControllerOf<PlatformFactoryRegistry[N]> {
        const factory = getFactory(name, 'resource-collection');
        return bindActions(new ResourceController(this, factory, opts), factory.actions, 'ResourceController', factory.name);
    }

    useOp<N extends FactoryNameOfKind<'async-op'>>(name: N): OpControllerOf<PlatformFactoryRegistry[N]> {
        const factory = getFactory(name, 'async-op');
        return bindActions(new OpController(this, factory), factory.actions, 'OpController', factory.name);
    }

    useForm<N extends FactoryNameOfKind<'form'>>(name: N): FormController {
        return new FormController(this, getFactory(name, 'form'));
    }

    useCursorList<N extends FactoryNameOfKind<'cursor-list'>>(name: N, opts?: { autoload?: boolean; autoloadFilters?: Record<string, unknown> | null }): CursorListController<CursorListItemOf<PlatformFactoryRegistry[N]>> {
        const factory = getFactory(name, 'cursor-list') as CursorListFactory<CursorListItemOf<PlatformFactoryRegistry[N]>>;
        return new CursorListController(this, factory, opts);
    }

    useFacets<N extends FactoryNameOfKind<'facets'>>(name: N): FacetsController {
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
    useSlice<N extends FactoryNameOfKind<'slice'>>(name: N): SliceControllerOf<PlatformFactoryRegistry[N]> {
        const factory = getFactory(name, 'slice');
        return bindActions(new SliceController(this, factory), factory.actions, 'SliceController', factory.name);
    }

    toast(i18n_key: string, options?: ToastOptions): void {
        if (typeof i18n_key !== 'string' || i18n_key.length === 0) {
            throw new Error('PlatformElement.toast: i18n_key required (non-empty string)');
        }
        const opts = options === undefined || options === null ? {} : options;
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
        const ns = explicitNs || readI18nNamespace(this.constructor) || getDefaultI18nNamespace();
        const qualified_key = i18n_key.includes(':') || !ns ? i18n_key : `${ns}:${i18n_key}`;
        this.dispatch(CoreEvents.UI_TOAST_SHOW, {
            type,
            i18n_key: qualified_key,
            i18n_vars,
            duration,
        });
    }

    openModal(kindOrClass: string | (abstract new (...args: never[]) => unknown), props?: Record<string, unknown> | null, options?: { replaceKinds?: string[]; skipEnterMotion?: boolean }): void {
        let kind: string;
        if (typeof kindOrClass === 'string' && kindOrClass.length > 0) {
            kind = kindOrClass;
        } else if (kindOrClass && typeof kindOrClass === 'function') {
            if (!('modalKind' in kindOrClass) || typeof kindOrClass.modalKind !== 'string') {
                throw new Error('PlatformElement.openModal: modal class missing static modalKind');
            }
            kind = kindOrClass.modalKind;
            if (typeof kind !== 'string' || kind.length === 0) {
                throw new Error('PlatformElement.openModal: modal class missing static modalKind');
            }
        } else {
            throw new Error('PlatformElement.openModal: kind (non-empty string) or modal class required');
        }
        const opts = options && typeof options === 'object' ? options : {};
        const replaceKinds = Array.isArray(opts.replaceKinds) ? opts.replaceKinds : null;
        if (replaceKinds !== null) {
            for (const replaceKind of replaceKinds) {
                if (typeof replaceKind !== 'string' || replaceKind.length === 0) {
                    throw new Error('PlatformElement.openModal: replaceKinds entries must be non-empty strings');
                }
            }
        }
        let modalProps: Record<string, unknown> | null = props === undefined ? null : props;
        if (opts.skipEnterMotion === true) {
            modalProps = {
                ...(modalProps && typeof modalProps === 'object' ? modalProps : {}),
                skipEnterMotion: true,
            };
        }
        const payload: { kind: string; props: Record<string, unknown> | null; replaceKinds?: string[] } = { kind, props: modalProps };
        if (replaceKinds !== null) {
            payload.replaceKinds = replaceKinds;
        }
        this.dispatch(CoreEvents.UI_MODAL_OPEN, payload);
    }

    openFile(fileOrId: string | Record<string, unknown>, options?: { source?: string }): void {
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

    closeModal(target?: string | { id: string } | null): void {
        let kind: string | null = null;
        let id: string | null = null;
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
        const payload: { kind: string | null; id?: string } = { kind };
        if (id !== null) payload.id = id;
        this.dispatch(CoreEvents.UI_MODAL_CLOSE, payload);
    }

    openSidebar(): void {
        this.dispatch(CoreEvents.UI_SIDEBAR_OPEN_REQUESTED, null);
    }

    closeSidebar(): void {
        this.dispatch(CoreEvents.UI_SIDEBAR_CLOSE_REQUESTED, null);
    }

    /**
     * Открыть нижний экран (bottom-sheet) по зарегистрированному kind'у.
     * Универсальный механизм вторичной мобильной навигации (mobile shell 2026).
     *
     * @param {string} kind — '<scope>.<name>' (snake_case), сheet должен быть зарегистрирован.
     * @param {object|null|undefined} [props] — props компонента листа.
     */
    openBottomSheet(kind: string, props?: Record<string, unknown> | null): void {
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
    closeBottomSheet(target?: string | { id: string } | null): void {
        let kind: string | null = null;
        let id: string | null = null;
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
        const payload: { kind: string | null; id?: string } = { kind };
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
    getCurrentRouteKey(): string | null {
        const key = this.bus.getState().router.routeKey;
        return typeof key === 'string' && key.length > 0 ? key : null;
    }

    navigate(routeKey: string, params?: Record<string, string>, navigationOptions?: { search?: string; replace?: boolean }): void {
        if (typeof routeKey !== 'string' || routeKey.length === 0) {
            throw new Error('PlatformElement.navigate: routeKey required (non-empty string)');
        }
        if (params !== undefined && (params === null || typeof params !== 'object')) {
            throw new Error('PlatformElement.navigate: params must be plain object or omitted');
        }
        if (navigationOptions !== undefined && (navigationOptions === null || typeof navigationOptions !== 'object')) {
            throw new Error('PlatformElement.navigate: navigationOptions must be plain object or omitted');
        }
        const payload: { routeKey: string; params: Record<string, string>; search?: string; replace?: boolean } = {
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

    copyToClipboard(text: string, options: { success_i18n_key: string; error_i18n_key: string }): void {
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

    setLocale(locale: string): void {
        if (typeof locale !== 'string' || locale.length === 0) {
            throw new Error('PlatformElement.setLocale: locale required (non-empty string)');
        }
        this.dispatch(CoreEvents.I18N_LOCALE_REQUESTED, { locale });
    }

    setTheme(mode: string): void {
        if (mode !== 'dark' && mode !== 'light') {
            throw new Error(`PlatformElement.setTheme: mode must be 'dark' | 'light', got "${mode}"`);
        }
        this.dispatch(CoreEvents.THEME_SET_REQUESTED, { mode });
    }

    switchCompany(company_id: string): void {
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
    startOAuth(provider: string, options?: { returnPath?: string | undefined; plan?: string | undefined }): void {
        if (typeof provider !== 'string' || provider.length === 0) {
            throw new Error('PlatformElement.startOAuth: provider required (non-empty string)');
        }
        if (options !== undefined && (options === null || typeof options !== 'object')) {
            throw new Error('PlatformElement.startOAuth: options must be a plain object or omitted');
        }
        const opts = options === undefined || options === null ? {} : options;
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

    async loadStyles(path: string): Promise<void> {
        const sheet = await StyleCache.load(path);
        if (!this.shadowRoot) {
            throw new Error('PlatformElement.loadStyles: shadowRoot unavailable');
        }
        this.shadowRoot.adoptedStyleSheets = [
            ...this.shadowRoot.adoptedStyleSheets,
            sheet,
        ];
    }

    override connectedCallback(): void {
        super.connectedCallback();
        // Реактивность переводов: подписка на сам бандл активной локали.
        // locale сразу проставлен initialState'ом, не меняется при первой загрузке.
        // Меняется только translations[locale] (с undefined на объект) — этого триггера
        // достаточно, чтобы перерендерить любой компонент, использующий this.t(...).
        // Production Flow UI iframe не бутстрапит PlatformApp — catalog может
        // монтировать PlatformElement (DataTable host); без bus подписка запрещена.
        if (hasPlatformBus() && !this._i18nSelectController) {
            this._i18nSelectController = this.select((s) => s.i18n.translations[s.i18n.locale]);
        }
        PlatformElement._registerStandaloneNoZoomGuard();
    }

    override disconnectedCallback(): void {
        for (const unsub of this._busTypeUnsubs) {
            unsub();
        }
        this._busTypeUnsubs = [];
        super.disconnectedCallback();
    }

    static _registerStandaloneNoZoomGuard(): void {
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
