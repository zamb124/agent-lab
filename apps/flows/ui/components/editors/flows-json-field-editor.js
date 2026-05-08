/**
 * flows-json-field-editor — поле для JSON-значений с подсветкой и
 * валидацией формата.
 *
 * Внутри использует `<flows-code-editor language='json'>`. При невалидном
 * JSON помечает контейнер `data-invalid` и не диспатчит change. На каждый
 * успешный парсинг → `emit('change', { value, parsed })`.
 *
 * Слот `toolbar-start` проксируется в `<flows-code-editor>` (левая часть шапки).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import './flows-code-editor.js';
import { asString } from '../../_helpers/flows-resolvers.js';

export class FlowsJsonFieldEditor extends PlatformElement {
    static properties = {
        value: { type: String },
        readonly: { type: Boolean },
        _invalid: { state: true },
        _error: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .wrapper[data-invalid] flows-code-editor { border-color: var(--error); }
            .error {
                color: var(--error);
                font-size: var(--text-xs);
                margin-top: var(--space-1);
            }
            ::slotted([slot="toolbar-start"]) {
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
            }
        `,
    ];

    constructor() {
        super();
        this.value = '{}';
        this.readonly = false;
        this._invalid = false;
        this._error = '';
    }

    _onChange(e) {
        const value = asString(e.detail?.value);
        try {
            const parsed = value.trim().length === 0 ? null : JSON.parse(value);
            this._invalid = false;
            this._error = '';
            this.value = value;
            this.emit('change', { value, parsed });
        } catch (err) {
            this._invalid = true;
            this._error = err.message;
        }
    }

    render() {
        return html`
            <div class="wrapper" ?data-invalid=${this._invalid}>
                <flows-code-editor
                    language="json"
                    ?readonly=${this.readonly}
                    .value=${this.value}
                    @change=${this._onChange}
                >
                    <slot name="toolbar-start" slot="toolbar-start"></slot>
                </flows-code-editor>
                ${this._invalid ? html`<div class="error">${this._error}</div>` : ''}
            </div>
        `;
    }
}

customElements.define('flows-json-field-editor', FlowsJsonFieldEditor);
