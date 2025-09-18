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
    updateChatHeader() {
        const title = document.getElementById('chat-widget-title');
        if (title) {
            title.textContent = this.currentAgent ? `Чат с ${this.currentAgent}` : 'Чат с агентом';
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
            tab.addEventListener('click', () => {
                this.switchToAgent(agentId);
            });
            
            container.appendChild(tab);
        });

        console.log(`🔄 Панель агентов обновлена: ${this.activeAgents.size} активных агентов`);
    }

    // Переключение на другого агента
    switchToAgent(agent_id) {
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
        this.updateChatHeader();
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
    }

    // Открыть чат с агентом
    open(options = {}) {
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
        this.updateChatHeader();
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
            }
        }, 100);
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
                // Пользовательское сообщение от бекенда
                this.addUserMessage(message.content);
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
    addUserMessage(message) {
        const messageObj = {
            type: MESSAGE_TYPES.TEXT,
            content: message,
            sender: 'user',
            timestamp: new Date()
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

        const messageElement = this.messageRenderer.renderMessage(messageObj);
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
        
        switch (message.type) {
            case MESSAGE_TYPES.HTML:
                div.innerHTML = this.sanitizeHTML(cleanContentWithoutLinks);
                break;
            case MESSAGE_TYPES.MARKDOWN:
                div.innerHTML = this.renderMarkdown(cleanContentWithoutLinks);
                break;
            default:
                div.textContent = cleanContentWithoutLinks;
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
            
            downloadLinks.forEach(link => {
                const linkButton = this.renderDownloadButton(link);
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
        // Ищем ссылки на наши файлы в тексте
        const linkRegex = /(https?:\/\/[^\s]+\/api\/v1\/files\/download\/[^\s]+)/g;
        const downloadLinks = [];
        let cleanContent = content;
        
        let match;
        while ((match = linkRegex.exec(content)) !== null) {
            const url = match[1];
            const fileId = url.split('/').pop();
            
            // Пытаемся извлечь имя файла из контекста
            const contextMatch = content.match(new RegExp(`файла?\\s+"([^"]+)"[^]*?${url.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}`));
            const fileName = contextMatch ? contextMatch[1] : `файл_${fileId}`;
            
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

    // Рендеринг кнопки скачивания
    renderDownloadButton(link) {
        const button = document.createElement('a');
        button.className = 'download-link-button';
        button.href = link.url;
        button.target = '_blank';
        button.download = link.fileName;
        
        button.innerHTML = `
            <i class="bi bi-download"></i>
            <span class="download-text">Скачать ${link.fileName}</span>
        `;
        
        return button;
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
        // Простой рендеринг markdown
        return markdown
            .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
            .replace(/\*(.*?)\*/g, '<em>$1</em>')
            .replace(/\n/g, '<br>');
    }
}

// Экспорт для использования в других модулях
export default ChatManager;
