/**
 * ExecutionRunner - универсальный исполнитель для любых flow через SSE streaming
 * Независимый компонент, работает с любыми агентами/workflows
 * 
 * Public API:
 * - Properties: agent-id, skill-id, .breakpoints
 * - Methods: run(), resume(), stop()
 * - Events: execution-started, node-status, execution-completed, execution-error, input-required, breakpoint-hit
 */
import { PlatformElement } from '@platform/lib/platform-element/index.js';

export class ExecutionRunner extends PlatformElement {
    static properties = {
        agentId: { type: String, attribute: 'agent-id' },
        skillId: { type: String, attribute: 'skill-id' },
        breakpoints: { type: Object },
    };

    constructor() {
        super();
        this.agentId = '';
        this.skillId = 'default';
        this.breakpoints = {};
        this._isRunning = false;
        this._contextId = null;
        this._taskId = null;
        this._nodeErrors = new Map();
    }

    render() {
        return null;
    }

    /**
     * Запустить выполнение
     * @param {string} message - сообщение пользователя
     * @param {File[]} files - файлы для отправки
     * @param {Object} breakpoints - объект breakpoints для отладки
     * @param {Array} mocks - массив мок-ответов для LLM
     */
    async run(message, files = [], breakpoints = {}, mocks = []) {
        if (this._isRunning) {
            console.warn('[ExecutionRunner] Уже выполняется');
            return;
        }

        if (!this.agentId) {
            this.error('Agent ID не указан');
            return;
        }

        this._isRunning = true;
        this._contextId = `exec-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`;
        this._taskId = null;
        this._nodeErrors.clear();

        this.emit('execution-started', { 
            contextId: this._contextId,
            agentId: this.agentId 
        });

        this.emit('clear-node-errors');

        try {
            // Формируем текст сообщения
            let messageText = message;
            
            if (files && files.length > 0) {
                const fileParts = await this._prepareFileParts(files);
                // Добавляем информацию о файлах к сообщению
                const fileInfo = fileParts.map(f => f.text || f.name || 'file').join(', ');
                messageText = `${message}\n\nПрикрепленные файлы: ${fileInfo}`;
            }

            console.log('[ExecutionRunner] Отправка breakpoints:', breakpoints);
            console.log('[ExecutionRunner] Отправка mocks:', mocks);

            // Используем a2a.service вместо прямого fetch
            await this.a2a.streamMessage(
                this.agentId,
                messageText,
                {
                    contextId: this._contextId,
                    skillId: this.skillId !== 'base' ? this.skillId : null,
                    breakpoints,
                    mocks
                },
                (event) => this._handleEvent(event)
            );

        } catch (error) {
            console.error('[ExecutionRunner] Ошибка:', error);
            this.emit('execution-error', { error: error.message });
        } finally {
            this._isRunning = false;
        }
    }

    /**
     * Продолжить выполнение после input-required
     * @param {string} answer - ответ пользователя
     * @param {string} contextId - ID контекста для resume
     */
    async resume(answer, contextId) {
        if (this._isRunning) {
            console.warn('[ExecutionRunner] Уже выполняется');
            return;
        }

        this._isRunning = true;
        this._contextId = contextId;

        try {
            // Используем a2a.service вместо прямого fetch
            await this.a2a.streamMessage(
                this.agentId,
                answer,
                {
                    contextId,
                    skillId: this.skillId !== 'base' ? this.skillId : null
                },
                (event) => this._handleEvent(event)
            );

        } catch (error) {
            console.error('[ExecutionRunner] Ошибка возобновления:', error);
            this.emit('execution-error', { error: error.message });
        } finally {
            this._isRunning = false;
        }
    }

    /**
     * Остановить выполнение
     */
    stop() {
        console.log('[ExecutionRunner] Остановка выполнения');
        // Note: a2a.service doesn't support abort, so we just mark as stopped
        this._isRunning = false;
    }

    /**
     * Обработать событие из SSE stream
     */
    _handleEvent(event) {
        if (event.error) {
            console.error('[ExecutionRunner] Ошибка сервера (event.error):', event.error);
            const errorMessage = typeof event.error === 'object' && event.error.message 
                ? event.error.message 
                : typeof event.error === 'string' 
                    ? event.error 
                    : 'Неизвестная ошибка';
            this.emit('execution-error', { error: errorMessage });
            return;
        }

        const result = event.result;
        if (!result) return;

        console.log('[ExecutionRunner] _handleEvent - kind:', result.kind);

        const resultTaskId = result.taskId || result.task_id;
        if (resultTaskId && !this._taskId) {
            this._taskId = resultTaskId;
            console.log('[ExecutionRunner] Получен taskId:', resultTaskId);
            
            this.emit('execution-started', { 
                contextId: this._contextId,
                taskId: this._taskId,
                agentId: this.agentId 
            });
        }

        if (result.kind === 'artifact-update') {
            this._handleArtifact(result);
        } else if (result.kind === 'status-update') {
            this._handleStatus(result);
        }
    }

