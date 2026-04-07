/**
 * Главный компонент чата
 * Наследует PlatformIsland для унифицированного glass-стиля
 */
import { html, css } from 'lit';
import { PlatformIsland } from '@platform/lib/components/layout/platform-island.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { FlowsStore } from '../../store/flows.store.js';
import '../../components/integration-badges.js';

let messageIdCounter = 0;

export class PlatformChat extends PlatformIsland {
    static styles = [
        PlatformIsland.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                height: 100%;
                overflow: hidden;
            }
            
            .island {
                display: flex;
                flex-direction: column;
                height: 100%;
            }
            
            .chat-header {
                display: flex;
                align-items: center;
                justify-content: space-between;
                padding: var(--space-4) var(--space-6);
                border-bottom: 1px solid var(--border-subtle);
                background: var(--glass-tint-subtle);
            }
            
            .chat-title-section {
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            
            .menu-btn {
                display: none;
                width: 32px;
                height: 32px;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                color: var(--text-primary);
                cursor: pointer;
                flex-shrink: 0;
            }
            
            .menu-btn:hover {
                background: var(--glass-solid-medium);
            }
            
            .chat-title {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xl);
                font-weight: var(--font-bold);
                color: var(--text-primary);
                letter-spacing: var(--tracking-tight);
            }
            
            .flow-name {
                max-width: 200px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            
            .chat-subtitle {
                font-size: var(--text-xs);
                color: var(--text-tertiary);
                margin-top: 2px;
            }
            
            .skill-badge {
                display: inline-flex;
                align-items: center;
                padding: var(--space-1) var(--space-3);
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--accent);
                background: var(--accent-subtle);
                border-radius: var(--radius-full);
                max-width: 120px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
                flex-shrink: 0;
            }
            
            .chat-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            
            .action-btn {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                background: transparent;
                border: 1px solid transparent;
                transition: all var(--duration-normal) var(--easing-default);
            }
            
