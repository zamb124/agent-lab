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
import type { OpController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import type {CSSResultGroup, TemplateResult} from 'lit';

const INTEGRATION_OP = 'office/integration_status';

export class OfficeIntegrationBanner extends PlatformElement {
    static i18nNamespace = 'documents';

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .banner {
                display: flex; align-items: flex-start;
                gap: var(--space-3);
                padding: var(--space-3) var(--space-4);
                background: var(--warning-bg);
                border: 1px solid var(--warning);
                border-radius: var(--radius-lg);
                color: var(--text-primary);
                font-size: var(--text-sm);
                margin-bottom: var(--space-4);
            }
            .banner platform-icon { color: var(--warning); flex-shrink: 0; }
        `,
    ];

    private _integration: OpController;

    constructor() {
        super();
        this._integration = this.useOp(INTEGRATION_OP);
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (!this._integration.lastResult && !this._integration.busy) {
            this._integration.run(null);
        }
    }

    override render(): TemplateResult {
        const result = this._integration.lastResult;
        if (!isPlainRecord(result)) return html``;
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
