/**
 * Bots Module - Управление ботами
 * Рефакторенная модульная версия
 */

import { BotModalManager } from './bot-modal/bot-modal.js';
import { BotSettingsManager } from './bot-modal/bot-settings.js';
import { ToolsManager } from './bot-editor/tools-manager.js';
import { MCPManager } from './bot-editor/mcp-manager.js';
import { BotSaver } from './bot-editor/bot-saver.js';
import { PlatformManager } from './platform-manager/platform-manager.js';
import { PlatformSaver } from './platform-manager/platform-saver.js';
import { KnowledgeBaseManager } from './knowledge-base/kb-manager.js';
import { KnowledgeBaseUploader } from './knowledge-base/kb-uploader.js';
import { RemigrationManager } from './utils/remigration.js';
import { copyToClipboard, togglePlatformCollapse, testApiEndpoint } from './utils/bot-utils.js';

export default class BotsModule {
    constructor(app) {
        this.app = app;
        this.name = 'bots';
        this.version = '2.0.0';
        
        this.kbManager = new KnowledgeBaseManager(app.authToken);
        this.toolsManager = new ToolsManager(app.authToken);
        this.mcpManager = new MCPManager(app.authToken);
        this.settingsManager = new BotSettingsManager(app, this.toolsManager, this.kbManager, this.mcpManager);
        this.modal = new BotModalManager(app, this.settingsManager);
        this.saver = new BotSaver(app, this.settingsManager, this.modal);
        this.platformManager = new PlatformManager(app, this.modal);
        this.platformSaver = new PlatformSaver(app, this.platformManager, this.modal);
        this.kbUploader = new KnowledgeBaseUploader(this.kbManager);
        this.remigration = new RemigrationManager(app);
        
        app.botsModule = this;
        app.bots = this;
    }
    
    async init() {
        console.log('🤖 Инициализация Bots модуля v2.0');
        
        this.setupGlobalFunctions();
        this.setupEventListeners();
        this.setupHeaderActions();
        
        return this;
    }
    
    setupGlobalFunctions() {
        window.openBotChat = (botId, botName) => this.modal.openBotChat(botId, botName);
        window.expandBot = (botId) => this.modal.expand(botId);
        window.closeBotModal = () => this.modal.close();
        window.toggleChat = (flowId, botName) => this.modal.toggleChat(flowId, botName);
        window.toggleBotModalFullscreen = () => this.modal.toggleFullscreen();
        window.toggleMobileActionsMenu = () => this.modal.toggleMobileActionsMenu();
        window.closeMobileActionsMenu = () => this.modal.closeMobileActionsMenu();
        window.updateLLMModels = () => this.settingsManager.updateLLMModels();
        window.saveBotSettings = (botId) => this.saver.save(botId);
        window.createBot = () => this.modal.expand('new');
        
        window.addPlatform = (botId) => this.platformManager.openModal(botId);
        window.editPlatform = (botId, platformType) => this.platformSaver.edit(botId, platformType);
        window.toggleTokenInput = () => this.platformManager.toggleTokenInput();
        window.closeAddPlatformModal = () => this.platformManager.closeModal();
        window.togglePlatformDropdown = () => this.platformManager.toggleDropdown();
        window.selectPlatform = (value, icon, text) => this.platformManager.selectPlatform(value, icon, text);
        window.updatePlatformFields = () => this.platformManager.updateFields();
        window.toggleWhatsAppTokenInput = () => this.platformManager.toggleWhatsAppTokenInput();
        window.toggleWhatsAppVerifyInput = () => this.platformManager.toggleWhatsAppVerifyInput();
        window.registerWhatsApp = (flowId) => this.platformManager.registerWhatsApp(flowId);
        window.addVariableRow = () => this.platformManager.addVariableRow();
        window.removeVariableRow = (button) => this.platformManager.removeVariableRow(button);
        window.updateVariableName = (input) => console.log('Variable name updated:', input.value);
        window.updateVariableValue = (input) => console.log('Variable value updated:', input.value);
        window.addAllowedUserRow = () => this.platformManager.addAllowedUserRow();
        window.removeAllowedUserRow = (button) => this.platformManager.removeAllowedUserRow(button);
        window.updateAllowedUser = (input) => console.log('Allowed user updated:', input.value);
        window.savePlatform = (botId) => this.platformSaver.save(botId);
        window.removePlatform = (botId, platformType) => this.platformSaver.remove(botId, platformType);
        
        window.openUploadTextModal = () => this.kbUploader.openTextModal();
        window.closeUploadTextModal = () => this.kbUploader.closeTextModal();
        window.uploadTextFromModal = (flowId) => this.kbUploader.uploadText(flowId);
        window.uploadDocumentToKnowledgeBase = (flowId) => this.kbUploader.uploadDocument(flowId);
        window.loadKnowledgeBaseDocuments = (flowId) => this.kbManager.loadDocuments(flowId);
        window.deleteKnowledgeBaseDocument = (flowId, documentId, event) => this.kbManager.deleteDocument(flowId, documentId, event);
        
        window.remigrateFlowWithDeps = (flowId) => this.remigration.openConfirmModal(flowId);
        window.closeRemigrateModal = () => this.remigration.closeModal();
        window.confirmRemigrate = () => this.remigration.confirmRemigrate();
        
        window.copyToClipboard = (elementIdOrText) => copyToClipboard(elementIdOrText, this.app);
        window.togglePlatformCollapse = (platformName) => togglePlatformCollapse(platformName);
        window.testApiEndpoint = (flowId) => testApiEndpoint(flowId, this.app.authToken);
    }
    
