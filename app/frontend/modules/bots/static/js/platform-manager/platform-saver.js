/**
 * Platform Saver
 */

import { showNotification } from '/static/js/components/notification.js';

export class PlatformSaver {
    constructor(app, platformManager, modalManager) {
        this.app = app;
        this.platformManager = platformManager;
        this.modalManager = modalManager;
    }
    
    async save(botId) {
        const modal = document.getElementById('add-platform-modal');
        const isEditMode = modal && modal.dataset.editMode === 'true';
        const editPlatformType = modal ? modal.dataset.editPlatform : '';
        
        const platformType = isEditMode ? editPlatformType : this.platformManager.selectedPlatformType;
        
        if (!platformType) {
            showNotification('Выберите тип каналы', 'warning');
            return;
        }

        let platformConfig = {};
        let savedToken = null;
        let savedUsername = null;
        
        const allowedUsers = this.platformManager.collectAllowedUsers();
        if (allowedUsers.length > 0) {
            platformConfig.allowed_users = allowedUsers;
        }
        
        if (platformType === 'whatsapp') {
            const whatsappConfig = this.platformManager.collectWhatsAppConfig();
            platformConfig = { ...platformConfig, ...whatsappConfig };
            
            if (!platformConfig.phone_number_id) {
                showNotification('Phone Number ID обязателен для WhatsApp', 'warning');
                return;
            }
            if (!platformConfig.access_token) {
                showNotification('Access Token обязателен для WhatsApp', 'warning');
                return;
            }
            if (!platformConfig.verify_token) {
                showNotification('Verify Token обязателен для WhatsApp', 'warning');
                return;
            }
        } else {
            const usernameInput = document.getElementById('platform-username');
            savedUsername = usernameInput?.value?.trim() || '';
            
            if (!savedUsername) {
                showNotification('Введите username/ID для каналы', 'warning');
                return;
            }
            
            let finalToken = '';
            const varRadio = document.getElementById('token-type-var');
            const isVarReference = varRadio && varRadio.checked;
            
            if (isVarReference) {
                const select = document.getElementById('platform-token-select');
                finalToken = select?.value?.trim() || '';
                
                if (!finalToken) {
                    showNotification('Выберите переменную с токеном', 'warning');
                    return;
                }
            } else {
                const input = document.getElementById('platform-token');
                finalToken = input?.value?.trim() || '';
                
                if (!finalToken) {
                    showNotification('Введите токен для каналы', 'warning');
                    return;
                }
                
                savedToken = finalToken;
            }
            
            platformConfig.token = finalToken;
            platformConfig.username = savedUsername;

            const variableRows = document.querySelectorAll('#custom-variables .variable-row');
            variableRows.forEach(row => {
                const keyInput = row.querySelector('input[placeholder="Ключ"]');
                const valueInput = row.querySelector('input[placeholder="Значение"]');
                
                if (keyInput?.value && valueInput?.value) {
                    platformConfig[keyInput.value] = valueInput.value;
                }
            });
        }

        if (botId === 'new') {
            showNotification('Сначала создайте бота, затем добавляйте каналы', 'warning');
            return;
        }

        try {
            const currentFlowResponse = await fetch(`/frontend/api/flows/${botId}`, {
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (!currentFlowResponse.ok) {
                const errorData = await currentFlowResponse.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Не удалось загрузить текущие настройки');
            }

            const currentFlow = await currentFlowResponse.json();
            
            if (!currentFlow.platforms) {
                currentFlow.platforms = {};
            }
            currentFlow.platforms[platformType] = platformConfig;

            if (savedToken && savedUsername) {
                const tokenResponse = await fetch('/api/v1/admin/tokens', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.app.authToken}`
                    },
                    body: JSON.stringify({
                        platform: platformType,
                        username: savedUsername,
                        token: savedToken
                    })
                });
                
                if (!tokenResponse.ok) {
                    const error = await tokenResponse.json().catch(() => ({}));
                    console.error('❌ Ошибка сохранения токена:', error);
                    throw new Error(error.detail || 'Не удалось сохранить токен');
                }
            }

            const updateResponse = await fetch(`/frontend/api/flows/${botId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.app.authToken}`
                },
                body: JSON.stringify({ platforms: currentFlow.platforms })
            });

            if (!updateResponse.ok) {
                const errorData = await updateResponse.json().catch(() => ({}));
                const errorMessage = errorData.detail || `HTTP ${updateResponse.status}: ${updateResponse.statusText}`;
                throw new Error(errorMessage);
            }

            showNotification(`Канал ${platformType} добавлен`, 'success');
            this.platformManager.closeModal();
            
            await this.modalManager.expand(botId);

        } catch (error) {
            console.error('❌ Ошибка добавления каналы:', error);
            showNotification('Ошибка добавления каналы: ' + error.message, 'danger');
        }
    }
    
    async remove(botId, platformType) {
        if (!confirm(`Удалить канал ${platformType}?`)) {
            return;
        }

        try {
            const currentFlowResponse = await fetch(`/frontend/api/flows/${botId}`, {
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (!currentFlowResponse.ok) {
                throw new Error('Не удалось загрузить текущие настройки');
            }

            const currentFlow = await currentFlowResponse.json();
            
            if (currentFlow.platforms && currentFlow.platforms[platformType]) {
                delete currentFlow.platforms[platformType];
                
                const updateResponse = await fetch(`/frontend/api/flows/${botId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${this.app.authToken}`
                    },
                    body: JSON.stringify({
                        platforms: currentFlow.platforms
                    })
                });

                if (!updateResponse.ok) {
                    throw new Error('Не удалось удалить канал');
                }

                showNotification(`Канал ${platformType} удален`, 'success');
                
                await this.modalManager.expand(botId);
            }

        } catch (error) {
            console.error('Ошибка удаления каналы:', error);
            showNotification('Ошибка удаления каналы: ' + error.message, 'danger');
        }
    }
    
    async edit(botId, platformType) {
        try {
            const response = await fetch(`/frontend/api/flows/${botId}`, {
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (!response.ok) {
                throw new Error('Не удалось загрузить настройки flow');
            }
            
            const flowData = await response.json();
            const platformConfig = flowData.platforms[platformType];
            
            if (!platformConfig) {
                throw new Error('Канал не найден');
            }
            
            await this.platformManager.openModal(botId);
            
            const modal = document.getElementById('add-platform-modal');
            modal.dataset.editMode = 'true';
            modal.dataset.editPlatform = platformType;
            
            const modalHeader = modal.querySelector('.modal-header h3');
            if (modalHeader) {
                modalHeader.textContent = 'Редактировать канал';
            }
            
            const platformIcons = {
                'telegram': 'bi-telegram',
                'whatsapp': 'bi-whatsapp',
                'web': 'bi-globe',
                'api': 'bi-code-slash',
                'amocrm': 'bi-building'
            };
            
            const platformNames = {
                'telegram': 'Telegram',
                'whatsapp': 'WhatsApp',
                'web': 'Web Chat',
                'api': 'REST API',
                'amocrm': 'AmoCRM'
            };
            
            await this.platformManager.selectPlatform(platformType, platformIcons[platformType] || 'bi-gear', platformNames[platformType] || platformType);
            
            await new Promise(resolve => setTimeout(resolve, 100));
            
            this.fillFormData(platformConfig, platformType);
            
        } catch (error) {
            console.error('Ошибка загрузки данных каналы:', error);
            showNotification('Не удалось загрузить настройки каналы: ' + error.message, 'danger');
        }
    }
    
    fillFormData(platformConfig, platformType) {
        if (platformConfig.allowed_users && Array.isArray(platformConfig.allowed_users)) {
            const container = document.getElementById('allowed-users-container');
            if (container) {
                container.innerHTML = '';
                platformConfig.allowed_users.forEach(user => {
                    const row = document.createElement('div');
                    row.className = 'allowed-user-row';
                    row.innerHTML = `
                        <input type="text" class="form-control" placeholder="User ID или username" 
                               value="${user}" onchange="updateAllowedUser(this)">
                        <button class="btn btn-outline-danger btn-sm" onclick="removeAllowedUserRow(this)">
                            <i class="bi bi-trash"></i>
                        </button>
                    `;
                    container.appendChild(row);
                });
                
                if (platformConfig.allowed_users.length === 0) {
                    this.platformManager.addAllowedUserRow();
                }
            }
        }
        
        if (platformType === 'whatsapp') {
            if (platformConfig.phone_number_id) {
                const phoneInput = document.getElementById('whatsapp-phone-number-id');
                if (phoneInput) phoneInput.value = platformConfig.phone_number_id;
            }
            
            if (platformConfig.access_token) {
                if (platformConfig.access_token.startsWith('@var:')) {
                    document.getElementById('wa-token-type-var').checked = true;
                    this.platformManager.toggleWhatsAppTokenInput();
                    const select = document.getElementById('whatsapp-access-token-select');
                    if (select) select.value = platformConfig.access_token;
                } else {
                    document.getElementById('wa-token-type-hardcoded').checked = true;
                    this.platformManager.toggleWhatsAppTokenInput();
                    const input = document.getElementById('whatsapp-access-token');
                    if (input) input.value = platformConfig.access_token;
                }
            }
        } else {
            if (platformConfig.username) {
                const usernameInput = document.getElementById('platform-username');
                if (usernameInput) usernameInput.value = platformConfig.username;
            }
            
            if (platformConfig.token) {
                if (platformConfig.token.startsWith('@var:')) {
                    document.getElementById('token-type-var').checked = true;
                    this.platformManager.toggleTokenInput();
                    const select = document.getElementById('platform-token-select');
                    if (select) select.value = platformConfig.token;
                } else {
                    document.getElementById('token-type-hardcoded').checked = true;
                    this.platformManager.toggleTokenInput();
                    const input = document.getElementById('platform-token');
                    if (input) input.value = platformConfig.token;
                }
            }
        }
    }
}

