/**
 * Primary action editor: none | platform.ui.submit (+formId) |
 * values.set | page.navigate (+target page).
 */
import { css, html, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';

export class FlowsInterfaceActionEditor extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        actions: { attribute: false },
        pages: { attribute: false },
    };

    static styles = [PlatformElement.styles, css`
        :host { display: grid; gap: 7px; }
        .title {
            font-size: 11px; font-weight: 700; text-transform: uppercase;
            letter-spacing: .06em; color: var(--text-tertiary); margin-top: 8px;
        }
    `];

    constructor() {
        super();
        this.actions = {};
        this.pages = [];
    }

    _primary() {
        const actions = this.actions && typeof this.actions === 'object' ? this.actions : {};
        if (actions.press) return actions.press;
        const entries = Object.values(actions);
        return entries.length ? entries[0] : null;
    }

    _emitAction(name, context = {}) {
        this.emit('action-change', { name, ...context });
    }

    render() {
        const action = this._primary();
        const selected = !action
            ? 'none'
            : (action.name === 'platform.ui.submit' ? 'platform.ui.submit' : (action.name || 'none'));
        const formId = action?.context?.formId || '';
        const pageId = action?.context?.pageId || '';
        return html`
            <div class="title">${this.t('interface_editor.action_title')}</div>
            <platform-field
                type="enum"
                .label=${this.t('interface_editor.action_kind')}
                .value=${selected}
                .config=${{ values: [
                    { value: 'none', label: this.t('interface_editor.action_none') },
                    { value: 'platform.ui.submit', label: this.t('interface_editor.action_submit') },
                    { value: 'values.set', label: this.t('interface_editor.action_values_set') },
                    { value: 'page.navigate', label: this.t('interface_editor.action_navigate') },
                ] }}
                mode="edit"
                @change=${(event) => this._emitAction(event.detail.value, { formId, pageId })}
            ></platform-field>
            ${selected === 'platform.ui.submit' ? html`
                <platform-field
                    type="string"
                    .label=${this.t('interface_editor.action_form_id')}
                    .value=${formId}
                    .placeholder=${'message-form'}
                    mode="edit"
                    @change=${(event) => this._emitAction(selected, { formId: String(event.detail.value).trim() })}
                ></platform-field>
            ` : nothing}
            ${selected === 'page.navigate' ? html`
                <platform-field
                    type="enum"
                    .label=${this.t('interface_editor.action_target_page')}
                    .value=${pageId}
                    .config=${{ values: (this.pages || []).map((page) => ({
                        value: page.page_id,
                        label: page.title?.default || page.page_id,
                    })) }}
                    mode="edit"
                    @change=${(event) => this._emitAction(selected, { pageId: event.detail.value })}
                ></platform-field>
            ` : nothing}
        `;
    }
}

if (!customElements.get('flows-interface-action-editor')) {
    customElements.define('flows-interface-action-editor', FlowsInterfaceActionEditor);
}
