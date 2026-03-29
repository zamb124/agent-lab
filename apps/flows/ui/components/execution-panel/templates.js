/**
 * ExecutionPanel templates
 * HTML шаблоны для execution panel
 */
import { html } from 'lit';
import '@platform/lib/components/platform-switch.js';

export function renderPanel(component) {
    const hasResult = component.result !== null;
    const hasError = component.errorMessage !== null;
    const showMocks = component.showMocks;
    const showState = component.showState;
    const showTracing = component.showTracing;

    return html`
        <div class="execution-panel-container">
            <div class="execution-panel-header">
                <div class="execution-panel-header-top">
                    <span class="execution-panel-title">Запуск агента</span>
                    <div class="execution-panel-actions">
                    <platform-switch
                        size="sm"
                        .checked=${component.persistSessionContext}
                        aria-label="Один и тот же контекст сессии между запусками"
                        @change=${(e) => { component.persistSessionContext = Boolean(e.detail.value); }}
                    ></platform-switch>
                    <platform-help-hint
                        .text=${component.persistContextHelpText}
                        label="Справка: контекст сессии"
                    ></platform-help-hint>
                    ${showState ? html`
                        <button 
                            type="button"
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
                            type="button"
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
                            type="button"
                            class="action-btn"
                            @click=${component._toggleMocks}
                            title="Настроить моки"
                        >
                            Mocks
                        </button>
                    ` : ''}
                    <button 
                        type="button"
                        class="close-btn"
                        @click=${component._handleClose}
                        title="Закрыть панель"
                    >
                        ×
                    </button>
                    </div>
                </div>
            </div>

            <div class="execution-panel-body">
                ${component.inputQuestion ? html`
                    <div class="input-question">
                        <platform-icon name="info" size="16"></platform-icon>
                        <span>${component.inputQuestion}</span>
                    </div>
                ` : ''}
                <div class="input-row">
                    <div class="input-tools-column">
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
                        ${component.isBreakpoint
                            ? html`
                                  <button
                                      type="button"
                                      class="btn-run-icon btn-resume-inline"
                                      @click=${component._handleResume}
                                      ?disabled=${component.inputQuestion && !component.message.trim()}
                                      title=${component.inputQuestion ? 'Отправить ответ' : 'Продолжить выполнение'}
                                  >
                                      <svg
                                          class="btn-resume-combo-svg"
                                          xmlns="http://www.w3.org/2000/svg"
                                          viewBox="0 0 24 24"
                                          width="20"
                                          height="20"
                                          aria-hidden="true"
                                      >
                                          <polygon points="4,5 4,19 13,12" fill="currentColor" />
                                          <rect x="15" y="6" width="2.8" height="12" rx="0.5" fill="currentColor" />
                                          <rect x="19.2" y="6" width="2.8" height="12" rx="0.5" fill="currentColor" />
                                      </svg>
                                  </button>
                              `
                            : component.isRunning
                              ? html`
                                    <button
                                        type="button"
                                        class="btn-run-icon btn-stop-icon"
                                        @click=${component._handleStop}
                                        title="Остановить"
                                    >
                                        <svg
                                            class="btn-stop-svg"
                                            xmlns="http://www.w3.org/2000/svg"
                                            viewBox="0 0 24 24"
                                            width="20"
                                            height="20"
                                            aria-hidden="true"
                                        >
                                            <rect
                                                x="5"
                                                y="5"
                                                width="14"
                                                height="14"
                                                rx="2"
                                                fill="currentColor"
                                            />
                                        </svg>
                                    </button>
                                `
                              : html`
                                    <button
                                        type="button"
                                        class="btn-run-icon ${hasError ? 'btn-retry-icon' : ''}"
                                        @click=${component._handleRun}
                                        ?disabled=${!component.message.trim()}
                                        title=${hasError ? 'Запустить заново' : 'Запустить'}
                                    >
                                        <platform-icon name="play" size="20"></platform-icon>
                                    </button>
                                `}
                    </div>
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
                                    type="button"
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

            ${hasError ? html`
                <div class="error-section">
                    <div class="error-header">
                        <platform-icon name="x" size="16" style="color: var(--error, #ef4444);"></platform-icon>
                        <span>Ошибка</span>
                        <button 
                            type="button"
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
                            type="button"
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
                            type="button"
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
                            type="button"
                            class="mocks-close"
                            @click=${component._toggleMocks}
                        >
                            ×
                        </button>
                    </div>
                    <div class="mocks-body">
                        <llm-mocks-editor
                            .mocks=${component.mockResponses}
                            .flowNodes=${component.flowNodes || {}}
                            @change=${component._handleMocksChange}
                        ></llm-mocks-editor>
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

