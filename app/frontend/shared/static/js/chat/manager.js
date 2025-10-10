/**
 * Chat Manager - управление чатом
 */

import VoiceRecorder from '/static/js/chat/voice-recorder.js';
import ChatMessageRenderer, { MESSAGE_TYPES } from '/static/js/chat/message-renderer.js';
import { generateUUID } from '/static/js/utils/uuid.js';
import { formatFileSize } from '/static/js/utils/formatting.js';
import { fileToBase64 } from '/static/js/utils/files.js';

class ChatManager {
    constructor(app) {
        this.app = app;
        this.websocket = null;
        this.isConnected = false;
        this.currentAgent = null;
        this.currentSession = null;
        this.agentSessions = this.loadAgentSessions();
        this.activeAgents = new Set();
        this.messageHistory = [];
        this.isVisible = false;
        this.container = null;
        this.messageRenderer = new ChatMessageRenderer();
        this.voiceRecorder = new VoiceRecorder();
        this.selectedFiles = null;
        
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.maxReconnectAttempts = 5;
    }

    loadAgentSessions() {
        try {
            const saved = localStorage.getItem('chat_agent_sessions');
            return saved ? JSON.parse(saved) : {};
        } catch (error) {
            console.error('❌ Ошибка загрузки сессий агентов:', error);
            return {};
        }
    }

    saveAgentSessions() {
        try {
            localStorage.setItem('chat_agent_sessions', JSON.stringify(this.agentSessions));
            console.log('💾 Сессии агентов сохранены:', this.agentSessions);
        } catch (error) {
            console.error('❌ Ошибка сохранения сессий агентов:', error);
        }
    }

    getOrCreateSessionForAgent(agent_id) {
        if (!agent_id) {
            agent_id = 'default_agent';
        }

        if (this.agentSessions[agent_id]) {
            console.log(`🔄 Используем существующую сессию для ${agent_id}: ${this.agentSessions[agent_id]}`);
            return this.agentSessions[agent_id];
        }

        const newSession = generateUUID();
        this.agentSessions[agent_id] = newSession;
        this.saveAgentSessions();
        
        console.log(`🆕 Создана новая сессия для ${agent_id}: ${newSession}`);
        return newSession;
    }

    createNewSessionForAgent(agent_id) {
        if (!agent_id) {
            agent_id = 'default_agent';
        }

        const oldSession = this.agentSessions[agent_id];
        const newSession = generateUUID();
        this.agentSessions[agent_id] = newSession;
        this.saveAgentSessions();
        
        console.log(`🔄 Создана новая сессия для ${agent_id}: ${oldSession} → ${newSession}`);
        return newSession;
    }

    async updateChatHeader() {
        const title = document.getElementById('chat-widget-title');
        if (!title) return;

        if (!this.currentAgent) {
            title.textContent = 'Чат с агентом';
            this.updateInfoIcon(null);
            return;
        }

        try {
            const flowInfo = await this.getFlowInfo(this.currentAgent);
            if (flowInfo && flowInfo.name) {
                title.textContent = `Чат с ${flowInfo.name}`;
                this.updateInfoIcon(flowInfo.description);
            } else {
                const prettyName = this.extractPrettyName(this.currentAgent);
                title.textContent = `Чат с ${prettyName}`;
                this.updateInfoIcon(null);
            }
        } catch (error) {
            console.warn('Не удалось получить метаданные флоу:', error);
            const prettyName = this.extractPrettyName(this.currentAgent);
            title.textContent = `Чат с ${prettyName}`;
            this.updateInfoIcon(null);
        }
    }

    async getFlowInfo(flowId) {
        try {
            const response = await fetch(`/api/v1/flows/${encodeURIComponent(flowId)}/info`);
            if (response.ok) {
                return await response.json();
            }
        } catch (error) {
            console.warn('Ошибка получения информации о флоу:', error);
        }
        return null;
    }

    extractPrettyName(agentPath) {
        if (!agentPath) return 'Агент';
        
        const parts = agentPath.split('.');
        const lastPart = parts[parts.length - 1];
        
        let name = lastPart.replace(/_config$/, '').replace(/_/g, ' ');
        
        name = name.split(' ')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
            
        return name;
    }

    updateInfoIcon(description) {
        const infoBtn = document.getElementById('chat-widget-info');
        if (!infoBtn) return;

        if (description && description.trim()) {
            infoBtn.style.display = 'inline-block';
            infoBtn.title = description;
        } else {
            infoBtn.style.display = 'none';
            infoBtn.title = '';
        }
    }

