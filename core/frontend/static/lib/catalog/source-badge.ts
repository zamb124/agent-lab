/**
 * `<platform-catalog-source-badge>` — бейдж источника значения наследуемого
 * поля каталога (chain-toggle): ``base`` — общее значение мастер-карты,
 * ``<facet>`` — переопределено для всего сервиса, ``<facet>:<id>`` — для
 * конкретного экземпляра (витрины/склада). ``reset``-кнопка снимает
 * override — поле снова наследует базу.
 *
 * Подписи уровней хост передаёт атрибутами `service-label`/`instance-label`
 * (лексика сервиса своя: «Все витрины»/«Эта витрина»).
 */

import { html, css } from 'lit';
import type { CSSResultGroup, PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '../platform-element/index.js';
import '../components/platform-icon.js';

export class PlatformCatalogSourceBadge extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        source: { type: String },
        serviceLabel: { type: String, attribute: 'service-label' },
        instanceLabel: { type: String, attribute: 'instance-label' },
        resettable: { type: Boolean },
    };

    declare source: string;
    declare serviceLabel: string;
    declare instanceLabel: string;
    declare resettable: boolean;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host { display: inline-flex; }
            .badge {
                display: inline-flex; align-items: center; gap: var(--space-1);
                padding: 0 var(--space-2); height: 18px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs); line-height: 1;
                background: var(--glass-tint-medium); color: var(--text-tertiary);
                border: 1px solid var(--glass-border-subtle);
                white-space: nowrap;
            }
            .badge[data-source='base'] {
                background: transparent;
            }
            .badge:not([data-source='base']) {
                color: var(--accent-primary);
                border-color: var(--accent-primary);
            }
            button.reset {
                display: inline-flex; align-items: center; justify-content: center;
                width: 16px; height: 16px; margin-inline-end: -4px;
                border: none; border-radius: var(--radius-full);
                background: transparent; color: inherit; cursor: pointer;
                padding: 0;
            }
            button.reset:hover { background: var(--glass-tint-strong); }
        `,
    ];

    constructor() {
        super();
        this.source = 'base';
        this.serviceLabel = '';
        this.instanceLabel = '';
        this.resettable = false;
    }

    private get _label(): string {
        if (this.source === 'base' || this.source === '') {
            return this.t('catalog.source_base');
        }
        return this.source.includes(':') ? this.instanceLabel : this.serviceLabel;
    }

    private _onReset(e: Event): void {
        e.stopPropagation();
        this.emit('catalog-source-reset');
    }

    override render(): TemplateResult {
        const overridden = this.source !== 'base' && this.source !== '';
        return html`
            <span class="badge" data-source=${overridden ? 'override' : 'base'} title=${this.t('catalog.source_hint')}>
                ${this._label}
                ${overridden && this.resettable
                    ? html`<button type="button" class="reset" title=${this.t('catalog.source_reset')} aria-label=${this.t('catalog.source_reset')} @click=${this._onReset}>
                        <platform-icon name="close" size="10"></platform-icon>
                    </button>`
                    : ''}
            </span>
        `;
    }
}

customElements.define('platform-catalog-source-badge', PlatformCatalogSourceBadge);
