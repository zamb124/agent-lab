/**
 * ExecutionPanel - UI панель для запуска execution с контролами
 * Независимый компонент для любых исполняемых сущностей
 * 
 * Public API:
 * - Properties: .runner, show-state, show-tracing, show-mocks, placeholder
 * - Methods: showResult(), clearResult(), setRunning()
 * - Events: run-requested (detail.reuseContext), stop-requested, state-requested, tracing-requested, mocks-requested, close-requested
 */
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { executionPanelStyles } from './styles.js';
import { renderPanel } from './templates.js';

export class ExecutionPanel extends PlatformElement {
    static styles = [PlatformElement.styles, executionPanelStyles];

    static properties = {
        runner: { type: Object },
        showState: { type: Boolean, attribute: 'show-state' },
        showTracing: { type: Boolean, attribute: 'show-tracing' },
        showMocks: { type: Boolean, attribute: 'show-mocks' },
        placeholder: { type: String },
        message: { type: String },
        files: { type: Array },
        isRunning: { type: Boolean },
        isBreakpoint: { type: Boolean },
        breakpointNodeId: { type: String },
        inputQuestion: { type: String },
        result: { type: Object },
        errorMessage: { type: String },
        hasExecutionData: { type: Boolean },
        contextId: { type: String },
        taskId: { type: String },
        showMocksSection: { type: Boolean },
        mockResponses: { type: Array },
        flowNodes: { type: Object },
        persistSessionContext: { type: Boolean, attribute: 'persist-session-context' },
    };

    constructor() {
        super();
        this.runner = null;
        this.showState = false;
        this.showTracing = false;
        this.showMocks = false;
        this.placeholder = '';
        this.message = '';
        this.files = [];
        this.isRunning = false;
        this.isBreakpoint = false;
        this.breakpointNodeId = null;
        this.inputQuestion = null;
        this.result = null;
        this.errorMessage = null;
        this.hasExecutionData = false;
        this.contextId = null;
        this.taskId = null;
        this.showMocksSection = false;
        this.mockResponses = [];
        this.flowNodes = {};
        this.persistSessionContext = true;
    }

    get persistContextHelpText() {
        return (
            'Включено: каждый запуск использует тот же contextId — продолжается один state сессии. '
            + 'Выключено: каждый запуск с новым контекстом.'
        );
    }

    _onPersistToggleClick() {
        this.persistSessionContext = !this.persistSessionContext;
    }

    render() {
        return renderPanel(this);
    }

    /**
     * Обработчик ввода сообщения
     */
    _handleMessageInput(e) {
        this.message = e.target.value;
    }

    /**
     * Обработчик выбора файлов
     */
    _handleFileSelect(e) {
        const newFiles = Array.from(e.target.files);
        this.files = [...this.files, ...newFiles];
        e.target.value = '';
    }

    /**
     * Удалить файл из списка
     */
    _removeFile(index) {
        this.files = this.files.filter((_, i) => i !== index);
    }

    /**
     * Обработчик клика Run
     */
    _handleRun() {
        if (!this.message.trim()) {
            return;
        }

        this.emit('run-requested', {
            message: this.message,
            files: this.files,
            mocks: this.mockResponses,
            reuseContext: this.persistSessionContext,
        });

        this.isRunning = true;
        this.result = null;
        this.errorMessage = null;
        this.hasExecutionData = false;
    }

    /**
     * Обработчик клика Stop
     */
    _handleStop() {
        this.emit('stop-requested');
        this.isRunning = false;
    }

    /**
     * Обработчик клика Resume (продолжить после breakpoint)
     */
    _handleResume() {
        const answer = this.message.trim();
        
        if (!this.contextId) {
            console.warn('[ExecutionPanel] Нет contextId для resume');
            return;
        }

        if (this.inputQuestion && !answer) {
            console.warn('[ExecutionPanel] Требуется ответ на вопрос');
            return;
        }

        this.emit('resume-flow', {
            answer: answer || 'continue',
            contextId: this.contextId
        });

        this.isBreakpoint = false;
        this.breakpointNodeId = null;
        this.inputQuestion = null;
        this.message = '';
        this.isRunning = true;
    }

    /**
     * Установить требование ввода от пользователя
     */
    setInputRequired(question, contextId) {
        this.inputQuestion = question;
        this.contextId = contextId;
        this.isBreakpoint = true;
        this.isRunning = false;
        this.message = '';
    }

    /**
     * Установить состояние breakpoint
     */
    setBreakpoint(nodeId) {
        this.isBreakpoint = true;
        this.breakpointNodeId = nodeId;
        this.isRunning = false;
    }

    /**
     * Очистить состояние breakpoint
     */
    clearBreakpoint() {
        this.isBreakpoint = false;
        this.breakpointNodeId = null;
        this.inputQuestion = null;
    }

    /**
     * Обработчик клика State
     */
    _handleStateClick() {
        if (this.contextId && this.taskId) {
            this.emit('state-requested', {
                contextId: this.contextId,
                taskId: this.taskId
            });
        }
    }

    /**
     * Обработчик клика Tracing
     */
    _handleTracingClick() {
        if (this.contextId && this.taskId) {
            this.emit('tracing-requested', {
                contextId: this.contextId,
                taskId: this.taskId
            });
        }
    }

    /**
     * Переключить секцию моков
     */
    _toggleMocks() {
        this.showMocksSection = !this.showMocksSection;
        if (this.showMocksSection) {
            this.emit('mocks-requested');
        }
    }

    /**
     * Обработчик изменения моков
     */
    _handleMocksChange(e) {
        this.mockResponses = e.detail.value;
    }

    /**
     * Получить мок-ответы
     */
    getMockResponses() {
        return this.mockResponses;
    }

    /**
     * Закрыть панель
     */
    _handleClose() {
        this.emit('close-requested');
    }

    /**
     * Показать результат выполнения
     */
    showResult(result) {
        this.result = result;
        this.errorMessage = null;
        this.message = '';
        this.files = [];
        this.isRunning = false;
    }

    /**
     * Показать ошибку выполнения
     */
    showError(error) {
        this.errorMessage = error;
        this.result = null;
        this.isRunning = false;
    }

    /**
     * Очистить результат
     */
    _clearResult() {
        this.result = null;
    }

    clearResult() {
        this._clearResult();
    }

    /**
     * Установить состояние выполнения
     */
    setRunning(isRunning) {
        this.isRunning = isRunning;
    }

    /**
     * Установить данные выполнения (contextId, taskId)
     */
    setExecutionData(contextId, taskId) {
        this.contextId = contextId;
        this.taskId = taskId;
        this.hasExecutionData = !!(contextId && taskId);
    }

    /**
     * Получить текущее сообщение
     */
    getMessage() {
        return this.message;
    }

    /**
     * Получить файлы
     */
    getFiles() {
        return this.files;
    }
}

customElements.define('execution-panel', ExecutionPanel);

