/**
 * Chat Manager - управление чатом
 */

import VoiceRecorder from '/static/js/chat/voice-recorder.js';
import ChatMessageRenderer, { MESSAGE_TYPES } from '/static/js/chat/message-renderer.js';
import CheckpointInspector from '/static/js/components/checkpoint-inspector.js';
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
        this.checkpointInspector = new CheckpointInspector(app, this);
        this.selectedFiles = null;
        this.embedToken = null; // Токен для встроенного чата
        this.isEmbedded = false; // Флаг для режима встраивания
        
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.maxReconnectAttempts = 5;
    }

    isMobileDevice() {
        return window.innerWidth <= 768;
    }

    handleResize() {
        if (!this.isVisible) return;
        
        const widget = document.getElementById('chat-widget');
        
        if (!widget) return;
        
        if (this.isMobileDevice() && !this.isEmbedded) {
            widget.classList.add('fullscreen');
            widget.classList.remove('minimized');
        }
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

    getDefaultAgent() {
        const DEFAULT_FAQ_FLOW_ID = 'app.flows.faq_flow.faq_flow_config';
        
        const customDefault = localStorage.getItem('default_agent_id');
        if (customDefault) {
            console.log('📦 Используем кастомный дефолтный агент:', customDefault);
            return customDefault;
        }

        console.log('✅ Используем дефолтный FAQ агент:', DEFAULT_FAQ_FLOW_ID);
        return DEFAULT_FAQ_FLOW_ID;
    }

    setDefaultAgent(agent_id) {
        if (agent_id) {
            localStorage.setItem('default_agent_id', agent_id);
            console.log('✅ Установлен дефолтный агент:', agent_id);
        }
    }

    clearDefaultAgentCache() {
        localStorage.removeItem('default_agent_id');
        console.log('🗑️ Кеш дефолтного агента очищен');
    }

    saveChatPosition(x, y) {
        try {
            const position = { x, y };
            localStorage.setItem('chat_position', JSON.stringify(position));
            console.log('💾 Позиция чата сохранена:', position);
        } catch (error) {
            console.error('❌ Ошибка сохранения позиции чата:', error);
        }
    }

    loadChatPosition() {
        try {
            const saved = localStorage.getItem('chat_position');
            if (saved) {
                const position = JSON.parse(saved);
                console.log('📦 Загружена сохраненная позиция чата:', position);
                return position;
            }
        } catch (error) {
            console.error('❌ Ошибка загрузки позиции чата:', error);
        }
        return null;
    }

    applyChatPosition() {
        const widget = document.getElementById('chat-widget');
        if (!widget) return;

        // Если чат в fullscreen режиме - не применяем сохраненную позицию
        if (widget.classList.contains('fullscreen')) {
            return;
        }

        const savedPosition = this.loadChatPosition();
        if (savedPosition && typeof savedPosition.x === 'number' && typeof savedPosition.y === 'number') {
            const { x, y } = savedPosition;
            
            // Ждем пока виджет отрисуется, чтобы получить его размеры
            setTimeout(() => {
                const rect = widget.getBoundingClientRect();
                const widgetWidth = rect.width || widget.offsetWidth || 380;
                const widgetHeight = rect.height || widget.offsetHeight || 520;
                
                // Проверяем, что позиция не выходит за границы экрана
                const maxX = window.innerWidth - widgetWidth;
                const maxY = window.innerHeight - widgetHeight;
                
                const validX = Math.max(0, Math.min(x, maxX));
                const validY = Math.max(0, Math.min(y, maxY));
                
                if (!isNaN(validX) && !isNaN(validY)) {
                    widget.style.left = validX + 'px';
                    widget.style.top = validY + 'px';
                    widget.style.right = 'auto';
                    widget.style.bottom = 'auto';
                    
                    console.log('📍 Применена сохраненная позиция чата:', { x: validX, y: validY });
                } else {
                    console.warn('⚠️ Некорректная сохраненная позиция, используем дефолтную');
                    this.resetChatPosition();
                }
            }, 10);
        } else {
            // Если нет сохраненной позиции или она некорректная - используем дефолтную
            this.resetChatPosition();
        }
    }
    
    resetChatPosition() {
        const widget = document.getElementById('chat-widget');
        if (!widget) return;
        
        // Удаляем некорректную позицию из localStorage
        try {
            localStorage.removeItem('chat_position');
            console.log('🗑️ Некорректная позиция удалена из localStorage');
        } catch (error) {
            console.warn('⚠️ Не удалось удалить позицию из localStorage:', error);
        }
        
        // Сбрасываем на дефолтную позицию (right: 20px, bottom: 80px)
        widget.style.left = 'auto';
        widget.style.top = 'auto';
        widget.style.right = '20px';
        widget.style.bottom = '80px';
        
        console.log('📍 Позиция чата сброшена на дефолтную');
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
            const response = await fetch(`/frontend/api/flows/${encodeURIComponent(flowId)}/info`);
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
        this.updateInputState();
        this.updateInspectButton();

        console.log(`✅ Переключились на агента ${agent_id}, сессия: ${this.currentSession}`);
    }

    updateInspectButton() {
        const inspectBtn = document.getElementById('chat-widget-inspect');
        if (!inspectBtn) {
            console.warn('⚠️ Кнопка inspect не найдена в DOM');
            return;
        }
        
        console.log('🔍 updateInspectButton:', {
            currentSession: this.currentSession,
            currentAgent: this.currentAgent,
            hasSession: !!this.currentSession
        });
        
        if (this.currentSession) {
            inspectBtn.classList.remove('hidden');
            inspectBtn.style.display = '';
            inspectBtn.disabled = false;
            console.log('✅ Кнопка inspect показана');
        } else {
            inspectBtn.classList.add('hidden');
            inspectBtn.style.display = 'none';
            inspectBtn.disabled = true;
            console.log('❌ Кнопка inspect скрыта - нет сессии');
        }
    }

    updateInputState() {
        const input = document.getElementById('chat-widget-input');
        const sendBtn = document.getElementById('chat-widget-send');
        const attachBtn = document.getElementById('chat-widget-attach');
        const voiceBtn = document.getElementById('chat-widget-voice');
        
        if (!input) return;
        
        // Проверяем, это сессия другой каналы?
        const isReadOnly = this.currentSession && 
                          this.currentSession.includes(':') && 
                          !this.currentSession.startsWith('web:');
        
        if (isReadOnly) {
            const platform = this.currentSession.split(':')[0];
            input.disabled = true;
            input.placeholder = `Сессия каналы "${platform}" (только просмотр)`;
            
            if (sendBtn) sendBtn.disabled = true;
            if (attachBtn) attachBtn.disabled = true;
            if (voiceBtn) voiceBtn.disabled = true;
            
            console.log(`🔒 Поле ввода заблокировано для каналы ${platform}`);
        } else {
            input.disabled = false;
            input.placeholder = 'Введите сообщение...';
            
            if (sendBtn) sendBtn.disabled = false;
            if (attachBtn) attachBtn.disabled = false;
            if (voiceBtn) voiceBtn.disabled = false;
            
            console.log('🔓 Поле ввода разблокировано');
        }
    }

    toggleAgentsPanel() {
        const panel = document.getElementById('chat-agents-panel');
        if (!panel) return;

        const isVisible = !panel.classList.contains('hidden');
        if (isVisible) {
            panel.classList.add('hidden');
            panel.style.display = 'none';
        } else {
            panel.classList.remove('hidden');
            panel.style.display = 'block';
        }
        
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
        const popup = document.getElementById('chat-widget-popup');
        const inspectBtn = document.getElementById('chat-widget-inspect');
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
        popup?.addEventListener('click', () => this.openInNewWindow());
        inspectBtn?.addEventListener('click', () => this.checkpointInspector.showInspector(this.currentSession));
        agentsBtn?.addEventListener('click', () => this.toggleAgentsPanel());
        infoBtn?.addEventListener('click', () => this.showFlowInfo());
        
        window.addEventListener('resize', () => this.handleResize());
        
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
                if (panel && !panel.classList.contains('hidden')) {
                    panel.classList.add('hidden');
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
                if (this.isMobileDevice()) return;
                
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
            
            if (this.isMobileDevice()) return;
            
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
                
                // Сохраняем позицию чата в localStorage
                this.saveChatPosition(currentX, currentY);
            }
        });
    }

    async open(options = {}) {
        console.log('🔵 Открытие чата:', options);
        
        let {
            agent_id = null,
            session_id = null,
            user_id = 'current_user',
            initial_message = null,
            position = 'right',
            size = 'medium'
        } = options;

        if (!agent_id) {
            agent_id = this.getDefaultAgent();
            console.log('📌 Агент не выбран, используем дефолтный FAQ агент:', agent_id);
        }

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
        
        let isExistingSession = false;
        let sessionToUse = session_id;
        
        if (!session_id && existingSession) {
            if (existingSession.startsWith('web:') || !existingSession.includes(':')) {
                sessionToUse = existingSession;
                isExistingSession = true;
                console.log('✅ Используем существующую web-сессию:', sessionToUse);
            } else {
                const platform = existingSession.split(':')[0];
                console.log(`⚠️ Последняя сессия для агента ${agent_id} - платформа ${platform}. Создаём новую web-сессию.`);
                sessionToUse = this.createNewSessionForAgent(agent_id);
                isExistingSession = false;
            }
        }
        
        this.currentSession = sessionToUse || this.getOrCreateSessionForAgent(agent_id);
        
        console.log('📋 Итоговая сессия:', {
            currentSession: this.currentSession,
            isExistingSession,
            willLoadHistory: isExistingSession
        });

        await this.updateChatHeader();
        this.updateAgentsPanel();
        this.updateInputState();
        this.updateInspectButton();

        this.showChat();

        this.connectWebSocket();

        if (isExistingSession) {
            console.log('📜 Загружаем историю для существующей web-сессии:', this.currentSession);
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
        this.updateInputState();
        this.updateInspectButton();

        this.showChat();

        this.connectWebSocket();

        await this.loadSessionHistory(session_id);
    }

    async loadSessionHistory(session_id) {
        try {
            console.log('📜 Загрузка истории для сессии:', session_id);
            
            let userId = 'unknown';
            try {
                const userResponse = await fetch('/frontend/api/admin/me');
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
            if (session_id.includes(':')) {
                // session_id уже полный (содержит канал)
                fullSessionId = session_id;
                console.log('✅ session_id уже полный:', fullSessionId);
            } else {
                // Добавляем префикс web
                const flowId = this.currentAgent || 'unknown';
                fullSessionId = `web:${userId}:${flowId}:${session_id}`;
                console.log('🔍 Сформирован полный session_id:', fullSessionId);
            }
            
            const encodedSessionId = encodeURIComponent(fullSessionId);
            const response = await fetch(`/frontend/api/history/sessions/${encodedSessionId}/messages?limit=100`);
            
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
        
        if (!widget) {
            console.error('❌ Виджет чата не найден в DOM');
            return;
        }
        
        console.log('🔵 showChat() вызван');
        console.log('📋 Состояние виджета до изменений:', {
            hasHidden: widget.classList.contains('hidden'),
            hasWidgetMode: widget.classList.contains('widget-mode'),
            hasMinimized: widget.classList.contains('minimized'),
            display: window.getComputedStyle(widget).display,
            visibility: window.getComputedStyle(widget).visibility,
            opacity: window.getComputedStyle(widget).opacity,
            zIndex: window.getComputedStyle(widget).zIndex
        });
        
        widget.classList.remove('hidden');
        widget.classList.remove('widget-mode');
        widget.classList.remove('minimized');
        this.isVisible = true;
        
        if (this.isMobileDevice() && !this.isEmbedded) {
            widget.classList.add('fullscreen');
        }
        
        console.log('📋 Состояние виджета после изменений:', {
            hasHidden: widget.classList.contains('hidden'),
            hasWidgetMode: widget.classList.contains('widget-mode'),
            hasMinimized: widget.classList.contains('minimized'),
            display: window.getComputedStyle(widget).display,
            visibility: window.getComputedStyle(widget).visibility,
            opacity: window.getComputedStyle(widget).opacity,
            zIndex: window.getComputedStyle(widget).zIndex,
            position: window.getComputedStyle(widget).position,
            top: window.getComputedStyle(widget).top,
            right: window.getComputedStyle(widget).right,
            bottom: window.getComputedStyle(widget).bottom,
            left: window.getComputedStyle(widget).left,
            width: window.getComputedStyle(widget).width,
            height: window.getComputedStyle(widget).height
        });
        
        if (toggle) {
            toggle.style.display = 'none';
        }
        
        // Применяем сохраненную позицию чата
        this.applyChatPosition();
        
        // Финальная проверка видимости через небольшую задержку
        setTimeout(() => {
            const finalDisplay = window.getComputedStyle(widget).display;
            const finalVisibility = window.getComputedStyle(widget).visibility;
            const rect = widget.getBoundingClientRect();
            const computedLeft = window.getComputedStyle(widget).left;
            const computedTop = window.getComputedStyle(widget).top;
            const computedRight = window.getComputedStyle(widget).right;
            const computedBottom = window.getComputedStyle(widget).bottom;
            
            const isVisible = rect.width > 0 && rect.height > 0 && 
                            rect.top >= -rect.height && rect.left >= -rect.width && 
                            rect.top < window.innerHeight && rect.left < window.innerWidth;
            
            console.log('✅ Финальная проверка видимости чата:', {
                display: finalDisplay,
                visibility: finalVisibility,
                position: {
                    left: computedLeft,
                    top: computedTop,
                    right: computedRight,
                    bottom: computedBottom
                },
                rect: {
                    top: rect.top,
                    left: rect.left,
                    width: rect.width,
                    height: rect.height,
                    visible: isVisible
                },
                viewport: {
                    width: window.innerWidth,
                    height: window.innerHeight
                }
            });
            
            if (finalDisplay === 'none') {
                console.error('❌ Чат все еще скрыт через display: none! Принудительно устанавливаем display: flex');
                widget.style.display = 'flex';
            }
            
            // Проверяем, не находится ли чат за пределами экрана
            if (!isVisible && finalDisplay !== 'none') {
                console.warn('⚠️ Чат находится вне видимой области! Сбрасываем позицию на дефолтную.');
                this.resetChatPosition();
            }
        }, 100);
        
        if (!this.currentAgent) {
            console.log('📌 Чат открывается без агента, автоматически выбираем дефолтный');
            this.open({});
        }
    }

    toggleChat() {
        console.log('🔄 toggleChat() вызван, isVisible:', this.isVisible);
        if (this.isVisible) {
            this.closeChat();
        } else {
            this.showChat();
        }
    }

    minimizeChat() {
        if (this.isMobileDevice() && !this.isEmbedded) {
            return;
        }
        
        const widget = document.getElementById('chat-widget');
        if (widget) {
            widget.classList.toggle('minimized');
        }
    }

    closeChat() {
        // Отправляем сообщение родительскому окну, чтобы оно могло закрыть модалку
        console.log('🚀 Отправка postMessage для закрытия чата');
        parent.postMessage({ action: 'closeChatModal' }, '*');

        const widget = document.getElementById('chat-widget');
        const toggle = document.getElementById('chat-widget-toggle');
        
        if (widget) {
            widget.classList.add('hidden');
            this.isVisible = false;
        }
        
        if (toggle) {
            toggle.style.display = 'block';
        }

        this.disconnectWebSocket();
    }


    openInNewWindow() {
        // Получаем JWT токен из куки auth_token
        const token = this.getCookie('auth_token');
        if (!token) {
            console.error('❌ JWT токен не найден в куки. Необходимо авторизоваться.');
            alert('Необходимо авторизоваться для открытия чата в отдельном окне.');
            return;
        }

        // Получаем текущие параметры
        const flowId = this.currentAgent || 'default_flow';
        const sessionId = this.currentSession;
        
        // Формируем URL для отдельной страницы
        let embedUrl = `/frontend/chat/embed?token=${encodeURIComponent(token)}&flow_id=${encodeURIComponent(flowId)}`;
        
        if (sessionId) {
            embedUrl += `&session_id=${encodeURIComponent(sessionId)}`;
        }

        // Открываем в новом окне
        const newWindow = window.open(
            embedUrl,
            'chat_popup',
            'width=500,height=700,scrollbars=yes,resizable=yes,toolbar=no,menubar=no,location=no,status=no'
        );
        
        if (newWindow) {
            newWindow.focus();
            console.log('✅ Чат открыт в отдельном окне');
        } else {
            console.warn('⚠️ Не удалось открыть новое окно (возможно заблокировано браузером)');
            // Fallback: открываем в той же вкладке
            window.open(embedUrl, '_blank');
        }
    }

    getCookie(name) {
        const value = `; ${document.cookie}`;
        const parts = value.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
        return null;
    }

    toggleFullscreen() {
        if (this.isMobileDevice() && !this.isEmbedded) {
            return;
        }
        
        const widget = document.getElementById('chat-widget');
        const fullscreenBtn = document.getElementById('chat-widget-fullscreen');
        const fullscreenIcon = fullscreenBtn?.querySelector('i');
        
        if (!widget) return;
        
        const isFullscreen = widget.classList.contains('fullscreen');
        
        if (isFullscreen) {
            widget.classList.remove('fullscreen');

            if (this.isEmbedded) {
                widget.style.left = '';
                widget.style.top = '';
                widget.style.right = '';
                widget.style.bottom = '';
            } else {
                widget.style.left = '';
                widget.style.top = '';
                widget.style.right = '20px';
                widget.style.bottom = '80px';
                // Применяем сохраненную позицию при выходе из полноэкранного режима
                this.applyChatPosition();
            }
            
            if (fullscreenIcon) {
                fullscreenIcon.className = 'ti ti-maximize';
            }
            if (fullscreenBtn) {
                fullscreenBtn.title = 'Развернуть на весь экран';
            }
        } else {
            widget.classList.add('fullscreen');
            widget.classList.remove('minimized');

            if (this.isEmbedded) {
                widget.style.left = '';
                widget.style.top = '';
                widget.style.right = '';
                widget.style.bottom = '';
            } else {
                widget.style.left = '0';
                widget.style.top = '0';
                widget.style.right = '0';
                widget.style.bottom = '0';
            }
            if (fullscreenIcon) {
                fullscreenIcon.className = 'ti ti-minimize';
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
            menu.classList.remove('hidden');
            menu.style.display = 'block';
            console.log('✅ Меню команд показано');
        }
    }

    hideCommandsMenu() {
        const menu = document.getElementById('chat-commands-menu');
        if (menu) {
            menu.classList.add('hidden');
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

        previewContainer.classList.remove('hidden');
        previewContainer.style.display = '';

        const maxVisible = 3;
        const extra = Math.max(0, files.length - maxVisible);
        const visibleFiles = files.slice(0, maxVisible);

        const chips = visibleFiles.map((file, idx) => {
            const base = (file.name || '').split('.')[0] || '';
            const short = base.length > 5 ? base.slice(0, 5) + '…' : base;
            return `
            <div class="file-preview-item" title="${file.name}">
                <i class="ti ti-file"></i>
                <span class="file-name">${short}</span>
                <button class="file-preview-remove" onclick="window.app.chat.removeFileAt(${idx})" aria-label="Удалить">✕</button>
            </div>`;
        }).join('');

        const moreChip = extra > 0 ? `<div class="file-preview-item more" title="ещё ${extra}">+${extra}</div>` : '';

        previewContainer.innerHTML = `<div class="file-preview-list">${chips}${moreChip}</div>`;

        // Подвешиваем обработчики удаления без inline onclick
        const removeButtons = previewContainer.querySelectorAll('.file-preview-remove');
        removeButtons.forEach((btn, idx) => {
            btn.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                this.removeFileAt(idx);
            });
        });

        this.selectedFiles = files;

        const input = document.getElementById('chat-widget-input');
        if (input) {
            input.placeholder = '';
        }
    }

    clearFilePreview() {
        const previewContainer = document.getElementById('chat-files-preview');
        if (previewContainer) {
            previewContainer.style.display = 'none';
            previewContainer.classList.add('hidden');
            previewContainer.innerHTML = '';
        }
        
        const input = document.getElementById('chat-widget-input');
        if (input) {
            input.placeholder = 'Введите сообщение...';
        }
        
        this.selectedFiles = null;
    }

    removeFileAt(index) {
        if (!this.selectedFiles || index < 0 || index >= this.selectedFiles.length) return;
        const updated = [...this.selectedFiles];
        updated.splice(index, 1);
        if (updated.length === 0) {
            this.clearFilePreview();
        } else {
            this.showFilePreview(updated);
        }
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
            // Проверяем: если текущая сессия не web: - запрещаем отправку
            if (this.currentSession && this.currentSession.includes(':') && !this.currentSession.startsWith('web:')) {
                const platform = this.currentSession.split(':')[0];
                console.warn(`⚠️ Попытка отправить файлы в сессию каналы ${platform}: ${this.currentSession}`);
                
                if (this.app && this.app.showNotification) {
                    this.app.showNotification(
                        `Нельзя отправлять сообщения в сессию каналы "${platform}". Это сессия только для просмотра.`, 
                        'warning'
                    );
                }
                return;
            }
            
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

        // ВАЖНО: Логирование для отладки
        console.log('🔍 [DEBUG] Проверка перед подключением WebSocket:');
        console.log('🔍 [DEBUG]   - this.embedToken:', this.embedToken);
        console.log('🔍 [DEBUG]   - typeof this.embedToken:', typeof this.embedToken);
        console.log('🔍 [DEBUG]   - this.embedToken значение:', JSON.stringify(this.embedToken));
        console.log('🔍 [DEBUG]   - this.embedToken длина:', this.embedToken ? this.embedToken.length : 0);
        console.log('🔍 [DEBUG]   - this.embedToken пустой?:', !this.embedToken || (typeof this.embedToken === 'string' && this.embedToken.trim() === ''));

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        let wsUrl = `${protocol}//${window.location.host}/frontend/chat/ws/chat`;
        
        // Если есть токен для встроенного чата, добавляем его в URL
        if (this.embedToken && typeof this.embedToken === 'string' && this.embedToken.trim() !== '') {
            wsUrl += `?token=${encodeURIComponent(this.embedToken)}`;
            console.log('🔑 [SUCCESS] Используем токен для встроенного чата, токен:', this.embedToken.substring(0, 20) + '...');
            console.log('🔑 [SUCCESS] Полный URL (замаскирован):', wsUrl.replace(/\?token=[^&]+/, '?token=***'));
        } else {
            console.error('❌ [ERROR] НЕТ ТОКЕНА для встроенного чата!');
            console.error('❌ [ERROR]   this.embedToken =', this.embedToken);
            console.error('❌ [ERROR]   typeof =', typeof this.embedToken);
            console.error('❌ [ERROR]   пустая строка? =', this.embedToken === '');
            console.error('❌ [ERROR]   null? =', this.embedToken === null);
            console.error('❌ [ERROR]   undefined? =', this.embedToken === undefined);
        }
        
        console.log('🔌 [FINAL] Подключение к WebSocket:', wsUrl.replace(/\?token=[^&]+/, '?token=***'));
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
        console.log(`🔍 [RECONNECT] Проверка токена при переподключении:`, this.embedToken ? this.embedToken.substring(0, 20) + '...' : 'НЕТ ТОКЕНА!');
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
        console.log('🔍 Текущая сессия:', this.currentSession);
        console.log('🔍 Сообщение для сессии:', message.session_id);

        // Фильтрация по session_id: показываем только сообщения для текущего чата
        if (message.session_id && this.currentSession) {
            // Извлекаем UUID из обоих session_id для сравнения
            const messageSessionUUID = message.session_id.includes(':') 
                ? message.session_id.split(':').pop() 
                : message.session_id;
            const currentSessionUUID = this.currentSession.includes(':') 
                ? this.currentSession.split(':').pop() 
                : this.currentSession;
            
            console.log('🔍 Сравнение UUID:', {
                messageSessionUUID,
                currentSessionUUID,
                match: messageSessionUUID === currentSessionUUID
            });
            
            if (messageSessionUUID !== currentSessionUUID) {
                console.log(`⏭️ Пропускаем сообщение для другой сессии: ${message.session_id} (текущая: ${this.currentSession})`);
                return;
            }
        }

        switch (message.type) {
            case 'SESSION_ASSIGNED':
                // Сервер назначил полный session_id - обновляем локальный
                console.log(`🔄 Session ID обновлен сервером: ${message.old_session_id} → ${message.new_session_id}`);
                if (this.currentAgent && message.agent_id === this.currentAgent) {
                    this.currentSession = message.new_session_id;
                    this.agentSessions[this.currentAgent] = message.new_session_id;
                    this.saveAgentSessions();
                    console.log(`✅ Локальная сессия обновлена на: ${this.currentSession}`);
                }
                break;
            case 'USER_MESSAGE':
                this.addUserMessage(message.content, message.timestamp, message.message_id);
                break;
            case 'AGENT_MESSAGE':
                this.showTypingIndicator(false);
                this.addAgentMessage(message.data);
                break;
            case 'AGENT_REASONING':
                console.log('💭 Получено AGENT_REASONING:', message.data);
                this.addReasoningMessage(message.data);
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
        if (!this.isConnected) {
            console.error('❌ WebSocket не подключен');
            return;
        }

        // Проверяем: если текущая сессия не web: - запрещаем отправку
        if (this.currentSession && this.currentSession.includes(':') && !this.currentSession.startsWith('web:')) {
            const platform = this.currentSession.split(':')[0];
            console.warn(`⚠️ Попытка отправить сообщение в сессию каналы ${platform}: ${this.currentSession}`);
            
            if (this.app && this.app.showNotification) {
                this.app.showNotification(
                    `Нельзя отправлять сообщения в сессию каналы "${platform}". Это сессия только для просмотра.`, 
                    'warning'
                );
            }
            return;
        }

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

    addReasoningMessage(data) {
        /**
         * Добавляет reasoning сообщение в чат.
         * Reasoning отображается как специальное сообщение с иконкой 💭
         */
        const messageObj = {
            type: 'reasoning',
            content: data.content,
            sender: 'agent',
            timestamp: new Date(data.timestamp),
            message_id: data.message_id || `reasoning_${Date.now()}`,
            isReasoning: true
        };
        
        this.addMessageToUI(messageObj);
        console.log('💭 Reasoning сообщение добавлено в UI');
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

