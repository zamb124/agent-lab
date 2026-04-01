/**
 * Humanitec Chat Widget - Встраиваемый виджет чата
 * Самодостаточный ES6 модуль без внешних зависимостей
 * 
 * Использование:
 * <script src="https://cdn.humanitec.ru/embed/chat-widget.min.js"></script>
 * <script>
 *   new HumanitecChat({
 *     embedId: 'embed_abc123',
 *     baseUrl: 'https://api.humanitec.ru'
 *   });
 * </script>
 */

(function() {
    'use strict';
    
    class HumanitecChat {
        constructor(config) {
            this.embedId = config.embedId;
            this.baseUrl = config.baseUrl || 'https://api.humanitec.ru';
            this.settings = null;
            this.eventSource = null;
            this.contextId = `ctx_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            this.messages = [];
            this.isOpen = false;
            /** @type {Record<string, unknown> | null} */
            this._flowsStrings = null;
            
            this.init();
        }
        
        async init() {
            try {
                await this.loadSettings();
                await this.loadI18n();
                this.render();
                this.attachEventListeners();
            } catch (error) {
                console.error('[HumanitecChat] Ошибка инициализации:', error);
            }
        }

        /**
         * Тексты виджета из GET /api/i18n/{locale} → namespace flows (см. core/i18n/translations).
         */
        async loadI18n() {
            const raw = navigator.language || 'en';
            const lang = raw.split('-')[0].toLowerCase();
            const locale = lang === 'ru' ? 'ru' : 'en';
            const response = await fetch(`${this.baseUrl}/api/i18n/${locale}`);
            if (!response.ok) {
                throw new Error(`HumanitecChat: i18n HTTP ${response.status}`);
            }
            const data = await response.json();
            const flows = data.flows;
            if (
                !flows ||
                typeof flows.chat_widget !== 'object' ||
                flows.chat_widget === null ||
                typeof flows.chat_widget.err_send !== 'string' ||
                typeof flows.chat_widget.err_process !== 'string'
            ) {
                throw new Error('HumanitecChat: flows.chat_widget i18n incomplete');
            }
            this._flowsStrings = flows;
        }

        /**
         * @param {string} key путь от корня flows.json, например chat_widget.err_send
         */
        _flowsT(key) {
            const parts = key.split('.');
            let node = this._flowsStrings;
            for (const p of parts) {
                if (node === undefined || node === null) {
                    throw new Error(`HumanitecChat i18n missing: flows.${key}`);
                }
                node = node[p];
            }
            if (typeof node !== 'string') {
                throw new Error(`HumanitecChat i18n not a string: flows.${key}`);
            }
            return node;
        }
        
        async loadSettings() {
            const response = await fetch(
                `${this.baseUrl}/flows/api/v1/embed/${this.embedId}/settings`
            );
            
            if (!response.ok) {
                throw new Error(`Не удалось загрузить настройки: ${response.status}`);
            }
            
            const data = await response.json();
            this.settings = data;
        }
        
        render() {
            const container = document.createElement('div');
            container.id = 'humanitec-chat-widget';
            
            const isDark = this.settings.theme === 'dark' || 
                          (this.settings.theme === 'auto' && window.matchMedia('(prefers-color-scheme: dark)').matches);
            
            container.innerHTML = `
                <style>
                    #humanitec-chat-widget {
                        position: fixed;
                        ${this.getPositionStyles()}
                        z-index: 999999;
                        font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
                    }
                    
                    .hc-toggle-button {
                        width: 60px;
                        height: 60px;
                        border-radius: 50%;
                        background: ${this.settings.primary_color};
                        border: none;
                        cursor: pointer;
                        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.15);
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.3s ease;
                    }
                    
                    .hc-toggle-button:hover {
                        transform: scale(1.1);
                        box-shadow: 0 6px 20px rgba(0, 0, 0, 0.2);
                    }
                    
                    .hc-toggle-button svg {
                        width: 28px;
                        height: 28px;
                        fill: white;
                    }
                    
                    .hc-chat-window {
                        display: none;
                        width: 380px;
                        height: 600px;
                        background: ${isDark ? '#1a1a2e' : '#ffffff'};
                        border-radius: 16px;
                        box-shadow: 0 8px 40px rgba(0, 0, 0, 0.3);
                        flex-direction: column;
                        overflow: hidden;
                        ${this.settings.position.includes('bottom') ? 'margin-bottom: 80px;' : 'margin-top: 80px;'}
                    }
                    
                    .hc-chat-window.open {
                        display: flex;
                    }
                    
                    .hc-header {
                        padding: 20px;
                        background: ${this.settings.primary_color};
                        color: white;
                        display: flex;
                        justify-content: space-between;
                        align-items: center;
                    }
                    
                    .hc-header-title {
                        font-size: 18px;
                        font-weight: 600;
                    }
                    
                    .hc-close-btn {
                        background: transparent;
                        border: none;
                        color: white;
                        cursor: pointer;
                        font-size: 24px;
                        padding: 0;
                        width: 28px;
                        height: 28px;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                    }
                    
                    .hc-messages {
                        flex: 1;
                        overflow-y: auto;
                        padding: 20px;
                        background: ${isDark ? '#0f0f1a' : '#f5f5f5'};
                    }
                    
                    .hc-message {
                        margin-bottom: 16px;
                        display: flex;
                        flex-direction: column;
                    }
                    
                    .hc-message.user {
                        align-items: flex-end;
                    }
                    
                    .hc-message-bubble {
                        max-width: 75%;
                        padding: 12px 16px;
                        border-radius: 12px;
                        word-wrap: break-word;
                    }
                    
                    .hc-message.user .hc-message-bubble {
                        background: ${this.settings.primary_color};
                        color: white;
                    }
                    
                    .hc-message.assistant .hc-message-bubble {
                        background: ${isDark ? '#2a2a3e' : '#ffffff'};
                        color: ${isDark ? '#e0e0e0' : '#333333'};
                        border: 1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'};
                    }
                    
                    .hc-message-reasoning {
                        font-size: 11px;
                        color: ${isDark ? '#999' : '#666'};
                        margin-top: 6px;
                        padding: 8px;
                        background: ${isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)'};
                        border-radius: 6px;
                        max-width: 75%;
                    }
                    
                    .hc-message-tool {
                        font-size: 11px;
                        color: ${this.settings.primary_color};
                        margin-top: 6px;
                        font-family: 'Courier New', monospace;
                        max-width: 75%;
                    }
                    
                    .hc-input-container {
                        padding: 16px;
                        background: ${isDark ? '#1a1a2e' : '#ffffff'};
                        border-top: 1px solid ${isDark ? 'rgba(255,255,255,0.1)' : 'rgba(0,0,0,0.1)'};
                        display: flex;
                        gap: 8px;
                    }
                    
                    .hc-input {
                        flex: 1;
                        padding: 12px 16px;
                        border: 1px solid ${isDark ? 'rgba(255,255,255,0.2)' : 'rgba(0,0,0,0.2)'};
                        border-radius: 24px;
                        background: ${isDark ? '#2a2a3e' : '#f5f5f5'};
                        color: ${isDark ? '#e0e0e0' : '#333'};
                        font-size: 14px;
                        outline: none;
                        transition: all 0.2s;
                    }
                    
                    .hc-input:focus {
                        border-color: ${this.settings.primary_color};
                    }
                    
                    .hc-send-btn {
                        width: 44px;
                        height: 44px;
                        border-radius: 50%;
                        background: ${this.settings.primary_color};
                        border: none;
                        cursor: pointer;
                        display: flex;
                        align-items: center;
                        justify-content: center;
                        transition: all 0.2s;
                    }
                    
                    .hc-send-btn:hover {
                        transform: scale(1.05);
                    }
                    
                    .hc-send-btn:disabled {
                        opacity: 0.5;
                        cursor: not-allowed;
                    }
                    
                    .hc-send-btn svg {
                        width: 20px;
                        height: 20px;
                        fill: white;
                    }
                    
                    .hc-typing-indicator {
                        display: flex;
                        gap: 4px;
                        padding: 12px 16px;
                    }
                    
                    .hc-typing-dot {
                        width: 8px;
                        height: 8px;
                        border-radius: 50%;
                        background: ${isDark ? '#666' : '#ccc'};
                        animation: typing 1.4s infinite;
                    }
                    
                    .hc-typing-dot:nth-child(2) {
                        animation-delay: 0.2s;
                    }
                    
                    .hc-typing-dot:nth-child(3) {
                        animation-delay: 0.4s;
                    }
                    
                    @keyframes typing {
                        0%, 60%, 100% {
                            transform: translateY(0);
                            opacity: 0.5;
                        }
                        30% {
                            transform: translateY(-10px);
                            opacity: 1;
                        }
                    }
                    
                    ${this.settings.branding ? `
                    .hc-branding {
                        text-align: center;
                        padding: 8px;
                        font-size: 11px;
                        color: ${isDark ? '#666' : '#999'};
                        border-top: 1px solid ${isDark ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.05)'};
                    }
                    
                    .hc-branding a {
                        color: ${this.settings.primary_color};
                        text-decoration: none;
                    }
                    ` : ''}
                    
                    @media (max-width: 480px) {
                        .hc-chat-window {
                            width: var(--app-vw, 100vw);
                            height: var(--app-vh, 100vh);
                            border-radius: 0;
                            margin: 0;
                        }
                    }
                </style>
                
                <button class="hc-toggle-button" id="hc-toggle">
                    <svg viewBox="0 0 24 24">
                        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10h10V12c0-5.52-4.48-10-10-10zm0 18c-4.41 0-8-3.59-8-8s3.59-8 8-8 8 3.59 8 8-3.59 8-8 8z"/>
                        <path d="M8.5 11c.83 0 1.5-.67 1.5-1.5S9.33 8 8.5 8 7 8.67 7 9.5 7.67 11 8.5 11zm7 0c.83 0 1.5-.67 1.5-1.5S16.33 8 15.5 8 14 8.67 14 9.5s.67 1.5 1.5 1.5zm-3.5 6.5c2.33 0 4.31-1.46 5.11-3.5H6.89c.8 2.04 2.78 3.5 5.11 3.5z"/>
                    </svg>
                </button>
                
                <div class="hc-chat-window" id="hc-window">
                    <div class="hc-header">
                        <div class="hc-header-title">AI Assistant</div>
                        <button class="hc-close-btn" id="hc-close">&times;</button>
                    </div>
                    
                    <div class="hc-messages" id="hc-messages">
                        ${this.settings.greeting_message ? `
                            <div class="hc-message assistant">
                                <div class="hc-message-bubble">${this.escapeHtml(this.settings.greeting_message)}</div>
                            </div>
                        ` : ''}
                    </div>
                    
                    <div class="hc-input-container">
                        <input 
                            type="text" 
                            class="hc-input" 
                            id="hc-input"
                            placeholder="${this.escapeHtml(this.settings.placeholder)}"
                        />
                        <button class="hc-send-btn" id="hc-send">
                            <svg viewBox="0 0 24 24">
                                <path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
                            </svg>
                        </button>
                    </div>
                    
                    ${this.settings.branding ? `
                        <div class="hc-branding">
                            Powered by <a href="https://humanitec.ru" target="_blank">Humanitec</a>
                        </div>
                    ` : ''}
                </div>
            `;
            
            document.body.appendChild(container);
        }
        
        getPositionStyles() {
            const positions = {
                'bottom-right': 'bottom: 20px; right: 20px;',
                'bottom-left': 'bottom: 20px; left: 20px;',
                'top-right': 'top: 20px; right: 20px;',
                'top-left': 'top: 20px; left: 20px;'
            };
            return positions[this.settings.position] || positions['bottom-right'];
        }
        
        attachEventListeners() {
            const toggleBtn = document.getElementById('hc-toggle');
            const closeBtn = document.getElementById('hc-close');
            const sendBtn = document.getElementById('hc-send');
            const input = document.getElementById('hc-input');
            
            toggleBtn.addEventListener('click', () => this.toggleChat());
            closeBtn.addEventListener('click', () => this.toggleChat());
            sendBtn.addEventListener('click', () => this.sendMessage());
            
            input.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && input.value.trim()) {
                    this.sendMessage();
                }
            });
        }
        
        toggleChat() {
            this.isOpen = !this.isOpen;
            const window = document.getElementById('hc-window');
            window.classList.toggle('open', this.isOpen);
            
            if (this.isOpen) {
                document.getElementById('hc-input').focus();
            }
        }
        
        async sendMessage() {
            const input = document.getElementById('hc-input');
            const message = input.value.trim();
            
            if (!message) return;
            
            input.value = '';
            input.disabled = true;
            document.getElementById('hc-send').disabled = true;
            
            this.addMessage(message, 'user');
            this.showTyping();
            
            try {
                await this.streamResponse(message);
            } catch (error) {
                console.error('[HumanitecChat] Ошибка отправки:', error);
                this.hideTyping();
                this.addMessage(this._flowsT('chat_widget.err_send'), 'assistant');
            } finally {
                input.disabled = false;
                document.getElementById('hc-send').disabled = false;
                input.focus();
            }
        }
        
        async streamResponse(message) {
            const url = new URL(`${this.baseUrl}/flows/api/v1/embed/${this.embedId}/stream`);
            url.searchParams.set('message', message);
            url.searchParams.set('context_id', this.contextId);
            
            if (this.eventSource) {
                this.eventSource.close();
            }
            
            this.eventSource = new EventSource(url.toString());
            
            let currentMessageId = null;
            let currentText = '';
            
            this.eventSource.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    
                    if (data.error) {
                        console.error('[HumanitecChat] Ошибка от сервера:', data.error);
                        this.hideTyping();
                        this.addMessage(this._flowsT('chat_widget.err_process'), 'assistant');
                        this.eventSource.close();
                        return;
                    }
                    
                    const result = data.result;
                    if (!result) return;
                    
                    if (result.kind === 'artifact-update') {
                        this.hideTyping();
                        
                        const artifact = result.artifact;
                        if (artifact?.parts) {
                            const text = artifact.parts
                                .filter(p => p.type === 'text')
                                .map(p => p.text)
                                .join('');
                            
                            if (text && text !== currentText) {
                                currentText = text;
                                
                                if (!currentMessageId) {
                                    currentMessageId = this.addMessage(text, 'assistant');
                                } else {
                                    this.updateMessage(currentMessageId, text);
                                }
                            }
                        }
                        
                        if (this.settings.show_reasoning && artifact?.reasoning) {
                            this.addReasoning(currentMessageId, artifact.reasoning);
                        }
                        
                        if (this.settings.show_tool_calls && artifact?.tool_calls) {
                            this.addToolCalls(currentMessageId, artifact.tool_calls);
                        }
                        
                        if (artifact?.state === 'complete') {
                            this.eventSource.close();
                        }
                    }
                } catch (error) {
                    console.error('[HumanitecChat] Ошибка парсинга:', error);
                }
            };
            
            this.eventSource.onerror = (error) => {
                console.error('[HumanitecChat] SSE ошибка:', error);
                this.hideTyping();
                this.eventSource.close();
            };
        }
        
        addMessage(text, role) {
            const messagesContainer = document.getElementById('hc-messages');
            const messageId = `msg_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
            
            const messageEl = document.createElement('div');
            messageEl.className = `hc-message ${role}`;
            messageEl.id = messageId;
            messageEl.innerHTML = `
                <div class="hc-message-bubble">${this.escapeHtml(text)}</div>
            `;
            
            messagesContainer.appendChild(messageEl);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
            
            return messageId;
        }
        
        updateMessage(messageId, text) {
            const messageEl = document.getElementById(messageId);
            if (messageEl) {
                const bubble = messageEl.querySelector('.hc-message-bubble');
                if (bubble) {
                    bubble.textContent = text;
                }
                
                const messagesContainer = document.getElementById('hc-messages');
                messagesContainer.scrollTop = messagesContainer.scrollHeight;
            }
        }
        
        addReasoning(messageId, reasoning) {
            const messageEl = document.getElementById(messageId);
            if (messageEl && !messageEl.querySelector('.hc-message-reasoning')) {
                const reasoningEl = document.createElement('div');
                reasoningEl.className = 'hc-message-reasoning';
                reasoningEl.textContent = `💭 ${reasoning}`;
                messageEl.appendChild(reasoningEl);
            }
        }
        
        addToolCalls(messageId, toolCalls) {
            const messageEl = document.getElementById(messageId);
            if (messageEl && !messageEl.querySelector('.hc-message-tool')) {
                const toolEl = document.createElement('div');
                toolEl.className = 'hc-message-tool';
                toolEl.textContent = `🔧 ${toolCalls.map(t => t.name).join(', ')}`;
                messageEl.appendChild(toolEl);
            }
        }
        
        showTyping() {
            const messagesContainer = document.getElementById('hc-messages');
            const typingEl = document.createElement('div');
            typingEl.className = 'hc-message assistant';
            typingEl.id = 'hc-typing';
            typingEl.innerHTML = `
                <div class="hc-message-bubble">
                    <div class="hc-typing-indicator">
                        <div class="hc-typing-dot"></div>
                        <div class="hc-typing-dot"></div>
                        <div class="hc-typing-dot"></div>
                    </div>
                </div>
            `;
            messagesContainer.appendChild(typingEl);
            messagesContainer.scrollTop = messagesContainer.scrollHeight;
        }
        
        hideTyping() {
            const typingEl = document.getElementById('hc-typing');
            if (typingEl) {
                typingEl.remove();
            }
        }
        
        escapeHtml(text) {
            const div = document.createElement('div');
            div.textContent = text;
            return div.innerHTML;
        }
    }
    
    window.HumanitecChat = HumanitecChat;
})();


