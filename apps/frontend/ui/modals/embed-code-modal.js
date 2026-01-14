/**
 * Модалка с кодом для встраивания виджета
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { formStyles } from '@platform/lib/styles/shared/form.styles.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import '@platform/lib/components/glass-modal.js';

export class EmbedCodeModal extends PlatformElement {
    static styles = [
        PlatformElement.styles,
        formStyles,
        buttonStyles,
        css`
            .modal-description {
                font-size: 14px;
                color: rgba(0, 0, 0, 0.6);
                margin-bottom: 16px;
            }

            .code-block {
                background: rgba(0, 0, 0, 0.04);
                border: 1px solid rgba(0, 0, 0, 0.08);
                border-radius: 12px;
                padding: 16px;
                font-family: 'SF Mono', 'Monaco', 'Menlo', monospace;
                font-size: 13px;
                overflow-x: auto;
                white-space: pre;
                color: rgba(0, 0, 0, 0.85);
                line-height: 1.5;
            }

            .loading-state {
                text-align: center;
                padding: 32px;
                color: rgba(0, 0, 0, 0.5);
            }

            @media (prefers-color-scheme: dark) {
                .modal-description {
                    color: rgba(255, 255, 255, 0.6);
                }

                .code-block {
                    background: rgba(255, 255, 255, 0.05);
                    border-color: rgba(255, 255, 255, 0.1);
                    color: rgba(255, 255, 255, 0.9);
                }

                .loading-state {
                    color: rgba(255, 255, 255, 0.5);
                }
            }
        `
    ];

    constructor() {
        super();
        this._embedId = '';
        this._code = '';
        this._open = false;
        this._loading = false;
    }

    async show(embedId) {
        this._embedId = embedId;
        this._open = true;
        this._loading = true;
        this.requestUpdate();
        
        const data = await this.services.get('embed').getCode(embedId);
        this._code = data.html_code;
        this._loading = false;
        this.requestUpdate();
    }

    _handleClose() {
        this._open = false;
        this.dispatchEvent(new CustomEvent('close'));
    }

    async _handleCopy() {
        await navigator.clipboard.writeText(this._code);
        this.success('Код скопирован в буфер обмена');
    }

    render() {
        return html`
            <glass-modal 
                ?open=${this._open} 
                @close=${this._handleClose}
                size="lg"
            >
                <span slot="title">Код для встраивания</span>
                
                <div slot="content">
                    ${this._loading ? html`
                        <div class="loading-state">Загрузка...</div>
                    ` : html`
                        <p class="modal-description">
                            Вставьте этот код на свой сайт перед закрывающим тегом &lt;/body&gt;:
                        </p>
                        <div class="code-block">${this._code}</div>
                    `}
                </div>
                
                <div slot="actions">
                    ${this._loading ? html`` : html`
                        <button class="btn btn-primary" style="width: 100%;" @click=${this._handleCopy}>
                            Скопировать код
                        </button>
                    `}
                </div>
            </glass-modal>
        `;
    }
}

customElements.define('embed-code-modal', EmbedCodeModal);
