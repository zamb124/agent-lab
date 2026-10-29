/**
 * flows-preview-share-modal — одноразовая гостевая ссылка на embed-тест текущего flow/ветки.
 */

import type { OpController } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import { copyTextToClipboard } from '@platform/lib/utils/clipboard.js';
import { isPlainRecord } from '@platform/lib/events/payload.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/fields/platform-field.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';

export class FlowsPreviewShareModal extends PlatformModal {
    static modalKind = 'flows.preview_share';
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        _guestCap: { state: true },
        _localShareUrl: { state: true },
    }
    declare flowId: string;
    declare branchId: string;
    declare _guestCap: any;
    declare _localShareUrl: any;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        css`
            .body-wrap {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-width: min(420px, calc(100vw - 48px));
            }
            .row-actions {
                display: flex;
                justify-content: flex-end;
                gap: var(--space-2);
            }
            .err {
                font-size: var(--text-sm);
                color: var(--danger);
            }
        `,
    ];
    private _previewShare: OpController;

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'default';
        this._guestCap = null;
        this._localShareUrl = null;
        this.size = 'md';
        this._previewShare = this.useOp('flows/flow_preview_share');
    }

    override willUpdate(changedProps: PropertyValues<this>): void {
        super.willUpdate(changedProps);
        if (changedProps.has('open') && this.open) {
            this._guestCap = null;
            this._localShareUrl = null;
        }
    }

    _onGuestCapChange(e: Event) {
        if (!(e instanceof CustomEvent) || !isPlainRecord(e.detail)) {
            this._guestCap = null;
            return;
        }
        const value = e.detail.value;
        this._guestCap = typeof value === 'number' && Number.isFinite(value) ? value : null;
    }

    async _createLink() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        const bid =
            typeof this.branchId === 'string' && this.branchId.trim() !== ''
                ? this.branchId.trim()
                : 'default';
        const payload: any = { flow_id: this.flowId, branch_id: bid };
        if (this._guestCap != null) {
            const n = Math.trunc(this._guestCap);
            if (n < 1 || n > 500) {
                this.toast('flows:preview_share.err_guest_max', { type: 'error' });
                return;
            }
            payload.guest_max_user_messages = n;
        }
        const out = await this._previewShare.run(payload);
        if (isPlainRecord(out)) {
            const shareUrl = out.share_url;
            if (typeof shareUrl === 'string' && shareUrl.length > 0) {
                this._localShareUrl = shareUrl;
            }
        }
        this.requestUpdate();
    }

    async _copyUrl(url: string) {
        if (typeof url !== 'string' || url.length === 0) {
            throw new Error('FlowsPreviewShareModal._copyUrl: url required');
        }
        await copyTextToClipboard(url);
        this.toast('flows:preview_share.copy_toast', { type: 'success' });
    }

    override renderHeader() {
        return this.t('preview_share.title');
    }

    override renderBody() {
        const st = this._previewShare.state;
        const shareUrl = typeof this._localShareUrl === 'string' ? this._localShareUrl : '';

        if (shareUrl.length > 0) {
            return html`
                <div class="body-wrap">
                    <platform-field
                        type="string"
                        mode="view"
                        label=${this.t('preview_share.url_label')}
                        .value=${shareUrl}
                    ></platform-field>
                    <div class="row-actions">
                        <platform-button variant="secondary" @click=${() => this._copyUrl(shareUrl)}>
                            <platform-icon name="copy" size="14"></platform-icon>
                            ${this.t('preview_share.copy')}
                        </platform-button>
                    </div>
                    <p style="font-size: var(--text-xs); color: var(--text-secondary);">
                        ${this.t('preview_share.hint_author')}
                    </p>
                </div>
            `;
        }

        if (st.busy) {
            return html`
                <div class="body-wrap">
                    <glass-spinner></glass-spinner>
                </div>
            `;
        }
        if (st.error) {
            return html`
                <div class="body-wrap">
                    <p class="err">${st.error}</p>
                </div>
            `;
        }

        return html`
            <div class="body-wrap">
                <platform-field
                    type="integer"
                    mode="edit"
                    label=${this.t('preview_share.guest_max_label')}
                    placeholder=${this.t('preview_share.guest_max_placeholder')}
                    hint=${this.t('preview_share.guest_max_hint')}
                    .value=${this._guestCap}
                    @change=${this._onGuestCapChange}
                ></platform-field>
                <p style="font-size: var(--text-xs); color: var(--text-secondary);">
                    ${this.t('preview_share.form_hint')}
                </p>
            </div>
        `;
    }

    override renderFooter() {
        const st = this._previewShare.state;
        const shareUrl = typeof this._localShareUrl === 'string' ? this._localShareUrl : '';
        if (shareUrl.length > 0) {
            return html`
                <platform-button variant="primary" @click=${() => this.close()}>
                    ${this.t('preview_share.close')}
                </platform-button>
            `;
        }
        return html`
            <platform-button variant="primary" ?disabled=${st.busy} @click=${() => void this._createLink()}>
                ${this.t('preview_share.create')}
            </platform-button>
        `;
    }
}

customElements.define('flows-preview-share-modal', FlowsPreviewShareModal);
registerModalKind(FlowsPreviewShareModal.modalKind, 'flows-preview-share-modal');
