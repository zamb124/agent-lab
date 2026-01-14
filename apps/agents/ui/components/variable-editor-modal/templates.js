import { html } from 'lit';

export function renderModal(component) {
    const isEdit = !!component.variableName;
    const title = isEdit ? `Редактировать: ${component.variableName}` : 'Новая переменная';
    
    return html`
        <div class="modal-overlay" @click=${component._onOverlayClick}>
            <div class="modal-container" @click=${(e) => e.stopPropagation()}>
                <div class="modal-header">
                    <span class="modal-title">
                        ${title}
                        ${component.isInherited ? html`
                            <span class="inherited-badge">from base</span>
                        ` : ''}
                    </span>
                    <button class="modal-close" @click=${component._onClose}>
                        <platform-icon name="x" size="20"></platform-icon>
                    </button>
                </div>

                <div class="modal-body">
                    ${!isEdit ? html`
                        <div class="form-group">
                            <label class="form-label form-label-required">Имя переменной</label>
                            <input
                                type="text"
                                class="form-input"
                                placeholder="my_variable"
                                .value=${component._formData.name}
                                @input=${(e) => component._updateFormData('name', e.target.value)}
                                required
                            />
                        </div>
                    ` : ''}

                    <div class="form-group">
                        <label class="form-label">Значение</label>
                        <div class="mode-toggle">
                            <button
                                class="mode-btn ${component._valueMode === 'text' ? 'active' : ''}"
                                @click=${() => component._setValueMode('text')}
                            >
                                Text
                            </button>
                            <button
                                class="mode-btn ${component._valueMode === 'json' ? 'active' : ''}"
                                @click=${() => component._setValueMode('json')}
                            >
                                JSON
                            </button>
                        </div>
                        <textarea
                            class="form-textarea"
                            placeholder=${component._valueMode === 'json' ? '{"key": "value"}' : 'Значение переменной'}
                            .value=${component._formData.value}
                            @input=${(e) => component._updateFormData('value', e.target.value)}
                        ></textarea>
                        <span class="form-hint">
                            ${component._valueMode === 'json' 
                                ? 'JSON формат для сложных структур данных' 
                                : 'Простое текстовое значение'}
                        </span>
                    </div>

                    <div class="form-group">
                        <label class="form-label">Заголовок</label>
                        <input
                            type="text"
                            class="form-input"
                            placeholder="Название компании"
                            .value=${component._formData.title || ''}
                            @input=${(e) => component._updateFormData('title', e.target.value)}
                        />
                    </div>

                    <div class="form-group">
                        <label class="form-label">Описание</label>
                        <input
                            type="text"
                            class="form-input"
                            placeholder="Для использования в ответах агента"
                            .value=${component._formData.description || ''}
                            @input=${(e) => component._updateFormData('description', e.target.value)}
                        />
                    </div>

                    <div class="form-group">
                        <label class="form-label">Порядок</label>
                        <input
                            type="number"
                            class="form-input"
                            placeholder="0"
                            .value=${component._formData.order !== null && component._formData.order !== undefined ? component._formData.order : ''}
                            @input=${(e) => component._updateFormData('order', e.target.value ? parseInt(e.target.value) : null)}
                        />
                        <span class="form-hint">Порядок отображения (необязательно)</span>
                    </div>

                    <div class="form-group">
                        <div class="form-checkbox-group">
                            <input
                                type="checkbox"
                                class="form-checkbox"
                                id="public-checkbox"
                                .checked=${component._formData.public}
                                @change=${(e) => component._updateFormData('public', e.target.checked)}
                            />
                            <label class="form-checkbox-label" for="public-checkbox">
                                Публичная (видна в agent-card)
                            </label>
                        </div>
                    </div>
                </div>

                <div class="modal-footer">
                    <button class="btn btn-secondary" @click=${component._onClose}>
                        Отмена
                    </button>
                    <button class="btn btn-primary" @click=${component._onSave}>
                        ${isEdit ? 'Сохранить' : 'Создать'}
                    </button>
                </div>
            </div>
        </div>
    `;
}


