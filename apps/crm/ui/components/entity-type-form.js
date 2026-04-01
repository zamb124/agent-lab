/**
 * Форма создания/редактирования типа сущности.
 * Используется в templates-page (шаблоны) и spaces-page (пространства).
 *
 * mode="create" - создание нового типа (type_id редактируемый)
 * mode="edit" - редактирование существующего (type_id read-only)
 *
 * Events:
 *   @type-saved  { detail: { type_id, payload } }
 *   @type-cancel
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-icon-picker.js';
import '@platform/lib/components/platform-switch.js';
import '@platform/lib/components/platform-help-hint.js';
import { COLOR_PALETTE } from '@platform/lib/utils/color-palette.js';

export class EntityTypeForm extends PlatformElement {
    static properties = {
        mode: { type: String },
        typeId: { type: String, attribute: 'type-id' },
        draft: { type: Object },
        saving: { type: Boolean },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host { display: block; }
            .form-card { border: 1px solid var(--crm-stroke); border-radius: var(--radius-lg); padding: var(--space-4); background: var(--crm-surface-muted); display: flex; flex-direction: column; gap: var(--space-3); }
            .form-header { display: flex; align-items: center; justify-content: space-between; gap: var(--space-2); }
            .form-title { display: flex; align-items: center; gap: var(--space-2); color: var(--text-primary); font-size: var(--text-sm); font-weight: 600; }
            .form-grid { display: grid; gap: var(--space-3); grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); }
            .form-group { display: flex; flex-direction: column; gap: var(--space-2); }
            .form-label { color: var(--text-secondary); font-size: var(--text-sm); font-weight: 500; }
            .label-with-hint { display: inline-flex; align-items: center; gap: var(--space-2); }
            .form-input, .form-select, .form-textarea { border: 1px solid var(--crm-stroke); border-radius: var(--radius-md); background: var(--crm-surface-elevated); color: var(--text-primary); padding: var(--space-2) var(--space-3); font-size: var(--text-sm); }
            .form-textarea { min-height: 88px; resize: vertical; }
            .form-input:disabled { opacity: 0.6; cursor: not-allowed; }
            .mono { font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace; font-size: var(--text-xs); }
            .save-btn { display: inline-flex; align-items: center; justify-content: center; gap: var(--space-2); border: 1px solid var(--crm-button-primary-bg); background: var(--crm-button-primary-bg); color: var(--crm-button-primary-text); border-radius: var(--radius-md); padding: var(--space-2) var(--space-4); cursor: pointer; width: fit-content; }
            .save-btn:disabled { opacity: 0.5; cursor: not-allowed; }
            .soft-btn { border-color: var(--crm-stroke); background: var(--crm-surface-elevated); color: var(--text-primary); }
            .hint { color: var(--text-tertiary); font-size: var(--text-xs); }
            .flag-row { display: flex; gap: var(--space-3); flex-wrap: wrap; }
            .flag-item { display: inline-flex; align-items: center; gap: var(--space-2); white-space: nowrap; }
            .actions { display: flex; gap: var(--space-2); flex-wrap: wrap; }
            .color-compose-span {
                grid-column: 1 / -1;
            }
            .color-compose-row {
                display: grid;
                grid-template-columns: 150px minmax(0, 1fr);
                gap: 12px;
                align-items: center;
                min-width: 0;
            }
            .color-compose-label-wrap {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .color-compose-label {
                font-size: var(--text-sm);
                line-height: 1.1;
                color: var(--text-secondary);
                letter-spacing: -0.01em;
            }
            .etype-color-palette {
                display: flex;
                align-items: center;
                gap: 8px;
                flex-wrap: wrap;
            }
            .etype-color-swatch {
                width: 22px;
                height: 22px;
                border: none;
                border-radius: 50%;
                padding: 0;
                cursor: pointer;
                box-shadow: inset 0 0 0 1px color-mix(in srgb, #000 10%, transparent);
            }
            .etype-color-swatch.active {
                box-shadow: 0 0 0 2px var(--glass-solid-strong), 0 0 0 4px color-mix(in srgb, #3f4959 55%, transparent);
            }
        `,
    ];

    constructor() {
        super();
        this.mode = 'create';
        this.typeId = '';
        this.draft = EntityTypeForm.defaultDraft();
        this.saving = false;
    }

    static defaultDraft() {
        return {
            type_id: '',
            name: '',
            description: '',
            prompt: '',
            parent_type_id: '',
            icon: '',
            color: '',
            is_event: false,
            check_duplicates: true,
            is_context_anchor: false,
        };
    }

    _update(field, value) {
        this.draft = { ...this.draft, [field]: value };
    }

    _isPaletteSwatchActive(dot) {
        const cur = (this.draft.color || '').trim().toLowerCase();
        return Boolean(cur) && cur === dot.toLowerCase();
    }

    _onSave() {
        const typeId = this.mode === 'create' ? (this.draft.type_id || '').trim() : this.typeId;
        if (!typeId) {
            this.error(this.i18n.t('entity_type_form.err_type_id_required'));
            return;
        }
        const name = (this.draft.name || '').trim();
        if (!name) {
            this.error(this.i18n.t('entity_type_form.err_name_required'));
            return;
        }
        this.dispatchEvent(new CustomEvent('type-saved', {
            detail: {
                type_id: typeId,
                payload: {
                    name,
                    description: (this.draft.description || '').trim() || null,
                    prompt: (this.draft.prompt || '').trim() || null,
                    parent_type_id: (this.draft.parent_type_id || '').trim() || null,
                    icon: (this.draft.icon || '').trim() || null,
                    color: (this.draft.color || '').trim() || null,
                    is_event: Boolean(this.draft.is_event),
                    check_duplicates: this.draft.check_duplicates !== false,
                    is_context_anchor: Boolean(this.draft.is_context_anchor),
                },
            },
            bubbles: true,
            composed: true,
        }));
    }

    _onCancel() {
        this.dispatchEvent(new CustomEvent('type-cancel', { bubbles: true, composed: true }));
    }

    render() {
        const isCreate = this.mode === 'create';
        const title = isCreate
            ? this.i18n.t('entity_type_form.title_create')
            : this.i18n.t('entity_type_form.title_edit', { id: this.typeId });
        const iconOptions = this.icon?.availableIcons || [];

        return html`
            <div class="form-card">
                <div class="form-header">
                    <div class="form-title">
                        <platform-icon name=${isCreate ? 'plus' : 'edit'} size="14"></platform-icon>
                        ${title}
                    </div>
                    <button class="save-btn soft-btn" @click=${this._onCancel}>${this.i18n.t('cancel', {}, 'common')}</button>
                </div>
                ${isCreate
                    ? html`<div class="hint">${this.i18n.t('entity_type_form.hint_type_id_once')}</div>`
                    : html`<div class="hint">${this.i18n.t('entity_type_form.hint_type_id_readonly')}</div>`}
                <div class="form-grid">
                    ${isCreate ? html`
                        <div class="form-group">
                            <label class="form-label label-with-hint">
                                <span>${this.i18n.t('entity_type_form.label_type_id')}</span>
                                <platform-help-hint strategy="local" label=${this.i18n.t('entity_type_form.help_type_id')} .text=${this.i18n.t('hints.typeId')}></platform-help-hint>
                            </label>
                            <input class="form-input mono" placeholder="snake_case_id" .value=${this.draft.type_id || ''} @input=${(e) => this._update('type_id', e.target.value)} />
                        </div>
                    ` : html`
                        <div class="form-group">
                            <label class="form-label">${this.i18n.t('entity_type_form.label_type_id_ro')}</label>
                            <input class="form-input mono" .value=${this.typeId} disabled />
                        </div>
                    `}
                    <div class="form-group">
                        <label class="form-label label-with-hint">
                            <span>${this.i18n.t('entity_type_form.label_name')}</span>
                            <platform-help-hint strategy="local" label=${this.i18n.t('entity_type_form.help_type_name')} .text=${this.i18n.t('hints.typeName')}></platform-help-hint>
                        </label>
                        <input class="form-input" .value=${this.draft.name || ''} @input=${(e) => this._update('name', e.target.value)} />
                    </div>
                    <div class="form-group">
                        <label class="form-label label-with-hint">
                            <span>${this.i18n.t('entity_type_form.label_parent')}</span>
                            <platform-help-hint strategy="local" label=${this.i18n.t('entity_type_form.help_parent')} .text=${this.i18n.t('hints.parentType')}></platform-help-hint>
                        </label>
                        <select class="form-select mono" .value=${this.draft.parent_type_id || ''} @change=${(e) => this._update('parent_type_id', e.target.value)}>
                            <option value="">${this.i18n.t('entity_type_form.parent_none')}</option>
                            <option value="note">note</option>
                            <option value="task">task</option>
                        </select>
                    </div>
                    ${iconOptions.length > 0 ? html`
                        <div class="form-group">
                            <label class="form-label label-with-hint">
                                <span>${this.i18n.t('entity_type_form.label_icon')}</span>
                                <platform-help-hint strategy="local" label=${this.i18n.t('entity_type_form.help_icon')} .text=${this.i18n.t('hints.typeIcon')}></platform-help-hint>
                            </label>
                            <platform-icon-picker .icons=${iconOptions} .value=${this.draft.icon || 'folder'} @change=${(e) => this._update('icon', e.detail.value)}></platform-icon-picker>
                        </div>
                    ` : ''}
                    <div class="form-group color-compose-span">
                        <div class="color-compose-row">
                            <div class="color-compose-label-wrap">
                                <span class="color-compose-label">${this.i18n.t('entity_type_form.label_color')}</span>
                                <platform-help-hint strategy="local" label=${this.i18n.t('entity_type_form.help_color')} .text=${this.i18n.t('hints.typeColor')}></platform-help-hint>
                            </div>
                            <div class="etype-color-palette" role="group" aria-label=${this.i18n.t('entity_type_form.palette_aria')}>
                                ${COLOR_PALETTE.map((entry) => html`
                                    <button
                                        type="button"
                                        class="etype-color-swatch ${this._isPaletteSwatchActive(entry.dot) ? 'active' : ''}"
                                        style=${`background:${entry.dot};`}
                                        title=${entry.key}
                                        @click=${() => this._update('color', entry.dot)}
                                    ></button>
                                `)}
                            </div>
                        </div>
                    </div>
                    <div class="form-group">
                        <label class="form-label">${this.i18n.t('entity_type_form.label_flags')}</label>
                        <div class="flag-row">
                            <div class="flag-item">
                                <platform-switch size="sm" label="is_event" .checked=${Boolean(this.draft.is_event)} @change=${(e) => this._update('is_event', Boolean(e.detail.value))}></platform-switch>
                                <platform-help-hint strategy="local" label=${this.i18n.t('entity_type_form.help_is_event')} .text=${this.i18n.t('hints.flagIsEvent')}></platform-help-hint>
                            </div>
                            <div class="flag-item">
                                <platform-switch size="sm" label="check_duplicates" .checked=${this.draft.check_duplicates !== false} @change=${(e) => this._update('check_duplicates', Boolean(e.detail.value))}></platform-switch>
                                <platform-help-hint strategy="local" label=${this.i18n.t('entity_type_form.help_check_duplicates')} .text=${this.i18n.t('hints.flagCheckDuplicates')}></platform-help-hint>
                            </div>
                            <div class="flag-item">
                                <platform-switch size="sm" label="is_context_anchor" .checked=${Boolean(this.draft.is_context_anchor)} @change=${(e) => this._update('is_context_anchor', Boolean(e.detail.value))}></platform-switch>
                                <platform-help-hint strategy="local" label=${this.i18n.t('entity_type_form.help_context_anchor')} .text=${this.i18n.t('hints.flagContextAnchor')}></platform-help-hint>
                            </div>
                        </div>
                    </div>
                    <div class="form-group">
                        <label class="form-label label-with-hint">
                            <span>${this.i18n.t('entity_type_form.label_description')}</span>
                            <platform-help-hint strategy="local" label=${this.i18n.t('entity_type_form.help_description')} .text=${this.i18n.t('hints.typeDescription')}></platform-help-hint>
                        </label>
                        <textarea class="form-textarea" .value=${this.draft.description || ''} @input=${(e) => this._update('description', e.target.value)}></textarea>
                    </div>
                    <div class="form-group">
                        <label class="form-label label-with-hint">
                            <span>${this.i18n.t('entity_type_form.label_ai_prompt')}</span>
                            <platform-help-hint strategy="local" label=${this.i18n.t('entity_type_form.help_prompt')} .text=${this.i18n.t('hints.typePrompt')}></platform-help-hint>
                        </label>
                        <textarea class="form-textarea" .value=${this.draft.prompt || ''} @input=${(e) => this._update('prompt', e.target.value)}></textarea>
                    </div>
                </div>
                <div class="actions">
                    <button class="save-btn" ?disabled=${this.saving} @click=${this._onSave}>
                        <platform-icon name="save" size="14"></platform-icon>
                        ${this.saving
                            ? this.i18n.t('entity_type_form.saving')
                            : isCreate
                              ? this.i18n.t('entity_type_form.submit_create')
                              : this.i18n.t('entity_type_form.submit_save')}
                    </button>
                </div>
            </div>
        `;
    }
}

customElements.define('entity-type-form', EntityTypeForm);
