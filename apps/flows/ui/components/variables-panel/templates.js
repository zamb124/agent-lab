/**
 * VariablesPanel templates
 * HTML шаблоны для variables panel
 */
import { html } from 'lit';

export function renderPanel(component) {
    const variables = Object.entries(component.variables || {});
    const isReadOnly = component.readOnly;
    const hasInherited = component.inheritedKeys && component.inheritedKeys.size > 0;

    return html`
        <div class="variables-panel-container">
            <div class="var-header">
                <span class="var-header-title">Variables</span>
                ${!isReadOnly ? html`
                    <button 
                        class="var-add-btn"
                        @click=${component._handleAdd}
                        title="Добавить переменную"
                    >
                        <platform-icon name="plus" size="14"></platform-icon>
                    </button>
                ` : ''}
            </div>

            <div class="var-list">
                ${variables.length === 0 ? html`
                    <div class="var-empty">
                        <span class="var-empty-text">Нет переменных</span>
                    </div>
                ` : ''}

                ${variables.map(([name, config]) => {
                    const value = typeof config === 'object' ? config.value : config;
                    const isInherited = component.inheritedKeys?.has(name);
                    const displayValue = component._formatValue(value);

                    return html`
                        <div 
                            class="var-item ${isInherited ? 'inherited' : ''}"
                            @click=${() => component._handleEdit(name)}
                        >
                            <div class="var-item-content">
                                <div class="var-item-header">
                                    <span class="var-name">${name}</span>
                                    ${isInherited && hasInherited ? html`
                                        <span class="var-badge">from base</span>
                                    ` : ''}
                                </div>
                                <div class="var-value">${displayValue}</div>
                            </div>
                            ${!isReadOnly && !isInherited ? html`
                                <button 
                                    class="var-delete"
                                    @click=${(e) => component._handleDelete(e, name)}
                                    title="Удалить"
                                >
                                    ×
                                </button>
                            ` : ''}
                        </div>
                    `;
                })}
            </div>
        </div>
    `;
}


