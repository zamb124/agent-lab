/**
 * Модальное окно для просмотра Raw JSON
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';

export class RawJsonModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        css`
            :host {
                --modal-max-width: 900px;
            }
            
            .raw-json-container {
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                min-height: 400px;
                max-height: 70vh;
            }
            
            .raw-json-preview {
                flex: 1;
                padding: var(--space-4);
                background: var(--bg-primary);
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                font-family: var(--font-mono);
                font-size: var(--text-sm);
                white-space: pre-wrap;
                word-break: break-word;
                overflow-y: auto;
                line-height: 1.5;
                color: var(--text-primary);
            }
            
            .download-json-btn {
                padding: var(--space-2) var(--space-4);
                background: var(--accent);
                border: none;
                border-radius: var(--radius-md);
                color: white;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
            }
            
            .download-json-btn:hover {
                background: var(--accent-hover);
                box-shadow: 0 2px 6px rgba(16, 185, 129, 0.3);
                transform: translateY(-1px);
            }
        `
    ];

    static properties = {
        ...PlatformModal.properties,
        data: { type: Object },
        title: { type: String },
    };

    constructor() {
        super();
        this.title = 'Raw JSON';
        this.data = null;
        this.title = '';
    }

    connectedCallback() {
        super.connectedCallback();
        if (this._customTitle) {
            this.title = this._customTitle;
        }
    }

    _downloadJson() {
        const beautified = this._beautifyData(this.data);
        const jsonStr = JSON.stringify(beautified, null, 2);
        const blob = new Blob([jsonStr], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `${this.data?.span_id || 'data'}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }

    renderHeader() {
        return this.title;
    }

    renderHeaderActions() {
        return html`
            <button class="header-btn" @click=${this._downloadJson} title="Скачать JSON">
                ⬇
            </button>
        `;
    }

    _beautifyData(data) {
        if (!data || typeof data !== 'object') return data;
        
        const result = { ...data };
        
        // Парсим вложенные JSON строки в attributes
        if (result.attributes && typeof result.attributes === 'object') {
            const attrs = { ...result.attributes };
            
            const jsonFields = [
                'platform.llm.request',
                'platform.llm.response', 
                'platform.state.snapshot',
                'platform.tool.args',
                'platform.tool.result',
                'platform.prompt.variables'
            ];
            
            for (const field of jsonFields) {
                if (attrs[field] && typeof attrs[field] === 'string') {
                    try {
                        attrs[field] = JSON.parse(attrs[field]);
                    } catch {
                        // оставляем как есть
                    }
                }
            }
            
            result.attributes = attrs;
        }
        
        // Парсим attributes если это строка
        if (typeof result.attributes === 'string') {
            try {
                result.attributes = JSON.parse(result.attributes);
                return this._beautifyData(result);
            } catch {
                // оставляем как есть
            }
        }
        
        return result;
    }

    renderBody() {
        if (!this.data) {
            return html`<p>Нет данных</p>`;
        }

        const beautified = this._beautifyData(this.data);
        const jsonStr = JSON.stringify(beautified, null, 2);

        return html`
            <div class="raw-json-container">
                <pre class="raw-json-preview">${jsonStr}</pre>
            </div>
        `;
    }
}

customElements.define('raw-json-modal', RawJsonModal);

