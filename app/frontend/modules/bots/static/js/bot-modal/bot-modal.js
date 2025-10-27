/**
 * Bot Modal Manager
 */

export class BotModalManager {
    constructor(app, settingsManager) {
        this.app = app;
        this.settingsManager = settingsManager;
        this.currentBotModal = null;
        this.currentBotChat = null;
    }
    
    async expand(botId) {
        const modal = document.getElementById('bot-expanded-modal');
        const modalDetails = document.getElementById('modal-bot-details');
        const listView = document.getElementById('bots-list-view');
        
        if (!modal || !modalDetails) {
            console.error('Modal elements not found!');
            alert('Модалка не найдена в DOM');
            return;
        }
        
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        
        modalDetails.innerHTML = `
            <div class="skeleton-modal" style="padding: 2rem;">
                <div class="skeleton skeleton-text skeleton-width-60" style="height: 2rem; margin-bottom: 1.5rem;"></div>
                <div class="skeleton skeleton-text" style="margin-bottom: 0.75rem;"></div>
                <div class="skeleton skeleton-text skeleton-width-90" style="margin-bottom: 0.75rem;"></div>
                <div class="skeleton skeleton-text skeleton-width-95" style="margin-bottom: 1.5rem;"></div>
                <div class="skeleton skeleton-text skeleton-width-85" style="margin-bottom: 0.75rem;"></div>
                <div class="skeleton skeleton-text skeleton-width-80" style="margin-bottom: 2rem;"></div>
                <div style="display: flex; gap: 1rem;">
                    <div class="skeleton skeleton-button" style="width: 150px;"></div>
                    <div class="skeleton skeleton-button" style="width: 120px;"></div>
                </div>
            </div>
        `;
        modal.style.display = 'flex';
        if (listView) listView.style.display = 'none';
        
        try {
            const response = await fetch(`/frontend/bots/${botId}/details`);
            const html = await response.text();
            
            modalDetails.innerHTML = html;
            
            this.currentBotModal = botId;
            
            this.settingsManager.init();
            
            const layout = modalDetails.querySelector('.bot-details-layout');
            if (layout) {
                layout.classList.add('chat-collapsed');
            }
                
        } catch (error) {
            console.error('Ошибка загрузки деталей бота:', error);
            modalDetails.innerHTML = '<div class="empty-state"><p>Ошибка загрузки деталей бота</p></div>';
        }
    }
    
    close() {
        const modal = document.getElementById('bot-expanded-modal');
        const listView = document.getElementById('bots-list-view');
        
        modal.style.display = 'none';
        if (listView) listView.style.display = 'block';
        
        if (this.settingsManager.promptEditor) {
            this.settingsManager.promptEditor.destroy();
            this.settingsManager.promptEditor = null;
        }
        
        this.currentBotModal = null;
        this.currentBotChat = null;
    }
    
    toggleChat(flowId, botName) {
        const chatSection = document.getElementById(`bot-chat-section-${flowId}`);
        const layout = document.querySelector('.bot-details-layout');
        const toggleBtn = chatSection?.querySelector('.btn-toggle-chat-sidebar');
        const toggleIcon = toggleBtn?.querySelector('i');
        
        if (!chatSection) return;
        
        const isCollapsed = chatSection.classList.contains('collapsed');
        
        if (isCollapsed) {
            chatSection.classList.remove('collapsed');
            if (layout) layout.classList.remove('chat-collapsed');
            if (toggleIcon) toggleIcon.className = 'bi bi-chevron-left';
            if (toggleBtn) toggleBtn.title = 'Свернуть чат';
            
            const placeholder = document.getElementById(`bot-chat-embed-${flowId}`);
            const entryPoint = placeholder?.dataset?.entryPoint;
            
            if (!placeholder.dataset.initialized) {
                this.initEmbeddedChat(flowId, botName, entryPoint);
                placeholder.dataset.initialized = 'true';
            }
        } else {
            chatSection.classList.add('collapsed');
            if (layout) layout.classList.add('chat-collapsed');
            if (toggleIcon) toggleIcon.className = 'bi bi-chevron-right';
            if (toggleBtn) toggleBtn.title = 'Развернуть чат';
        }
    }
    
    initEmbeddedChat(flowId, botName, entryPoint) {
        console.log('Создание нового чата для flow:', flowId);
        
        const placeholder = document.getElementById(`bot-chat-embed-${flowId}`);
        if (!placeholder) {
            console.error('Placeholder не найден');
            return;
        }
        
        const originalChat = document.getElementById('chat-widget');
        if (!originalChat) {
            console.error('Оригинальный чат не найден');
            placeholder.innerHTML = `
                <div style="display: flex; align-items: center; justify-content: center; height: 100%; flex-direction: column; gap: 1rem; color: var(--text-secondary); padding: 2rem;">
                    <i class="bi bi-exclamation-triangle" style="font-size: 3rem;"></i>
                    <h4 style="margin: 0;">Чат не инициализирован</h4>
                    <p>Обновите страницу</p>
                </div>
            `;
            return;
        }
        
        const clonedChat = originalChat.cloneNode(true);
        clonedChat.id = `chat-widget-${flowId}`;
        clonedChat.classList.add('embedded-in-modal');
        clonedChat.style.display = 'flex';
        
        placeholder.innerHTML = '';
        placeholder.appendChild(clonedChat);
        
        this.currentBotChat = {
            flowId: flowId,
            botName: botName,
            widget: clonedChat
        };
        
        setTimeout(() => {
            if (this.app.chat) {
                this.app.chat.open({
                    agent_id: flowId,
                    session_id: null,
                    title: botName
                });
                console.log('Чат активирован для flow:', flowId);
            }
        }, 100);
    }
    
    async toggleFullscreen() {
        const { showNotification } = await import('/static/js/components/notification.js');
        const modalContent = document.querySelector('.bot-modal-content');
        const btn = document.querySelector('.btn-fullscreen i');
        
        if (!modalContent) return;
        
        try {
            if (!document.fullscreenElement) {
                await modalContent.requestFullscreen();
                if (btn) btn.className = 'bi bi-fullscreen-exit';
            } else {
                await document.exitFullscreen();
                if (btn) btn.className = 'bi bi-fullscreen';
            }
        } catch (err) {
            console.error('Ошибка fullscreen:', err);
            showNotification('Не удалось переключить полноэкранный режим', 'warning');
        }
    }
    
    openBotChat(botId, botName) {
        if (this.app && this.app.chat && typeof this.app.chat.open === 'function') {
            this.app.chat.open({
                agent_id: botId,
                session_id: null,
                title: botName
            });
        } else {
            console.error('Chat manager не инициализирован:', {
                app: !!this.app,
                chat: !!this.app?.chat,
                openMethod: typeof this.app?.chat?.open
            });
            alert('Чат недоступен. Попробуйте обновить страницу.');
        }
    }
    
    toggleMobileActionsMenu() {
        const dropdown = document.getElementById('mobile-actions-dropdown');
        if (dropdown) {
            dropdown.classList.toggle('show');
        }
    }
    
    closeMobileActionsMenu() {
        const dropdown = document.getElementById('mobile-actions-dropdown');
        if (dropdown) {
            dropdown.classList.remove('show');
        }
    }
    
    getCurrentBotId() {
        return this.currentBotModal;
    }
}