    updateAgentsPanel() {
        const panel = document.getElementById('chat-agents-panel');
        if (!panel) return;

        const container = panel.querySelector('.d-flex');
        if (!container) return;

        container.innerHTML = '';

        this.activeAgents.forEach(agentId => {
            const tab = document.createElement('div');
            tab.className = `agent-tab ${agentId === this.currentAgent ? 'active' : ''}`;
            tab.dataset.agentId = agentId;
            
            tab.innerHTML = `
                <div class="agent-indicator"></div>
                <span>${agentId}</span>
            `;
            
            tab.addEventListener('click', async () => {
                await this.switchToAgent(agentId);
            });
            
            container.appendChild(tab);
        });

        console.log(`🔄 Панель агентов обновлена: ${this.activeAgents.size} активных агентов`);
    }

    async switchToAgent(agent_id) {
        if (agent_id === this.currentAgent) {
            return;
        }

        console.log(`🔄 Переключаемся с ${this.currentAgent} на ${agent_id}`);

        this.clearChatMessages();

        this.currentAgent = agent_id;
        this.currentSession = this.getOrCreateSessionForAgent(agent_id);

        await this.updateChatHeader();
        this.updateAgentsPanel();

        console.log(`✅ Переключились на агента ${agent_id}, сессия: ${this.currentSession}`);
    }

    toggleAgentsPanel() {
        const panel = document.getElementById('chat-agents-panel');
        if (!panel) return;

        const isVisible = panel.style.display !== 'none';
        panel.style.display = isVisible ? 'none' : 'block';
        
        console.log(`🔄 Панель агентов ${isVisible ? 'скрыта' : 'показана'}`);
    }

