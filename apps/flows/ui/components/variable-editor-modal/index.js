/**
 * VariableEditorModal — создание/редактирование переменных flow (value, public, title, description, order).
 * Режимы значения: text и JSON.
 */
import { html, css } from 'lit';
import { PlatformModal } from '@platform/lib/components/glass-modal.js';
import { buttonStyles } from '@platform/lib/styles/shared/button.styles.js';
import { variableEditorFormStyles } from './styles.js';

export class VariableEditorModal extends PlatformModal {
    static styles = [
        PlatformModal.styles,
        buttonStyles,
        variableEditorFormStyles,
        css`
            :host {
                --modal-max-width: 600px;
            }
        `,
    ];

    static properties = {
        ...PlatformModal.properties,
        variableName: { type: String },
        variableData: { type: Object },
        isInherited: { type: Boolean },
        valueMode: { type: String },
        _formData: { state: true },
    };

    constructor() {
        super();
        this.variableName = '';
        this.variableData = null;
        this.isInherited = false;
        this.valueMode = 'text';
        this.size = 'lg';
        this.title = '';
        this._formData = {
            name: '',
            value: '',
            public: false,
            title: null,
            description: null,
            order: null,
        };
    }

    showCreate() {
        this.variableName = '';
        this.variableData = null;
        this.isInherited = false;
        this.valueMode = 'text';
        this.title = this.i18n.t('flow_variable_editor.title_new');
        this._formData = {
            name: '',
            value: '',
            public: false,
            title: null,
            description: null,
            order: null,
        };
        this.open = true;
    }

    showEdit(name, data, isInherited = false) {
        this.variableName = name;
        this.isInherited = isInherited;

        let value = data;
        if (typeof data === 'object' && data !== null) {
            if ('value' in data) {
                value = data.value;
            }
        }

        const valueStr = this._formatValue(value);
        const isJson = this._isJsonValue(valueStr);

        this.valueMode = isJson ? 'json' : 'text';
        this._formData = {
            name: name,
            value: valueStr,
            public: data ? data.public || false : false,
            title: data ? data.title || null : null,
            description: data ? data.description || null : null,
            order: data && data.order !== undefined ? data.order : null,
        };
        this.variableData = data;
        this.title = this.i18n.t('flow_variable_editor.title_edit', { name });
        this.open = true;
    }

    renderHeader() {
        return html`
            ${this.title}
            ${this.isInherited
                ? html`<span class="inherited-badge">${this.i18n.t('flow_variable_editor.inherited_badge')}</span>`
                : ''}
        `;
    }

    renderBody() {
        const isEdit = !!this.variableName;
        return html`
            ${!isEdit
                ? html`
                      <div class="form-group">
                          <label class="form-label form-label-required">${this.i18n.t('flow_variable_editor.field_variable_name')}</label>
                          <input
                              type="text"
                              class="form-input"
                              placeholder=${this.i18n.t('flow_variable_editor.placeholder_variable_key')}
                              .value=${this._formData.name}
                              @input=${(e) => this._updateFormData('name', e.target.value)}
                              required
                          />
                      </div>
                  `
                : ''}
            <div class="form-group">
                <label class="form-label">${this.i18n.t('flow_variable_editor.field_value')}</label>
                <div class="mode-toggle">
                    <button
                        type="button"
                        class="mode-btn ${this.valueMode === 'text' ? 'active' : ''}"
                        @click=${() => this._setValueMode('text')}
                    >
                        ${this.i18n.t('flow_variable_editor.mode_text')}
                    </button>
                    <button
                        type="button"
                        class="mode-btn ${this.valueMode === 'json' ? 'active' : ''}"
                        @click=${() => this._setValueMode('json')}
                    >
                        ${this.i18n.t('flow_variable_editor.mode_json')}
                    </button>
                </div>
                <textarea
                    class="form-textarea"
                    placeholder=${this.valueMode === 'json'
                        ? '{"key": "value"}'
                        : this.i18n.t('flow_variable_editor.placeholder_value_plain')}
                    .value=${this._formData.value}
                    @input=${(e) => this._updateFormData('value', e.target.value)}
                ></textarea>
                <span class="form-hint">
                    ${this.valueMode === 'json'
                        ? this.i18n.t('flow_variable_editor.hint_value_json')
                        : this.i18n.t('flow_variable_editor.hint_value_text')}
                </span>
            </div>
            <div class="form-group">
                <label class="form-label">${this.i18n.t('flow_variable_editor.field_title')}</label>
                <input
                    type="text"
                    class="form-input"
                    placeholder=${this.i18n.t('flow_variable_editor.placeholder_title')}
                    .value=${this._formData.title || ''}
                    @input=${(e) => this._updateFormData('title', e.target.value)}
                />
            </div>
            <div class="form-group">
                <label class="form-label">${this.i18n.t('flow_variable_editor.field_description')}</label>
                <input
                    type="text"
                    class="form-input"
                    placeholder=${this.i18n.t('flow_variable_editor.placeholder_description')}
                    .value=${this._formData.description || ''}
                    @input=${(e) => this._updateFormData('description', e.target.value)}
                />
            </div>
            <div class="form-group">
                <label class="form-label">${this.i18n.t('flow_variable_editor.field_order')}</label>
                <input
                    type="number"
                    class="form-input"
                    placeholder=${this.i18n.t('flow_variable_editor.placeholder_order')}
                    .value=${this._formData.order !== null && this._formData.order !== undefined
                        ? this._formData.order
                        : ''}
                    @input=${(e) =>
                        this._updateFormData(
                            'order',
                            e.target.value ? parseInt(e.target.value, 10) : null,
                        )}
                />
                <span class="form-hint">${this.i18n.t('flow_variable_editor.hint_order')}</span>
            </div>
            <div class="form-group">
                <div class="form-checkbox-group">
                    <input
                        type="checkbox"
                        class="form-checkbox"
                        id="public-checkbox"
                        .checked=${this._formData.public}
                        @change=${(e) => this._updateFormData('public', e.target.checked)}
                    />
                    <label class="form-checkbox-label" for="public-checkbox">
                        ${this.i18n.t('flow_variable_editor.field_public')}
                    </label>
                </div>
            </div>
        `;
    }

