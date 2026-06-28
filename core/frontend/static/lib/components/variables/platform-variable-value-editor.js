/**
 * Static vs expression value editor for PlatformVariable payload.base.
 */

import { html, css } from 'lit';
import { PlatformElement } from '../../platform-element/index.js';
import '../fields/platform-field.js';

export class PlatformVariableValueEditor extends PlatformElement {
    static i18nNamespace = 'company_variables';

    static properties = {
        valueKind: { type: String, attribute: 'value-kind' },
        value: { type: String },
        expression: { type: String },
        readonly: { type: Boolean, reflect: true },
    };

    static styles = css`
        :host { display: block; }
        .tabs {
            display: flex;
            gap: var(--space-2);
            margin-bottom: var(--space-3);
        }
        .tab {
            padding: var(--space-2) var(--space-3);
            border: 1px solid var(--glass-border-subtle);
            border-radius: var(--radius-md);
            background: transparent;
            color: var(--text-secondary);
            cursor: pointer;
            font-size: var(--text-sm);
        }
        .tab.active {
            border-color: var(--accent);
            color: var(--accent);
            background: var(--accent-subtle);
        }
        .field { margin-bottom: var(--space-3); }
    `;

    constructor() {
        super();
        this.valueKind = 'static';
        this.value = '';
        this.expression = '';
        this.readonly = false;
    }

    _emitChange(next) {
        this.dispatchEvent(new CustomEvent('change', {
            bubbles: true,
            composed: true,
            detail: next,
        }));
    }

    _setKind(kind) {
        if (this.readonly) {
            return;
        }
        if (kind !== 'static' && kind !== 'expression') {
            throw new Error('platform-variable-value-editor: invalid value_kind');
        }
        this._emitChange({
            value_kind: kind,
            value: this.value,
            expression: this.expression,
        });
    }

    render() {
        const kind = this.valueKind === 'expression' ? 'expression' : 'static';
        return html`
            <div class="tabs">
                <button type="button" class="tab ${kind === 'static' ? 'active' : ''}" ?disabled=${this.readonly} @click=${() => this._setKind('static')}>
                    ${this.t('editor.value_kind_static')}
                </button>
                <button type="button" class="tab ${kind === 'expression' ? 'active' : ''}" ?disabled=${this.readonly} @click=${() => this._setKind('expression')}>
                    ${this.t('editor.value_kind_expression')}
                </button>
            </div>
            ${kind === 'static'
                ? html`
                    <div class="field">
                        <platform-field
                            type="text"
                            mode="edit"
                            .label=${this.t('editor.field_static_value')}
                            .value=${this.value}
                            ?disabled=${this.readonly}
                            @change=${(e) => {
                                this._emitChange({
                                    value_kind: 'static',
                                    value: typeof e.detail.value === 'string' ? e.detail.value : '',
                                    expression: this.expression,
                                });
                            }}
                        ></platform-field>
                    </div>
                `
                : html`
                    <div class="field">
                        <platform-field
                            type="text"
                            mode="edit"
                            .label=${this.t('editor.field_expression')}
                            .value=${this.expression}
                            ?disabled=${this.readonly}
                            @change=${(e) => {
                                this._emitChange({
                                    value_kind: 'expression',
                                    value: this.value,
                                    expression: typeof e.detail.value === 'string' ? e.detail.value : '',
                                });
                            }}
                        ></platform-field>
                    </div>
                `}
        `;
    }
}

customElements.define('platform-variable-value-editor', PlatformVariableValueEditor);
