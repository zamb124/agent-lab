/**
 * ServiceRegistry - Единый реестр сервисов приложения
 */
import { AuthService } from '../../services/auth.service.js';
import { ThemeService } from '../../services/theme.service.js';
import { NotifyService } from '../../services/notify.service.js';
import { IconService } from '../../services/icon.service.js';
import { getPWAService } from '../../services/pwa.service.js';

class ServiceRegistryClass {
    constructor() {
        this.services = new Map();
        this._initialized = false;
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
        this.register('pwa', getPWAService(baseUrl));

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

    get auth() { return this.get('auth'); }
    get theme() { return this.get('theme'); }
    get notify() { return this.get('notify'); }
    get icon() { return this.get('icon'); }
    get a2a() { return this.has('a2a') ? this.get('a2a') : null; }
    get companies() { return this.has('companies') ? this.get('companies') : null; }
    get ragApi() { return this.has('ragApi') ? this.get('ragApi') : null; }
    get team() { return this.has('team') ? this.get('team') : null; }
    get apiKeys() { return this.has('apiKeys') ? this.get('apiKeys') : null; }
    get billing() { return this.has('billing') ? this.get('billing') : null; }
    get settings() { return this.has('settings') ? this.get('settings') : null; }
    get servicesStatus() { return this.has('servicesStatus') ? this.get('servicesStatus') : null; }
    get pwa() { return this.has('pwa') ? this.get('pwa') : null; }
}

export const ServiceRegistry = new ServiceRegistryClass();
export const Services = ServiceRegistry;
