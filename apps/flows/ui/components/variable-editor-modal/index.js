/**
 * VariableEditorModal - Modal для создания/редактирования переменных
 * Поддерживает все поля: value, public, title, description, order
 * Два режима: text и JSON для value
 */
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { variableEditorModalStyles } from './styles.js';
import { renderModal } from './templates.js';

export class VariableEditorModal extends PlatformElement {
    static styles = [PlatformElement.styles, variableEditorModalStyles];

    static properties = {
        open: { type: Boolean },
        variableName: { type: String },
        variableData: { type: Object },
        isInherited: { type: Boolean },
        valueMode: { type: String },
    };

    constructor() {
        super();
        this.open = false;
        this.variableName = '';
        this.variableData = null;
        this.isInherited = false;
        this.valueMode = 'text';
        this._formData = {
            name: '',
            value: '',
            public: false,
            title: null,
            description: null,
            order: null,
        };
    }

    render() {
        if (!this.open) return null;
        return renderModal(this);
    }

    showCreate() {
        this.variableName = '';
        this.variableData = null;
        this.isInherited = false;
        this.valueMode = 'text';
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
            public: data ? (data.public || false) : false,
            title: data ? (data.title || null) : null,
            description: data ? (data.description || null) : null,
            order: data && data.order !== undefined ? data.order : null,
        };
        this.variableData = data;
        this.open = true;
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
        return (trimmed.startsWith('{') && trimmed.endsWith('}')) ||
               (trimmed.startsWith('[') && trimmed.endsWith(']'));
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
                    this.error('Не удалось преобразовать в JSON');
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
                throw new Error('Некорректный JSON формат');
            }
        }

        return str;
    }

    _onSave() {
        const name = this._formData.name.trim();
        
        if (!this.variableName && !name) {
            this.error('Имя переменной обязательно');
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
        this.open = false;
    }

    _onClose() {
        this.open = false;
    }

    _onOverlayClick() {
        this.open = false;
    }
}

customElements.define('variable-editor-modal', VariableEditorModal);

