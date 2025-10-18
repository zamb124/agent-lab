/**
 * Bots Module - Управление ботами
 */

import { slugify, generateUniqueId } from '/static/js/utils/slugify.js';
import { showNotification } from '/static/js/components/notification.js';

export default class BotsModule {
    constructor(app) {
        this.app = app;
        this.name = 'bots';
        this.version = '1.0.0';
        
        this.currentBotModal = null;
        this.promptEditor = null;
    }
    
    async init() {
        console.log('🤖 Инициализация Bots модуля');
        
        this.setupGlobalFunctions();
        
        return this;
    }
    
    /**
     * Регистрируем глобальные функции для обратной совместимости
     */
    setupGlobalFunctions() {
        window.openBotChat = (botId, botName) => this.openBotChat(botId, botName);
        window.expandBot = (botId) => this.expandBot(botId);
        window.closeExpandedBot = () => this.closeExpandedBot();
        window.editBot = (botId) => this.editBot(botId);
        window.deleteBot = (botId) => this.deleteBot(botId);
        window.deployBot = (botId, platform) => this.deployBot(botId, platform);
    }
    
    /**
     * Открыть чат с ботом
     */
    openBotChat(botId, botName) {
        if (this.app.chat) {
            this.app.chat.open({
                agent_id: botId,
                session_id: null,
                title: botName
            });
        } else {
            console.error('Chat manager не инициализирован');
            alert('Чат недоступен. Попробуйте обновить страницу.');
        }
    }
    
    /**
     * Развернуть детали бота
     */
    async expandBot(botId) {
        const modal = document.getElementById('bot-expanded-modal');
        const modalDetails = document.getElementById('modal-bot-details');
        
        if (!modal || !modalDetails) {
            console.error('Modal elements not found!');
            return;
        }
        
        modalDetails.innerHTML = '<div class="loading-indicator"><div class="spinner"></div><span>Загрузка...</span></div>';
        modal.style.display = 'flex';
        
        try {
            const response = await fetch(`/frontend/bots/${botId}/details`);
            const html = await response.text();
            modalDetails.innerHTML = html;
        } catch (error) {
            console.error('Ошибка загрузки деталей бота:', error);
            modalDetails.innerHTML = '<div class="error">Ошибка загрузки</div>';
        }
    }
    
    /**
     * Закрыть модалку
     */
    closeExpandedBot() {
        const modal = document.getElementById('bot-expanded-modal');
        if (modal) {
            modal.style.display = 'none';
        }
    }
    
    /**
     * Редактировать бота
     */
    async editBot(botId) {
        console.log('Editing bot:', botId);
    }
    
    /**
     * Удалить бота
     */
    async deleteBot(botId) {
        if (!confirm('Вы уверены, что хотите удалить этого бота?')) {
            return;
        }
        
        try {
            const response = await fetch(`/api/v1/bots/${botId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (response.ok) {
                showNotification('Бот успешно удален', 'success');
                htmx.ajax('GET', '/frontend/bots/', {target: '#content'});
            } else {
                throw new Error('Ошибка удаления');
            }
        } catch (error) {
            console.error('Ошибка удаления бота:', error);
            showNotification('Ошибка при удалении бота', 'danger');
        }
    }
    
    /**
     * Развернуть бота на платформе
     */
    async deployBot(botId, platform) {
        console.log('Deploying bot:', botId, 'to', platform);
    }
    
    destroy() {
        console.log('🧹 Bots модуль выгружен');
    }
}

