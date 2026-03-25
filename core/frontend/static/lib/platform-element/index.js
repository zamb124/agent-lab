/**
 * PlatformElement - Базовый класс для всех Lit компонентов
 */
import { LitElement } from 'lit';
import { ServiceRegistry } from '../services/ServiceRegistry.js';
import { StyleCache } from '../utils/style-cache.js';
import { baseStyles } from './styles.js';
import { glassStyles } from '../styles/shared/glass.styles.js';
import { use } from '../utils/use-store.js';

export class PlatformElement extends LitElement {
    static styles = [baseStyles, glassStyles];

    get services() { return ServiceRegistry; }
    get auth() { return ServiceRegistry.auth; }
    get a2a() { return ServiceRegistry.a2a; }
    get theme() { return ServiceRegistry.theme; }
    get notify() { return ServiceRegistry.notify; }
    get icon() { return ServiceRegistry.icon; }
    get companies() { return ServiceRegistry.companies; }
    get syncApi() { return ServiceRegistry.syncApi; }
    get syncWs() { return ServiceRegistry.syncWs; }
    get crmApi() { return ServiceRegistry.crmApi; }
    get ragApi() { return ServiceRegistry.ragApi; }

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
}
