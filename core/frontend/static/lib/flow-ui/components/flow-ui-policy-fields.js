/**
 * <flow-ui-policy-fields> — editable FlowInterfacePolicy fields.
 * Used by flow edit modal and embed create modal.
 *
 * Props:
 *   .policy — FlowInterfacePolicy snapshot
 *   disabled — read-only
 *
 * Events:
 *   policy-changed — detail: { patch }
 *
 * i18n: flows:chat_settings.* (shared labels for matching policy field names)
 */

import { html, css } from '../../lit-shim.js';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/fields/platform-field.js';

export class FlowUIPolicyFields extends PlatformElement {
    static i18nNamespace = 'flows';

    static properties = {
        policy: { attribute: false },
        disabled: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            :host([disabled]) { opacity: 0.65; pointer-events: none; }
            .policy-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: var(--space-2) var(--space-3);
            }
            @media (max-width: 640px) {
                .policy-grid { grid-template-columns: 1fr; }
            }
        `,
    ];

    constructor() {
        super();
        this.policy = null;
        this.disabled = false;
    }

    _emitPatch(patch) {
        this.emit('policy-changed', { patch });
    }

    _renderBoolean(key) {
        return html`
            <platform-field
                type="boolean"
                mode="edit"
                data-policy-field=${key}
                .label=${this.t(`chat_settings.${key}`)}
                .hint=${this.t(`chat_settings.${key}_hint`)}
                .value=${this.policy[key] === true}
                @change=${(e) => this._emitPatch({ [key]: e.detail.value === true })}
            ></platform-field>
        `;
    }

    render() {
        if (!this.policy || typeof this.policy !== 'object') {
            return null;
        }
        return html`
            <div class="policy-grid">
                <platform-field
                    type="enum"
                    mode="edit"
                    data-policy-field="tool_calls_display"
                    .label=${this.t('chat_settings.tool_calls_display')}
                    .hint=${this.t('chat_settings.tool_calls_display_hint')}
                    .config=${{
                        values: [
                            { value: 'hidden', label: this.t('chat_settings.tool_calls_hidden') },
                            { value: 'compact', label: this.t('chat_settings.tool_calls_compact') },
                            { value: 'detailed', label: this.t('chat_settings.tool_calls_detailed') },
                        ],
                    }}
                    .value=${this.policy.tool_calls_display}
                    @change=${(e) => this._emitPatch({ tool_calls_display: e.detail.value })}
                ></platform-field>
                <platform-field
                    type="enum"
                    mode="edit"
                    data-policy-field="errors_display"
                    .label=${this.t('chat_settings.errors_display')}
                    .hint=${this.t('chat_settings.errors_display_hint')}
                    .config=${{
                        values: [
                            { value: 'generic', label: this.t('chat_settings.errors_generic') },
                            { value: 'detailed', label: this.t('chat_settings.errors_detailed') },
                        ],
                    }}
                    .value=${this.policy.errors_display}
                    @change=${(e) => this._emitPatch({ errors_display: e.detail.value })}
                ></platform-field>
                ${this._renderBoolean('show_reasoning')}
                ${this._renderBoolean('show_activity')}
                ${this._renderBoolean('show_skill_loads')}
                ${this._renderBoolean('show_reflection')}
                ${this._renderBoolean('show_run_trace')}
                ${this._renderBoolean('show_trace_actions')}
                ${this._renderBoolean('show_browser_previews')}
                ${this._renderBoolean('show_files_panel')}
                ${this._renderBoolean('allow_cancel')}
                ${this._renderBoolean('allow_voice')}
                ${this._renderBoolean('embed_safe_mode')}
            </div>
        `;
    }
}

if (!customElements.get('flow-ui-policy-fields')) {
    customElements.define('flow-ui-policy-fields', FlowUIPolicyFields);
}
