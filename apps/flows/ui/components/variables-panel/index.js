/**
 * VariablesPanel - CRUD панель для управления переменными
 * Независимый компонент для любых переменных (flow, chat, debug, settings)
 * 
 * Public API:
 * - Properties: .variables, .inheritedKeys, mode, read-only
 * - Methods: setVariables(), getVariables()
 * - Events: variable-created, variable-updated, variable-deleted
 */
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { variablesPanelStyles } from './styles.js';
import { renderPanel } from './templates.js';

export class VariablesPanel extends PlatformElement {
    static styles = [PlatformElement.styles, variablesPanelStyles];

    static properties = {
        variables: { type: Object },
        inheritedKeys: { type: Object },
        mode: { type: String },
        readOnly: { type: Boolean, attribute: 'read-only' },
    };

    constructor() {
        super();
        this.variables = {};
        this.inheritedKeys = new Set();
        this.mode = 'base';
        this.readOnly = false;
    }

    updated(changedProperties) {
        if (changedProperties.has('variables')) {
            console.log('[VariablesPanel] Переменные обновлены:', {
                variables: this.variables,
                variables_json: JSON.stringify(this.variables, null, 2),
                keys: Object.keys(this.variables || {}),
                type: typeof this.variables,
                entries: Object.entries(this.variables || {}),
            });
        }
    }

    render() {
        return renderPanel(this);
    }

    /**
     * Форматировать значение для отображения
     */
    _formatValue(value) {
        if (value === null) {
            return 'null';
        }
        if (value === undefined) {
            return 'undefined';
        }
        if (typeof value === 'object') {
            try {
                const str = JSON.stringify(value);
                return str.length > 50 ? str.substring(0, 47) + '...' : str;
            } catch (e) {
                console.error('[VariablesPanel] Ошибка преобразования значения в строку:', e);
                throw e;
            }
        }
        const str = String(value);
        return str.length > 50 ? str.substring(0, 47) + '...' : str;
    }

    /**
     * Обработчик добавления переменной
     */
    _handleAdd() {
        this.emit('variable-add-requested');
    }

    /**
     * Обработчик редактирования переменной
     */
    _handleEdit(name) {
        if (this.readOnly) {
            return;
        }

        const config = this.variables[name];
        const value = typeof config === 'object' ? config.value : config;
        const isInherited = this.inheritedKeys ? this.inheritedKeys.has(name) : false;

        this.emit('variable-edit-requested', { 
            name, 
            value,
            isInherited 
        });
    }

    /**
     * Обработчик удаления переменной
     */
    _handleDelete(e, name) {
        e.stopPropagation();

        if (this.readOnly) {
            return;
        }

        const isInherited = this.inheritedKeys ? this.inheritedKeys.has(name) : false;
        if (isInherited) {
            return;
        }

        const confirmed = confirm(`Удалить переменную "${name}"?`);
        if (confirmed) {
            this.emit('variable-deleted', { name });
        }
    }

    /**
     * Установить переменные
     */
    setVariables(variables, inheritedKeys = null) {
        this.variables = variables || {};
        this.inheritedKeys = inheritedKeys || new Set();
    }

    /**
     * Получить текущие переменные
     */
    getVariables() {
        return this.variables;
    }

    /**
     * Получить список имён переменных
     */
    getVariableNames() {
        return Object.keys(this.variables);
    }
}

customElements.define('variables-panel', VariablesPanel);

