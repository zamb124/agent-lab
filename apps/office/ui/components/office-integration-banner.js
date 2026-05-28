/**
 * OfficeIntegrationBanner — баннер «интеграция не настроена».
 *
 * Читает `useOp('office/integration_status')` (autoload в connectedCallback).
 * Если бэк ответил `configured: false`, показывает подсказку из i18n
 * `documents:integration.notConfigured`. Иначе — пусто.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

const INTEGRATION_OP = 'office/integration_status';

export class OfficeIntegrationBanner extends PlatformElement {
    static i18nNamespace = 'documents';

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .banner {
                display: flex; align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--warning-subtle, rgba(255, 200, 80, 0.12));
                border: 1px solid var(--warning, rgba(255, 200, 80, 0.35));
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-sm);
                margin-bottom: var(--space-4);
            }
            .banner platform-icon { color: var(--warning, rgba(255, 200, 80, 0.85)); flex-shrink: 0; }
        `,
    ];

    constructor() {
        super();
        this._integration = this.useOp(INTEGRATION_OP);
    }

    connectedCallback() {
        super.connectedCallback();
        if (!this._integration.lastResult && !this._integration.busy) {
            this._integration.run(null);
        }
    }

    render() {
        const result = this._integration.lastResult;
        if (!result) return html``;
        if (result.configured) return html``;
        return html`
            <div class="banner">
                <platform-icon name="warning" size="18"></platform-icon>
                <span>${this.t('integration.notConfigured')}</span>
            </div>
        `;
    }
}

customElements.define('office-integration-banner', OfficeIntegrationBanner);
