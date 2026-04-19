/**
 * System access modal — выбор роли для входа админа в чужую компанию.
 *
 * Открывается с props { company_id }. После выбора роли вызывает
 * `systemAccessEnterOp` через useOp; обновление списка компаний делает
 * onSuccess в фабрике.
 */
import { html } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';

const ROLES = ['admin', 'developer', 'viewer'];

export class FrontendSystemAccessModal extends PlatformFormModal {
    static modalKind = 'frontend.system_access';

    static properties = {
        ...PlatformFormModal.properties,
        company_id: { type: String },
        _role: { state: true },
    };

    constructor() {
        super();
        this.company_id = '';
        this._role = 'admin';
        this.size = 'sm';
        this._enter = this.useOp('frontend/admin_system_access_enter');
    }

    willUpdate(changed) {
        super.willUpdate(changed);
        this.title = this.t('platform_billing_page.system_access_modal_title');
    }

    validateForm() {
        const errors = {};
        if (!this.company_id) {
            errors.company_id = this.t('platform_billing_page.system_access_company_required');
        }
        if (!ROLES.includes(this._role)) {
            errors.role = this.t('platform_billing_page.system_access_company_required');
        }
        return errors;
    }

    async handleSubmit() {
        this._enter.run({ company_id: this.company_id, role: this._role });
        this.closeAfterSave();
    }

    renderBody() {
        return html`
            <p>${this.t('platform_billing_page.system_access_modal_subtitle', { company_id: this.company_id })}</p>
            <div class="form-group">
                ${ROLES.map((role) => html`
                    <label style="display:flex;align-items:center;gap:var(--space-2);padding:var(--space-2)">
                        <input
                            type="radio"
                            name="role"
                            value=${role}
                            ?checked=${this._role === role}
                            @change=${() => { this._role = role; this.isDirty = true; }}
                        />
                        ${this.t(`platform_billing_page.system_access_role_${role}`)}
                    </label>
                `)}
            </div>
        `;
    }

    renderFooter() {
        return html`
            <div class="form-actions">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.t('platform_billing_page.cancel')}
                </button>
                <button type="button" class="btn btn-primary" @click=${() => this._performSave()}>
                    ${this.t('platform_billing_page.system_access_enter')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-system-access-modal', FrontendSystemAccessModal);
registerModalKind(FrontendSystemAccessModal.modalKind, 'frontend-system-access-modal');
