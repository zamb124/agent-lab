/**
 * Why-path bottom sheet for Access Explorer (mobile).
 */
import { html, css } from 'lit';
import { PlatformBottomSheet } from '@platform/lib/components/layout/platform-bottom-sheet.js';
import { registerBottomSheetKind } from '@platform/lib/utils/bottom-sheet-registry.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';
import '@platform/lib/components/platform-button.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';

export class FrontendAccessWhySheet extends PlatformBottomSheet {
    static bottomSheetKind = 'frontend.access_why';
    static i18nNamespace = 'frontend';

    static override properties: PropertyDeclarations = {
        ...PlatformBottomSheet.properties,
        userId: { type: String },
        objectType: { type: String },
        objectKey: { type: String },
        objectTitle: { type: String },
    }
    declare userId: string;
    declare objectType: string;
    declare objectKey: string;
    declare objectTitle: string;
;

    static override styles: CSSResultGroup = [
        PlatformBottomSheet.styles,
        css`
            .why-body { display: flex; flex-direction: column; gap: var(--space-3); }
            .why-item {
                padding: var(--space-3);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                color: var(--text-primary);
            }
            .why-empty { color: var(--text-secondary); }
            .why-meta {
                display: flex;
                flex-wrap: wrap;
                align-items: center;
                gap: var(--space-2);
            }
            .why-title {
                color: var(--text-primary);
                font-weight: var(--font-medium);
            }
        `,
    ];

    constructor() {
        super();
        this.userId = '';
        this.objectType = '';
        this.objectKey = '';
        this.objectTitle = '';
        this._why = this.useOp('frontend/authz_explorer_why');
        this._loadedKey = '';
    }
    private _why: OpController;
    private _loadedKey: string;


    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        this.heading = this.t('access_page.why_title');
        const key = `${this.userId}\n${this.objectType}\n${this.objectKey}`;
        if (key === this._loadedKey) {
            return;
        }
        if (this.userId === '' || this.objectType === '' || this.objectKey === '') {
            return;
        }
        this._loadedKey = key;
        void this._why.run({
            user_id: this.userId,
            object_type: this.objectType,
            object_key: this.objectKey,
        });
    }

    override renderBody() {
        const result = this._why.lastResult;
        if (this._why.busy && !result) {
            return html`<glass-spinner></glass-spinner>`;
        }
        if (this._why.error) {
            return html`<div class="why-empty">${this.t('access_page.why_error')}</div>`;
        }
        if (!result) {
            return html`<div class="why-empty">${this.t('access_page.why_empty')}</div>`;
        }
        if (!isPlainRecord(result)) {
            return html`<div class="why-empty">${this.t('access_page.why_empty')}</div>`;
        }
        const reasonsValue = result.reasons;
        const reasons = Array.isArray(reasonsValue) ? reasonsValue : [];
        const allowed = result.allowed === true;
        return html`
            <div class="why-body">
                <div class="why-meta">
                    <platform-user-chip user-id=${this.userId} size="sm"></platform-user-chip>
                    <div class="why-title">${
                        this.objectTitle !== ''
                            ? this.objectTitle
                            : this.t('access_page.title_missing')
                    }</div>
                    <platform-button
                        variant="ghost"
                        density="dense"
                        @click=${() => this._copyId()}
                    >${this.t('access_page.why_copy_id')}</platform-button>
                </div>
                <div class=${allowed ? 'why-item' : 'why-empty'}>
                    ${allowed
                        ? this.t('access_page.why_allowed')
                        : this.t('access_page.why_denied')}
                </div>
                ${reasons.length === 0
                    ? html`<div class="why-empty">${this.t('access_page.why_empty')}</div>`
                    : reasons.map((reason: string) => html`
                        <div class="why-item">${this.t(`access_page.why_${reason}`)}</div>
                    `)}
            </div>
        `;
    }

    _copyId() {
        this.copyToClipboard(`${this.objectType}:${this.objectKey}`, {
            success_i18n_key: 'frontend:access_page.toast_copied',
            error_i18n_key: 'frontend:access_page.err_clipboard',
        });
    }
}

customElements.define('frontend-access-why-sheet', FrontendAccessWhySheet);
registerBottomSheetKind(
    FrontendAccessWhySheet.bottomSheetKind,
    'frontend-access-why-sheet',
);
