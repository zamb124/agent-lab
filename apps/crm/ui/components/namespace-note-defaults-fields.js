/**
 * Общие поля настроек заметок (`default_note_voice`, `show_note_voice_ui`)
 * для страницы пространства и страницы шаблона — одна разметка и одни ключи i18n.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/fields/platform-field.js';

export class CRMNamespaceNoteDefaultsFields extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        defaultNoteVoiceMode: { attribute: false },
        showNoteVoiceUi: { type: Boolean, attribute: false },
        disabled: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: contents;
            }
            .nf-field {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .nf-label {
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                letter-spacing: 0.04em;
                text-transform: uppercase;
            }
            .nf-label-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .nf-label-row .nf-label {
                margin: 0;
            }
            .nf-switch-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .nf-switch-row platform-switch {
                flex: 1;
                min-width: 0;
            }
            .nf-hint {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
        `,
    ];

    constructor() {
        super();
        this.defaultNoteVoiceMode = 'self';
        this.showNoteVoiceUi = true;
        this.disabled = false;
    }

    _voiceModeEnumConfig() {
        return {
            values: [
                { value: 'self', label: this.t('namespace_note_defaults.voice_mode_self') },
                { value: 'none', label: this.t('namespace_note_defaults.voice_mode_none') },
                { value: 'last', label: this.t('namespace_note_defaults.voice_mode_last') },
            ],
        };
    }

    _onModeFieldChange(e) {
        if (!e.detail || typeof e.detail.value !== 'string') {
            throw new Error('CRMNamespaceNoteDefaultsFields: voice mode expects change detail.value string');
        }
        const v = e.detail.value;
        if (v !== 'none' && v !== 'last' && v !== 'self') {
            throw new Error(`CRMNamespaceNoteDefaultsFields: invalid voice mode '${v}'`);
        }
        this.emit('default-note-voice-change', { value: v });
    }

    _onShowUiChange(e) {
        const d = e.detail;
        if (d === undefined || d === null || typeof d !== 'object' || typeof d.value !== 'boolean') {
            return;
        }
        this.emit('show-note-voice-ui-change', { value: d.value });
    }

    render() {
        const dis = this.disabled === true;
        const mode =
            this.defaultNoteVoiceMode === 'none'
            || this.defaultNoteVoiceMode === 'last'
            || this.defaultNoteVoiceMode === 'self'
                ? this.defaultNoteVoiceMode
                : 'self';
        return html`
            <div class="nf-field">
                <div class="nf-label-row">
                    <span class="nf-label">${this.t('namespace_note_defaults.section_title')}</span>
                    <platform-help-hint
                        .text=${this.t('namespace_note_defaults.section_title_hint')}
                        label=${this.t('templates_page.field_hint_button_aria')}
                    ></platform-help-hint>
                </div>
                <p class="nf-hint">${this.t('namespace_note_defaults.section_hint')}</p>
            </div>
            <div class="nf-field">
                <div class="nf-label-row">
                    <label class="nf-label" for="nf-voice-mode">${this.t('namespace_note_defaults.voice_mode_label')}</label>
                    <platform-help-hint
                        .text=${this.t('namespace_note_defaults.voice_mode_label_hint')}
                        label=${this.t('templates_page.field_hint_button_aria')}
                    ></platform-help-hint>
                </div>
                <platform-field
                    id="nf-voice-mode"
                    type="enum"
                    mode="edit"
                    label=""
                    .value=${mode}
                    .config=${this._voiceModeEnumConfig()}
                    ?disabled=${dis}
                    @change=${this._onModeFieldChange}
                ></platform-field>
                <p class="nf-hint">${this.t('namespace_note_defaults.voice_mode_hint')}</p>
            </div>
            <div class="nf-field">
                <div class="nf-switch-row">
                    <platform-switch
                        size="sm"
                        label=${this.t('namespace_note_defaults.show_ui_label')}
                        .checked=${this.showNoteVoiceUi === true}
                        ?disabled=${dis}
                        @change=${this._onShowUiChange}
                    ></platform-switch>
                    <platform-help-hint
                        .text=${this.t('namespace_note_defaults.show_ui_label_hint')}
                        label=${this.t('templates_page.field_hint_button_aria')}
                    ></platform-help-hint>
                </div>
            </div>
        `;
    }
}

customElements.define('crm-namespace-note-defaults-fields', CRMNamespaceNoteDefaultsFields);