    /**
     * Обработать artifact событие (node_start, node_complete, node_error)
     */
    _handleArtifact(event) {
        if (!event.artifact) return;

        const artifactName = event.artifact.name || '';
        const parts = event.artifact.parts || [];
        const data = parts[0]?.data || parts[0]?.root?.data;
        
        console.log('[ExecutionRunner] _handleArtifact:', { artifactName, data });
        
        if (artifactName.startsWith('node_start_')) {
            const nodeId = data?.node_id || artifactName.replace('node_start_', '');
            if (nodeId) {
                console.log('[ExecutionRunner] Запуск ноды:', nodeId);
                this.emit('node-status', { nodeId, status: 'running' });
            }
        } else if (artifactName.startsWith('node_complete_')) {
            const nodeId = data?.node_id || artifactName.replace('node_complete_', '');
            if (nodeId) {
                console.log('[ExecutionRunner] Завершение ноды:', nodeId);
                this.emit('node-status', { nodeId, status: 'completed' });
            }
        } else if (artifactName.startsWith('node_error_')) {
            const nodeId = data?.node_id || artifactName.replace('node_error_', '');
            if (nodeId) {
                const errorMessage = data?.error || 'Ошибка выполнения ноды';
                console.log('[ExecutionRunner] Ошибка ноды:', nodeId, errorMessage);
                
                this._nodeErrors.set(nodeId, errorMessage);
                
                this.emit('node-status', { nodeId, status: 'error' });
                this.emit('node-error-details', { nodeId, error: errorMessage });
            }
        } else if (artifactName.startsWith('breakpoint_')) {
            this._handleBreakpointArtifact(data);
        }
    }

    /**
     * Обработать breakpoint artifact
     */
    _handleBreakpointArtifact(data) {
        if (!data || data.event !== 'breakpoint') {
            return;
        }

        const { node_id, node_type, state_snapshot } = data;
        console.log('[ExecutionRunner] Сработала точка останова (artifact):', node_id, node_type);

        this.emit('node-status', { nodeId: node_id, status: 'breakpoint' });
    }

    /**
     * Обработать status событие
     */
    _handleStatus(event) {
        if (!event.status) return;

        const state = event.status.state;
        const isFinal = event.final === true;

        if (isFinal) {
            if (state === 'completed') {
                console.log('[ExecutionRunner] Выполнение завершено');
                const message = event.status.message;
                const text = this._extractTextFromMessage(message);
                this.emit('execution-completed', { 
                    result: text,
                    contextId: this._contextId,
                    taskId: this._taskId
                });
            } else if (state === 'failed') {
                console.log('[ExecutionRunner] Получен failed status:', event);
                const message = event.status.message;
                console.log('[ExecutionRunner] message object:', message);
                const text = this._extractTextFromMessage(message);
                console.log('[ExecutionRunner] Extracted error text:', text);
                this.emit('execution-error', { error: text || 'Выполнение завершилось с ошибкой' });
            } else if (state === 'input-required' || state === 'input_required') {
                const metadata = event.metadata || {};
                
                if (metadata.breakpoint) {
                    console.log('[ExecutionRunner] Сработала точка останова из статуса');
                    const nodeId = metadata.node_id;
                    const nodeType = metadata.node_type || 'unknown';
                    const stateSnapshot = metadata.state_snapshot || {};
                    
                    if (nodeId) {
                        this.emit('node-status', { nodeId, status: 'breakpoint' });
                        this.emit('breakpoint-hit', { 
                            nodeId, 
                            nodeType, 
                            stateSnapshot 
                        });
                    }
                } else {
                    console.log('[ExecutionRunner] Требуется ввод');
                    const message = event.status.message;
                    const question = this._extractTextFromMessage(message);
                    this.emit('input-required', { 
                        question, 
                        contextId: event.contextId || this._contextId 
                    });
                }
            }
        }
    }

    /**
     * Извлечь текст из message
     */
    _extractTextFromMessage(message) {
        if (!message) return '';
        
        // Если message - строка, вернуть её
        if (typeof message === 'string') {
            return message;
        }
        
        // Если есть parts, извлечь текст из них
        if (message.parts && Array.isArray(message.parts)) {
            return message.parts
                .filter(p => p.kind === 'text' && p.text)
                .map(p => p.text)
                .join('');
        }
        
        // Если есть text напрямую
        if (message.text) {
            return message.text;
        }
        
        // Если есть error
        if (message.error) {
            return typeof message.error === 'string' ? message.error : message.error.message || JSON.stringify(message.error);
        }
        
        return '';
    }

    /**
     * Подготовить file parts для отправки
     */
    async _prepareFileParts(files) {
        const parts = [];
        
        for (const file of files) {
            const base64 = await this._fileToBase64(file);
            parts.push({
                kind: 'file',
                file: {
                    name: file.name,
                    mimeType: file.type || 'application/octet-stream',
                    bytes: base64
                }
            });
        }
        
        return parts;
    }

    /**
     * Конвертировать файл в base64
     */
    _fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const base64 = reader.result.split(',')[1];
                resolve(base64);
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    /**
     * Получить текущее состояние
     */
    isRunning() {
        return this._isRunning;
    }

    getContextId() {
        return this._contextId;
    }

    getTaskId() {
        return this._taskId;
    }
}

customElements.define('execution-runner', ExecutionRunner);

