/**
 * Модалка system access — выбор роли для входа админа в чужую компанию.
 *
 * Открывается с props { company_id }. После выбора роли вызывает
 * `systemAccessEnterOp` через useOp; обновление списка компаний делает
 * onSuccess в фабрике.
 */
import { html } from 'lit';
import { PlatformFormModal } from '@platform/lib/components/glass-form-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import type {PropertyDeclarations, PropertyValues} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';

const ROLES = ['admin', 'developer', 'viewer'];

export class FrontendSystemAccessModal extends PlatformFormModal {
    static modalKind = 'frontend.system_access';

    static override properties: PropertyDeclarations = {
        ...PlatformFormModal.properties,
        company_id: { type: String },
        _role: { state: true },
    }
    declare company_id: string;
    declare _role: string;
;

    constructor() {
        super();
        this.company_id = '';
        this._role = 'admin';
        this.size = 'sm';
        this._enter = this.useOp('frontend/admin_system_access_enter');
    }
    private _enter: OpController;


    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.title = this.t('platform_billing_page.system_access_modal_title');
    }

    override validateForm() {
        const errors: Record<string, any> = {};
        if (!this.company_id) {
            errors.company_id = this.t('platform_billing_page.system_access_company_required');
        }
        if (!ROLES.includes(this._role)) {
            errors.role = this.t('platform_billing_page.system_access_company_required');
        }
        return errors;
    }

    override async handleSubmit() {
        this._enter.run({ company_id: this.company_id, role: this._role });
        this.closeAfterSave();
    }

    override renderBody() {
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

    override renderFooter() {
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
