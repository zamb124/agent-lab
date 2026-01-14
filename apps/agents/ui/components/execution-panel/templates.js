/**
 * ExecutionPanel templates
 * HTML шаблоны для execution panel
 */
import { html } from 'lit';

export function renderPanel(component) {
    const hasResult = component.result !== null;
    const hasError = component.errorMessage !== null;
    const showMocks = component.showMocks;
    const showState = component.showState;
    const showTracing = component.showTracing;

    return html`
        <div class="execution-panel-container">
            <div class="execution-panel-header">
                <span class="execution-panel-title">Запуск агента</span>
                <div class="execution-panel-actions">
                    ${showState ? html`
                        <button 
                            class="action-btn"
                            ?disabled=${!component.hasExecutionData}
                            @click=${component._handleStateClick}
                            title="Показать State"
                        >
                            State
                        </button>
                    ` : ''}
                    ${showTracing ? html`
                        <button 
                            class="action-btn"
                            ?disabled=${!component.hasExecutionData}
                            @click=${component._handleTracingClick}
                            title="Трейсинг"
                        >
                            Tracing
                        </button>
                    ` : ''}
                    ${showMocks ? html`
                        <button 
                            class="action-btn"
                            @click=${component._toggleMocks}
                            title="Настроить моки"
                        >
                            Mocks
                        </button>
                    ` : ''}
                    <button 
                        class="close-btn"
                        @click=${component._handleClose}
                        title="Закрыть панель"
                    >
                        ×
                    </button>
                </div>
            </div>

            <div class="execution-panel-body">
                ${component.inputQuestion ? html`
                    <div class="input-question">
                        <platform-icon name="info" size="16"></platform-icon>
                        <span>${component.inputQuestion}</span>
                    </div>
                ` : ''}
                <div class="input-wrapper">
                    <label class="file-attach-btn" title="Прикрепить файлы">
                        <input 
                            type="file" 
                            class="file-input" 
                            multiple 
                            hidden
                            @change=${component._handleFileSelect}
                        >
                        <platform-icon name="file" size="20"></platform-icon>
                    </label>
                    <textarea
                        class="input-text"
                        placeholder=${component.inputQuestion ? 'Введите ваш ответ...' : (component.placeholder || 'Введите сообщение для агента...')}
                        rows="3"
                        .value=${component.message}
                        @input=${component._handleMessageInput}
                        ?disabled=${component.isRunning}
                    ></textarea>
                </div>

                ${component.files.length > 0 ? html`
                    <div class="file-list">
                        ${component.files.map((file, index) => html`
                            <div class="file-item">
                                <span class="file-name">${file.name}</span>
                                <button 
                                    class="file-remove"
                                    @click=${() => component._removeFile(index)}
                                >
                                    ×
                                </button>
                            </div>
                        `)}
                    </div>
                ` : ''}
            </div>

            <div class="execution-panel-footer">
                ${component.isBreakpoint ? html`
                    <button 
                        class="btn btn-resume"
                        @click=${component._handleResume}
                        ?disabled=${component.inputQuestion && !component.message.trim()}
                    >
                        <platform-icon name="play" size="14"></platform-icon>
                        ${component.inputQuestion ? 'Отправить ответ' : 'Продолжить выполнение'}
                    </button>
                ` : component.isRunning ? html`
                    <button 
                        class="btn btn-stop"
                        @click=${component._handleStop}
                    >
                        <platform-icon name="stop" size="14"></platform-icon>
                        Остановить
                    </button>
                ` : html`
                    <button 
                        class="btn btn-run ${hasError ? 'btn-retry' : ''}"
                        @click=${component._handleRun}
                        ?disabled=${!component.message.trim()}
                    >
                        <platform-icon name="play" size="14"></platform-icon>
                        ${hasError ? 'Запустить заново' : 'Запустить'}
                    </button>
                `}
            </div>

            ${hasError ? html`
                <div class="error-section">
                    <div class="error-header">
                        <platform-icon name="x" size="16" style="color: var(--error, #ef4444);"></platform-icon>
                        <span>Ошибка</span>
                        <button 
                            class="error-clear"
                            @click=${() => { component.errorMessage = null; }}
                            title="Закрыть"
                        >
                            ×
                        </button>
                    </div>
                    <div class="error-content">
                        ${component.errorMessage}
                    </div>
                    <div class="error-actions">
                        <button 
                            class="error-copy-btn"
                            @click=${() => {
                                navigator.clipboard.writeText(component.errorMessage).then(() => {
                                    const btn = event.target;
                                    const originalText = btn.textContent;
                                    btn.textContent = 'Скопировано!';
                                    setTimeout(() => {
                                        btn.textContent = originalText;
                                    }, 1500);
                                });
                            }}
                            title="Копировать"
                        >
                            Копировать
                        </button>
                    </div>
                </div>
            ` : ''}

            ${hasResult ? html`
                <div class="result-section">
                    <div class="result-header">
                        <span>Результат</span>
                        <button 
                            class="result-clear"
                            @click=${component._clearResult}
                            title="Очистить"
                        >
                            ×
                        </button>
                    </div>
                    <div class="result-content">
                        ${component.result}
                    </div>
                </div>
            ` : ''}

            ${component.showMocksSection && showMocks ? html`
                <div class="mocks-section">
                    <div class="mocks-header">
                        <span>Настройка моков</span>
                        <button 
                            class="mocks-close"
                            @click=${component._toggleMocks}
                        >
                            ×
                        </button>
                    </div>
                    <div class="mocks-body">
                        <llm-mocks-editor
                            .mocks=${component.mockResponses}
                            @change=${component._handleMocksChange}
                        ></llm-mocks-editor>
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