    setupHeaderActions() {
        document.addEventListener('click', (e) => {
            const action = e.target.closest('.btn-plugin-action[data-action]');
            if (!action) return;
            
            const actionType = action.getAttribute('data-action');
            if (!actionType || !actionType.startsWith('bots:')) return;
            
            e.preventDefault();
            
            const [, method] = actionType.split(':');
            
            switch(method) {
                case 'save':
                    const botId = this.getCurrentBotId();
                    if (botId) this.saveBot(botId);
                    break;
                    
                case 'copy_id':
                    const botIdToCopy = this.getCurrentBotId();
                    if (botIdToCopy) {
                        navigator.clipboard.writeText(botIdToCopy).then(() => {
                            if (this.app && this.app.showNotification) {
                                this.app.showNotification('ID скопирован', 'success');
                            }
                        });
                    }
                    break;
                    
                case 'delete':
                    const botIdToDelete = this.getCurrentBotId();
                    if (botIdToDelete && confirm(`Вы уверены, что хотите удалить бота ${botIdToDelete}?`)) {
                        this.deleteBot(botIdToDelete);
                    }
                    break;
                    
                case 'create':
                    this.modal.expand('new');
                    break;
                    
                case 'refresh':
                    const content = document.getElementById('content');
                    if (content) {
                        content.dispatchEvent(new Event('htmx:refresh'));
                    }
                    break;
            }
        });
    }
    
    getCurrentBotId() {
        const modal = document.getElementById('bot-expanded-modal');
        if (modal && modal.style.display === 'flex') {
            const botDetails = document.querySelector('#modal-bot-details');
            if (botDetails) {
                const flowIdInput = botDetails.querySelector('input[name="flow_id"], input[id*="flow_id"]');
                if (flowIdInput) {
                    return flowIdInput.value;
                }
                const form = botDetails.querySelector('form');
                if (form) {
                    const formData = new FormData(form);
                    return formData.get('flow_id') || this.modal.currentBotModal || null;
                }
                return this.modal.currentBotModal || null;
            }
        }
        return null;
    }
    
    setupEventListeners() {
        document.body.addEventListener('htmx:beforeSwap', (event) => {
            if (event.detail.target.id === 'content') {
                const modal = document.getElementById('bot-expanded-modal');
                if (modal && modal.style.display === 'flex') {
                    this.modal.close();
                }
            }
        });
        
        document.addEventListener('fullscreenchange', () => {
            const btn = document.querySelector('.btn-fullscreen i');
            if (btn) {
                if (document.fullscreenElement) {
                    btn.className = 'bi bi-fullscreen-exit';
                } else {
                    btn.className = 'bi bi-fullscreen';
                }
            }
        });
        
        document.addEventListener('click', (e) => {
            const dropdown = document.getElementById('mobile-actions-dropdown');
            const menu = document.querySelector('.mobile-actions-menu');
            
            if (dropdown && dropdown.classList.contains('show') && menu && !menu.contains(e.target)) {
                dropdown.classList.remove('show');
            }
            
            if (e.target.id === 'bot-expanded-modal') {
                this.modal.close();
            }
            
            if (e.target.id === 'add-platform-modal') {
                this.platformManager.closeModal();
            }
            
            if (e.target.id === 'remigrate-confirm-modal') {
                this.remigration.closeModal();
            }
            
            const platformDropdown = document.getElementById('platform-dropdown');
            const customSelect = document.getElementById('platform-type-select');
            
            if (platformDropdown && customSelect && platformDropdown.classList.contains('show')) {
                if (!customSelect.contains(e.target)) {
                    platformDropdown.classList.remove('show');
                    document.querySelector('.select-value')?.classList.remove('active');
                }
            }
        });
        
        document.addEventListener('keydown', (e) => {
            if (e.key === 'Escape') {
                const remigrateModal = document.getElementById('remigrate-confirm-modal');
                if (remigrateModal && remigrateModal.style.display === 'flex') {
                    this.remigration.closeModal();
                } else if (document.getElementById('add-platform-modal')?.style.display === 'flex') {
                    this.platformManager.closeModal();
                } else if (this.modal.currentBotModal) {
                    this.modal.close();
                }
            }
        });
    }
    
    initBotSettings() {
        this.settingsManager.init();
    }
    
    saveBot(botId) {
        if (botId === 'new') {
            this.saver.save('new');
        } else {
            this.saver.save(botId);
        }
    }
    
    async deleteBot(botId) {
        if (!botId || botId === 'new') {
            console.warn('Cannot delete: invalid bot ID');
            return;
        }
        
        try {
            const response = await fetch(`/api/v1/flows/${botId}`, {
                method: 'DELETE',
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`,
                    'Content-Type': 'application/json'
                }
            });
            
            if (response.ok) {
                this.app.showNotification('Бот успешно удален', 'success');
                setTimeout(() => {
                    window.location.href = '/frontend/bots/';
                }, 1000);
            } else {
                const error = await response.json().catch(() => ({ detail: 'Ошибка удаления' }));
                this.app.showNotification(error.detail || 'Ошибка при удалении бота', 'danger');
            }
        } catch (error) {
            console.error('Ошибка при удалении бота:', error);
            this.app.showNotification('Ошибка при удалении бота', 'danger');
        }
    }
    
    destroy() {
        console.log('🧹 Bots модуль выгружен');
    }
}
