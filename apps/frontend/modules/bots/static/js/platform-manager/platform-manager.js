/**
 * Platform Manager - управление платформами
 */

import { showNotification } from '/static/js/components/notification.js';

export class PlatformManager {
    constructor(app, modalManager) {
        this.app = app;
        this.modalManager = modalManager;
        this.selectedPlatformType = '';
    }
    
    async openModal(botId) {
        const modal = document.getElementById('add-platform-modal');
        
        if (!modal) {
            console.error('Модальное окно add-platform-modal не найдено');
            return;
        }
        
        this.resetForm();
        modal.dataset.editMode = 'false';
        modal.dataset.editPlatform = '';
        
        try {
            const response = await fetch('/agents/api/v1/admin/variables', {
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            if (response.ok) {
                const varsData = await response.json();
                const select = document.getElementById('platform-token-select');
                
                if (select) {
                    select.innerHTML = '<option value="">-- Выберите переменную --</option>';
                    Object.entries(varsData).forEach(([key, varInfo]) => {
                        const desc = varInfo.description ? ` - ${varInfo.description}` : '';
                        const option = document.createElement('option');
                        option.value = `@var:${key}`;
                        option.textContent = `@var:${key}${desc}`;
                        select.appendChild(option);
                    });
                }
            }
        } catch (err) {
            console.error('Ошибка загрузки переменных:', err);
        }
        
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        
        modal.style.display = 'flex';
        modal.style.position = 'fixed';
        modal.style.top = '0';
        modal.style.left = '0';
        modal.style.width = '100%';
        modal.style.height = '100%';
        modal.style.zIndex = '9999';
        
        document.body.style.overflow = 'hidden';
        
        const modalHeader = modal.querySelector('.modal-header h3');
        if (modalHeader) {
            modalHeader.textContent = 'Добавить канал общения';
        }
        
        console.log('🔧 Модалка открыта, parent:', modal.parentElement.tagName);
    }
    
    closeModal() {
        const modal = document.getElementById('add-platform-modal');
        if (modal) {
            modal.style.display = 'none';
        }
        document.body.style.overflow = 'auto';

        this.resetForm();

        const whatsappContainer = document.getElementById('whatsapp-fields-container');
        if (whatsappContainer) {
            whatsappContainer.remove();
        }
    }
    
    toggleDropdown() {
        const dropdown = document.getElementById('platform-dropdown');
        const selectValue = document.querySelector('.select-value');
        
        const isOpen = dropdown.classList.contains('show');
        
        if (isOpen) {
            dropdown.classList.remove('show');
            selectValue.classList.remove('active');
        } else {
            dropdown.classList.add('show');
            selectValue.classList.add('active');
        }
    }
    
    async selectPlatform(value, icon, text) {
        this.selectedPlatformType = value;
        
        const selectText = document.querySelector('.select-text');
        selectText.innerHTML = `<i class="${icon}"></i> ${text}`;
        
        document.getElementById('platform-dropdown').classList.remove('show');
        document.querySelector('.select-value').classList.remove('active');
        
        await this.updateFields();
    }
    
    collectAllowedUsers() {
        const allowedUsers = [];
        const rows = document.querySelectorAll('#allowed-users-container .allowed-user-row');
        
        rows.forEach(row => {
            const input = row.querySelector('input');
            if (input && input.value.trim()) {
                allowedUsers.push(input.value.trim());
            }
        });
        
        return allowedUsers;
    }
    
    addAllowedUserRow() {
        const container = document.getElementById('allowed-users-container');
        const row = document.createElement('div');
        row.className = 'allowed-user-row';
        row.innerHTML = `
            <input type="text" class="form-control" placeholder="User ID или username" 
                   onchange="updateAllowedUser(this)">
            <button class="btn btn-outline-danger btn-sm" onclick="removeAllowedUserRow(this)">
                <i class="ti ti-trash"></i>
            </button>
        `;
        container.appendChild(row);
    }
    
    removeAllowedUserRow(button) {
        const container = document.getElementById('allowed-users-container');
        const rows = container.querySelectorAll('.allowed-user-row');
        if (rows.length > 1) {
            button.closest('.allowed-user-row').remove();
        } else {
            button.closest('.allowed-user-row').querySelector('input').value = '';
        }
    }
    
    addVariableRow() {
        const container = document.getElementById('custom-variables');
        const row = document.createElement('div');
        row.className = 'variable-row';
        row.innerHTML = `
            <input type="text" class="form-control" placeholder="Ключ" 
                   onchange="updateVariableName(this)">
            <input type="text" class="form-control" placeholder="Значение"
                   onchange="updateVariableValue(this)">
            <button class="btn btn-outline-danger btn-sm" onclick="removeVariableRow(this)">
                <i class="ti ti-trash"></i>
            </button>
        `;
        container.appendChild(row);
    }
    
    removeVariableRow(button) {
        button.closest('.variable-row').remove();
    }
    
    toggleTokenInput() {
        const varGroup = document.getElementById('token-var-select-group');
        const hardcodedGroup = document.getElementById('token-hardcoded-group');
        const varRadio = document.getElementById('token-type-var');
        
        if (varGroup && hardcodedGroup) {
            if (varRadio.checked) {
                varGroup.style.display = 'block';
                hardcodedGroup.style.display = 'none';
            } else {
                varGroup.style.display = 'none';
                hardcodedGroup.style.display = 'block';
            }
        }
    }
    
    async updateFields() {
        const platformType = this.selectedPlatformType;
        const configSection = document.getElementById('platform-config-section');
        
        if (!configSection) {
            console.error('❌ platform-config-section не найден');
            return;
        }
        
        if (platformType) {
            configSection.style.display = 'block';
            
            if (platformType === 'whatsapp') {
                await this.showWhatsAppFields();
            } else {
                this.showStandardFields(platformType);
            }
        } else {
            configSection.style.display = 'none';
        }
    }
    
    showStandardFields(platformType) {
        const tokenField = document.getElementById('platform-token');
        const usernameField = document.getElementById('platform-username');
        
        if (!tokenField || !usernameField) {
            console.error('❌ Поля токена или username не найдены');
            return;
        }
        
        const tokenFormGroup = tokenField.closest('.form-group');
        const usernameFormGroup = usernameField.closest('.form-group');
        
        if (tokenFormGroup) tokenFormGroup.style.display = 'block';
        if (usernameFormGroup) usernameFormGroup.style.display = 'block';
        
        const whatsappFields = document.getElementById('whatsapp-fields-container');
        if (whatsappFields) {
            whatsappFields.style.display = 'none';
        }
        
        tokenField.disabled = false;
        
        const placeholders = {
            'telegram': ['Токен от @BotFather', 'username бота (без @)'],
            'amocrm': ['API ключ AmoCRM', 'Домен (example.amocrm.ru)'],
            'web': ['Не требуется', 'Название чата'],
            'api': ['API ключ (опционально)', 'Название API']
        };
        
        const [tokenPlaceholder, usernamePlaceholder] = placeholders[platformType] || ['Токен каналы', 'Username/ID'];
        tokenField.placeholder = tokenPlaceholder;
        usernameField.placeholder = usernamePlaceholder;
        
        if (platformType === 'web') {
            tokenField.disabled = true;
        }
    }
    
    async showWhatsAppFields() {
        const tokenField = document.getElementById('platform-token');
        const usernameField = document.getElementById('platform-username');
        
        if (tokenField) {
            const tokenFormGroup = tokenField.closest('.form-group');
            if (tokenFormGroup) tokenFormGroup.style.display = 'none';
        }
        if (usernameField) {
            const usernameFormGroup = usernameField.closest('.form-group');
            if (usernameFormGroup) usernameFormGroup.style.display = 'none';
        }
        
        let whatsappContainer = document.getElementById('whatsapp-fields-container');
        
        if (!whatsappContainer) {
            try {
                const response = await fetch('/frontend/bots/platform-fields/whatsapp');
                if (!response.ok) {
                    throw new Error('Не удалось загрузить поля для WhatsApp');
                }
                
                const html = await response.text();
                
                const customVarsSection = document.getElementById('custom-variables').closest('.form-group');
                customVarsSection.insertAdjacentHTML('beforebegin', html);
            } catch (error) {
                console.error('Ошибка загрузки WhatsApp полей:', error);
                showNotification('Не удалось загрузить поля для WhatsApp', 'error');
                return;
            }
        } else {
            whatsappContainer.style.display = 'block';
        }
        
        await this.loadVariablesForWhatsApp();
    }
    
    async loadVariablesForWhatsApp() {
        try {
            const response = await fetch('/agents/api/v1/admin/variables', {
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (response.ok) {
                const varsData = await response.json();
                const variables = Object.entries(varsData).map(([key, info]) => ({
                    key: key,
                    is_secret: info.is_secret || false
                }));
                
                const accessTokenSelect = document.getElementById('whatsapp-access-token-select');
                if (accessTokenSelect) {
                    accessTokenSelect.innerHTML = '<option value="">-- Выберите переменную --</option>';
                    variables.forEach(v => {
                        const option = document.createElement('option');
                        option.value = `@var:${v.key}`;
                        option.textContent = `@var:${v.key}${v.is_secret ? ' 🔒' : ''}`;
                        accessTokenSelect.appendChild(option);
                    });
                }
                
                const verifyTokenSelect = document.getElementById('whatsapp-verify-token-select');
                if (verifyTokenSelect) {
                    verifyTokenSelect.innerHTML = '<option value="">-- Выберите переменную --</option>';
                    variables.forEach(v => {
                        const option = document.createElement('option');
                        option.value = `@var:${v.key}`;
                        option.textContent = `@var:${v.key}${v.is_secret ? ' 🔒' : ''}`;
                        verifyTokenSelect.appendChild(option);
                    });
                }
            }
        } catch (error) {
            console.error('Ошибка загрузки переменных для WhatsApp:', error);
        }
    }
    
    toggleWhatsAppTokenInput() {
        const isVar = document.getElementById('wa-token-type-var').checked;
        document.getElementById('wa-token-var-select-group').style.display = isVar ? 'block' : 'none';
        document.getElementById('wa-token-hardcoded-group').style.display = isVar ? 'none' : 'block';
    }
    
    toggleWhatsAppVerifyInput() {
        const isVar = document.getElementById('wa-verify-type-var').checked;
        document.getElementById('wa-verify-var-select-group').style.display = isVar ? 'block' : 'none';
        document.getElementById('wa-verify-hardcoded-group').style.display = isVar ? 'none' : 'block';
    }
    
    collectWhatsAppConfig() {
        const config = {};
        
        const phoneNumberId = document.getElementById('whatsapp-phone-number-id')?.value;
        if (phoneNumberId) config.phone_number_id = phoneNumberId;
        
        const tokenVarRadio = document.getElementById('wa-token-type-var');
        if (tokenVarRadio && tokenVarRadio.checked) {
            const select = document.getElementById('whatsapp-access-token-select');
            if (select && select.value) config.access_token = select.value;
        } else {
            const input = document.getElementById('whatsapp-access-token');
            if (input && input.value) config.access_token = input.value;
        }
        
        const verifyVarRadio = document.getElementById('wa-verify-type-var');
        if (verifyVarRadio && verifyVarRadio.checked) {
            const select = document.getElementById('whatsapp-verify-token-select');
            if (select && select.value) config.verify_token = select.value;
        } else {
            const input = document.getElementById('whatsapp-verify-token');
            if (input && input.value) config.verify_token = input.value;
        }
        
        const businessAccountId = document.getElementById('whatsapp-business-account-id')?.value;
        if (businessAccountId) config.business_account_id = businessAccountId;
        
        const displayName = document.getElementById('whatsapp-display-name')?.value;
        if (displayName) config.display_name = displayName;
        
        return config;
    }
    
    async registerWhatsApp(flowId) {
        try {
            showNotification('Регистрация WhatsApp...', 'info');
            
            const response = await fetch(`/frontend/api/admin/whatsapp/register/${flowId}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                showNotification('WhatsApp успешно зарегистрирован!', 'success');
                
                if (result.result && result.result.webhook_url) {
                    const urlElement = document.getElementById('whatsapp-webhook-url');
                    if (urlElement) {
                        urlElement.textContent = result.result.webhook_url;
                    }
                }
                
                await this.modalManager.expand(flowId);
            } else {
                const error = await response.json();
                showNotification(`Ошибка регистрации: ${error.detail}`, 'error');
            }
        } catch (error) {
            console.error('Ошибка регистрации WhatsApp:', error);
            showNotification('Ошибка регистрации WhatsApp', 'error');
        }
    }
    
    resetForm() {
        this.selectedPlatformType = '';
        
        const selectText = document.querySelector('.select-text');
        if (selectText) {
            selectText.innerHTML = 'Выберите канал';
        }
        
        const dropdown = document.getElementById('platform-dropdown');
        if (dropdown) {
            dropdown.classList.remove('show');
        }
        
        const selectValue = document.querySelector('.select-value');
        if (selectValue) {
            selectValue.classList.remove('active');
        }
        
        const tokenField = document.getElementById('platform-token');
        const usernameField = document.getElementById('platform-username');
        
        if (tokenField) {
            tokenField.value = '';
            tokenField.disabled = false;
            tokenField.closest('.form-group').style.display = 'block';
        }
        
        if (usernameField) {
            usernameField.value = '';
            usernameField.closest('.form-group').style.display = 'block';
        }
        
        const configSection = document.getElementById('platform-config-section');
        if (configSection) {
            configSection.style.display = 'none';
        }
        
        const whatsappContainer = document.getElementById('whatsapp-fields-container');
        if (whatsappContainer) {
            whatsappContainer.remove();
        }
    }
}

