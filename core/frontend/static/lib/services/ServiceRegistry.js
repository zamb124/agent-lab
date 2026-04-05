/**
 * ServiceRegistry - Единый реестр сервисов приложения
 */
import { AuthService } from '../../services/auth.service.js';
import { ThemeService } from '../../services/theme.service.js';
import { NotifyService } from '../../services/notify.service.js';
import { IconService } from '../../services/icon.service.js';
import { CalendarService } from '../../services/calendar.service.js';
import { FilesService } from '../../services/files.service.js';
import { TeamService } from '../../services/team.service.js';
import { getPWAService } from '../../services/pwa.service.js';
import { i18n } from '../../services/i18n/i18n.service.js';
import { AppEvents } from '../utils/types.js';
import { redirectToLogin } from '../utils/auth-redirect.js';

class ServiceRegistryClass {
    constructor() {
        this.services = new Map();
        this._initialized = false;
        this._auth401ListenerRegistered = false;
    }

    register(name, service) {
        this.services.set(name, service);
    }

    get(name) {
        if (!this.services.has(name)) {
            throw new Error(`Service '${name}' not registered. Available: ${Array.from(this.services.keys()).join(', ')}`);
        }
        return this.services.get(name);
    }

    has(name) {
        return this.services.has(name);
    }

    async registerCore(baseUrl = '') {
        if (this._initialized) return;

        this.register('auth', new AuthService(baseUrl));
        this.register('theme', new ThemeService());
        this.register('notify', new NotifyService());
        this.register('icon', new IconService('/static/core/assets/icons'));
        this.register('calendarApi', new CalendarService(baseUrl));
        this.register('filesApi', new FilesService(baseUrl));
        this.register('team', new TeamService(baseUrl));
        this.register('pwa', getPWAService(baseUrl));
        this.register('i18n', i18n);

        if (!this._auth401ListenerRegistered) {
            this._auth401ListenerRegistered = true;
            window.addEventListener(AppEvents.AUTH_UNAUTHORIZED, () => {
                this.auth.clearAuth();
                redirectToLogin();
            });
        }

        for (const [, service] of this.services) {
            if (service && typeof service.init === 'function') {
                await service.init();
            }
        }

        this._initialized = true;
    }

    get isInitialized() {
        return this._initialized;
    }

    /**
     * Полный сброс реестра для изоляции компонентных UI-тестов (tests/ui_components).
     * Не использовать вне тестового окружения.
     */
    resetForUiTests() {
        this.services.clear();
        this._initialized = false;
        this._auth401ListenerRegistered = false;
    }

    get auth() { return this.get('auth'); }
    get theme() { return this.get('theme'); }
    get notify() { return this.get('notify'); }
    get icon() { return this.get('icon'); }
    get a2a() { return this.has('a2a') ? this.get('a2a') : null; }
    get companies() { return this.has('companies') ? this.get('companies') : null; }
    get ragApi() { return this.has('ragApi') ? this.get('ragApi') : null; }
    get officeApi() { return this.has('officeApi') ? this.get('officeApi') : null; }
    get syncApi() { return this.has('syncApi') ? this.get('syncApi') : null; }
    get syncWs() { return this.has('syncWs') ? this.get('syncWs') : null; }
    get crmApi() { return this.has('crmApi') ? this.get('crmApi') : null; }
    get team() { return this.has('team') ? this.get('team') : null; }
    get apiKeys() { return this.has('apiKeys') ? this.get('apiKeys') : null; }
    get billing() { return this.has('billing') ? this.get('billing') : null; }
    get settings() { return this.has('settings') ? this.get('settings') : null; }
    get servicesStatus() { return this.has('servicesStatus') ? this.get('servicesStatus') : null; }
    get pwa() { return this.has('pwa') ? this.get('pwa') : null; }
    get i18n() { return this.get('i18n'); }
    get calendarApi() { return this.has('calendarApi') ? this.get('calendarApi') : null; }
    get filesApi() { return this.has('filesApi') ? this.get('filesApi') : null; }
}

export const ServiceRegistry = new ServiceRegistryClass();
export const Services = ServiceRegistry;

// i18n до registerCore: в body стоит app-loader (PlatformElement), он подписывается в connectedCallback.
ServiceRegistry.register('i18n', i18n);