    renderSaveHeaderButton() {
        const isEdit = !!this.variableName;
        const title = isEdit
            ? this.i18n.t('flow_variable_editor.btn_save')
            : this.i18n.t('flow_variable_editor.btn_create');
        return this._renderHeaderSaveIcon({
            onClick: () => this._onSave(),
            disabled: false,
            title,
        });
    }

    renderFooter() {
        return html`
            <div class="modal-actions-inner">
                <button type="button" class="btn btn-secondary" @click=${() => this.close()}>
                    ${this.i18n.t('flow_variable_editor.btn_cancel')}
                </button>
            </div>
        `;
    }

    render() {
        if (!this.open) {
            return html``;
        }
        return super.render();
    }

    _formatValue(value) {
        if (value === null || value === undefined) {
            return '';
        }
        if (typeof value === 'object') {
            return JSON.stringify(value, null, 2);
        }
        return String(value);
    }

    _isJsonValue(str) {
        if (!str || typeof str !== 'string') return false;
        const trimmed = str.trim();
        return (
            (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
            (trimmed.startsWith('[') && trimmed.endsWith(']'))
        );
    }

    _setValueMode(mode) {
        if (this.valueMode === mode) return;

        if (mode === 'json' && this.valueMode === 'text') {
            try {
                const parsed = JSON.parse(this._formData.value);
                this._formData.value = JSON.stringify(parsed, null, 2);
            } catch {
                try {
                    this._formData.value = JSON.stringify(this._formData.value, null, 2);
                } catch {
                    this.error(this.i18n.t('flow_variable_editor.err_to_json'));
                    return;
                }
            }
        }

        this.valueMode = mode;
    }

    _updateFormData(field, value) {
        this._formData = {
            ...this._formData,
            [field]: value,
        };
    }

    _parseValue(str) {
        if (!str) return '';

        if (this.valueMode === 'json') {
            try {
                return JSON.parse(str);
            } catch (e) {
                throw new Error(this.i18n.t('flow_variable_editor.err_json_invalid'));
            }
        }

        return str;
    }

    _onSave() {
        const name = this._formData.name.trim();

        if (!this.variableName && !name) {
            this.error(this.i18n.t('flow_variable_editor.err_name_required'));
            return;
        }

        let value;
        try {
            value = this._parseValue(this._formData.value);
        } catch (e) {
            this.error(e.message);
            return;
        }

        const data = {
            name: this.variableName || name,
            value: value,
            public: this._formData.public,
            title: this._formData.title || null,
            description: this._formData.description || null,
            order: this._formData.order,
        };

        this.emit('variable-saved', data);
        this.close();
    }
}

customElements.define('variable-editor-modal', VariableEditorModal);
