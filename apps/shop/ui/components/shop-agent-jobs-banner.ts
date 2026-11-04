/**
 * shop-agent-jobs-banner — активные задачи агента `shop_menu_agent` заведения:
 * импорт меню, меню из каталога, обогащение блюд.
 *
 * Список — `shop/menu_imports_list`; фабрика перечитывает его по push
 * `worktracker/work_item/*` со ссылкой на заведение и по старту новой задачи.
 * Строка задачи — core `<platform-work-item-row>`.
 */

import { html, css, nothing } from 'lit';
import type { PropertyDeclarations, PropertyValues, TemplateResult } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-spinner.js';
import '@platform/lib/components/platform-work-item-row.js';

export class ShopAgentJobsBanner extends PlatformElement {
    static i18nNamespace = 'shop';

    static override properties: PropertyDeclarations = {
        shopId: { type: String, attribute: 'shop-id' },
    };
    declare shopId: string;

    private _jobs: ControllerFor<'shop/menu_imports_list'>;

    static override styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .banner {
                display: flex; flex-direction: column; gap: var(--space-1);
                border: 1px solid color-mix(in srgb, var(--accent) 30%, transparent);
                border-radius: var(--radius-lg);
                background: color-mix(in srgb, var(--accent) 6%, var(--bg-surface));
                padding: var(--space-3);
                margin-bottom: var(--space-4);
            }
            .head {
                display: flex; align-items: center; gap: var(--space-2);
                color: var(--text-primary); font-weight: var(--font-semibold); font-size: var(--text-sm);
                padding: 0 var(--space-1);
            }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); padding: 0 var(--space-1); }
        `,
    ];

    constructor() {
        super();
        this.shopId = '';
        this._jobs = this.useOp('shop/menu_imports_list');
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (changed.has('shopId') && this.shopId !== '') {
            void this._jobs.run({ shop_id: this.shopId });
        }
    }

    override render(): TemplateResult | typeof nothing {
        const result = this._jobs.lastResult;
        if (result === null || result.items.length === 0) {
            return nothing;
        }
        return html`
            <div class="banner" role="status">
                <div class="head">
                    <platform-spinner size="16"></platform-spinner>
                    ${this.t('jobs.title', { count: result.items.length })}
                </div>
                <div class="hint">${this.t('jobs.hint')}</div>
                ${result.items.map((item) => html`<platform-work-item-row .item=${item}></platform-work-item-row>`)}
            </div>
        `;
    }
}

customElements.define('shop-agent-jobs-banner', ShopAgentJobsBanner);