            .action-btn:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-subtle);
                color: var(--text-primary);
                transform: translateY(-1px);
            }
            
            .action-btn.active {
                background: var(--accent-subtle);
                border-color: var(--accent);
                color: var(--accent);
            }
            
            .user-badge {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                padding: var(--space-2) var(--space-3);
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                font-size: var(--text-sm);
                color: var(--text-secondary);
            }
            
            .user-badge platform-icon {
                color: var(--accent);
            }
            
            .chat-body {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                background: var(--glass-solid-subtle);
                border-radius: var(--radius-xl);
                border: 1px solid var(--glass-border-subtle);
                overflow: hidden;
                position: relative;
            }
            
            chat-messages {
                flex: 1;
                min-height: 0;
            }
            
            .state-btn {
                position: absolute;
                top: var(--space-3);
                left: var(--space-3);
                z-index: 10;
                width: 36px;
                height: 36px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                background: var(--glass-solid-medium);
                border: 1px solid var(--glass-border-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast) var(--easing-default);
                box-shadow: var(--glass-shadow-subtle);
            }
            
            .state-btn:hover {
                background: var(--glass-solid-strong);
                border-color: var(--accent);
                color: var(--accent);
                transform: scale(1.05);
            }

            .chat-badges {
                position: absolute;
                top: var(--space-3);
                right: var(--space-3);
                z-index: 10;
            }
            
            .mobile-actions-container {
                display: none;
            }

            .actions-menu-btn {
                width: 40px;
                height: 40px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-lg);
                color: var(--text-secondary);
                background: transparent;
                border: 1px solid transparent;
                cursor: pointer;
            }

            .actions-menu-btn:hover {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }

            .actions-dropdown {
                display: none;
                position: absolute;
                top: 100%;
                right: 0;
                margin-top: var(--space-2);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                padding: var(--space-2);
                box-shadow: var(--glass-shadow-strong);
                z-index: var(--z-dropdown);
                min-width: 180px;
            }

            .actions-dropdown.open {
                display: block;
            }

            .actions-dropdown-item {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                width: 100%;
                padding: var(--space-3);
                background: transparent;
                border: none;
                border-radius: var(--radius-md);
                color: var(--text-primary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: background var(--duration-fast);
                text-align: left;
            }

            .actions-dropdown-item:hover {
                background: var(--glass-solid-medium);
            }
            
            @media (max-width: 768px) {
                :host {
                    margin: 0;
                    height: var(--app-vh, 100vh);
                    border-radius: 0;
                }

                .chat-header {
                    padding: max(var(--space-3), env(safe-area-inset-top, 0px)) var(--space-4) var(--space-3);
                }

                .menu-btn {
                    display: flex;
                }

                .chat-title {
                    font-size: var(--text-base);
                }
                
                .flow-name {
                    max-width: 140px;
                }

                .chat-subtitle {
                    display: none;
                }

                .skill-badge {
                    font-size: var(--text-xs);
                    padding: var(--space-1) var(--space-2);
                    max-width: 100px;
                }

                .chat-actions .action-btn {
                    display: none;
                }

                .mobile-actions-container {
                    display: block;
                    position: relative;
                }
                
                .chat-body {
                    border-radius: 0;
                    border-left: none;
                    border-right: none;
                }
            }

            /* Element fullscreen (DOM Fullscreen API) */
            :host:fullscreen,
            :host:-webkit-full-screen {
                margin: 0;
                border-radius: 25px;
            }

            :host:fullscreen .island,
            :host:-webkit-full-screen .island {
                border-radius: 25px;
            }

            :host:fullscreen .chat-body,
            :host:-webkit-full-screen .chat-body {
                border-radius: 25px;
                border-left: 1px solid var(--glass-border-subtle);
                border-right: 1px solid var(--glass-border-subtle);
            }

            :host:fullscreen .island-header-glow,
            :host:-webkit-full-screen .island-header-glow {
                border-radius: 25px 25px 0 0;
            }
        `
    ];

    static properties = {
        flowId: { type: String },
        flowName: { type: String },
        skillId: { type: String },
        skillName: { type: String },
        _actionsMenuOpen: { state: true },
    };

    constructor() {
        super();
        this.flowId = '';
        this.flowName = '';
        this.skillId = '';
        this.skillName = '';
        this.headerGlow = false;
        this.hideMenu = true;
        this._actionsMenuOpen = false;
        this._streamAbortController = null;
        
        this.state = this.use(s => ({
            messages: s.chat.messages,
            loading: s.chat.loading,
            streamPending: s.chat.streamPending,
            contextId: s.chat.contextId,
            currentTaskId: s.chat.currentTaskId,
        }));
    }

    _toggleActionsMenu() {
        this._actionsMenuOpen = !this._actionsMenuOpen;
    }

    _closeActionsMenu() {
        this._actionsMenuOpen = false;
    }

    _openSidebar() {
        window.dispatchEvent(new CustomEvent('platform-sidebar-open', {
            bubbles: true,
            composed: true,
        }));
    }

    connectedCallback() {
        super.connectedCallback();
        FlowsStore.initChat();
    }

    _isActiveTakeover() {
        const msgs = FlowsStore.state.chat.messages;
        for (let i = msgs.length - 1; i >= 0; i--) {
            const m = msgs[i];
            if (m.role !== 'assistant') continue;
            return (
                m.inputRequired?.interruptKind === 'operator_task' &&
                m.inputRequired.handoffMode === 'takeover'
            );
        }
        return false;
    }

    _onStopStream() {
        if (this._streamAbortController) {
            this._streamAbortController.abort();
            this._streamAbortController = null;
        }
        const taskId = this.state.value.currentTaskId;
        if (taskId && this.flowId) {
            this.a2a.cancelTask(this.flowId, taskId).catch(err => {
                console.warn('[PlatformChat] Failed to cancel task:', err);
            });
        }
    }

    async _onSendMessage(e) {
        const { message, files = [] } = e.detail;
        if (!message && files.length === 0) return;

        const takeover = this._isActiveTakeover();

        if (!takeover && (this.state.value.loading || this.state.value.streamPending)) {
            return;
        }

        const fileParts = await Promise.all(
            files.map(file => this._fileToBase64Part(file))
        );

        const userMessage = {
            id: `msg_${++messageIdCounter}`,
            role: 'user',
            content: message,
            timestamp: new Date().toLocaleTimeString(),
            files: files.map(f => ({ name: f.name, size: f.size, type: f.type })),
        };
        FlowsStore.addMessage(userMessage);

        // A2A Section 3.4.3: при активном operator takeover реплика пользователя
        // отправляется через тот же message/stream; бэкенд маршрутизирует в dialog_log.
        if (takeover) {
            await this.a2a.streamMessage(
                this.flowId,
                message,
                { contextId: this.state.value.contextId, files: fileParts },
                () => {},
            ).catch(err => {
                this.error(this.i18n.t('platform_chat.err_with_message', { message: err.message }));
            });
            return;
        }

        FlowsStore.setLoading(true);
        FlowsStore.setStreamPending(true);

        this._streamAbortController = new AbortController();

        const assistantMessage = {
            id: `msg_${++messageIdCounter}`,
            role: 'assistant',
            content: '',
            streaming: true,
            reasoning: '',
            operatorReply: '',
            toolCalls: [],
            toolResults: [],
            inputRequired: null,
            breakpoint: null,
        };
        FlowsStore.addMessage(assistantMessage);
        this._activeStreamMessageId = assistantMessage.id;

        try {
            await this.a2a.streamMessage(
                this.flowId,
                message,
                {
                    files: fileParts,
                    contextId: this.state.value.contextId,
                    skillId: this.skillId || null,
                    signal: this._streamAbortController.signal,
                },
                (event) => this._handleStreamEvent(event, this._activeStreamMessageId)
            );
        } catch (err) {
            if (err.name === 'AbortError') {
                FlowsStore.updateMessage(assistantMessage.id, { streaming: false });
            } else {
                this.error(this.i18n.t('platform_chat.err_with_message', { message: err.message }));
                FlowsStore.updateMessage(assistantMessage.id, {
                    content: this.i18n.t('platform_chat.stream_fallback_content'),
                    streaming: false,
                });
            }
        } finally {
            this._streamAbortController = null;
            FlowsStore.setLoading(false);
            FlowsStore.setStreamPending(false);
        }
    }

    async _fileToBase64Part(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.onload = () => {
                const base64 = reader.result.split(',')[1];
                resolve({
                    kind: 'file',
                    name: file.name,
                    mimeType: file.type,
                    data: base64,
                });
            };
            reader.onerror = reject;
            reader.readAsDataURL(file);
        });
    }

    _handleStreamEvent(event, messageId) {
        console.log('[PlatformChat] SSE event received:', event);

        if (event.error) {
            console.error('[PlatformChat] Error in SSE:', event.error);
            FlowsStore.updateMessage(messageId, { 
                content: event.error.message || this.i18n.t('platform_chat.err_short'), 
                streaming: false 
            });
            return;
        }

        const result = event.result;
        if (!result) {
            console.warn('[PlatformChat] No result in event');
            return;
        }

        console.log('[PlatformChat] Event kind:', result.kind);

        if (result.kind === 'artifact-update') {
            const artifact = result.artifact;
            console.log('[PlatformChat] artifact-update:', artifact?.name, artifact);
            
            const { task_id } = result.metadata || {};
            
            if (task_id) {
                const currentTaskId = this.state.value.currentTaskId;
                if (task_id !== currentTaskId) {
                    FlowsStore.setState((s) => ({
                        chat: { ...s.chat, currentTaskId: task_id },
                    }));
                    this.emit(AppEvents.TASK_UPDATE, { taskId: task_id, artifact });
                }
            }
            
            const state = artifact?.state;
            const message = artifact?.message;

            if (artifact?.parts) {
                const text = artifact.parts
                    .filter(p => p.kind === 'text' && p.text)
                    .map(p => p.text)
                    .join('');
                
                if (text) {
                    console.log('[PlatformChat] appending text from artifact.parts:', text, 'name:', artifact.name);
                    
                    if (artifact.name === 'reasoning') {
                        FlowsStore.appendToMessageField(messageId, 'reasoning', text);
                    } else if (artifact.name === 'operator_reply') {
                        FlowsStore.addMessage({
                            id: `msg_${++messageIdCounter}`,
                            role: 'operator',
                            content: text,
                            timestamp: new Date().toLocaleTimeString(),
                        });
                    } else if (artifact.name === 'operator_files') {
                        // handled below via DataPart
                    } else {
                        const currentMsg = FlowsStore.state.chat.messages.find(m => m.id === messageId);
                        if (currentMsg?.inputRequired) {
                            FlowsStore.updateMessage(messageId, { inputRequired: null, streaming: false });
                            const resumeMsg = {
                                id: `msg_${++messageIdCounter}`,
                                role: 'assistant',
                                content: '',
                                streaming: true,
                                reasoning: '',
                                operatorReply: '',
                                toolCalls: [],
                                toolResults: [],
                                inputRequired: null,
                                breakpoint: null,
                            };
                            FlowsStore.addMessage(resumeMsg);
                            this._activeStreamMessageId = resumeMsg.id;
                            messageId = resumeMsg.id;
                        }
                        FlowsStore.appendToMessage(messageId, text);
                    }
                }
            }

            if (artifact?.name === 'operator_files' && artifact?.parts) {
                const dataPart = artifact.parts.find(p => p.data?.file_ids);
                if (dataPart) {
                    const fileIds = dataPart.data.file_ids;
                    const messages = FlowsStore.state.chat.messages;
                    const lastOperatorMsg = [...messages].reverse().find(m => m.role === 'operator');
                    if (lastOperatorMsg) {
                        const existing = lastOperatorMsg.fileIds || [];
                        FlowsStore.updateMessage(lastOperatorMsg.id, {
                            fileIds: [...existing, ...fileIds],
                        });
                    } else {
                        FlowsStore.addMessage({
                            id: `msg_${++messageIdCounter}`,
                            role: 'operator',
                            content: '',
                            fileIds,
                            timestamp: new Date().toLocaleTimeString(),
                        });
                    }
                }
            }

            if (message && message.parts) {
                const text = message.parts
                    .filter(p => p.kind === 'text' && p.text)
                    .map(p => p.text)
                    .join('');
                
                if (text) {
                    console.log('[PlatformChat] appending text from message.parts:', text);
                    FlowsStore.appendToMessage(messageId, text);
                }
                
                const reasoning = message.parts.find(p => p.kind === 'reasoning');
                if (reasoning?.text) {
                    FlowsStore.updateMessage(messageId, { reasoning: reasoning.text });
                }
            }

            if (message && message.metadata) {
                if (message.metadata.tool_calls) {
                    const messages = FlowsStore.state.chat.messages;
                    const currentMsg = messages.find(m => m.id === messageId);
                    if (currentMsg) {
                        const newToolCalls = message.metadata.tool_calls.filter(
                            tc => !currentMsg.toolCalls.find(existing => existing.id === tc.id)
                        );
                        if (newToolCalls.length > 0) {
                            FlowsStore.updateMessage(messageId, { 
                                toolCalls: [...currentMsg.toolCalls, ...newToolCalls] 
                            });
                        }
                    }
                }

                if (message.metadata.tool_result) {
                    const messages = FlowsStore.state.chat.messages;
                    const currentMsg = messages.find(m => m.id === messageId);
                    if (currentMsg) {
                        const resultExists = currentMsg.toolResults.find(
                            r => r.id === message.metadata.tool_result.id
                        );
                        if (!resultExists) {
                            FlowsStore.updateMessage(messageId, { 
                                toolResults: [...currentMsg.toolResults, message.metadata.tool_result] 
                            });
                        }
                    }
                }
            }

            if (state === 'completed' && result.final) {
                const taskId = result.taskId || result.task_id || this.state.value.currentTaskId;
                FlowsStore.updateMessage(messageId, { streaming: false, taskId });
                
                if (message && message.parts) {
                    const text = message.parts
                        .filter(p => p.kind === 'text' && p.text)
                        .map(p => p.text)
                        .join('');
                        
                    if (text) {
                        const messages = FlowsStore.state.chat.messages;
                        const msg = messages.find(m => m.id === messageId);
                        if (msg && !msg.content.trim()) {
                            FlowsStore.updateMessage(messageId, { content: text });
                        }
                    }
                }
            }

            if (state === 'failed' && result.final) {
                let errorText = this.i18n.t('platform_chat.err_occurred');
                
                if (message && message.parts) {
                    const extracted = message.parts
                        .filter(p => p.kind === 'text' && p.text)
                        .map(p => p.text)
                        .join('');
                    if (extracted) {
                        errorText = extracted;
                    }
                }
                
                FlowsStore.updateMessage(messageId, { 
                    content: errorText,
                    streaming: false 
                });
            }

            if ((state === 'input-required' || state === 'input_required') && result.final) {
                const metadata = result.metadata || {};
                const taskId = result.taskId || result.task_id || this.state.value.currentTaskId;
                
                if (metadata.breakpoint) {
                    const breakpointData = {
                        node_id: metadata.breakpoint.node_id,
                        state: metadata.breakpoint.state,
                        step: metadata.breakpoint.step,
                        data: metadata.breakpoint.data
                    };
                    FlowsStore.updateMessage(messageId, { 
                        breakpoint: breakpointData,
                        streaming: false,
                        taskId
                    });
                } else {
                    FlowsStore.updateMessage(messageId, {
                        inputRequired: this._buildInputRequiredPayload(message, metadata),
                        streaming: false,
                        taskId,
                    });
                }
            }
        } else if (result.kind === 'status-update') {
            const status = result.status;
            if (!status) return;

            const message = status.message;
            const state = status.state;

            const isTerminal = state === 'completed' || state === 'finished' ||
                               state === 'failed' || state === 'error';
            if (isTerminal && message && message.parts) {
                const text = message.parts
                    .filter(p => p.kind === 'text' && p.text)
                    .map(p => p.text)
                    .join('');
                
                if (text) {
                    const messages = FlowsStore.state.chat.messages;
                    const msg = messages.find(m => m.id === messageId);
                    if (msg && !(msg.content || '').trim()) {
                        FlowsStore.updateMessage(messageId, { content: text });
                    }
                }
            }

            if (message && message.metadata) {
                if (message.metadata.tool_calls) {
                    const messages = FlowsStore.state.chat.messages;
                    const currentMsg = messages.find(m => m.id === messageId);
                    if (currentMsg) {
                        const newToolCalls = message.metadata.tool_calls.filter(
                            tc => !currentMsg.toolCalls.find(existing => existing.id === tc.id)
                        );
                        if (newToolCalls.length > 0) {
                            FlowsStore.updateMessage(messageId, { 
                                toolCalls: [...currentMsg.toolCalls, ...newToolCalls] 
                            });
                        }
                    }
                }

                if (message.metadata.tool_result) {
                    const messages = FlowsStore.state.chat.messages;
                    const currentMsg = messages.find(m => m.id === messageId);
                    if (currentMsg) {
                        const resultExists = currentMsg.toolResults.find(
                            r => r.id === message.metadata.tool_result.id
                        );
                        if (!resultExists) {
                            FlowsStore.updateMessage(messageId, { 
                                toolResults: [...currentMsg.toolResults, message.metadata.tool_result] 
                            });
                        }
                    }
                }
            }

            if (state === 'completed' || state === 'finished') {
                const taskId = result.taskId || result.task_id || this.state.value.currentTaskId;
                FlowsStore.updateMessage(messageId, { streaming: false, taskId, inputRequired: null });
            }

            if (state === 'failed' || state === 'error') {
                let errorText = this.i18n.t('platform_chat.err_occurred');
                const taskId = result.taskId || result.task_id || this.state.value.currentTaskId;
                
                if (message && message.parts) {
                    const extracted = message.parts
                        .filter(p => p.kind === 'text' && p.text)
                        .map(p => p.text)
                        .join('');
                    if (extracted) {
                        errorText = extracted;
                    }
                }
                
                FlowsStore.updateMessage(messageId, { 
                    content: errorText,
                    streaming: false,
                    taskId,
                    inputRequired: null,
                });
            }

            if (state === 'input-required' || state === 'input_required') {
                const metadata = result.metadata || {};
                const taskId = result.taskId || result.task_id || status.taskId || status.task_id || this.state.value.currentTaskId;
                const handoffContinue = metadata.platform_handoff_continue === true;
                const oauthContinue = metadata.platform_oauth_continue === true;

                if (!result.final && (handoffContinue || oauthContinue)) {
                    FlowsStore.setLoading(false);
                    FlowsStore.updateMessage(messageId, {
                        inputRequired: this._buildInputRequiredPayload(message, metadata),
                        streaming: false,
                        taskId,
                    });
                } else if (metadata.breakpoint) {
                    const breakpointData = {
                        node_id: metadata.breakpoint.node_id,
                        state: metadata.breakpoint.state,
                        step: metadata.breakpoint.step,
                        data: metadata.breakpoint.data
                    };
                    FlowsStore.updateMessage(messageId, { 
                        breakpoint: breakpointData,
                        streaming: false,
                        taskId
                    });
                } else {
                    FlowsStore.updateMessage(messageId, {
                        inputRequired: this._buildInputRequiredPayload(message, metadata),
                        streaming: false,
                        taskId,
                    });
                }
            }
        }
    }


    _buildInputRequiredPayload(message, resultMetadata) {
        const meta = resultMetadata || {};
        const msgMeta = message?.metadata || {};
        const pi = meta.platform_interrupt || msgMeta.platform_interrupt;
        if (pi && typeof pi === 'object' && pi.body && pi.body.kind) {
            const kind = pi.body.kind;
            if (kind === 'user_message') {
                return { question: pi.body.question, interruptKind: kind };
            }
            if (kind === 'operator_task') {
                return {
                    question: pi.body.question,
                    interruptKind: kind,
                    operatorTaskTitle: pi.body.task_title,
                    operatorAssigneeQueue: pi.body.assignee_queue,
                    handoffMode: pi.body.handoff_mode || 'single_reply',
                    operatorTaskId: pi.body.operator_task_id || null,
                };
            }
            if (kind === 'oauth_required') {
                return {
                    question: pi.body.question,
                    interruptKind: kind,
                    authUrl: pi.body.auth_url,
                    provider: pi.body.provider,
                    service: pi.body.service,
                };
            }
            throw new Error(`Unknown interrupt kind: ${kind}`);
        }
        return { question: this._extractQuestionFromMessage(message) };
    }

    _extractQuestionFromMessage(message) {
        if (!message) return '';
        
        if (message.parts) {
            return message.parts
                .filter(p => p.kind === 'text' && p.text)
                .map(p => p.text)
                .join('');
        }
        
        if (typeof message === 'string') return message;
        if (message.text) return message.text;
        
        return '';
    }

    _clearChat() {
        FlowsStore.clearChat();
        this.info(this.i18n.t('platform_chat.info_chat_cleared'));
    }

    _openSessions() {
        const modal = document.createElement('sessions-modal');
        modal.flowId = this.flowId;
        document.body.appendChild(modal);
        modal.addEventListener('close', () => modal.remove());
        modal.showModal();
    }

    _openState() {
        const { contextId, currentTaskId } = this.state.value;
        if (!contextId) {
            this.warn(this.i18n.t('platform_chat.warn_no_session'));
            return;
        }
        
        const modal = document.createElement('state-modal');
        modal.contextId = contextId;
        modal.taskId = currentTaskId;
        modal.flowId = this.flowId;
        document.body.appendChild(modal);
        modal.addEventListener('close', () => modal.remove());
        modal.showModal();
    }

    _onShowTracingFromMessage(e) {
        const { taskId } = e.detail;
        if (!taskId) {
            this.warn(this.i18n.t('platform_chat.warn_no_task_tracing'));
            return;
        }
        
        const modal = document.createElement('tracing-modal');
        modal.flowId = this.flowId;
        modal.taskId = taskId;
        document.body.appendChild(modal);
        modal.addEventListener('close', () => modal.remove());
        modal.showModal();
    }
    
    _editFlow() {
        const modal = document.createElement('flow-edit-modal');
        modal.flowId = this.flowId;
        if (this.skillId) {
            modal.skillId = this.skillId;
        }
        document.body.appendChild(modal);
        
        requestAnimationFrame(() => {
            modal.setAttribute('open', '');
        });
        
        modal.addEventListener('close', () => modal.remove());
    }

    render() {
        const { messages, loading, contextId, currentTaskId } = this.state.value;
        const hasState = contextId && messages.length > 0;
        
        return html`
            <div class="island">
                <header class="chat-header">
                    <div class="chat-title-section">
                        <button class="menu-btn" @click=${this._openSidebar} title=${this.i18n.t('platform_chat.title_menu')}>
                            <platform-icon name="menu" size="18"></platform-icon>
                        </button>
                        <div>
                            <h1 class="chat-title">
                                <span class="flow-name" title="${this.flowName || this.flowId}">${this.flowName || this.flowId}</span>
                                ${this.skillId ? html`<span class="skill-badge" title="${this.skillName || this.skillId}">${this.skillName || this.skillId}</span>` : ''}
                            </h1>
                            <div class="chat-subtitle">${this.i18n.t('platform_chat.session_label')} ${contextId ? `${contextId.substring(0, 12)}...` : this.i18n.t('platform_chat.session_none')}</div>
                        </div>
                    </div>
                    <div class="chat-actions">
                        <button class="action-btn" @click=${this._openSessions} title=${this.i18n.t('platform_chat.title_sessions')}>
                            <platform-icon name="folder" size="20"></platform-icon>
                        </button>
                        <button class="action-btn" @click=${this._editFlow} title=${this.i18n.t('platform_chat.title_edit_agent')}>
                            <platform-icon name="settings" size="20"></platform-icon>
                        </button>
                        <button class="action-btn" @click=${this._clearChat} title=${this.i18n.t('platform_chat.title_clear_chat')}>
                            <platform-icon name="refresh" size="20"></platform-icon>
                        </button>
                        
                        <!-- Mobile actions menu -->
                        <div class="mobile-actions-container">
                            <button class="actions-menu-btn" @click=${this._toggleActionsMenu} title=${this.i18n.t('platform_chat.title_actions')}>
                                <platform-icon name="settings" size="20"></platform-icon>
                            </button>
                            <div class="actions-dropdown ${this._actionsMenuOpen ? 'open' : ''}" @click=${(e) => e.stopPropagation()}>
                                <button class="actions-dropdown-item" @click=${() => { this._openSessions(); this._closeActionsMenu(); }}>
                                    <platform-icon name="folder" size="16"></platform-icon>
                                    <span>${this.i18n.t('platform_chat.menu_sessions')}</span>
                                </button>
                                <button class="actions-dropdown-item" @click=${() => { this._editFlow(); this._closeActionsMenu(); }}>
                                    <platform-icon name="settings" size="16"></platform-icon>
                                    <span>${this.i18n.t('platform_chat.menu_edit')}</span>
                                </button>
                                <button class="actions-dropdown-item" @click=${() => { this._clearChat(); this._closeActionsMenu(); }}>
                                    <platform-icon name="refresh" size="16"></platform-icon>
                                    <span>${this.i18n.t('platform_chat.menu_clear_chat')}</span>
                                </button>
                            </div>
                        </div>
                    </div>
                </header>
                
                <div class="chat-body">
                    ${hasState ? html`
                        <button class="state-btn" @click=${this._openState} title=${this.i18n.t('platform_chat.title_session_state')}>
                            <platform-icon name="database" size="18"></platform-icon>
                        </button>
                    ` : ''}

                    <integration-badges class="chat-badges"></integration-badges>
                    
                    <chat-messages
                        .messages=${messages}
                        ?loading=${loading}
                        @show-tracing=${this._onShowTracingFromMessage}
                    ></chat-messages>
                    
                    <chat-input
                        ?loading=${loading}
                        placeholder=${this.i18n.t('chat_widget.placeholder_message')}
                        @send=${this._onSendMessage}
                        @stop=${this._onStopStream}
                    ></chat-input>
                </div>
            </div>
        `;
    }
}

customElements.define('platform-chat', PlatformChat);
