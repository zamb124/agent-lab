/**
 * flows-tag-input — chip-input для строковых тегов.
 *
 * Поведение: Enter / запятая → добавить тег; Backspace в пустом поле →
 * удалить последний тег. Дубликаты игнорируются.
 *
 * Property API:
 *   - tags: string[]
 *   - placeholder: string
 *   - allowedValues: string[] — если непустой, теги только из этого списка (ввод через select)
 *
 * Events (emit):
 *   - 'change' { tags }
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class FlowsTagInput extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        tags: { type: Array },
        placeholder: { type: String },
        /** Непустой массив — режим выбора только из перечисленных строк */
        allowedValues: { type: Array, attribute: 'allowed-values' },
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
            select.add-select {
                flex: 1;
                min-width: 120px;
                border: none;
                background: transparent;
                color: var(--text-primary);
                padding: 4px;
                font: inherit;
                outline: none;
                cursor: pointer;
            }
        `,
    ];

    constructor() {
        super();
        this.tags = [];
        this.placeholder = '';
        this.allowedValues = [];
        this._draft = '';
    }

    _allowedList() {
        return Array.isArray(this.allowedValues) ? this.allowedValues : [];
    }

    _enumMode() {
        return this._allowedList().length > 0;
    }

    _commit(raw) {
        const v = raw.trim();
        if (!v) return;
        const allowed = this._allowedList();
        if (allowed.length > 0 && !allowed.includes(v)) {
            this._draft = '';
            return;
        }
        const list = Array.isArray(this.tags) ? this.tags : [];
        if (list.includes(v)) {
            this._draft = '';
            return;
        }
        const next = [...list, v];
        this._draft = '';
        this.emit('change', { tags: next });
    }

    _onSelectAdd(e) {
        const sel = e.target;
        if (!(sel instanceof HTMLSelectElement)) {
            throw new Error('flows-tag-input: expected select change');
        }
        const v = sel.value;
        sel.value = '';
        if (!v) return;
        this._commit(v);
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
        if (this._enumMode()) return;
        if (this._draft.trim().length > 0) this._commit(this._draft);
    }

    render() {
        const list = Array.isArray(this.tags) ? this.tags : [];
        const allowed = this._allowedList();
        const enumMode = allowed.length > 0;
        const available = enumMode ? allowed.filter((x) => !list.includes(x)) : [];
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
                ${enumMode
                    ? html`
                        <select class="add-select" aria-label=${this.placeholder} @change=${this._onSelectAdd}>
                            <option value="">${this.placeholder}</option>
                            ${available.map((v) => html`<option value=${v}>${v}</option>`)}
                        </select>
                    `
                    : html`
                        <input
                            type="text"
                            .value=${this._draft}
                            placeholder=${list.length === 0 ? this.placeholder : ''}
                            @input=${this._onInput}
                            @keydown=${this._onKeydown}
                            @blur=${this._onBlur}
                        />
                    `}
            </div>
        `;
    }
}

customElements.define('flows-tag-input', FlowsTagInput);
