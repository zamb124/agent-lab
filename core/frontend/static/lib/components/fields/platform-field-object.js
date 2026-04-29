import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import { formStyles } from '../../styles/shared/form.styles.js';

export class PlatformFieldObject extends PlatformElement {
    static properties = {
        value: { type: Object },
        mode: { type: String },
        disabled: { type: Boolean },
        flat: { type: Boolean, reflect: true },
    };

    static styles = [
        PlatformElement.styles,
        formStyles,
        css`
            :host { display: block; }

            .view-json {
                font-family: 'SF Mono', 'Fira Code', monospace;
                font-size: var(--text-xs);
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
                border: 1px solid var(--glass-border-subtle);
                border-radius: var(--radius-md);
                padding: var(--space-3);
                white-space: pre-wrap;
                word-break: break-word;
                max-height: 200px;
                overflow-y: auto;
            }

            .empty {
                font-size: var(--text-sm);
                color: var(--text-disabled);
                font-style: italic;
            }

            .form-textarea {
                font-family: 'SF Mono', 'Fira Code', monospace;
                font-size: var(--text-xs);
                min-height: 100px;
                resize: vertical;
            }

            .json-error {
                font-size: var(--text-xs);
                color: var(--error);
                margin-top: var(--space-1);
            }
        `,
    ];

    constructor() {
        super();
        this.value = null;
        this.mode = 'view';
        this.disabled = false;
        this.flat = false;
        this._jsonError = '';
    }

    _onInput(e) {
        const raw = e.target.value.trim();
        if (raw === '') {
            this._jsonError = '';
            this.requestUpdate();
            this.dispatchEvent(new CustomEvent('change', {
                detail: { value: null },
                bubbles: true,
                composed: true,
            }));
            return;
        }

        try {
            const parsed = JSON.parse(raw);
            this._jsonError = '';
            this.requestUpdate();
            this.dispatchEvent(new CustomEvent('change', {
                detail: { value: parsed },
                bubbles: true,
                composed: true,
            }));
        } catch {
            this._jsonError = 'Invalid JSON';
            this.requestUpdate();
        }
    }

    _serialize(val) {
        if (val == null) return '';
        return JSON.stringify(val, null, 2);
    }

    render() {
        if (this.mode === 'view') {
            if (this.value == null || (typeof this.value === 'object' && Object.keys(this.value).length === 0)) {
                return html`<span class="empty">${(this.t('platform_field.empty_value') || 'platform_field.empty_value')}</span>`;
            }
            return html`<pre class="view-json">${this._serialize(this.value)}</pre>`;
        }

        return html`
            <textarea
                class="form-textarea"
                .value=${this._serialize(this.value)}
                placeholder=${(this.t('platform_field.object_placeholder') || 'platform_field.object_placeholder')}
                ?disabled=${this.disabled}
                @input=${this._onInput}
            ></textarea>
            ${this._jsonError ? html`<div class="json-error">${this._jsonError}</div>` : ''}
        `;
    }
}

customElements.define('platform-field-object', PlatformFieldObject);
