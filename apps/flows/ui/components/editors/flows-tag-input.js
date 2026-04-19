/**
 * flows-tag-input — chip-input для строковых тегов.
 *
 * Поведение: Enter / запятая → добавить тег; Backspace в пустом поле →
 * удалить последний тег. Дубликаты игнорируются.
 *
 * Property API:
 *   - tags: string[]
 *   - placeholder: string
 *
 * Events (emit):
 *   - 'change' { tags }
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class FlowsTagInput extends PlatformElement {
    static properties = {
        tags: { type: Array },
        placeholder: { type: String },
        _draft: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .wrap {
                display: flex; flex-wrap: wrap; align-items: center;
                gap: var(--space-1);
                padding: var(--space-1) var(--space-2);
                border-radius: var(--radius-md);
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-solid-subtle);
                min-height: var(--input-height);
                box-sizing: border-box;
            }
            .wrap:focus-within {
                border-color: var(--accent);
                box-shadow: 0 0 0 3px var(--accent-subtle);
            }
            .chip {
                display: inline-flex; align-items: center; gap: 4px;
                padding: 2px var(--space-2);
                font-size: var(--text-sm);
                background: var(--accent-subtle);
                color: var(--accent);
                border-radius: var(--radius-full);
            }
            .chip button {
                background: none; border: none; padding: 0; margin: 0;
                color: var(--accent); cursor: pointer;
                font-size: var(--text-base);
                line-height: 1;
            }
            input {
                flex: 1; min-width: 80px;
                border: none; background: transparent;
                color: var(--text-primary);
                padding: 4px;
                font: inherit;
                outline: none;
            }
        `,
    ];

    constructor() {
        super();
        this.tags = [];
        this.placeholder = '';
        this._draft = '';
    }

    _commit(raw) {
        const v = raw.trim();
        if (!v) return;
        const list = Array.isArray(this.tags) ? this.tags : [];
        if (list.includes(v)) {
            this._draft = '';
            return;
        }
        const next = [...list, v];
        this._draft = '';
        this.emit('change', { tags: next });
    }

    _remove(idx) {
        const list = Array.isArray(this.tags) ? this.tags : [];
        const next = list.filter((_, i) => i !== idx);
        this.emit('change', { tags: next });
    }

    _onInput(e) {
        this._draft = e.target.value;
    }

    _onKeydown(e) {
        if (e.key === 'Enter' || e.key === ',') {
            e.preventDefault();
            this._commit(this._draft);
            return;
        }
        if (e.key === 'Backspace' && this._draft.length === 0) {
            const list = Array.isArray(this.tags) ? this.tags : [];
            if (list.length > 0) this._remove(list.length - 1);
        }
    }

    _onBlur() {
        if (this._draft.trim().length > 0) this._commit(this._draft);
    }

    render() {
        const list = Array.isArray(this.tags) ? this.tags : [];
        return html`
            <div class="wrap">
                ${list.map((tag, i) => html`
                    <span class="chip">
                        ${tag}
                        <button
                            type="button"
                            aria-label=${this.t('tag_input.remove')}
                            @click=${() => this._remove(i)}
                        >×</button>
                    </span>
                `)}
                <input
                    type="text"
                    .value=${this._draft}
                    placeholder=${list.length === 0 ? this.placeholder : ''}
                    @input=${this._onInput}
                    @keydown=${this._onKeydown}
                    @blur=${this._onBlur}
                />
            </div>
        `;
    }
}

customElements.define('flows-tag-input', FlowsTagInput);
