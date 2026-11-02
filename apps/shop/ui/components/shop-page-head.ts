/**
 * ShopPageHead — контекстная шапка внутренних страниц конструктора витрин.
 *
 * Крошки «Магазины / <имя магазина> / <раздел>» через platform-breadcrumbs:
 * имя магазина — trail-сегмент, ведущий на рабочий экран меню, раздел —
 * current-label. Крупно показывает имя магазина со статусом и ссылкой на
 * публичную витрину; действия страницы приходят через слот `actions`.
 */

import { html, css, nothing } from 'lit';
import type { PropertyDeclarations, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-icon.js';

export interface ShopHeadRow {
    shop_id: string;
    name: string;
    slug: string;
    status: string;
}

/**
 * Fail-closed извлечение строки магазина из коллекции `shop/shops`:
 * без обязательных строковых полей контекст не показываем.
 */
export function shopHeadRow(value: unknown): ShopHeadRow | null {
    if (value === null || typeof value !== 'object') return null;
    const row = value as Record<string, unknown>;
    if (typeof row.shop_id !== 'string' || row.shop_id === '') return null;
    if (typeof row.name !== 'string' || row.name === '') return null;
    if (typeof row.slug !== 'string') return null;
    if (typeof row.status !== 'string') return null;
    return { shop_id: row.shop_id, name: row.name, slug: row.slug, status: row.status };
}

const STATUS_TONES: Record<string, string> = {
    draft: 'var(--text-tertiary)',
    published: 'var(--success)',
    suspended: 'var(--warning)',
};

export class ShopPageHead extends PlatformElement {
    static i18nNamespace = 'shop';

    static override properties: PropertyDeclarations = {
        shop: { attribute: false },
        shopId: { type: String, attribute: 'shop-id' },
        section: { type: String },
    };
    declare shop: ShopHeadRow | null;
    declare shopId: string;
    declare section: string;

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: block; margin-bottom: var(--space-5); }
            .title-row {
                display: flex;
                align-items: center;
                gap: var(--space-4);
                flex-wrap: wrap;
            }
            h1 {
                margin: 0;
                font-size: var(--text-2xl);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                letter-spacing: -0.01em;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .section-label {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-tertiary);
            }
            .status {
                display: inline-flex;
                align-items: center;
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
            }
            .storefront {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                font-size: var(--text-xs);
                color: var(--accent);
                text-decoration: none;
            }
            .storefront:hover { text-decoration: underline; }
            .meta {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                min-width: 0;
            }
            .actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                margin-left: auto;
                flex-wrap: wrap;
            }
            .actions:empty { display: none; }
            .slug {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            @media (max-width: 767px) {
                .actions { margin-left: 0; width: 100%; }
            }
        `,
    ];

    constructor() {
        super();
        this.shop = null;
        this.shopId = '';
        this.section = '';
    }

    override render(): TemplateResult {
        const shop = this.shop;
        const trail = shop !== null
            ? [{ label: shop.name, routeKey: 'shop_menu', params: { shopId: this.shopId } }]
            : [];
        const published = shop?.status === 'published';
        return html`
            <platform-breadcrumbs
                .trail=${trail}
                current-label=${this.section}
            ></platform-breadcrumbs>
            <div class="title-row">
                <h1>${shop !== null ? shop.name : this.section}</h1>
                ${shop !== null
                    ? html`
                        <div class="meta">
                            <span class="section-label">${this.section}</span>
                            <span class="status" style="color:${STATUS_TONES[shop.status] ?? 'var(--text-tertiary)'}">
                                ${this.t(`status.${shop.status}`)}
                            </span>
                            <span class="slug">${shop.slug}</span>
                            ${published
                                ? html`
                                    <a class="storefront"
                                        href="/shop/api/v1/public/s/${encodeURIComponent(shop.slug)}"
                                        target="_blank" rel="noopener"
                                    >
                                        <platform-icon name="globe" size="12"></platform-icon>
                                        ${this.t('context.open_storefront')}
                                    </a>`
                                : nothing}
                        </div>`
                    : nothing}
                <div class="actions"><slot name="actions"></slot></div>
            </div>
        `;
    }
}

customElements.define('shop-page-head', ShopPageHead);
