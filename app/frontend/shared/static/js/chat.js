/**
 * Chat Manager - единый класс для управления чатом
 */

// Типы сообщений
const MESSAGE_TYPES = {
    TEXT: 'text',
    HTML: 'html',
    MARKDOWN: 'markdown',
    FORM: 'form',
    BUTTONS: 'buttons',
    COMMAND: 'command',
    REACTION: 'reaction',
    POLL: 'poll',
    CARD: 'card',
    CAROUSEL: 'carousel',
    LOCATION: 'location',
    CONTACT: 'contact'
};

// Типы вложений
const ATTACHMENT_TYPES = {
    FILE: 'file'
};

/**
 * Класс для записи голоса через браузер в формате OGG/Opus
 */
class VoiceRecorder {
    constructor() {
        this.recorder = null;
        this.stream = null;
        this.isRecording = false;
    }

    async startRecording() {
        try {
            console.log('🎤 Запрашиваем доступ к микрофону...');
            this.stream = await navigator.mediaDevices.getUserMedia({ 
                audio: {
                    echoCancellation: true,
                    noiseSuppression: true,
                    sampleRate: 48000
                } 
            });

            console.log('✅ Доступ к микрофону получен');
            console.log('🎤 Создаем Opus Recorder для записи в OGG/Opus');
            
            // Создаем Opus Recorder
            this.recorder = new Recorder({
                encoderPath: '/static/js/encoderWorker.min.js',
                encoderSampleRate: 16000, // Cloud Voice рекомендует 16kHz для речи
                encoderApplication: 2048, // VOIP
                encoderFrameSize: 20, // 20ms фреймы
                encoderComplexity: 10, // Максимальное качество
                encoderBitRate: 16000, // 16kbps битрейт
                streamPages: false, // Получаем весь файл целиком
                numberOfChannels: 1,
                sourceNode: this.stream
            });

            // Добавляем обработчик ошибок
            this.recorder.onerror = (error) => {
                console.error('❌ Ошибка Opus Recorder:', error);
            };

            await this.recorder.start();
            this.isRecording = true;
            
            console.log('🎤 Запись началась в формате OGG/Opus');
            return true;
        } catch (error) {
            console.error('❌ Ошибка доступа к микрофону:', error);
            console.error('Детали ошибки:', {
                name: error.name,
                message: error.message,
                stack: error.stack
            });
            
            let errorMessage = 'Не удалось получить доступ к микрофону. ';
            if (error.name === 'NotAllowedError' || error.name === 'PermissionDeniedError') {
                errorMessage += 'Проверьте разрешения браузера.';
            } else if (error.name === 'NotFoundError' || error.name === 'DevicesNotFoundError') {
                errorMessage += 'Микрофон не найден.';
            } else if (error.name === 'NotSupportedError') {
                errorMessage += 'Формат записи не поддерживается.';
            } else {
                errorMessage += error.message;
            }
            
            alert(errorMessage);
            return false;
        }
    }

    async stopRecording() {
        return new Promise((resolve, reject) => {
            if (!this.recorder || !this.isRecording) {
                reject(new Error('Запись не начата'));
                return;
            }

            // Устанавливаем callback ДО вызова stop()
            this.recorder.ondataavailable = (typedArray) => {
                console.log('🎤 Получены аудио данные:', typedArray.length, 'байт');
                console.log('🔍 Первые байты:', Array.from(typedArray.slice(0, 20)).map(b => b.toString(16).padStart(2, '0')).join(' '));
                console.log('🔍 Первые символы:', String.fromCharCode(...typedArray.slice(0, 4)));
                
                const audioBlob = new Blob([typedArray], { type: 'audio/ogg; codecs=opus' });
                
                if (this.stream) {
                    this.stream.getTracks().forEach(track => track.stop());
                    this.stream = null;
                }

                this.isRecording = false;
                console.log('🎤 Запись завершена, размер Blob:', audioBlob.size, 'байт, формат: OGG/Opus');
                
                resolve({
                    blob: audioBlob,
                    mimeType: 'audio/ogg; codecs=opus'
                });
            };

            // Останавливаем запись - это вызовет ondataavailable
            console.log('🎤 Останавливаем запись...');
            this.recorder.stop();
        });
    }

    cancelRecording() {
        if (this.recorder && this.isRecording) {
            this.recorder.stop();
            
            if (this.stream) {
                this.stream.getTracks().forEach(track => track.stop());
                this.stream = null;
            }
            
            this.isRecording = false;
            console.log('🎤 Запись отменена');
        }
    }
}

class ChatManager {
    constructor(app) {
        this.app = app;
        this.websocket = null;
        this.isConnected = false;
        this.currentAgent = null;
        this.currentSession = null; // Будет установлена при открытии чата
        this.agentSessions = this.loadAgentSessions(); // Загружаем сохраненные сессии
        this.activeAgents = new Set(); // Отслеживаем активных агентов
        this.messageHistory = [];
        this.isVisible = false;
        this.container = null;
        this.messageRenderer = new ChatMessageRenderer();
        this.voiceRecorder = new VoiceRecorder(); // Рекордер для голоса
    }

    // Загрузка сохраненных сессий агентов из localStorage
    loadAgentSessions() {
        try {
            const saved = localStorage.getItem('chat_agent_sessions');
            return saved ? JSON.parse(saved) : {};
        } catch (error) {
            console.error('❌ Ошибка загрузки сессий агентов:', error);
            return {};
        }
    }

    // Сохранение сессий агентов в localStorage
    saveAgentSessions() {
        try {
            localStorage.setItem('chat_agent_sessions', JSON.stringify(this.agentSessions));
            console.log('💾 Сессии агентов сохранены:', this.agentSessions);
        } catch (error) {
            console.error('❌ Ошибка сохранения сессий агентов:', error);
        }
    }

    // Получение или создание сессии для агента
    getOrCreateSessionForAgent(agent_id) {
        if (!agent_id) {
            agent_id = 'default_agent';
        }

        // Проверяем есть ли уже сессия для этого агента
        if (this.agentSessions[agent_id]) {
            console.log(`🔄 Используем существующую сессию для ${agent_id}: ${this.agentSessions[agent_id]}`);
            return this.agentSessions[agent_id];
        }

        // Создаем новую сессию для агента
        const newSession = this.generateSessionId(agent_id);
        this.agentSessions[agent_id] = newSession;
        this.saveAgentSessions();
        
        console.log(`🆕 Создана новая сессия для ${agent_id}: ${newSession}`);
        return newSession;
    }

