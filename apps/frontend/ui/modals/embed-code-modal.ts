/**
 * Модалка embed-кода — диалог только для отображения с HTML/JS-кодом виджета и
 * S2S-инструкциями по выдаче short-lived embed-session токена.
 *
 * Загружает данные через op `frontend/embed_code` (load by embed_id);
 * результат проецируется в slice как `codeByEmbedId[id]`, чтобы повторное
 * открытие модалки на тот же embed_id не требовало перезагрузки.
 *
 * Все операции копирования — через `this.copyToClipboard(...)`.
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { registerModalKind } from '@platform/lib/utils/modal-registry.js';
import '@platform/lib/components/glass-spinner.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues} from 'lit';
import type { OpController } from '@platform/lib/base/use-resource.js';

export class FrontendEmbedCodeModal extends PlatformModal {
    static modalKind = 'frontend.embed_code';

    static override properties: PropertyDeclarations = {
        ...PlatformModal.properties,
        embedId: { type: String },
    }
    declare embedId: string;
;

    static override styles: CSSResultGroup = [
        PlatformModal.styles,
        css`
            .section { margin-bottom: var(--space-5); }
            .section-title {
                color: var(--text-primary);
                font-weight: var(--font-semibold);
                font-size: var(--text-sm);
                margin-bottom: var(--space-2);
            }
            .section-desc {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                margin-bottom: var(--space-2);
            }
            pre {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                background: var(--glass-solid-subtle);
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle, var(--glass-border-subtle));
                white-space: pre;
                overflow-x: auto;
                overflow-y: auto;
                word-break: normal;
                overflow-wrap: normal;
                tab-size: 2;
                line-height: 1.5;
                max-height: 360px;
                color: var(--text-primary);
                margin: 0 0 var(--space-2) 0;
                -webkit-overflow-scrolling: touch;
            }
            .endpoint {
                font-family: var(--font-mono);
                font-size: var(--text-xs);
                background: var(--glass-solid-subtle);
                padding: var(--space-2) var(--space-3);
                border-radius: var(--radius-md);
                color: var(--text-primary);
                user-select: all;
                margin-bottom: var(--space-2);
                word-break: break-all;
            }
            ol { padding-left: var(--space-5); margin: var(--space-2) 0; color: var(--text-secondary); font-size: var(--text-sm); }
            ol li { margin-bottom: var(--space-1); }
            .actions { display: flex; gap: var(--space-3); justify-content: flex-end; width: 100%; }
            .btn {
                padding: var(--space-2) var(--space-4);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                cursor: pointer;
                font-size: var(--text-sm);
                background: transparent;
                color: var(--text-primary);
            }
            .btn:hover { border-color: var(--accent); }
            .btn-primary { background: var(--accent); border-color: var(--accent); color: white; }
            .btn-primary:hover { filter: brightness(1.1); }
            .copy-btn {
                font-size: var(--text-xs);
                padding: 4px 10px;
                margin-bottom: var(--space-3);
            }
            .loading {
                padding: var(--space-6);
                display: flex; justify-content: center;
            }
        `,
    ];

    constructor() {
        super();
        this.embedId = '';
        this.size = 'lg';
        this._code = this.useOp('frontend/embed_code');
        this._loaded = false;
    }
    private _code: OpController;
    private _loaded: boolean;


    override willUpdate(changed: PropertyValues<this>): void {
        super.willUpdate(changed);
        this.title = this.t('embed_code_modal.header');
        if (changed.has('open') && this.open && this.embedId && !this._loaded) {
            this._loaded = true;
            this._code.run({ embed_id: this.embedId, public_origin: window.location.origin });
        }
        if (changed.has('embedId')) {
            this._loaded = false;
        }
    }

    _entry() {
        if (typeof this.embedId !== 'string' || this.embedId.length === 0) return null;
        const map = this._code.state.codeByEmbedId;
        if ((map as Record<string, any>)[this.embedId] === undefined) return null;
        return (map as Record<string, any>)[this.embedId];
    }

    _isLoading() {
        if (typeof this.embedId !== 'string' || this.embedId.length === 0) return false;
        const map = this._code.state.codeLoadingById;
        return Boolean((map as Record<string, any>)[this.embedId]);
    }

    _copy(text: string, successKey: string) {
        if (!text) {
            this.toast('embed_code_modal.err_no_code', { type: 'error' });
            return;
        }
        this.copyToClipboard(text, {
            success_i18n_key: successKey,
            error_i18n_key: 'embed_code_modal.err_copy_failed',
        });
    }

    override renderBody() {
        if (this._isLoading() || !this._entry()) {
            return html`<div class="loading"><glass-spinner></glass-spinner></div>`;
        }
        const entry = this._entry();
        const html_code = entry.html_code;
        const page_url = typeof entry.page_url === 'string' ? entry.page_url : '';
        const presentation = entry.presentation === 'page' ? 'page' : 'drawer';
        const token_endpoint = entry.token_endpoint;
        const backendExample = typeof entry.backend_proxy_code === 'string' ? entry.backend_proxy_code : '';
        const clientExample = typeof entry.browser_to_host_backend_code === 'string' ? entry.browser_to_host_backend_code : '';
        const origins = Array.isArray(entry.allowed_origins) ? entry.allowed_origins : [];
        return html`
            ${presentation === 'page' && page_url ? html`
            <div class="section">
                <div class="section-title">${this.t('embed_code_modal.page_url_title')}</div>
                <div class="section-desc">${this.t('embed_code_modal.page_url_description')}</div>
                <div class="endpoint">${page_url}</div>
                <button class="btn btn-primary copy-btn"
                    @click=${() => this._copy(page_url, 'embed_code_modal.toast_copied')}
                >${this.t('embed_code_modal.copy_page_url')}</button>
            </div>
            ` : ''}

            <div class="section">
                <div class="section-title">${this.t('embed_code_modal.snippet_title')}</div>
                <div class="section-desc">${this.t('embed_code_modal.description')}</div>
                <pre>${html_code}</pre>
                <button class="btn btn-primary copy-btn"
                    @click=${() => this._copy(html_code, 'embed_code_modal.toast_copied')}
                >${this.t('embed_code_modal.copy_title')}</button>
            </div>

            <div class="section">
                <div class="section-title">${this.t('embed_code_modal.token_howto_title')}</div>
                <ol>
                    <li>${this.t('embed_code_modal.token_howto_step_1')}</li>
                    <li>${this.t('embed_code_modal.token_howto_step_2')}</li>
                    <li>${this.t('embed_code_modal.token_howto_step_3')}</li>
                </ol>
                <div class="section-desc">${this.t('embed_code_modal.token_endpoint_description')}</div>
                <div class="endpoint">${token_endpoint}</div>
                <button class="btn copy-btn"
                    @click=${() => this._copy(token_endpoint, 'embed_code_modal.toast_copied')}
                >${this.t('embed_code_modal.copy_token_endpoint')}</button>
            </div>

            <div class="section">
                <div class="section-title">${this.t('embed_code_modal.allowed_origins_title')}</div>
                <div class="section-desc">
                    ${origins.length === 0
                        ? this.t('embed_code_modal.allowed_origins_empty')
                        : this.t('embed_code_modal.allowed_origins_nonempty')}
                </div>
                <pre>${origins.length === 0 ? '[]' : JSON.stringify(origins, null, 2)}</pre>
            </div>

            <div class="section">
                <div class="section-title">${this.t('embed_code_modal.backend_proxy_example_title')}</div>
                <pre>${backendExample}</pre>
                <button class="btn copy-btn"
                    @click=${() => this._copy(backendExample, 'embed_code_modal.toast_copied')}
                >${this.t('embed_code_modal.copy_backend_proxy_example')}</button>
            </div>

            <div class="section">
                <div class="section-title">${this.t('embed_code_modal.client_backend_example_title')}</div>
                <div class="section-desc">${this.t('embed_code_modal.client_backend_example_description')}</div>
                <pre>${clientExample}</pre>
                <button class="btn copy-btn"
                    @click=${() => this._copy(clientExample, 'embed_code_modal.toast_copied')}
                >${this.t('embed_code_modal.copy_client_backend_example')}</button>
            </div>
        `;
    }

    override renderFooter() {
        return html`
            <div class="actions">
                <button class="btn" @click=${() => this.close()}>
                    ${this.t('embed_create_modal.cancel')}
                </button>
            </div>
        `;
    }
}

customElements.define('frontend-embed-code-modal', FrontendEmbedCodeModal);
registerModalKind(FrontendEmbedCodeModal.modalKind, 'frontend-embed-code-modal');