    showFlowInfo() {
        const infoBtn = document.getElementById('chat-widget-info');
        if (!infoBtn || !infoBtn.title) return;

        const modal = document.createElement('div');
        modal.style.cssText = `
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: rgba(0, 0, 0, 0.5);
            display: flex;
            align-items: center;
            justify-content: center;
            z-index: 10000;
        `;

        const content = document.createElement('div');
        content.style.cssText = `
            background: var(--chat-bg, #ffffff);
            color: var(--chat-input-text, #000000);
            padding: 20px;
            border-radius: 8px;
            max-width: 400px;
            max-height: 300px;
            overflow-y: auto;
            box-shadow: 0 4px 12px rgba(0, 0, 0, 0.3);
        `;

        content.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                <h4 style="margin: 0; color: var(--chat-input-text, #000000);">Информация о флоу</h4>
                <button id="close-info-modal" style="background: none; border: none; font-size: 20px; cursor: pointer; color: var(--chat-input-text, #000000);">&times;</button>
            </div>
            <p style="margin: 0; line-height: 1.5; color: var(--chat-input-text, #000000);">${infoBtn.title}</p>
        `;

        modal.appendChild(content);
        document.body.appendChild(modal);

        const closeBtn = content.querySelector('#close-info-modal');
        const closeModal = () => document.body.removeChild(modal);
        
        closeBtn.addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
                document.removeEventListener('keydown', handleEscape);
            }
        };
        document.addEventListener('keydown', handleEscape);
    }

    init() {
        console.log('🚀 Инициализация ChatManager...');
        
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        
        this.createChatContainer();
        this.bindEvents();
        
        this.connectWebSocket();
        
        this.startConnectionHealthCheck();
        
        console.log('✅ ChatManager инициализирован');
    }

    createChatContainer() {
        this.container = document.body;
        
        const widget = document.getElementById('chat-widget');
        if (!widget) {
            console.error('❌ Виджет чата не найден в DOM');
            return false;
        }
        
        console.log('✅ Виджет чата найден в DOM');
        return true;
    }

    bindEvents() {
        const toggle = document.getElementById('chat-widget-toggle');
        const fullscreen = document.getElementById('chat-widget-fullscreen');
        const minimize = document.getElementById('chat-widget-minimize');
        const close = document.getElementById('chat-widget-close');
        const agentsBtn = document.getElementById('chat-widget-agents');
        const infoBtn = document.getElementById('chat-widget-info');
        const commandsBtn = document.getElementById('chat-widget-commands');
        const attachBtn = document.getElementById('chat-widget-attach');
        const sendBtn = document.getElementById('chat-widget-send');
        const input = document.getElementById('chat-widget-input');
        const fileInput = document.getElementById('chat-file-input');

        toggle?.addEventListener('click', () => this.toggleChat());
        fullscreen?.addEventListener('click', () => this.toggleFullscreen());
        minimize?.addEventListener('click', () => this.minimizeChat());
        close?.addEventListener('click', () => this.closeChat());
        agentsBtn?.addEventListener('click', () => this.toggleAgentsPanel());
        infoBtn?.addEventListener('click', () => this.showFlowInfo());
        
        const connectionStatus = document.getElementById('chat-connection-status');
        connectionStatus?.addEventListener('click', () => {
            console.log('🔗 Клик на индикатор соединения, isConnected:', this.isConnected);
            if (!this.isConnected) {
                console.log('🔄 Запускаем принудительное переподключение...');
                this.forceReconnect();
            }
        });
        
        commandsBtn?.addEventListener('click', (e) => {
            e.preventDefault();
            e.stopPropagation();
            console.log('🔧 Клик по кнопке команд');
            this.toggleCommandsMenu();
        });
        attachBtn?.addEventListener('click', () => this.openFileDialog());
        sendBtn?.addEventListener('click', () => this.sendMessage());
        fileInput?.addEventListener('change', (e) => this.handleFileSelection(e));
        
        this.initVoiceRecording();

        document.addEventListener('click', (e) => {
            if (e.target.closest('.command-item')) {
                const command = e.target.closest('.command-item').dataset.command;
                this.executeCommand(command);
            }
            if (!e.target.closest('#chat-widget-commands') && !e.target.closest('#chat-commands-menu')) {
                this.hideCommandsMenu();
            }
            
            if (!e.target.closest('#chat-widget-agents') && !e.target.closest('#chat-agents-panel')) {
                const panel = document.getElementById('chat-agents-panel');
                if (panel && panel.style.display !== 'none') {
                    panel.style.display = 'none';
                }
            }
        });
        
        input?.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.sendMessage();
            }
        });

        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const widget = document.getElementById('chat-widget');
                if (widget && widget.classList.contains('fullscreen')) {
                    this.toggleFullscreen();
                }
            }
        });
        
        this.makeChatDraggable();
    }
    
    makeChatDraggable() {
        const widget = document.getElementById('chat-widget');
        const header = document.querySelector('.chat-widget-header');
        
        if (!widget || !header) return;
        
        let isDragging = false;
        let currentX;
        let currentY;
        let initialX;
        let initialY;
        
        header.addEventListener('mousedown', (e) => {
            if (e.target.closest('button')) return;
            
            if (widget.classList.contains('fullscreen')) return;
            
            isDragging = true;
            
            const rect = widget.getBoundingClientRect();
            initialX = e.clientX - rect.left;
            initialY = e.clientY - rect.top;
            
            widget.style.transition = 'none';
        });
        
        document.addEventListener('mousemove', (e) => {
            if (!isDragging) return;
            
            e.preventDefault();
            
            currentX = e.clientX - initialX;
            currentY = e.clientY - initialY;
            
            const maxX = window.innerWidth - widget.offsetWidth;
            const maxY = window.innerHeight - widget.offsetHeight;
            
            currentX = Math.max(0, Math.min(currentX, maxX));
            currentY = Math.max(0, Math.min(currentY, maxY));
            
            widget.style.left = currentX + 'px';
            widget.style.top = currentY + 'px';
            widget.style.right = 'auto';
            widget.style.bottom = 'auto';
        });
        
        document.addEventListener('mouseup', () => {
            if (isDragging) {
                isDragging = false;
                widget.style.transition = '';
            }
        });
    }

    async open(options = {}) {
        console.log('🔵 Открытие чата:', options);
        
        const {
            agent_id = null,
            session_id = null,
            user_id = 'current_user',
            initial_message = null,
            position = 'right',
            size = 'medium'
        } = options;

        if (agent_id) {
            this.activeAgents.add(agent_id);
        }

        this.currentAgent = agent_id;
        
        const existingSession = this.agentSessions[agent_id];
        console.log('🔍 Проверка существующей сессии:', {
            agent_id,
            existingSession,
            providedSessionId: session_id,
            allSessions: this.agentSessions
        });
        
        const isExistingSession = existingSession && !session_id;
        
        this.currentSession = session_id || this.getOrCreateSessionForAgent(agent_id);
        
        console.log('📋 Итоговая сессия:', {
            currentSession: this.currentSession,
            isExistingSession,
            willLoadHistory: isExistingSession
        });

        await this.updateChatHeader();
        this.updateAgentsPanel();

        this.showChat();

        this.connectWebSocket();

        if (isExistingSession) {
            console.log('📜 Загружаем историю для существующей сессии:', this.currentSession);
            await this.loadSessionHistory(this.currentSession);
        } else {
            console.log('🆕 Новая сессия или передан session_id, история не загружается');
        }

        if (initial_message) {
            setTimeout(() => {
                this.sendUserMessage(initial_message);
            }, 500);
        }
    }

    async openExistingSession(agent_id, session_id) {
        console.log('🔵 Открытие существующей сессии:', { agent_id, session_id });
        
        if (!agent_id || !session_id) {
            console.error('❌ Необходимы agent_id и session_id для открытия существующей сессии');
            return;
        }

        this.activeAgents.add(agent_id);
        this.currentAgent = agent_id;
        this.currentSession = session_id;

        this.agentSessions[agent_id] = session_id;
        this.saveAgentSessions();

        await this.updateChatHeader();
        this.updateAgentsPanel();

        this.showChat();

        this.connectWebSocket();

        await this.loadSessionHistory(session_id);
    }

    async loadSessionHistory(session_id) {
        try {
            console.log('📜 Загрузка истории для сессии:', session_id);
            
            let userId = 'unknown';
            try {
                const userResponse = await fetch('/api/v1/admin/me');
                if (userResponse.ok) {
                    const userData = await userResponse.json();
                    userId = userData.user_id;
                    console.log('✅ Получен user_id:', userId);
                } else {
                    console.warn('⚠️ Не удалось получить user_id, используем unknown');
                }
            } catch (e) {
                console.warn('⚠️ Ошибка получения user_id:', e);
            }
            
            // Проверяем формат session_id
            let fullSessionId;
            if (session_id.startsWith('web:') || session_id.startsWith('telegram:') || session_id.startsWith('whatsapp:')) {
                // session_id уже полный
                fullSessionId = session_id;
                console.log('✅ session_id уже полный:', fullSessionId);
            } else {
                // Добавляем префикс
                const flowId = this.currentAgent || 'unknown';
                fullSessionId = `web:${userId}:${flowId}:${session_id}`;
                console.log('🔍 Сформирован полный session_id:', fullSessionId);
            }
            
            const encodedSessionId = encodeURIComponent(fullSessionId);
            const response = await fetch(`/api/v1/history/sessions/${encodedSessionId}/messages?limit=100`);
            
            if (!response.ok) {
                throw new Error(`Ошибка загрузки истории: ${response.status}`);
            }

            const history = await response.json();
            await this.processHistory(history);
            
        } catch (error) {
            console.error('❌ Ошибка загрузки истории сессии:', error);
            this.addAgentMessage({
                content: 'Не удалось загрузить историю сообщений',
                timestamp: new Date().toISOString(),
                message_type: 'text'
            });
        }
    }
    
    async processHistory(history) {
        this.clearChatMessages();

        if (history.messages && history.messages.length > 0) {
            for (const msg of history.messages) {
                if (msg.role === 'user') {
                    this.addUserMessage(msg.content, msg.timestamp, `history_${msg.timestamp}`);
                } else if (msg.role === 'assistant') {
                    if (msg.content) {
                        this.addAgentMessage({
                            content: msg.content,
                            timestamp: msg.timestamp,
                            message_type: 'text',
                            message_id: `history_${msg.timestamp}`
                        });
                    }
                }
            }
            
            console.log(`✅ Загружено ${history.messages.length} сообщений из истории`);
        } else {
            console.log('📭 История сессии пуста');
        }
    }

    showChat() {
        const widget = document.getElementById('chat-widget');
        const toggle = document.getElementById('chat-widget-toggle');
        
        if (widget) {
            widget.style.display = 'flex';
            widget.classList.remove('minimized');
            this.isVisible = true;
        }
        
        if (toggle) {
            toggle.style.display = 'none';
        }
    }

    toggleChat() {
        if (this.isVisible) {
            this.closeChat();
        } else {
            this.showChat();
        }
    }

    minimizeChat() {
        const widget = document.getElementById('chat-widget');
        if (widget) {
            widget.classList.toggle('minimized');
        }
    }

    closeChat() {
        const widget = document.getElementById('chat-widget');
        const toggle = document.getElementById('chat-widget-toggle');
        
        if (widget) {
            widget.style.display = 'none';
            this.isVisible = false;
        }
        
        if (toggle) {
            toggle.style.display = 'block';
        }

        this.disconnectWebSocket();
    }

    toggleFullscreen() {
        const widget = document.getElementById('chat-widget');
        const fullscreenBtn = document.getElementById('chat-widget-fullscreen');
        const fullscreenIcon = fullscreenBtn?.querySelector('i');
        
        if (!widget) return;
        
        const isFullscreen = widget.classList.contains('fullscreen');
        
        if (isFullscreen) {
            widget.classList.remove('fullscreen');
            widget.style.left = '';
            widget.style.top = '';
            widget.style.right = '20px';
            widget.style.bottom = '80px';
            if (fullscreenIcon) {
                fullscreenIcon.className = 'bi bi-arrows-fullscreen';
            }
            if (fullscreenBtn) {
                fullscreenBtn.title = 'Развернуть на весь экран';
            }
        } else {
            widget.classList.add('fullscreen');
            widget.classList.remove('minimized');
            widget.style.left = '0';
            widget.style.top = '0';
            widget.style.right = '0';
            widget.style.bottom = '0';
            if (fullscreenIcon) {
                fullscreenIcon.className = 'bi bi-fullscreen-exit';
            }
            if (fullscreenBtn) {
                fullscreenBtn.title = 'Выйти из полноэкранного режима';
            }
        }
        
        setTimeout(() => {
            const messagesContainer = document.getElementById('chat-widget-messages');
            if (messagesContainer) {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
                messagesContainer.style.display = 'none';
                messagesContainer.offsetHeight;
                messagesContainer.style.display = '';
            }
        }, 150);
    }

    toggleCommandsMenu() {
        const menu = document.getElementById('chat-commands-menu');
        
        if (!menu) {
            console.error('❌ Меню команд не найдено в DOM');
            return;
        }

        const isVisible = menu.style.display === 'block';
        
        if (isVisible) {
            this.hideCommandsMenu();
        } else {
            this.showCommandsMenu();
        }
    }

    showCommandsMenu() {
        const menu = document.getElementById('chat-commands-menu');
        if (menu) {
            menu.style.display = 'block';
            console.log('✅ Меню команд показано');
        }
    }

    hideCommandsMenu() {
        const menu = document.getElementById('chat-commands-menu');
        if (menu) {
            menu.style.display = 'none';
        }
    }

    executeCommand(command) {
        console.log(`🔧 Выполняем команду: ${command}`);
        
        this.hideCommandsMenu();
        
        this.sendUserMessage(command);
    }

    openFileDialog() {
        const fileInput = document.getElementById('chat-file-input');
        if (fileInput) {
            fileInput.click();
        }
    }

    async handleFileSelection(event) {
        const files = event.target.files;
        if (!files || files.length === 0) return;

        console.log(`📎 Выбрано файлов: ${files.length}`);
        
        this.showFilePreview(Array.from(files));
        
        event.target.value = '';
    }

    showFilePreview(files) {
        const previewContainer = document.getElementById('chat-files-preview');
        if (!previewContainer) return;

        previewContainer.style.display = 'block';
        
        previewContainer.innerHTML = `
            <div class="file-preview-header">
                <span>📎 ${files.length} файл${files.length > 1 ? 'а' : ''}</span>
                <button class="file-preview-cancel" onclick="window.app.chat.clearFilePreview()">
                    <i class="bi bi-x"></i>
                </button>
            </div>
            <div class="file-preview-list">
                ${files.map(file => `
                    <div class="file-preview-item">
                        <i class="bi bi-file-earmark"></i>
                        <span class="file-name">${file.name}</span>
                        <span class="file-size">${formatFileSize(file.size)}</span>
                    </div>
                `).join('')}
            </div>
        `;
        
        this.selectedFiles = files;
        
        const input = document.getElementById('chat-widget-input');
        if (input) {
            input.placeholder = `Сообщение с ${files.length} файл${files.length > 1 ? 'ами' : 'ом'}...`;
        }
    }

    clearFilePreview() {
        const previewContainer = document.getElementById('chat-files-preview');
        if (previewContainer) {
            previewContainer.style.display = 'none';
            previewContainer.innerHTML = '';
        }
        
        const input = document.getElementById('chat-widget-input');
        if (input) {
            input.placeholder = 'Введите сообщение...';
        }
        
        this.selectedFiles = null;
    }

    async sendMessageWithFiles(message) {
        if (!this.selectedFiles || this.selectedFiles.length === 0) {
            console.error('❌ Нет выбранных файлов для отправки');
            return;
        }

        console.log(`📎 Отправляем сообщение с ${this.selectedFiles.length} файлами:`, this.selectedFiles);

        const filesData = [];
        for (const file of this.selectedFiles) {
            try {
                console.log(`📎 Конвертируем файл: ${file.name} (${formatFileSize(file.size)})`);
                const base64Content = await fileToBase64(file);
                filesData.push({
                    name: file.name,
                    content: base64Content,
                    content_type: file.type,
                    size: file.size
                });
                console.log(`✅ Файл ${file.name} сконвертирован`);
            } catch (error) {
                console.error(`❌ Ошибка конвертации файла ${file.name}:`, error);
            }
        }
        
        console.log(`📎 Итого сконвертировано ${filesData.length} из ${this.selectedFiles.length} файлов`);

        if (this.isConnected && filesData.length > 0) {
            const wsMessage = {
                type: 'USER_MESSAGE',
                data: {
                    message: message,
                    files: filesData,
                    agent_id: this.currentAgent,
                    session_id: this.currentSession
                }
            };
            
            this.websocket.send(JSON.stringify(wsMessage));
            console.log(`✅ Отправлено сообщение с ${filesData.length} файлами`);
        }
    }

    updateConnectionStatus(status) {
        const indicator = document.querySelector('.connection-indicator');
        if (!indicator) return;

        indicator.classList.remove('connected', 'connecting', 'disconnected', 'reconnecting');
        
        indicator.classList.add(status);
        
        const statusContainer = document.getElementById('chat-connection-status');
        if (statusContainer) {
            const statusText = {
                'connected': 'Подключено',
                'connecting': 'Подключение...',
                'disconnected': 'Отключено',
                'reconnecting': 'Переподключение...'
            };
            statusContainer.title = statusText[status] || 'Неизвестно';
        }
        
        console.log(`🔗 Статус соединения: ${status}`);
    }

    connectWebSocket() {
        if (this.websocket && this.websocket.readyState === WebSocket.OPEN) {
            console.log('🔗 WebSocket уже подключен');
            return;
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/frontend/chat/ws/chat`;
        
        console.log('🔌 Подключение к WebSocket:', wsUrl);
        this.updateConnectionStatus('connecting');

        this.websocket = new WebSocket(wsUrl);

        this.websocket.onopen = () => {
            console.log('✅ WebSocket подключен');
            this.isConnected = true;
            this.isReconnecting = false;
            this.reconnectAttempts = 0;
            this.reconnectDelay = 1000;
            this.updateConnectionStatus('connected');
        };

        this.websocket.onmessage = (event) => {
            try {
                const message = JSON.parse(event.data);
                this.handleWebSocketMessage(message);
            } catch (error) {
                console.error('❌ Ошибка парсинга сообщения:', error);
            }
        };

        this.websocket.onclose = (event) => {
            console.log(`❌ WebSocket отключен (код: ${event.code})`);
            this.isConnected = false;
            this.updateConnectionStatus('disconnected');
            
            if (!this.isReconnecting && this.reconnectAttempts < this.maxReconnectAttempts) {
                console.log('✅ Запускаем автоматическое переподключение');
                this.scheduleReconnect();
            } else {
                setTimeout(() => {
                    if (!this.isConnected) {
                        this.reconnectAttempts = 0;
                        this.isReconnecting = false;
                    }
                }, 30000);
            }
        };

        this.websocket.onerror = (error) => {
            console.error('❌ WebSocket ошибка:', error);
            this.isConnected = false;
            this.isReconnecting = false;
            this.updateConnectionStatus('disconnected');
        };
    }

