/**
 * ShopMenuTemplateModal — новое меню из блюд каталога силами агента.
 *
 * `shop/menu_template_build` ставит WorkItem агенту `shop_menu_agent`
 * (`mode=template`): агент собирает меню `menu_name` по описанию `brief`
 * только из существующих блюд. Ход задачи — `shop-agent-jobs-banner`.
 */

import { html, css } from 'lit';
import type { TemplateResult } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import type { ControllerFor } from '@platform/lib/base/use-resource.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/fields/platform-field.js';

export class ShopMenuTemplateModal extends PlatformModal {
    static modalKind = 'shop.menu_template';
    static i18nNamespace = 'shop';

    declare shopId: string;

    private _buildOp: ControllerFor<'shop/menu_template_build'>;

    declare _menuName: string;
    declare _brief: string;

    static override properties = {
        ...PlatformModal.properties,
        shopId: { type: String, attribute: 'shop-id' },
        _menuName: { state: true },
        _brief: { state: true },
    };

    static override styles = [
        ...(PlatformModal.styles ? [PlatformModal.styles] : []),
        css`
            .body { display: flex; flex-direction: column; gap: var(--space-4); padding: var(--space-4); }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); line-height: 1.5; }
            .actions { display: flex; gap: var(--space-2); justify-content: flex-end; }
        `,
    ];

    constructor() {
        super();
        this._menuName = '';
        this._brief = '';
        this._buildOp = this.useOp('shop/menu_template_build');
    }

    override connectedCallback(): void {
        super.connectedCallback();
        if (typeof this.shopId !== 'string' || this.shopId.length === 0) {
            throw new Error('ShopMenuTemplateModal: prop "shopId" required');
        }
    }

    private async _submit() {
        const menuName = this._menuName.trim();
        if (menuName === '') return;
        const started = await this._buildOp.run({ shop_id: this.shopId, menu_name: menuName, brief: this._brief.trim() });
        if (started !== null) this.close();
    }

    override renderHeader() {
        return this.t('menu_template.title');
    }

    override renderBody(): TemplateResult {
        return html`
            <div class="body">
                <div class="hint">${this.t('menu_template.hint')}</div>
                <platform-field type="string" mode="edit" label=${this.t('menu_template.field_name')} .value=${this._menuName}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._menuName = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <platform-field type="text" mode="edit" label=${this.t('menu_template.field_brief')} .value=${this._brief}
                    .hint=${this.t('menu_template.brief_placeholder')}
                    @change=${(e: CustomEvent<{ value?: unknown }>) => { this._brief = typeof e.detail.value === 'string' ? e.detail.value : ''; }}
                ></platform-field>
                <div class="actions">
                    <platform-button variant="secondary" @click=${() => this.close()}>${this.t('menu_template.cancel')}</platform-button>
                    <platform-button variant="primary" ?loading=${this._buildOp.busy} ?disabled=${this._menuName.trim() === ''}
                        @click=${() => this._submit()}
                    ><platform-icon name="sparkle" size="14"></platform-icon> ${this.t('menu_template.build')}</platform-button>
                </div>
            </div>`;
    }
}

customElements.define('shop-menu-template-modal', ShopMenuTemplateModal);
registerModalKind(ShopMenuTemplateModal.modalKind, 'shop-menu-template-modal');
