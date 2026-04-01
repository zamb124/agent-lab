/**
 * PlatformElement - Базовый класс для всех Lit компонентов
 */
import { LitElement } from 'lit';
import { ServiceRegistry } from '../services/ServiceRegistry.js';
import { StyleCache } from '../utils/style-cache.js';
import { baseStyles } from './styles.js';
import { glassStyles } from '../styles/shared/glass.styles.js';
import { use } from '../utils/use-store.js';

const PLATFORM_MOBILE_VIEWPORT_CONTENT = 'width=device-width, initial-scale=1.0, maximum-scale=1.0, minimum-scale=1.0, user-scalable=no, viewport-fit=cover';
const ZOOM_BLOCKED_KEYBOARD_KEYS = new Set(['+', '-', '=', '_', '0']);
const ZOOM_BLOCKED_KEYBOARD_CODES = new Set(['NumpadAdd', 'NumpadSubtract', 'Digit0', 'Equal', 'Minus']);

function preventDefaultAction(event) {
    event.preventDefault();
}

function preventPinchZoom(event) {
    if (event.touches && event.touches.length > 1) {
        event.preventDefault();
    }
}

function preventCtrlWheelZoom(event) {
    if (event.ctrlKey || event.metaKey) {
        event.preventDefault();
    }
}

function preventKeyboardZoom(event) {
    if (!(event.ctrlKey || event.metaKey)) {
        return;
    }
    if (ZOOM_BLOCKED_KEYBOARD_KEYS.has(event.key) || ZOOM_BLOCKED_KEYBOARD_CODES.has(event.code)) {
        event.preventDefault();
    }
}

export class PlatformElement extends LitElement {
    static styles = [baseStyles, glassStyles];
    static _standaloneNoZoomGuardRegistered = false;

    get services() { return ServiceRegistry; }
    get auth() { return ServiceRegistry.auth; }
    get a2a() { return ServiceRegistry.a2a; }
    get theme() { return ServiceRegistry.theme; }
    get i18n() { return ServiceRegistry.i18n; }
    get notify() { return ServiceRegistry.notify; }
    get icon() { return ServiceRegistry.icon; }
    get companies() { return ServiceRegistry.companies; }
    get syncApi() { return ServiceRegistry.syncApi; }
    get syncWs() { return ServiceRegistry.syncWs; }
    get crmApi() { return ServiceRegistry.crmApi; }
    get ragApi() { return ServiceRegistry.ragApi; }
    get calendarApi() { return ServiceRegistry.calendarApi; }
    get filesApi() { return ServiceRegistry.filesApi; }

    async loadStyles(path) {
        const sheet = await StyleCache.load(path);
        this.shadowRoot.adoptedStyleSheets = [
            ...this.shadowRoot.adoptedStyleSheets,
            sheet
        ];
    }

    success(message, duration) { this.notify?.success(message, duration); }
    error(message, duration) { this.notify?.error(message, duration); }
    warning(message, duration) { this.notify?.warning(message, duration); }
    info(message, duration) { this.notify?.info(message, duration); }

    emit(name, detail = null) {
        this.dispatchEvent(new CustomEvent(name, {
            detail,
            bubbles: true,
            composed: true,
        }));
    }

    use(selector) {
        return use(this, selector);
    }

    connectedCallback() {
        super.connectedCallback();
        this._platformI18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
        PlatformElement._registerStandaloneNoZoomGuard();
    }

    disconnectedCallback() {
        if (this._platformI18nUnsub) {
            this._platformI18nUnsub();
            this._platformI18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    static _registerStandaloneNoZoomGuard() {
        if (PlatformElement._standaloneNoZoomGuardRegistered) {
            return;
        }
        if (!PlatformElement._isStandalonePwaMode()) {
            return;
        }

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
