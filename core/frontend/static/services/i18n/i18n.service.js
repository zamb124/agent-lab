/**
 * I18n Service - Система переводов для frontend
 *
 * Локаль: localStorage `locale`, cookie `language` (для Context на API), document.documentElement.lang.
 */

const SUPPORTED = ['ru', 'en'];
const COOKIE_NAME = 'language';
const COOKIE_MAX_AGE_SEC = 365 * 24 * 60 * 60;

/**
 * Локаль по языку ОС/браузера: только ru → ru, иначе en (в т.ч. iOS/Android WebView через navigator.languages).
 */
export function defaultLocaleFromNavigator() {
    if (typeof navigator === 'undefined') {
        return 'en';
    }
    const raw =
        navigator.languages && navigator.languages.length > 0
            ? navigator.languages[0]
            : navigator.language || '';
    const primary = String(raw).split('-')[0].toLowerCase();
    return primary === 'ru' ? 'ru' : 'en';
}

class I18nService {
    constructor() {
        this._currentLocale = 'en';
        this._fallbackLocale = 'ru';
        this._translations = {};
        this._listeners = new Set();
        this._loadedLocales = new Set();
        /** Namespace для t(key, params) без третьего аргумента (landing до PlatformApp). */
        this._defaultNamespace = 'landing';

        this._detectLocale();
    }

    getDefaultNamespace() {
        return this._defaultNamespace;
    }

    setDefaultNamespace(namespace) {
        if (typeof namespace !== 'string' || namespace === '') {
            throw new Error('I18nService.setDefaultNamespace: ожидается непустая строка');
        }
        this._defaultNamespace = namespace;
    }

    _readCookie(name) {
        const escaped = name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const match = document.cookie.match(new RegExp(`(?:^|; )${escaped}=([^;]*)`));
        return match ? decodeURIComponent(match[1]) : null;
    }

    _writeLanguageCookie(locale) {
        document.cookie = `${COOKIE_NAME}=${encodeURIComponent(locale)};path=/;max-age=${COOKIE_MAX_AGE_SEC};SameSite=Lax`;
    }

    _applyDocumentLocale(locale) {
        document.documentElement.lang = locale;
        this._writeLanguageCookie(locale);
    }

    _detectLocale() {
        const savedLocale = localStorage.getItem('locale');
        if (savedLocale && SUPPORTED.includes(savedLocale)) {
            this._currentLocale = savedLocale;
            return;
        }

        const cookieLocale = this._readCookie(COOKIE_NAME);
        if (cookieLocale && SUPPORTED.includes(cookieLocale)) {
            this._currentLocale = cookieLocale;
            localStorage.setItem('locale', cookieLocale);
            return;
        }

        this._currentLocale = defaultLocaleFromNavigator();
    }

    /**
     * Вызывается из ServiceRegistry.registerCore: загрузка бандла текущей локали и синхрон document/cookie.
     */
    async init() {
        await this.loadLocale(this._currentLocale);
        this._applyDocumentLocale(this._currentLocale);
    }

    async loadLocale(locale) {
        if (!SUPPORTED.includes(locale)) {
            throw new Error(`Unsupported locale: ${locale}`);
        }

        if (this._loadedLocales.has(locale)) {
            return;
        }

        const response = await fetch(`/api/i18n/${locale}`);
        if (!response.ok) {
            throw new Error(`Failed to load locale ${locale}: HTTP ${response.status}`);
        }

        const translations = await response.json();
        this._translations[locale] = translations;
        this._loadedLocales.add(locale);
    }

    async setLocale(locale) {
        if (this._currentLocale === locale) {
            return;
        }

        if (!SUPPORTED.includes(locale)) {
            throw new Error(`Unsupported locale: ${locale}`);
        }

        await this.loadLocale(locale);

        this._currentLocale = locale;
        localStorage.setItem('locale', locale);
        this._applyDocumentLocale(locale);

        this._notifyListeners();
    }

    getCurrentLocale() {
        return this._currentLocale;
    }

    t(key, params = {}, namespace) {
        const ns = namespace === undefined ? this._defaultNamespace : namespace;
        const locale = this._currentLocale;
        const translations = this._translations[locale] || this._translations[this._fallbackLocale] || {};
        
        const keys = key.split('.');
        let value = translations[ns];
        
        for (const k of keys) {
            if (value && typeof value === 'object') {
                value = value[k];
            } else {
                value = undefined;
                break;
            }
        }

        if (value === undefined) {
            console.warn(`Translation missing: ${ns}.${key} [${locale}]`);
            return key;
        }

        if (typeof value === 'string' && Object.keys(params).length > 0) {
            return value.replace(/\{\{(\w+)\}\}/g, (match, paramKey) => {
                return params[paramKey] !== undefined ? params[paramKey] : match;
            });
        }

        return value;
    }

    subscribe(callback) {
        this._listeners.add(callback);
        return () => this._listeners.delete(callback);
    }

    _notifyListeners() {
        this._listeners.forEach(callback => callback(this._currentLocale));
    }

    getSupportedLocales() {
        return [...SUPPORTED];
    }

    getLocaleName(locale) {
        const names = {
            'ru': 'Русский',
            'en': 'English'
        };
        return names[locale] || locale.toUpperCase();
    }
}

export const i18n = new I18nService();

export function useI18n(component) {
    const updateLocale = () => {
        component.requestUpdate();
    };

    const unsubscribe = i18n.subscribe(updateLocale);

    const originalConnectedCallback = component.connectedCallback;
    component.connectedCallback = function() {
        if (originalConnectedCallback) {
            originalConnectedCallback.call(this);
        }
        void i18n
            .loadLocale(i18n.getCurrentLocale())
            .then(() => component.requestUpdate())
            .catch((err) => {
                console.error('[useI18n] loadLocale failed', err);
                throw err;
            });
    };

    const originalDisconnectedCallback = component.disconnectedCallback;
    component.disconnectedCallback = function() {
        if (originalDisconnectedCallback) {
            originalDisconnectedCallback.call(this);
        }
        unsubscribe();
    };

    return {
        t: (key, params, namespace) => i18n.t(key, params ?? {}, namespace),
        locale: () => i18n.getCurrentLocale(),
        setLocale: (locale) => i18n.setLocale(locale)
    };
}

export function t(key, params = {}, namespace) {
    return i18n.t(key, params, namespace);
}

export { i18nDefaultNamespaceForBaseUrl, I18nNs } from './i18n-default-namespace.js';

export default i18n;

