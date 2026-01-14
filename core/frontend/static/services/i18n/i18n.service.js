/**
 * I18n Service - Система переводов для frontend
 * 
 * Простая и легковесная система локализации без внешних зависимостей
 * Интегрируется с Lit компонентами через reactive properties
 */

class I18nService {
    constructor() {
        this._currentLocale = 'ru';
        this._fallbackLocale = 'ru';
        this._translations = {};
        this._listeners = new Set();
        this._loadedLocales = new Set();
        
        this._detectLocale();
    }

    _detectLocale() {
        const savedLocale = localStorage.getItem('locale');
        if (savedLocale) {
            this._currentLocale = savedLocale;
            return;
        }

        const browserLocale = navigator.language || navigator.userLanguage;
        const locale = browserLocale.split('-')[0];
        
        if (['ru', 'en'].includes(locale)) {
            this._currentLocale = locale;
        }
    }

    async loadLocale(locale) {
        if (this._loadedLocales.has(locale)) {
            return true;
        }

        try {
            const response = await fetch(`/api/i18n/${locale}`);
            if (!response.ok) {
                console.warn(`Failed to load locale: ${locale}`);
                return false;
            }

            const translations = await response.json();
            this._translations[locale] = translations;
            this._loadedLocales.add(locale);
            return true;
        } catch (error) {
            console.error(`Error loading locale ${locale}:`, error);
            return false;
        }
    }

    async setLocale(locale) {
        if (this._currentLocale === locale) {
            return;
        }

        await this.loadLocale(locale);
        
        this._currentLocale = locale;
        localStorage.setItem('locale', locale);
        
        this._notifyListeners();
    }

    getCurrentLocale() {
        return this._currentLocale;
    }

    t(key, params = {}, namespace = 'landing') {
        const locale = this._currentLocale;
        const translations = this._translations[locale] || this._translations[this._fallbackLocale] || {};
        
        const keys = key.split('.');
        let value = translations[namespace];
        
        for (const k of keys) {
            if (value && typeof value === 'object') {
                value = value[k];
            } else {
                value = undefined;
                break;
            }
        }

        if (value === undefined) {
            console.warn(`Translation missing: ${namespace}.${key} [${locale}]`);
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
        return ['ru', 'en'];
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
        i18n.loadLocale(i18n.getCurrentLocale());
    };

    const originalDisconnectedCallback = component.disconnectedCallback;
    component.disconnectedCallback = function() {
        if (originalDisconnectedCallback) {
            originalDisconnectedCallback.call(this);
        }
        unsubscribe();
    };

    return {
        t: (key, params) => i18n.t(key, params),
        locale: () => i18n.getCurrentLocale(),
        setLocale: (locale) => i18n.setLocale(locale)
    };
}

export function t(key, params = {}, namespace = 'landing') {
    return i18n.t(key, params, namespace);
}

export default i18n;

