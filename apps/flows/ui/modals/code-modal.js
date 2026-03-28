/**
 * CodeModal - модалка для показа JSON кода агента
 * Наследуется от PlatformModal (DRY)
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

const codeModalStyles = css`
    :host {
        --modal-max-width: 1200px;
    }

    .code-modal-title-row {
        display: inline-flex;
        align-items: center;
        gap: var(--space-2, 8px);
        min-width: 0;
        max-width: 100%;
    }

    .code-modal-title-text {
        overflow: hidden;
        text-overflow: ellipsis;
    }

    .code-container {
        flex: 1;
        overflow: auto;
        padding: var(--space-4);
        background: var(--bg-secondary);
    }

    pre {
        margin: 0;
        font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', monospace;
        font-size: 13px;
        line-height: 1.6;
        color: var(--text-primary);
        white-space: pre;
    }

    .json-key {
        color: #88C0D0;
    }

    .json-string {
        color: #A3BE8C;
    }

    .json-number {
        color: #B48EAD;
    }

    .json-boolean {
        color: #EBCB8B;
    }

    .json-null {
        color: #BF616A;
    }
`;

export class CodeModal extends PlatformModal {
    static styles = [PlatformModal.styles, codeModalStyles];

    static properties = {
        ...PlatformModal.properties,
        code: { type: Object },
    };

    constructor() {
        super();
        this.size = 'xl';
        this.code = null;
    }

    showModal(code) {
        this.code = code;
        super.showModal();
    }

    _copyWithExecCommand(text) {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', '');
        ta.style.position = 'fixed';
        ta.style.left = '-9999px';
        ta.style.top = '0';
        document.body.appendChild(ta);
        ta.focus();
        ta.select();
        ta.setSelectionRange(0, text.length);
        const ok = document.execCommand('copy');
        document.body.removeChild(ta);
        return ok;
    }

    async _onCopy() {
        const text = JSON.stringify(this.code, null, 2);
        let copied = false;
        if (navigator.clipboard?.writeText) {
            try {
                await navigator.clipboard.writeText(text);
                copied = true;
            } catch {
                copied = this._copyWithExecCommand(text);
            }
        } else {
            copied = this._copyWithExecCommand(text);
        }
        if (copied) {
            this.success('Код скопирован в буфер обмена');
        } else {
            this.error('Не удалось скопировать код');
        }
    }

    _syntaxHighlight(json) {
        let jsonStr = JSON.stringify(json, null, 2);
        jsonStr = jsonStr.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
        return jsonStr.replace(/("(\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+\-]?\d+)?)/g, (match) => {
            let cls = 'json-number';
            if (/^"/.test(match)) {
                if (/:$/.test(match)) {
                    cls = 'json-key';
                } else {
                    cls = 'json-string';
                }
            } else if (/true|false/.test(match)) {
                cls = 'json-boolean';
            } else if (/null/.test(match)) {
                cls = 'json-null';
            }
            return '<span class="' + cls + '">' + match + '</span>';
        });
    }

    renderHeader() {
        return html`
            <span class="code-modal-title-row">
                <platform-icon name="code" size="20"></platform-icon>
                <span class="code-modal-title-text">Код агента</span>
            </span>
        `;
    }

    renderHeaderActions() {
        return html`
            <button type="button" class="header-btn" title="Копировать" @click=${this._onCopy}>
                <platform-icon name="copy" size="16"></platform-icon>
            </button>
        `;
    }

    renderBody() {
        return html`
            <div class="code-container">
                <pre .innerHTML=${this.code ? this._syntaxHighlight(this.code) : ''}></pre>
            </div>
        `;
    }

    renderFooter() {
        return null;
    }
}

customElements.define('code-modal', CodeModal);