    scheduleReconnect() {
        if (this.isReconnecting) return;
        
        this.isReconnecting = true;
        this.reconnectAttempts++;
        
        console.log(`🔄 Планируем переподключение #${this.reconnectAttempts} через ${this.reconnectDelay}ms`);
        this.updateConnectionStatus('reconnecting');
        
        setTimeout(() => {
            if (this.reconnectAttempts <= this.maxReconnectAttempts) {
                console.log(`🔄 Попытка переподключения #${this.reconnectAttempts}`);
                this.connectWebSocket();
                
                this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 10000);
            } else {
                console.error('❌ Превышено максимальное количество попыток переподключения');
                this.isReconnecting = false;
                this.updateConnectionStatus('disconnected');
            }
        }, this.reconnectDelay);
    }

    forceReconnect() {
        console.log('🔄 Принудительное переподключение...');
        
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.isReconnecting = false;
        this.isConnected = false;
        
        if (this.websocket) {
            this.websocket.onclose = null;
            this.websocket.close();
            this.websocket = null;
        }
        
        console.log('🔄 Состояние сброшено, подключаемся заново...');
        
        setTimeout(() => {
            this.connectWebSocket();
        }, 500);
    }

    startConnectionHealthCheck() {
        setInterval(() => {
            if (this.websocket) {
                if (this.websocket.readyState === WebSocket.OPEN && this.isConnected) {
                    try {
                        this.websocket.send(JSON.stringify({type: 'PING'}));
                    } catch (error) {
                        console.error('❌ Ошибка отправки ping:', error);
                    }
                }
            } else if (!this.isReconnecting && !this.isConnected) {
                console.log('🔍 Нет WebSocket соединения, подключаемся...');
                this.connectWebSocket();
            }
        }, 15000);
    }

    disconnectWebSocket() {
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
            this.isConnected = false;
        }
    }

    handleWebSocketMessage(message) {
        console.log('📨 Получено сообщение:', message);

        switch (message.type) {
            case 'USER_MESSAGE':
                this.addUserMessage(message.content, message.timestamp, message.message_id);
                break;
            case 'AGENT_MESSAGE':
                this.showTypingIndicator(false);
                this.addAgentMessage(message.data);
                break;
            case 'AGENT_INTERRUPT':
                this.showTypingIndicator(false);
                this.handleAgentInterrupt(message.data);
                break;
            case 'AGENT_TYPING':
                console.log('💬 Получено AGENT_TYPING уведомление:', message.data);
                this.showTypingIndicator(message.data.is_typing);
                break;
            case 'CLEAR_CHAT':
                console.log('🧹 Получена команда очистки чата');
                this.clearChatMessages();
                
                if (this.currentAgent) {
                    const oldSession = this.currentSession;
                    this.currentSession = this.createNewSessionForAgent(this.currentAgent);
                    console.log(`🔄 Сессия для агента ${this.currentAgent} обновлена: ${oldSession} → ${this.currentSession}`);
                }
                
                this.addAgentMessage({
                    content: message.data.message,
                    timestamp: message.data.timestamp,
                    message_type: 'text'
                });
                break;
            case 'ERROR':
                this.showError(message.data.message);
                break;
            case 'PONG':
                break;
        }
    }

    async sendMessage() {
        const input = document.getElementById('chat-widget-input');
        const message = input?.value?.trim() || '';
        
        if (!message && (!this.selectedFiles || this.selectedFiles.length === 0)) {
            return;
        }

        if (this.selectedFiles && this.selectedFiles.length > 0) {
            await this.sendMessageWithFiles(message);
        } else {
            this.sendUserMessage(message);
        }
        
        if (input) input.value = '';
        
        this.clearFilePreview();
    }

    sendUserMessage(message) {
        if (this.isConnected) {
            const wsMessage = {
                type: 'USER_MESSAGE',
                data: {
                    message: message,
                    agent_id: this.currentAgent,
                    session_id: this.currentSession
                }
            };
            this.websocket.send(JSON.stringify(wsMessage));
        }
    }

    addUserMessage(message, timestamp = null, messageId = null) {
        const messageObj = {
            type: MESSAGE_TYPES.TEXT,
            content: message,
            sender: 'user',
            timestamp: timestamp ? new Date(timestamp) : new Date(),
            message_id: messageId || `user_${Date.now()}`
        };
        
        this.addMessageToUI(messageObj);
    }

    addAgentMessage(data) {
        const messageObj = {
            type: data.message_type || MESSAGE_TYPES.TEXT,
            content: data.content,
            sender: 'agent',
            timestamp: new Date(data.timestamp),
            message_id: data.message_id || `agent_${Date.now()}`,
            attachments: data.attachments || [],
            buttons: data.buttons || [],
            form: data.form || null
        };
        
        this.addMessageToUI(messageObj);
    }

    addMessageToUI(messageObj) {
        const messagesContainer = document.getElementById('chat-widget-messages');
        if (!messagesContainer) return;

        if (messageObj.message_id) {
            const existingMessage = messagesContainer.querySelector(`[data-message-id="${messageObj.message_id}"]`);
            if (existingMessage) {
                console.log(`⚠️ Сообщение ${messageObj.message_id} уже отображено, пропускаем`);
                return;
            }
        }

        const messageElement = this.messageRenderer.renderMessage(messageObj);
        
        if (messageObj.message_id) {
            messageElement.setAttribute('data-message-id', messageObj.message_id);
        }
        
        messagesContainer.appendChild(messageElement);

        setTimeout(() => {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }, 10);

        this.messageHistory.push(messageObj);
    }

    handleAgentInterrupt(data) {
        console.log('🟡 Агент запросил ввод:', data.question);
        
        this.addAgentMessage({
            content: data.question,
            message_type: MESSAGE_TYPES.TEXT
        });
    }

    showTypingIndicator(isTyping) {
        const messagesContainer = document.getElementById('chat-widget-messages');
        let typingIndicator = document.getElementById('chat-typing-indicator');
        
        if (!messagesContainer) {
            console.error('❌ Контейнер сообщений не найден');
            return;
        }
        
        if (isTyping) {
            if (!typingIndicator) {
                typingIndicator = document.createElement('div');
                typingIndicator.id = 'chat-typing-indicator';
                typingIndicator.className = 'chat-typing-indicator';
                typingIndicator.innerHTML = `
                    <div class="chat-message agent typing-message">
                        <span class="typing-text">Печатает</span>
                        <div class="typing-dots">
                            <span></span>
                            <span></span>
                            <span></span>
                        </div>
                    </div>
                `;
                messagesContainer.appendChild(typingIndicator);
            }
            
            typingIndicator.style.display = 'block';
            
            setTimeout(() => {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }, 10);
        } else {
            if (typingIndicator) {
                typingIndicator.remove();
            }
        }
    }

    clearChatMessages() {
        const messagesContainer = document.getElementById('chat-widget-messages');
        if (messagesContainer) {
            messagesContainer.innerHTML = '';
            console.log('🧹 Сообщения чата очищены');
        }
        
        this.messageHistory = [];
        
        this.showTypingIndicator(false);
    }

    showError(message) {
        if (this.app && this.app.showNotification) {
            this.app.showNotification(message, 'danger');
        }
    }

    initVoiceRecording() {
        const voiceBtn = document.getElementById('chat-voice-btn') || document.getElementById('chat-widget-voice');
        const indicator = document.getElementById('voice-recording-indicator') || document.getElementById('voice-recording-indicator-widget');
        
        if (!voiceBtn) {
            console.log('⚠️ Кнопка микрофона не найдена');
            return;
        }

        console.log('🎤 Инициализация кнопки микрофона:', voiceBtn.id);

        voiceBtn.addEventListener('mousedown', async (e) => {
            e.preventDefault();
            const success = await this.voiceRecorder.startRecording();
            if (success) {
                if (indicator) indicator.style.display = 'block';
                voiceBtn.classList.add('recording');
            }
        });

        voiceBtn.addEventListener('mouseup', async (e) => {
            e.preventDefault();
            await this.handleVoiceRecordingStop(voiceBtn, indicator);
        });

        voiceBtn.addEventListener('mouseleave', async (e) => {
            if (this.voiceRecorder.isRecording) {
                await this.handleVoiceRecordingStop(voiceBtn, indicator);
            }
        });

        voiceBtn.addEventListener('touchstart', async (e) => {
            e.preventDefault();
            const success = await this.voiceRecorder.startRecording();
            if (success) {
                if (indicator) indicator.style.display = 'block';
                voiceBtn.classList.add('recording');
            }
        });

        voiceBtn.addEventListener('touchend', async (e) => {
            e.preventDefault();
            await this.handleVoiceRecordingStop(voiceBtn, indicator);
        });
    }

    async handleVoiceRecordingStop(voiceBtn, indicator) {
        if (!this.voiceRecorder.isRecording) return;

        try {
            const { blob, mimeType } = await this.voiceRecorder.stopRecording();
            
            if (indicator) indicator.style.display = 'none';
            if (voiceBtn) voiceBtn.classList.remove('recording');

            if (blob.size < 1000) {
                this.app.showNotification('Запись слишком короткая', 'warning');
                return;
            }

            let extension = 'webm';
            let finalMimeType = mimeType;
            
            if (mimeType.includes('ogg')) {
                extension = 'ogg';
                if (mimeType === 'audio/ogg' || mimeType === 'audio/ogg;') {
                    finalMimeType = 'audio/ogg; codecs=opus';
                }
            } else if (mimeType.includes('wav')) {
                extension = 'wav';
                finalMimeType = 'audio/wave';
            } else if (mimeType.includes('webm')) {
                extension = 'webm';
            }
            
            const timestamp = new Date().toISOString().replace(/[:.]/g, '-');
            const audioFile = new File([blob], `voice-${timestamp}.${extension}`, {
                type: finalMimeType
            });

            console.log('🎤 Голосовое сообщение записано:', {
                fileName: audioFile.name,
                originalMime: mimeType,
                finalMime: finalMimeType,
                size: blob.size
            });

            this.showFilePreview([audioFile]);
            
        } catch (error) {
            console.error('❌ Ошибка обработки голосового сообщения:', error);
            if (indicator) indicator.style.display = 'none';
            if (voiceBtn) voiceBtn.classList.remove('recording');
            this.app.showNotification('Ошибка записи голоса: ' + error.message, 'danger');
        }
    }
}

export default ChatManager;