    // Создание новой сессии для агента (для команды /clear)
    createNewSessionForAgent(agent_id) {
        if (!agent_id) {
            agent_id = 'default_agent';
        }

        const oldSession = this.agentSessions[agent_id];
        const newSession = this.generateSessionId(agent_id);
        this.agentSessions[agent_id] = newSession;
        this.saveAgentSessions();
        
        console.log(`🔄 Создана новая сессия для ${agent_id}: ${oldSession} → ${newSession}`);
        return newSession;
    }

    // Генерация простого UUID для сессии чата
    generateSessionId(agent_id = null) {
        // Генерируем простой UUID
        if (typeof crypto !== 'undefined' && crypto.randomUUID) {
            return crypto.randomUUID();
        }
        
        // Fallback генератор
        const timestamp = Date.now().toString(36);
        const random = Math.random().toString(36).substr(2, 9);
        return `${timestamp}_${random}`;
    }

    // Обновление заголовка чата
    async updateChatHeader() {
        const title = document.getElementById('chat-widget-title');
        if (!title) return;

        if (!this.currentAgent) {
            title.textContent = 'Чат с агентом';
            this.updateInfoIcon(null); // Скрываем иконку когда нет агента
            return;
        }

        // Пытаемся получить метаданные флоу
        try {
            const flowInfo = await this.getFlowInfo(this.currentAgent);
            if (flowInfo && flowInfo.name) {
                title.textContent = `Чат с ${flowInfo.name}`;
                // Обновляем иконку с описанием
                this.updateInfoIcon(flowInfo.description);
            } else {
                // Fallback - показываем красивое имя из пути
                const prettyName = this.extractPrettyName(this.currentAgent);
                title.textContent = `Чат с ${prettyName}`;
                this.updateInfoIcon(null);
            }
        } catch (error) {
            console.warn('Не удалось получить метаданные флоу:', error);
            // Fallback - показываем красивое имя из пути
            const prettyName = this.extractPrettyName(this.currentAgent);
            title.textContent = `Чат с ${prettyName}`;
            this.updateInfoIcon(null);
        }
    }

    // Получение информации о флоу
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

    // Извлечение красивого имени из пути флоу
    extractPrettyName(agentPath) {
        if (!agentPath) return 'Агент';
        
        // Извлекаем последнюю часть пути и делаем её читаемой
        const parts = agentPath.split('.');
        const lastPart = parts[parts.length - 1];
        
        // Убираем _config и делаем CamelCase читаемым
        let name = lastPart.replace(/_config$/, '').replace(/_/g, ' ');
        
        // Преобразуем snake_case в Title Case
        name = name.split(' ')
            .map(word => word.charAt(0).toUpperCase() + word.slice(1))
            .join(' ');
            
        return name;
    }

    // Обновление иконки с информацией о флоу
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

    // Обновление панели агентов
    updateAgentsPanel() {
        const panel = document.getElementById('chat-agents-panel');
        if (!panel) return;

        const container = panel.querySelector('.d-flex');
        if (!container) return;

        // Очищаем панель
        container.innerHTML = '';

        // Добавляем табы для каждого активного агента
        this.activeAgents.forEach(agentId => {
            const tab = document.createElement('div');
            tab.className = `agent-tab ${agentId === this.currentAgent ? 'active' : ''}`;
            tab.dataset.agentId = agentId;
            
            tab.innerHTML = `
                <div class="agent-indicator"></div>
                <span>${agentId}</span>
            `;
            
            // Добавляем обработчик клика
            tab.addEventListener('click', async () => {
                await this.switchToAgent(agentId);
            });
            
            container.appendChild(tab);
        });

        console.log(`🔄 Панель агентов обновлена: ${this.activeAgents.size} активных агентов`);
    }

    // Переключение на другого агента
    async switchToAgent(agent_id) {
        if (agent_id === this.currentAgent) {
            return; // Уже активный агент
        }

        console.log(`🔄 Переключаемся с ${this.currentAgent} на ${agent_id}`);

        // Очищаем текущий чат (без удаления сессии)
        this.clearChatMessages();

        // Переключаем агента и сессию
        this.currentAgent = agent_id;
        this.currentSession = this.getOrCreateSessionForAgent(agent_id);

        // Обновляем UI
        await this.updateChatHeader();
        this.updateAgentsPanel();

        console.log(`✅ Переключились на агента ${agent_id}, сессия: ${this.currentSession}`);
    }

    // Показать/скрыть панель агентов
    toggleAgentsPanel() {
        const panel = document.getElementById('chat-agents-panel');
        if (!panel) return;

        const isVisible = panel.style.display !== 'none';
        panel.style.display = isVisible ? 'none' : 'block';
        
        console.log(`🔄 Панель агентов ${isVisible ? 'скрыта' : 'показана'}`);
    }

    // Показать информацию о флоу
    showFlowInfo() {
        const infoBtn = document.getElementById('chat-widget-info');
        if (!infoBtn || !infoBtn.title) return;

        // Создаем простое модальное окно с описанием
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

        // Обработчики закрытия
        const closeBtn = content.querySelector('#close-info-modal');
        const closeModal = () => document.body.removeChild(modal);
        
        closeBtn.addEventListener('click', closeModal);
        modal.addEventListener('click', (e) => {
            if (e.target === modal) closeModal();
        });

        // Закрытие по Escape
        const handleEscape = (e) => {
            if (e.key === 'Escape') {
                closeModal();
                document.removeEventListener('keydown', handleEscape);
            }
        };
        document.addEventListener('keydown', handleEscape);
    }

    // Инициализация чата
    init() {
        console.log('🚀 Инициализация ChatManager...');
        
        // Сбрасываем состояние переподключения
        this.isReconnecting = false;
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        
        this.createChatContainer();
        this.bindEvents();
        
        // Автоматически подключаемся к WebSocket при инициализации
        this.connectWebSocket();
        
        // Запускаем периодическую проверку соединения
        this.startConnectionHealthCheck();
        
        console.log('✅ ChatManager инициализирован');
    }

    // Инициализация контейнера чата (уже существует в HTML)
    createChatContainer() {
        // Виджет чата уже должен быть в HTML (включен в base.html)
        this.container = document.body; // Контейнер не нужен, виджет уже в DOM
        
        // Проверяем что виджет существует
        const widget = document.getElementById('chat-widget');
        if (!widget) {
            console.error('❌ Виджет чата не найден в DOM. Убедитесь что chat_widget_inline.html включен в базовый шаблон.');
            return false;
        }
        
        console.log('✅ Виджет чата найден в DOM');
        return true;
    }


    // Привязка событий
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
        
        // Переподключение при клике на индикатор соединения
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
        
        // Инициализация кнопки микрофона
        this.initVoiceRecording();

