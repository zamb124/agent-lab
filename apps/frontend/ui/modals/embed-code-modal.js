/**
 * Модалка с кодом для встраивания виджета
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import '@platform/lib/components/platform-icon.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';

export class EmbedCodeModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        formStyles,
        buttonStyles,
        css`
            .modal-description {
                font-size: 14px;
                color: var(--text-secondary);
                margin-bottom: 16px;
                line-height: 1.5;
            }

            .steps {
                margin: 0 0 16px 0;
                padding-left: 18px;
                color: var(--text-secondary);
                line-height: 1.6;
                font-size: 14px;
            }

            .steps li {
                margin-bottom: 6px;
            }

            .section-title {
                margin: 16px 0 8px;
                font-size: 13px;
                font-weight: 600;
                color: var(--text-primary);
            }

            .code-block {
                background: var(--glass-tint-subtle);
                border: 1px solid var(--border-default);
                border-radius: 12px;
                padding: 16px;
                font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
                font-size: 13px;
                overflow-x: auto;
                white-space: pre;
                color: var(--text-primary);
                line-height: 1.5;
            }

            .code-actions {
                display: flex;
                justify-content: flex-end;
                margin: 8px 0 16px;
            }

            .loading-state {
                text-align: center;
                padding: 32px;
                color: var(--text-tertiary);
            }
        `,
    ];

    constructor() {
        super();
        this.size = 'lg';
        this.open = false;
        this._embedId = '';
        this._code = '';
        this._tokenEndpoint = '';
        this._loading = false;
    }

    connectedCallback() {
        super.connectedCallback();
        this._i18nUnsub = this.i18n.subscribe(() => this.requestUpdate());
    }

    disconnectedCallback() {
        if (this._i18nUnsub) {
            this._i18nUnsub();
            this._i18nUnsub = null;
        }
        super.disconnectedCallback();
    }

    async show(embedId) {
        this._embedId = embedId;
        this.open = true;
        this._loading = true;
        this.requestUpdate();
        try {
            const data = await this.services.get('embed').getCode(embedId);
            this._code = data.html_code;
            this._tokenEndpoint = data.token_endpoint || '';
        } catch (error) {
            const message = error instanceof Error ? error.message : this.i18n.t('embed_code_modal.load_error', {});
            this.error(message);
            throw error;
        } finally {
            this._loading = false;
            this.requestUpdate();
        }
    }

    close() {
        this.open = false;
        super.close();
        this.dispatchEvent(new CustomEvent('close'));
    }

    _handleClose() {
        this.close();
    }

    async _copyToClipboard(text) {
        if (typeof navigator !== 'undefined' && navigator.clipboard?.writeText) {
            try {
                await navigator.clipboard.writeText(text);
                return;
            } catch {
                // Secure Context может отказать — пробуем execCommand
            }
        }
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.cssText = 'position:fixed;left:-9999px;top:0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        try {
            const ok = document.execCommand('copy');
            if (!ok) {
                throw new Error(this.i18n.t('embed_code_modal.err_copy_cmd', {}));
            }
        } finally {
            document.body.removeChild(ta);
        }
    }

    async _handleCopy() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        if (!this._code) {
            this.error(td('embed_code_modal.err_no_code'));
            return;
        }
        try {
            await this._copyToClipboard(this._code);
            this.success(td('embed_code_modal.toast_copied'));
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(td('embed_code_modal.err_copy_failed', { msg }));
        }
    }

    _buildBackendTokenProxyExample() {
        const endpoint = this._tokenEndpoint || 'https://api.humanitec.ru/frontend/api/embed/configs/embed_xxx/session-token';
        const escapedEndpoint = endpoint.replaceAll('"', '\\"');
        return `curl -X POST "${escapedEndpoint}" \\
  -H "Authorization: Bearer hum_YOUR_ISSUER_TOKEN" \\
  -H "Content-Type: application/json" \\
  -d '{"origin":"https://your-site.example","expires_in_seconds":300}'`;
    }

    _buildClientBackendCallExample() {
        return `fetch('/api/chat-token', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    embed_id: '${this._embedId}',
    origin: window.location.origin,
    expires_in_seconds: 300
  })
});`;
    }

    async _handleCopyTokenEndpoint() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        if (!this._tokenEndpoint) {
            this.error(td('embed_code_modal.err_no_token_endpoint'));
            return;
        }
        try {
            await this._copyToClipboard(this._tokenEndpoint);
            this.success(td('embed_code_modal.toast_copied'));
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(td('embed_code_modal.err_copy_failed', { msg }));
        }
    }

    async _handleCopyBackendProxyExample() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        try {
            await this._copyToClipboard(this._buildBackendTokenProxyExample());
            this.success(td('embed_code_modal.toast_copied'));
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(td('embed_code_modal.err_copy_failed', { msg }));
        }
    }

    async _handleCopyClientBackendExample() {
        const td = (k, p) => this.i18n.t(k, p ?? {});
        try {
            await this._copyToClipboard(this._buildClientBackendCallExample());
            this.success(td('embed_code_modal.toast_copied'));
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e);
            this.error(td('embed_code_modal.err_copy_failed', { msg }));
        }
    }

    renderHeader() {
        return this.i18n.t('embed_code_modal.header', {});
    }

    renderHeaderActions() {
        const td = (k) => this.i18n.t(k, {});
        if (this._loading || !this._code) {
            return html``;
        }
        return html`
            <button
                type="button"
                class="header-btn"
                title=${td('embed_code_modal.copy_title')}
                aria-label=${td('embed_code_modal.copy_title')}
                @click=${this._handleCopy}
            >
                <platform-icon name="copy" size="16"></platform-icon>
            </button>
        `;
    }

    renderBody() {
        const td = (k) => this.i18n.t(k, {});
        const backendProxyExample = this._buildBackendTokenProxyExample();
        const clientBackendExample = this._buildClientBackendCallExample();
        return this._loading
            ? html`<div class="loading-state">${td('embed_code_modal.loading')}</div>`
            : html`
                <p class="modal-description">${td('embed_code_modal.token_howto_title')}</p>
                <ol class="steps">
                    <li>${td('embed_code_modal.token_howto_step_1')}</li>
                    <li>${td('embed_code_modal.token_howto_step_2')}</li>
                    <li>${td('embed_code_modal.token_howto_step_3')}</li>
                </ol>

                <p class="modal-description">
                    ${td('embed_code_modal.description')}
                </p>
                <div class="code-block">${this._code}</div>

                <p class="modal-description">
                    ${td('embed_code_modal.token_endpoint_description')}
                </p>
                <div class="code-block">${this._tokenEndpoint}</div>
                <div class="code-actions">
                    <button class="btn btn-secondary" @click=${this._handleCopyTokenEndpoint}>
                        ${td('embed_code_modal.copy_token_endpoint')}
                    </button>
                </div>

                <p class="section-title">${td('embed_code_modal.backend_proxy_example_title')}</p>
                <div class="code-block">${backendProxyExample}</div>
                <div class="code-actions">
                    <button class="btn btn-secondary" @click=${this._handleCopyBackendProxyExample}>
                        ${td('embed_code_modal.copy_backend_proxy_example')}
                    </button>
                </div>

                <p class="section-title">${td('embed_code_modal.client_backend_example_title')}</p>
                <div class="code-block">${clientBackendExample}</div>
                <div class="code-actions">
                    <button class="btn btn-secondary" @click=${this._handleCopyClientBackendExample}>
                        ${td('embed_code_modal.copy_client_backend_example')}
                    </button>
                </div>
            `;
    }

    renderFooter() {
        return html``;
    }

    render() {
        if (!this.open) {
            return html``;
        }
        return super.render();
    }
}

customElements.define('embed-code-modal', EmbedCodeModal);