        // Обработчики для команд
        document.addEventListener('click', (e) => {
            if (e.target.closest('.command-item')) {
                const command = e.target.closest('.command-item').dataset.command;
                this.executeCommand(command);
            }
            // Закрываем меню команд при клике вне его
            if (!e.target.closest('#chat-widget-commands') && !e.target.closest('#chat-commands-menu')) {
                this.hideCommandsMenu();
            }
            
            // Закрываем панель агентов при клике вне её
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

        // Обработка клавиши Escape для выхода из полноэкранного режима
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const widget = document.getElementById('chat-widget');
                if (widget && widget.classList.contains('fullscreen')) {
                    this.toggleFullscreen();
                }
            }
        });
        
        // Добавляем возможность перетаскивания чата
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
            // Игнорируем клики по кнопкам
            if (e.target.closest('button')) return;
            
            // Не перетаскиваем в полноэкранном режиме
            if (widget.classList.contains('fullscreen')) return;
            
            isDragging = true;
            
            // Получаем текущую позицию виджета
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
            
            // Ограничиваем перемещение в пределах экрана
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

    // Открыть чат с агентом
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

        // Добавляем агента в активные
        if (agent_id) {
            this.activeAgents.add(agent_id);
        }

        this.currentAgent = agent_id;
        // Используем персистентную сессию для агента или создаем новую
        this.currentSession = session_id || this.getOrCreateSessionForAgent(agent_id);

        // Обновляем заголовок и панель агентов
        await this.updateChatHeader();
        this.updateAgentsPanel();

        // Показываем чат
        this.showChat();

        // Подключаемся к WebSocket
        this.connectWebSocket();

        // Отправляем начальное сообщение если есть
        if (initial_message) {
            setTimeout(() => {
                this.sendUserMessage(initial_message);
            }, 500);
        }
    }

    // Открыть существующую сессию чата
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

    // Загрузка истории сообщений для сессии
    async loadSessionHistory(session_id) {
        try {
            console.log('📜 Загрузка истории для сессии:', session_id);
            
            const response = await fetch(`/api/v1/history/sessions/${session_id}/messages?limit=100`);
            
            if (!response.ok) {
                throw new Error(`Ошибка загрузки истории: ${response.status}`);
            }

            const history = await response.json();
            
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
        } catch (error) {
            console.error('❌ Ошибка загрузки истории сессии:', error);
            this.addAgentMessage({
                content: 'Не удалось загрузить историю сообщений',
                timestamp: new Date().toISOString(),
                message_type: 'text'
            });
        }
    }

    // Показать чат
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

    // Переключить видимость чата
    toggleChat() {
        if (this.isVisible) {
            this.closeChat();
        } else {
            this.showChat();
        }
    }

    // Минимизировать чат
    minimizeChat() {
        const widget = document.getElementById('chat-widget');
        if (widget) {
            widget.classList.toggle('minimized');
        }
    }

    // Закрыть чат
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

        // Отключаемся от WebSocket
        this.disconnectWebSocket();
    }

    // Переключить полноэкранный режим
    toggleFullscreen() {
        const widget = document.getElementById('chat-widget');
        const fullscreenBtn = document.getElementById('chat-widget-fullscreen');
        const fullscreenIcon = fullscreenBtn?.querySelector('i');
        
        if (!widget) return;
        
        const isFullscreen = widget.classList.contains('fullscreen');
        
        if (isFullscreen) {
            // Выходим из полноэкранного режима
            widget.classList.remove('fullscreen');
            // Восстанавливаем позиционирование после перетаскивания
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
            console.log('🔲 Чат свернут из полноэкранного режима');
        } else {
            // Входим в полноэкранный режим
            widget.classList.add('fullscreen');
            widget.classList.remove('minimized'); // Убираем минимизацию если была
            // Сбрасываем позиционирование для полноэкранного режима
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
            console.log('🔳 Чат развернут на весь экран');
        }
        
        // Прокручиваем сообщения вниз после изменения размера
        setTimeout(() => {
            const messagesContainer = document.getElementById('chat-widget-messages');
            if (messagesContainer) {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
                // Принудительно обновляем стили для корректного отображения
                messagesContainer.style.display = 'none';
                messagesContainer.offsetHeight; // Trigger reflow
                messagesContainer.style.display = '';
            }
        }, 150);
    }

    // Переключить меню команд
    toggleCommandsMenu() {
        const menu = document.getElementById('chat-commands-menu');
        console.log('🔧 toggleCommandsMenu: меню найдено =', !!menu);
        
        if (!menu) {
            console.error('❌ Меню команд не найдено в DOM');
            return;
        }

        const isVisible = menu.style.display === 'block';
        console.log('🔧 Меню команд сейчас видимо =', isVisible);
        
        if (isVisible) {
            this.hideCommandsMenu();
        } else {
            this.showCommandsMenu();
        }
    }

    // Показать меню команд
    showCommandsMenu() {
        const menu = document.getElementById('chat-commands-menu');
        if (menu) {
            menu.style.display = 'block';
            console.log('✅ Меню команд показано');
        } else {
            console.error('❌ Не удалось показать меню команд - элемент не найден');
        }
    }

    // Скрыть меню команд
    hideCommandsMenu() {
        const menu = document.getElementById('chat-commands-menu');
        if (menu) {
            menu.style.display = 'none';
            console.log('❌ Меню команд скрыто');
        }
    }

    // Выполнить команду
    executeCommand(command) {
        console.log(`🔧 Выполняем команду: ${command}`);
        
        // Скрываем меню команд
        this.hideCommandsMenu();
        
        // Отправляем команду как обычное сообщение
        this.sendUserMessage(command);
    }

    // Открыть диалог выбора файлов
    openFileDialog() {
        const fileInput = document.getElementById('chat-file-input');
        if (fileInput) {
            fileInput.click();
        }
    }

    // Обработка выбора файлов
    async handleFileSelection(event) {
        const files = event.target.files;
        if (!files || files.length === 0) return;

        console.log(`📎 Выбрано файлов: ${files.length}`);
        
        // Показываем предпросмотр выбранных файлов
        this.showFilePreview(Array.from(files));
        
        // Очищаем input для повторного выбора тех же файлов
        event.target.value = '';
    }

    // Показать предпросмотр файлов
    showFilePreview(files) {
        const previewContainer = document.getElementById('chat-files-preview');
        if (!previewContainer) return;

        // Показываем контейнер предпросмотра
        previewContainer.style.display = 'block';
        
        // Заполняем предпросмотр
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
                        <span class="file-size">${this.formatFileSize(file.size)}</span>
                    </div>
                `).join('')}
            </div>
        `;
        
        // Сохраняем файлы для отправки
        this.selectedFiles = files;
        
        // Обновляем placeholder поля ввода
        const input = document.getElementById('chat-widget-input');
        if (input) {
            input.placeholder = `Сообщение с ${files.length} файл${files.length > 1 ? 'ами' : 'ом'}...`;
        }
    }

    // Очистить предпросмотр файлов
    clearFilePreview() {
        const previewContainer = document.getElementById('chat-files-preview');
        if (previewContainer) {
            previewContainer.style.display = 'none';
            previewContainer.innerHTML = '';
        }
        
        // Восстанавливаем placeholder
        const input = document.getElementById('chat-widget-input');
        if (input) {
            input.placeholder = 'Введите сообщение...';
        }
        
        // Очищаем выбранные файлы
        this.selectedFiles = null;
    }

    // Форматирование размера файла
    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    // Отправка сообщения с файлами
    async sendMessageWithFiles(message) {
        if (!this.selectedFiles || this.selectedFiles.length === 0) {
            console.error('❌ Нет выбранных файлов для отправки');
            return;
        }

        console.log(`📎 Отправляем сообщение с ${this.selectedFiles.length} файлами:`, this.selectedFiles);

        // Конвертируем файлы в base64
        const filesData = [];
        for (const file of this.selectedFiles) {
            try {
                console.log(`📎 Конвертируем файл: ${file.name} (${this.formatFileSize(file.size)})`);
                const base64Content = await this.fileToBase64(file);
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

        // Отправляем через WebSocket
        if (this.isConnected && filesData.length > 0) {
            const wsMessage = {
                type: 'USER_MESSAGE',
                data: {
                    message: message,
                    files: filesData, // Добавляем файлы к обычному сообщению
                    agent_id: this.currentAgent,
                    session_id: this.currentSession
                }
            };
            
            this.websocket.send(JSON.stringify(wsMessage));
            console.log(`✅ Отправлено сообщение с ${filesData.length} файлами`);
        }
    }

    // Конвертация файла в base64
    fileToBase64(file) {
        return new Promise((resolve, reject) => {
            const reader = new FileReader();
            reader.readAsDataURL(file);
            reader.onload = () => {
                // Убираем префикс data:mime/type;base64,
                const base64 = reader.result.split(',')[1];
                resolve(base64);
            };
            reader.onerror = error => reject(error);
        });
    }

    // Обновление индикатора состояния соединения
    updateConnectionStatus(status) {
        const indicator = document.querySelector('.connection-indicator');
        if (!indicator) return;

        // Удаляем все классы состояний
        indicator.classList.remove('connected', 'connecting', 'disconnected', 'reconnecting');
        
        // Добавляем новый класс
        indicator.classList.add(status);
        
        // Обновляем tooltip
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

    // Подключение к WebSocket с индикаторами и реконнектами
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
            this.reconnectAttempts = 0; // Сбрасываем счетчик попыток
            this.reconnectDelay = 1000; // Сбрасываем задержку
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
            
            console.log(`🔍 Проверяем переподключение: isReconnecting=${this.isReconnecting}, attempts=${this.reconnectAttempts}/${this.maxReconnectAttempts}`);
            
            // Исправляем undefined maxReconnectAttempts
            if (typeof this.maxReconnectAttempts === 'undefined') {
                this.maxReconnectAttempts = 5;
                console.log('🔧 Исправлен undefined maxReconnectAttempts');
            }
            
            // Автоматическое переподключение
            if (!this.isReconnecting && this.reconnectAttempts < this.maxReconnectAttempts) {
                console.log('✅ Запускаем автоматическое переподключение');
                this.scheduleReconnect();
            } else {
                console.log('❌ Переподключение заблокировано - кликните на индикатор для принудительного переподключения');
                
                // Через 30 секунд сбрасываем счетчики для автоматического восстановления
                setTimeout(() => {
                    if (!this.isConnected) {
                        console.log('🔄 Сбрасываем счетчики после длительного отключения');
                        this.reconnectAttempts = 0;
                        this.isReconnecting = false;
                    }
                }, 30000);
            }
        };

        this.websocket.onerror = (error) => {
            console.error('❌ WebSocket ошибка:', error);
            this.isConnected = false;
            this.isReconnecting = false; // Сбрасываем чтобы разблокировать следующие попытки
            this.updateConnectionStatus('disconnected');
        };
    }

    // Планирование переподключения
    scheduleReconnect() {
        if (this.isReconnecting) return;
        
        // Исправляем undefined значения
        if (typeof this.maxReconnectAttempts === 'undefined') {
            this.maxReconnectAttempts = 5;
        }
        if (typeof this.reconnectAttempts === 'undefined') {
            this.reconnectAttempts = 0;
        }
        if (typeof this.reconnectDelay === 'undefined') {
            this.reconnectDelay = 1000;
        }
        
        this.isReconnecting = true;
        this.reconnectAttempts++;
        
        console.log(`🔄 Планируем переподключение #${this.reconnectAttempts} через ${this.reconnectDelay}ms`);
        this.updateConnectionStatus('reconnecting');
        
        setTimeout(() => {
            if (this.reconnectAttempts <= this.maxReconnectAttempts) {
                console.log(`🔄 Попытка переподключения #${this.reconnectAttempts}`);
                this.connectWebSocket();
                
                // Увеличиваем задержку (exponential backoff)
                this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 10000);
            } else {
                console.error('❌ Превышено максимальное количество попыток переподключения');
                this.isReconnecting = false;
                this.updateConnectionStatus('disconnected');
            }
        }, this.reconnectDelay);
    }

    // Принудительное переподключение
    forceReconnect() {
        console.log('🔄 Принудительное переподключение...');
        
        // ПОЛНОСТЬЮ сбрасываем все счетчики и состояние
        this.reconnectAttempts = 0;
        this.reconnectDelay = 1000;
        this.isReconnecting = false;
        this.isConnected = false;
        
        // Закрываем текущее соединение принудительно
        if (this.websocket) {
            this.websocket.onclose = null; // Убираем обработчик чтобы не вызвать scheduleReconnect
            this.websocket.close();
            this.websocket = null;
        }
        
        console.log('🔄 Состояние сброшено, подключаемся заново...');
        
        // Подключаемся заново
        setTimeout(() => {
            this.connectWebSocket();
        }, 500);
    }

    // Периодическая проверка соединения
    startConnectionHealthCheck() {
        setInterval(() => {
            // Только проверяем состояние, НЕ переподключаемся (это делает onclose)
            if (this.websocket) {
                if (this.websocket.readyState === WebSocket.OPEN && this.isConnected) {
                    // Отправляем ping для проверки соединения
                    try {
                        this.websocket.send(JSON.stringify({type: 'PING'}));
                    } catch (error) {
                        console.error('❌ Ошибка отправки ping:', error);
                    }
                }
            } else if (!this.isReconnecting && !this.isConnected) {
                // Нет WebSocket соединения и не переподключаемся - создаем
                console.log('🔍 Нет WebSocket соединения, подключаемся...');
                this.connectWebSocket();
            }
        }, 15000); // Проверяем каждые 15 секунд
    }

    // Отключение от WebSocket
    disconnectWebSocket() {
        if (this.websocket) {
            this.websocket.close();
            this.websocket = null;
            this.isConnected = false;
        }
    }

    // Обработка сообщений от WebSocket
    handleWebSocketMessage(message) {
        console.log('📨 Получено сообщение:', message);

        switch (message.type) {
            case 'USER_MESSAGE':
                // Пользовательское сообщение от бекенда (передаем весь объект)
                this.addUserMessage(message.content, message.timestamp, message.message_id);
                break;
            case 'AGENT_MESSAGE':
                // Принудительно скрываем индикатор печати при получении сообщения агента
                this.showTypingIndicator(false);
                this.addAgentMessage(message.data);
                break;
            case 'AGENT_INTERRUPT':
                // Принудительно скрываем индикатор печати при interrupt
                this.showTypingIndicator(false);
                this.handleAgentInterrupt(message.data);
                break;
            case 'AGENT_TYPING':
                console.log('💬 Получено AGENT_TYPING уведомление:', message.data);
                this.showTypingIndicator(message.data.is_typing);
                break;
            case 'CLEAR_CHAT':
                // Очистка чата
                console.log('🧹 Получена команда очистки чата');
                this.clearChatMessages();
                
                // Создаем новую сессию для текущего агента
                if (this.currentAgent) {
                    const oldSession = this.currentSession;
                    this.currentSession = this.createNewSessionForAgent(this.currentAgent);
                    console.log(`🔄 Сессия для агента ${this.currentAgent} обновлена: ${oldSession} → ${this.currentSession}`);
                }
                
                // Показываем сообщение о очистке
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
                // Ответ на ping
                break;
        }
    }

    // Отправка сообщения
    async sendMessage() {
        const input = document.getElementById('chat-widget-input');
        const message = input?.value?.trim() || '';
        
        // Проверяем есть ли файлы или текст
        if (!message && (!this.selectedFiles || this.selectedFiles.length === 0)) {
            return; // Нет ни текста ни файлов
        }

        // Если есть файлы - отправляем с файлами
        if (this.selectedFiles && this.selectedFiles.length > 0) {
            await this.sendMessageWithFiles(message);
        } else {
            // Обычное текстовое сообщение
            this.sendUserMessage(message);
        }
        
        // Очищаем поле ввода
        if (input) input.value = '';
        
        // Очищаем предпросмотр файлов
        this.clearFilePreview();
    }

    // Отправка сообщения пользователя
    sendUserMessage(message) {
        // НЕ добавляем сообщение в UI сами - ждем от бекенда
        // this.addUserMessage(message); // УБРАНО - теперь бекенд отправляет

        // НЕ показываем индикатор печати здесь - это делает бекенд
        // this.showTypingIndicator(true); // УБРАНО - теперь бекенд контролирует

        // Отправляем через WebSocket
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

    // Добавление сообщения пользователя в UI
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

    // Добавление сообщения агента в UI
    addAgentMessage(data) {
        // НЕ скрываем индикатор печати здесь - это делает бекенд через AGENT_TYPING
        // this.showTypingIndicator(false); // УБРАНО - теперь бекенд контролирует
        
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

    // Добавление сообщения в UI
    addMessageToUI(messageObj) {
        const messagesContainer = document.getElementById('chat-widget-messages');
        if (!messagesContainer) return;

        // Проверяем дубликаты по message_id
        if (messageObj.message_id) {
            const existingMessage = messagesContainer.querySelector(`[data-message-id="${messageObj.message_id}"]`);
            if (existingMessage) {
                console.log(`⚠️ Сообщение ${messageObj.message_id} уже отображено, пропускаем`);
                return;
            }
        }

        const messageElement = this.messageRenderer.renderMessage(messageObj);
        
        // Добавляем data-message-id для дедупликации
        if (messageObj.message_id) {
            messageElement.setAttribute('data-message-id', messageObj.message_id);
        }
        
        messagesContainer.appendChild(messageElement);

        // Плавно прокручиваем вниз
        setTimeout(() => {
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }, 10);

        // Сохраняем в историю
        this.messageHistory.push(messageObj);
    }

    // Обработка interrupt от агента
    handleAgentInterrupt(data) {
        console.log('🟡 Агент запросил ввод:', data.question);
        
        // Показываем вопрос от агента
        this.addAgentMessage({
            content: data.question,
            message_type: MESSAGE_TYPES.TEXT
        });

        // TODO: Можно добавить специальный UI для interrupt
    }

    // Показать индикатор печати
    showTypingIndicator(isTyping) {
        const messagesContainer = document.getElementById('chat-widget-messages');
        let typingIndicator = document.getElementById('chat-typing-indicator');
        
        console.log(`💬 showTypingIndicator вызван: isTyping=${isTyping}, элемент найден=${!!typingIndicator}`);
        
        if (!messagesContainer) {
            console.error('❌ Контейнер сообщений не найден');
            return;
        }
        
        if (isTyping) {
            // Создаем индикатор если его нет
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
            console.log('💬 ✅ Индикатор печати ПОКАЗАН');
            
            // Прокручиваем к индикатору
            setTimeout(() => {
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }, 10);
        } else {
            // Удаляем индикатор полностью
            if (typingIndicator) {
                typingIndicator.remove();
                console.log('💬 ❌ Индикатор печати УДАЛЕН');
            }
        }
    }

    // Очистить сообщения в чате
    clearChatMessages() {
        const messagesContainer = document.getElementById('chat-widget-messages');
        if (messagesContainer) {
            messagesContainer.innerHTML = '';
            console.log('🧹 Сообщения чата очищены');
        }
        
        // Очищаем историю сообщений
        this.messageHistory = [];
        
        // Скрываем индикатор печати если был
        this.showTypingIndicator(false);
    }

    // Показать ошибку
    showError(message) {
        this.app.showNotification(message, 'danger');
    }

    // Инициализация записи голоса
    initVoiceRecording() {
        const voiceBtn = document.getElementById('chat-voice-btn') || document.getElementById('chat-widget-voice');
        const indicator = document.getElementById('voice-recording-indicator') || document.getElementById('voice-recording-indicator-widget');
        
        if (!voiceBtn) {
            console.log('⚠️ Кнопка микрофона не найдена');
            return;
        }

        console.log('🎤 Инициализация кнопки микрофона:', voiceBtn.id);

        // Обработчик нажатия (начало записи)
        voiceBtn.addEventListener('mousedown', async (e) => {
            e.preventDefault();
            const success = await this.voiceRecorder.startRecording();
            if (success) {
                if (indicator) indicator.style.display = 'block';
                voiceBtn.classList.add('recording');
            }
        });

        // Обработчик отпускания (остановка и отправка)
        voiceBtn.addEventListener('mouseup', async (e) => {
            e.preventDefault();
            await this.handleVoiceRecordingStop(voiceBtn, indicator);
        });

        // Обработчик если мышь ушла с кнопки во время записи
        voiceBtn.addEventListener('mouseleave', async (e) => {
            if (this.voiceRecorder.isRecording) {
                await this.handleVoiceRecordingStop(voiceBtn, indicator);
            }
        });

        // Поддержка touch событий для мобильных
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

    // Обработка остановки записи
    async handleVoiceRecordingStop(voiceBtn, indicator) {
        if (!this.voiceRecorder.isRecording) return;

        try {
            // Останавливаем запись
            const { blob, mimeType } = await this.voiceRecorder.stopRecording();
            
            // Скрываем индикатор
            if (indicator) indicator.style.display = 'none';
            if (voiceBtn) voiceBtn.classList.remove('recording');

            // Проверяем размер
            if (blob.size < 1000) {
                this.app.showNotification('Запись слишком короткая', 'warning');
                return;
            }

            // Определяем расширение по MIME типу
            let extension = 'webm';  // По умолчанию webm (Chrome/Edge)
            let finalMimeType = mimeType;
            
            if (mimeType.includes('ogg')) {
                extension = 'ogg';
                // Добавляем codecs=opus если это OGG без параметра
                if (mimeType === 'audio/ogg' || mimeType === 'audio/ogg;') {
                    finalMimeType = 'audio/ogg; codecs=opus';
                }
            } else if (mimeType.includes('wav')) {
                extension = 'wav';
                finalMimeType = 'audio/wave';
            } else if (mimeType.includes('webm')) {
                extension = 'webm';
                // WebM уже имеет правильный формат
            }
            
            // Создаем файл
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

            // Добавляем в превью как обычный файл
            this.showFilePreview([audioFile]);
            
        } catch (error) {
            console.error('❌ Ошибка обработки голосового сообщения:', error);
            if (indicator) indicator.style.display = 'none';
            if (voiceBtn) voiceBtn.classList.remove('recording');
            this.app.showNotification('Ошибка записи голоса: ' + error.message, 'danger');
        }
    }
}

// Рендерер сообщений
class ChatMessageRenderer {
    renderMessage(message) {
        const container = document.createElement('div');
        container.className = `chat-message ${message.sender}`;
        
        // Основной контент
        const contentDiv = this.renderContent(message);
        container.appendChild(contentDiv);
        
        // Вложения
        if (message.attachments && message.attachments.length > 0) {
            const attachmentsDiv = this.renderAttachments(message.attachments);
            container.appendChild(attachmentsDiv);
        }
        
        // Кнопки
        if (message.buttons && message.buttons.length > 0) {
            const buttonsDiv = this.renderButtons(message.buttons);
            container.appendChild(buttonsDiv);
        }
        
        // Форма
        if (message.form) {
            const formDiv = this.renderForm(message.form);
            container.appendChild(formDiv);
        }
        
        return container;
    }

    renderContent(message) {
        const div = document.createElement('div');
        div.className = 'message-content';
        
        let content = message.content;
        
        // Парсим файлы из содержимого сообщения
        const { cleanContent, files } = this.parseFilesFromContent(content);
        
        // Парсим ссылки на скачивание из текста
        const { cleanContentWithoutLinks, downloadLinks } = this.parseDownloadLinksFromContent(cleanContent);
        
        // Убираем метки [СКАЧАТЬ: ...] из текста
        let finalContent = cleanContentWithoutLinks.replace(/\[СКАЧАТЬ:\s*[^\]]+\]/g, '').trim();
        
        switch (message.type) {
            case MESSAGE_TYPES.HTML:
                div.innerHTML = this.sanitizeHTML(finalContent);
                break;
            default:
                div.innerHTML = this.renderMarkdown(finalContent);
                break;
        }
        
        // Добавляем файлы как карточки
        if (files.length > 0) {
            const filesContainer = document.createElement('div');
            filesContainer.className = 'message-files';
            
            files.forEach(file => {
                const fileCard = this.renderFileCard(file);
                filesContainer.appendChild(fileCard);
            });
            
            div.appendChild(filesContainer);
        }
        
        // Добавляем ссылки на скачивание как кнопки
        if (downloadLinks.length > 0) {
            const linksContainer = document.createElement('div');
            linksContainer.className = 'message-download-links';
            
            downloadLinks.forEach(async (link) => {
                const linkButton = await this.renderDownloadButton(link);
                linksContainer.appendChild(linkButton);
            });
            
            div.appendChild(linksContainer);
        }
        
        return div;
    }

    // Парсинг файлов из содержимого сообщения
    parseFilesFromContent(content) {
        const fileRegex = /\[FILE\](.*?)\[\/FILE\]/gs;
        const files = [];
        let cleanContent = content;
        
        let match;
        while ((match = fileRegex.exec(content)) !== null) {
            const fileText = match[1];
            
            // Парсим информацию о файле
            const nameMatch = fileText.match(/Файл:\s*([^(]+)/);
            const idMatch = fileText.match(/ID:\s*([^,]+)/);
            const urlMatch = fileText.match(/URL:\s*([^,]+)/);
            const typeMatch = fileText.match(/тип:\s*([^,]+)/);
            const sizeMatch = fileText.match(/размер:\s*([^)]+)/);
            
            if (nameMatch) {
                files.push({
                    name: nameMatch[1].trim(),
                    id: idMatch ? idMatch[1].trim() : '',
                    url: urlMatch ? urlMatch[1].trim() : '',
                    type: typeMatch ? typeMatch[1].trim() : '',
                    size: sizeMatch ? sizeMatch[1].trim() : ''
                });
            }
            
            // Убираем [FILE]...[/FILE] из текста
            cleanContent = cleanContent.replace(match[0], '');
        }
        
        return { 
            cleanContent: cleanContent.trim(), 
            files 
        };
    }

    // Рендеринг карточки файла
    renderFileCard(file) {
        const fileCard = document.createElement('div');
        fileCard.className = 'chat-file-card';
        
        // Определяем иконку по типу файла
        const icon = this.getFileIcon(file.type);
        
        fileCard.innerHTML = `
            <div class="file-card-icon">
                <i class="bi ${icon}"></i>
            </div>
            <div class="file-card-info">
                <div class="file-card-name">${file.name}</div>
                <div class="file-card-details">${file.size} • ${file.type}</div>
            </div>
            <div class="file-card-actions">
                <a href="${file.url}" target="_blank" class="file-download-btn" title="Скачать">
                    <i class="bi bi-download"></i>
                </a>
            </div>
        `;
        
        return fileCard;
    }

    // Получение иконки для типа файла
    getFileIcon(mimeType) {
        if (mimeType.startsWith('image/')) return 'bi-file-earmark-image';
        if (mimeType.startsWith('video/')) return 'bi-file-earmark-play';
        if (mimeType.startsWith('audio/')) return 'bi-file-earmark-music';
        if (mimeType.includes('pdf')) return 'bi-file-earmark-pdf';
        if (mimeType.includes('word') || mimeType.includes('document')) return 'bi-file-earmark-word';
        if (mimeType.includes('excel') || mimeType.includes('spreadsheet')) return 'bi-file-earmark-excel';
        if (mimeType.includes('powerpoint') || mimeType.includes('presentation')) return 'bi-file-earmark-ppt';
        if (mimeType.includes('zip') || mimeType.includes('archive')) return 'bi-file-earmark-zip';
        return 'bi-file-earmark';
    }

    // Парсинг ссылок на скачивание из текста
    parseDownloadLinksFromContent(content) {
        // Ищем ссылки на наши файлы в тексте (поддерживаем file_ и audio_ префиксы)
        const linkRegex = /(https?:\/\/[^\s]+\/api\/v1\/files\/download\/(file_|audio_)[a-z0-9]+)/gi;
        const downloadLinks = [];
        let cleanContent = content;
        
        let match;
        while ((match = linkRegex.exec(content)) !== null) {
            const url = match[1];
            const fileId = url.split('/').pop();
            
            // Пытаемся извлечь имя файла из контекста
            const contextMatch = content.match(new RegExp(`файла?\\s+"([^"]+)"[^]*?${url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`));
            const fileName = contextMatch ? contextMatch[1] : fileId;
            
            downloadLinks.push({
                url: url,
                fileName: fileName,
                fileId: fileId
            });
            
            // Заменяем ссылку на placeholder
            cleanContent = cleanContent.replace(url, `[СКАЧАТЬ: ${fileName}]`);
        }
        
        return {
            cleanContentWithoutLinks: cleanContent,
            downloadLinks: downloadLinks
        };
    }

    // Рендеринг кнопки скачивания с превью
    async renderDownloadButton(link) {
        const container = document.createElement('div');
        container.className = 'download-link-container';
        
        // Показываем индикатор загрузки
        container.innerHTML = `
            <div class="file-preview loading-preview">
                <div class="spinner-border spinner-border-sm" role="status"></div>
                <span class="ms-2">Загрузка превью...</span>
            </div>
        `;
        
        // Пытаемся определить тип файла
        const fileType = this.detectFileType(link.fileName);
        
        // Если уже определен конкретный тип (не document), сразу показываем превью
        if (fileType !== 'document') {
            this.renderFilePreview(container, link, null, fileType);
        } else {
            // Иначе пробуем загрузить MIME тип через API
            try {
                const mimeType = await this.fetchFileMimeType(link.url);
                this.renderFilePreview(container, link, mimeType);
            } catch (error) {
                console.error('Ошибка загрузки файла:', error);
                this.renderFilePreview(container, link, null);
            }
        }
        
        return container;
    }
    
    // Получение MIME типа файла через API
    async fetchFileMimeType(url) {
        try {
            // Извлекаем file_id из URL
            const fileId = url.split('/').pop();
            
            // Используем API эндпоинт для получения информации о файле
            const infoUrl = url.replace(`/download/${fileId}`, `/info/${fileId}`);
            const response = await fetch(infoUrl);
            
            if (!response.ok) {
                console.warn('Не удалось получить информацию о файле:', response.status);
                return null;
            }
            
            const fileInfo = await response.json();
            return fileInfo.content_type;
        } catch (error) {
            console.error('Ошибка получения MIME типа:', error);
            return null;
        }
    }
    
    // Рендеринг превью на основе типа
    renderFilePreview(container, link, mimeType = null, knownType = null) {
        let fileType = knownType;
        
        // Если передан MIME тип, определяем тип файла по нему
        if (mimeType && !knownType) {
            if (mimeType.startsWith('image/')) fileType = 'image';
            else if (mimeType.startsWith('video/')) fileType = 'video';
            else if (mimeType.startsWith('audio/')) fileType = 'audio';
            else if (mimeType.includes('pdf')) fileType = 'pdf';
            else fileType = 'document';
        }
        
        if (fileType === 'image') {
            // Для изображений показываем превью
            container.innerHTML = `
                <div class="file-preview image-preview">
                    <img src="${link.url}" alt="${link.fileName}" 
                         style="max-width: 300px; max-height: 300px; border-radius: 8px; cursor: pointer; object-fit: contain;"
                         onclick="window.open('${link.url}', '_blank')"
                         onerror="this.parentElement.innerHTML='<div class=error-preview>❌ Не удалось загрузить изображение</div>'"
                    >
                    <div class="file-info" style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <span class="file-name" style="font-size: 14px; color: #666;">${link.fileName}</span>
                        <a href="${link.url}" class="btn btn-sm btn-outline-primary" download="${link.fileName}">
                            <i class="bi bi-download"></i> Скачать
                        </a>
                    </div>
                </div>
            `;
        } else if (fileType === 'video') {
            // Для видео показываем video player
            container.innerHTML = `
                <div class="file-preview video-preview">
                    <video controls style="max-width: 400px; border-radius: 8px;">
                        <source src="${link.url}" type="${mimeType || 'video/mp4'}">
                        Ваш браузер не поддерживает видео.
                    </video>
                    <div class="file-info" style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <span class="file-name" style="font-size: 14px; color: #666;">${link.fileName}</span>
                        <a href="${link.url}" class="btn btn-sm btn-outline-primary" download="${link.fileName}">
                            <i class="bi bi-download"></i> Скачать
                        </a>
                    </div>
                </div>
            `;
        } else if (fileType === 'audio') {
            // Для аудио показываем audio player
            container.innerHTML = `
                <div class="file-preview audio-preview">
                    <audio controls style="width: 300px;">
                        <source src="${link.url}" type="${mimeType || 'audio/mpeg'}">
                        Ваш браузер не поддерживает аудио.
                    </audio>
                    <div class="file-info" style="margin-top: 8px; display: flex; justify-content: space-between; align-items: center;">
                        <span class="file-name" style="font-size: 14px; color: #666;">${link.fileName}</span>
                        <a href="${link.url}" class="btn btn-sm btn-outline-primary" download="${link.fileName}">
                            <i class="bi bi-download"></i> Скачать
                        </a>
                    </div>
                </div>
            `;
        } else {
            // Для остальных файлов показываем иконку и кнопку
            const icon = this.getFileIcon(link.fileName);
            container.innerHTML = `
                <div class="file-preview document-preview" style="display: flex; align-items: center; padding: 12px; border: 1px solid #ddd; border-radius: 8px; background: #f8f9fa;">
                    <div class="file-icon" style="font-size: 32px; margin-right: 12px;">${icon}</div>
                    <div class="file-info" style="flex-grow: 1;">
                        <div class="file-name" style="font-size: 14px; font-weight: 500;">${link.fileName}</div>
                        ${mimeType ? `<div class="file-type" style="font-size: 12px; color: #666;">${mimeType}</div>` : ''}
                    </div>
                    <a href="${link.url}" class="btn btn-sm btn-outline-primary" download="${link.fileName}">
                        <i class="bi bi-download"></i>
                    </a>
                </div>
            `;
        }
    }
    
    // Определение типа файла
    detectFileType(fileName) {
        // Проверяем префикс для специальных ID
        if (fileName.startsWith('audio_')) {
            return 'audio';
        }
        
        // Если нет расширения, возвращаем document (будет определен через API)
        if (!fileName.includes('.')) {
            return 'document';
        }
        
        const ext = fileName.split('.').pop().toLowerCase();
        
        // Изображения
        if (['jpg', 'jpeg', 'png', 'gif', 'webp', 'svg', 'bmp'].includes(ext)) {
            return 'image';
        }
        
        // Видео
        if (['mp4', 'webm', 'ogg', 'mov', 'avi'].includes(ext)) {
            return 'video';
        }
        
        // Аудио
        if (['mp3', 'wav', 'ogg', 'flac', 'm4a'].includes(ext)) {
            return 'audio';
        }
        
        // PDF
        if (ext === 'pdf') {
            return 'pdf';
        }
        
        return 'document';
    }

    renderAttachments(attachments) {
        const container = document.createElement('div');
        container.className = 'message-attachments';
        
        attachments.forEach(attachment => {
            const attachmentElement = this.renderAttachment(attachment);
            container.appendChild(attachmentElement);
        });
        
        return container;
    }

    renderAttachment(attachment) {
        const div = document.createElement('div');
        div.className = 'chat-file';
        
        const displayType = this.getFileDisplayType(attachment.mime_type);
        
        if (displayType === 'image') {
            div.innerHTML = `
                <img src="${attachment.url}" alt="${attachment.name}" 
                     style="max-width: 200px; max-height: 200px; cursor: pointer;"
                     onclick="window.open('${attachment.url}', '_blank')">
                <div class="file-info">
                    <span>${attachment.name}</span>
                    <span>${this.formatFileSize(attachment.size)}</span>
                </div>
            `;
        } else {
            const icon = this.getFileIcon(attachment.name);
            div.innerHTML = `
                <div class="d-flex align-items-center">
                    <span class="me-2">${icon}</span>
                    <div class="flex-grow-1">
                        <div>${attachment.name}</div>
                        <small class="text-muted">${this.formatFileSize(attachment.size)}</small>
                    </div>
                    <a href="${attachment.url}" target="_blank" class="btn btn-sm btn-outline-primary">
                        <i class="bi bi-download"></i>
                    </a>
                </div>
            `;
        }
        
        return div;
    }

    renderButtons(buttons) {
        const container = document.createElement('div');
        container.className = 'message-buttons mt-2';
        
        buttons.forEach(button => {
            const btn = document.createElement('button');
            btn.className = 'btn btn-sm btn-outline-primary me-1 mb-1';
            btn.textContent = button.text;
            btn.onclick = () => this.handleButtonClick(button);
            container.appendChild(btn);
        });
        
        return container;
    }

    renderForm(form) {
        // TODO: Реализовать рендеринг форм
        const div = document.createElement('div');
        div.className = 'message-form';
        div.innerHTML = `<p><strong>Форма:</strong> ${form.title}</p>`;
        return div;
    }

    handleButtonClick(button) {
        console.log('🔘 Нажата кнопка:', button);
        // TODO: Отправить callback_data через WebSocket
    }

    getFileDisplayType(mimeType) {
        if (mimeType.startsWith('image/')) return 'image';
        if (mimeType.startsWith('video/')) return 'video';
        if (mimeType.startsWith('audio/')) return 'audio';
        return 'document';
    }

    getFileIcon(filename) {
        const ext = filename.split('.').pop().toLowerCase();
        const icons = {
            'pdf': '📄', 'doc': '📝', 'docx': '📝',
            'xls': '📊', 'xlsx': '📊', 'ppt': '📈', 'pptx': '📈',
            'txt': '📃', 'zip': '📦', 'rar': '📦'
        };
        return icons[ext] || '📎';
    }

    formatFileSize(bytes) {
        if (bytes === 0) return '0 Bytes';
        const k = 1024;
        const sizes = ['Bytes', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }

    sanitizeHTML(html) {
        // Простая санитизация HTML
        const div = document.createElement('div');
        div.textContent = html;
        return div.innerHTML;
    }

    renderMarkdown(markdown) {
        let html = markdown;
        
        html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>');
        html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>');
        html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>');
        
        html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>');
        html = html.replace(/\*(.*?)\*/g, '<em>$1</em>');
        
        html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
        
        html = html.replace(/`([^`]+)`/g, '<code>$1</code>');
        
        const lines = html.split('\n');
        const result = [];
        let inOrderedList = false;
        let inUnorderedList = false;
        
        for (let i = 0; i < lines.length; i++) {
            const line = lines[i];
            const trimmedLine = line.trim();
            
            if (/^\d+\.\s+/.test(trimmedLine)) {
                if (!inOrderedList) {
                    result.push('<ol>');
                    inOrderedList = true;
                }
                if (inUnorderedList) {
                    result.push('</ul>');
                    inUnorderedList = false;
                }
                result.push('<li>' + trimmedLine.replace(/^\d+\.\s+/, '') + '</li>');
            }
            else if (/^[-*]\s+/.test(trimmedLine)) {
                if (!inUnorderedList) {
                    result.push('<ul>');
                    inUnorderedList = true;
                }
                result.push('<li>' + trimmedLine.replace(/^[-*]\s+/, '') + '</li>');
            }
            else {
                if (inOrderedList && trimmedLine === '') {
                    result.push('</ol>');
                    inOrderedList = false;
                }
                if (inUnorderedList && trimmedLine === '') {
                    result.push('</ul>');
                    inUnorderedList = false;
                }
                
                if (trimmedLine === '') {
                    result.push('<br>');
                } else if (!trimmedLine.startsWith('<h')) {
                    result.push(line);
                } else {
                    result.push(line);
                }
            }
        }
        
        if (inOrderedList) result.push('</ol>');
        if (inUnorderedList) result.push('</ul>');
        
        return result.join('\n');
    }
}

// Экспорт для использования в других модулях
export default ChatManager;
