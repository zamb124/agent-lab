/**
 * Управление ботами
 */

(function() {
    'use strict';
    
    let currentBotModal = null;
    let currentBotChat = null;
    let promptEditor = null;

    window.openBotChat = function(botId, botName) {
        if (window.app && window.app.chat) {
            window.app.chat.open({
                agent_id: botId,
                session_id: null,
                title: botName
            });
        } else {
            console.error('Chat manager не инициализирован');
            alert('Чат недоступен. Попробуйте обновить страницу.');
        }
    };

    window.expandBot = async function(botId) {
        const modal = document.getElementById('bot-expanded-modal');
        const modalDetails = document.getElementById('modal-bot-details');
        const listView = document.getElementById('bots-list-view');
        
        modalDetails.innerHTML = '<div class="loading-indicator"><div class="spinner"></div><span>Загрузка...</span></div>';
        modal.style.display = 'flex';
        if (listView) listView.style.display = 'none';
        
        try {
            const response = await fetch(`/frontend/bots/${botId}/details`);
            const html = await response.text();
            
            modalDetails.innerHTML = html;
            
        currentBotModal = botId;
        
        initBotSettings();
        
        const layout = modalDetails.querySelector('.bot-details-layout');
        if (layout) {
            layout.classList.add('chat-collapsed');
        }
            
        } catch (error) {
            console.error('Ошибка загрузки деталей бота:', error);
            modalDetails.innerHTML = '<div class="empty-state"><p>Ошибка загрузки деталей бота</p></div>';
        }
    };

    window.toggleChat = function(flowId, botName) {
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
                initEmbeddedChat(flowId, botName, entryPoint);
                placeholder.dataset.initialized = 'true';
            }
        } else {
            chatSection.classList.add('collapsed');
            if (layout) layout.classList.add('chat-collapsed');
            if (toggleIcon) toggleIcon.className = 'bi bi-chevron-right';
            if (toggleBtn) toggleBtn.title = 'Развернуть чат';
        }
    };

    function initEmbeddedChat(flowId, botName, entryPoint) {
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
        
        currentBotChat = {
            flowId: flowId,
            botName: botName,
            widget: clonedChat
        };
        
        setTimeout(() => {
            if (window.app && window.app.chat) {
                window.app.chat.open({
                    agent_id: flowId,
                    session_id: null,
                    title: botName
                });
                console.log('Чат активирован для flow:', flowId);
            }
        }, 100);
    }

    window.toggleBotModalFullscreen = async function() {
        const modalContent = document.querySelector('.bot-modal-content');
        const btn = document.querySelector('.btn-fullscreen i');
        
        if (!modalContent) return;
        
        try {
            if (!document.fullscreenElement) {
                // Входим в fullscreen
                await modalContent.requestFullscreen();
                if (btn) btn.className = 'bi bi-fullscreen-exit';
            } else {
                // Выходим из fullscreen
                await document.exitFullscreen();
                if (btn) btn.className = 'bi bi-fullscreen';
            }
        } catch (err) {
            console.error('Ошибка fullscreen:', err);
            showNotification('Не удалось переключить полноэкранный режим', 'warning');
        }
    };
    
    // Обработчик изменения fullscreen состояния
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

    window.closeBotModal = function() {
        const modal = document.getElementById('bot-expanded-modal');
        const listView = document.getElementById('bots-list-view');
        
        modal.style.display = 'none';
        if (listView) listView.style.display = 'block';
        
        // Уничтожаем prompt editor
        if (promptEditor) {
            promptEditor.destroy();
            promptEditor = null;
        }
        
        currentBotModal = null;
        currentBotChat = null;
    };
    
    function initBotSettings() {
        const tabs = document.querySelectorAll('.settings-tab');
        const panels = document.querySelectorAll('.settings-panel');
        
        tabs.forEach(tab => {
            tab.addEventListener('click', () => {
                const targetPanel = tab.dataset.tab;
                
                tabs.forEach(t => t.classList.remove('active'));
                panels.forEach(p => p.classList.remove('active'));
                
                tab.classList.add('active');
                const panel = document.querySelector(`[data-panel="${targetPanel}"]`);
                if (panel) {
                    panel.classList.add('active');
                    
                    // Инициализируем Prompt Editor при переключении на вкладку "Основное"
                    if (targetPanel === 'main' && !promptEditor) {
                        initPromptEditor();
                    }
                }
            });
        });
        
        // Инициализируем prompt editor сразу для активной вкладки "Основное"
        const activePanel = document.querySelector('.settings-panel.active');
        if (activePanel && activePanel.dataset.panel === 'main') {
            initPromptEditor();
        }
    }
    
    function initPromptEditor() {
        const container = document.getElementById('bot-prompt-editor-container');
        if (!container) {
            console.error('Контейнер для prompt editor не найден');
            return;
        }
        
        // Получаем данные из DOM
        const botCard = document.querySelector('.bot-details-content');
        const flowId = currentBotModal;
        const promptData = container.dataset.prompt || '';
        
        // Создаем редактор через app
        if (window.app && window.app.createPromptEditor) {
            promptEditor = window.app.createPromptEditor(container, {
                initialValue: promptData,
                flowId: flowId,
                placeholder: 'Введите системный промпт для агента...\n\nИспользуйте {переменные} для подстановки значений.',
                onChange: (value) => {
                    console.log('Промпт изменен');
                },
                onVariablesChange: (type, variables) => {
                    console.log(`Переменные ${type} изменены:`, variables);
                }
            });
            
            console.log('✅ Prompt Editor инициализирован для bot:', flowId);
        } else {
            console.error('app.createPromptEditor недоступен');
        }
    }

    window.saveBotSettings = async function(botId) {
        const flowData = {
            name: document.getElementById('bot-name')?.value,
            description: document.getElementById('bot-description')?.value,
            timeout: document.getElementById('bot-timeout')?.value || null,
            max_retries: parseInt(document.getElementById('bot-max-retries')?.value) || 0,
        };
        
        // Собираем конфигурацию платформ (БЕЗ токенов)
        const telegramToken = document.getElementById(`telegram-token-${botId}`);
        
        if (telegramToken && telegramToken.value) {
            if (!flowData.platforms) flowData.platforms = {};
            
            // Пытаемся найти существующий username из точного поля
            const telegramUsernameField = document.getElementById(`telegram-username-${botId}`);
            const existingUsername = telegramUsernameField?.value || null;
            
            // Сохраняем в platforms только username, токен сохраним отдельно
            flowData.platforms.telegram = {
                username: existingUsername || `bot_${botId}`
            };
        }
        
        // Получаем значение из Prompt Editor
        const promptValue = promptEditor ? promptEditor.getValue() : null;
        const flowVariables = promptEditor ? promptEditor.getFlowVariables() : null;
        
        console.log('🔍 DEBUG: flowVariables до добавления =', flowVariables);
        
        // Добавляем переменные в flowData если есть
        if (flowVariables && Object.keys(flowVariables).length > 0) {
            flowData.variables = flowVariables;
        }
        
        console.log('💾 Сохранение настроек бота:', {
            botId: botId,
            flowData: flowData,
            promptValue: promptValue ? `${promptValue.substring(0, 100)}...` : null,
            flowVariables: flowVariables,
            hasPromptEditor: !!promptEditor
        });
        
        try {
            // 1. Сохраняем FlowConfig
            const flowResponse = await fetch(`/frontend/api/flows/${botId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${window.app.authToken}`
                },
                body: JSON.stringify(flowData)
            });
            
            if (!flowResponse.ok) {
                const error = await flowResponse.json();
                showNotification(`Ошибка: ${error.detail || 'Не удалось сохранить'}`, 'danger');
                return;
            }
            
            // 2. Сохраняем токен отдельно, если есть
            if (telegramToken && telegramToken.value && flowData.platforms?.telegram?.username) {
                const tokenResponse = await fetch('/api/v1/admin/tokens', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${window.app.authToken}`
                    },
                    body: JSON.stringify({
                        platform: 'telegram',
                        username: flowData.platforms.telegram.username,
                        token: telegramToken.value
                    })
                });
                
                if (!tokenResponse.ok) {
                    console.warn('Не удалось сохранить токен Telegram');
                } else {
                    // Перезагружаем Telegram polling
                    try {
                        const reloadResponse = await fetch('/api/v1/admin/reload-telegram-bots', {
                            method: 'POST',
                            headers: {
                                'Authorization': `Bearer ${window.app.authToken}`
                            }
                        });
                        
                        if (reloadResponse.ok) {
                            const reloadData = await reloadResponse.json();
                            console.log('✅ Telegram polling перезагружен:', reloadData);
                        }
                    } catch (reloadError) {
                        console.warn('⚠️ Ошибка перезагрузки telegram polling:', reloadError);
                    }
                }
            }
            
            // 3. Сохраняем промпт агента, если есть
            if (promptValue !== undefined && promptValue !== null) {
                const entryPointField = document.getElementById('bot-entry-point');
                const entryPoint = entryPointField?.value;
                
                if (entryPoint) {
                    const agentResponse = await fetch(`/frontend/api/agents/${encodeURIComponent(entryPoint)}`, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${window.app.authToken}`
                        },
                        body: JSON.stringify({ prompt: promptValue })
                    });
                    
                    if (!agentResponse.ok) {
                        console.warn('❌ Не удалось сохранить промпт агента:', agentResponse.status, agentResponse.statusText);
                    } else {
                        console.log('✅ Промпт агента сохранен успешно');
                    }
                }
            }
            
            showNotification('Настройки бота сохранены', 'success');
            
        } catch (error) {
            console.error('Ошибка сохранения:', error);
            showNotification('Ошибка сохранения настроек', 'danger');
        }
    };

    window.addPlatform = async function(botId) {
        let modal = document.getElementById('add-platform-modal');
        
        // Загружаем доступные переменные для токена
        try {
            const response = await fetch('/api/v1/admin/variables', {
                headers: {
                    'Authorization': `Bearer ${window.app.authToken}`
                }
            });
            if (response.ok) {
                const varsData = await response.json();
                const select = document.getElementById('platform-token-select');
                
                // Очищаем и заполняем dropdown
                select.innerHTML = '<option value="">-- Выберите переменную --</option>';
                Object.entries(varsData).forEach(([key, varInfo]) => {
                    const desc = varInfo.description ? ` - ${varInfo.description}` : '';
                    const option = document.createElement('option');
                    option.value = `@var:${key}`;
                    option.textContent = `@var:${key}${desc}`;
                    select.appendChild(option);
                });
            }
        } catch (err) {
            console.error('Ошибка загрузки переменных:', err);
        }
        
        // Перемещаем модальное окно в body если оно не там
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
        
        document.getElementById('platform-type-select').value = '';
        document.getElementById('platform-config-section').style.display = 'none';
        resetPlatformForm();
        
        // Блокируем прокрутку body
        document.body.style.overflow = 'hidden';
        
        console.log('🔧 Modal opened, parent:', modal.parentElement.tagName);
    };
    
    window.toggleTokenInput = function() {
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
    };

    window.closeAddPlatformModal = function() {
        document.getElementById('add-platform-modal').style.display = 'none';
        document.body.style.overflow = 'auto'; // Возвращаем прокрутку
        resetPlatformForm();
    };

    // Глобальная переменная для хранения выбранной платформы
    let selectedPlatformType = '';

    window.togglePlatformDropdown = function() {
        const dropdown = document.getElementById('platform-dropdown');
        const selectValue = document.querySelector('.select-value');
        
        console.log('🔽 Toggle dropdown called, dropdown:', dropdown, 'selectValue:', selectValue);
        
        const isOpen = dropdown.classList.contains('show');
        console.log('🔽 Current state isOpen:', isOpen);
        
        if (isOpen) {
            dropdown.classList.remove('show');
            selectValue.classList.remove('active');
            console.log('🔽 Dropdown закрыт');
        } else {
            dropdown.classList.add('show');
            selectValue.classList.add('active');
            console.log('🔽 Dropdown открыт, z-index:', window.getComputedStyle(dropdown).zIndex);
        }
    };

    window.selectPlatform = function(value, icon, text) {
        selectedPlatformType = value;
        
        // Обновляем отображение выбранной платформы
        const selectText = document.querySelector('.select-text');
        selectText.innerHTML = `<i class="${icon}"></i> ${text}`;
        
        // Закрываем dropdown
        document.getElementById('platform-dropdown').classList.remove('show');
        document.querySelector('.select-value').classList.remove('active');
        
        // Вызываем функцию обновления полей
        updatePlatformFields();
    };

    window.updatePlatformFields = function() {
        const platformType = selectedPlatformType;
        const configSection = document.getElementById('platform-config-section');
        
        if (platformType) {
            configSection.style.display = 'block';
            
            // Обновляем плейсхолдеры в зависимости от типа платформы
            const tokenField = document.getElementById('platform-token');
            const usernameField = document.getElementById('platform-username');
            
            // Сбрасываем состояние полей
            tokenField.disabled = false;
            
            switch(platformType) {
                case 'telegram':
                    tokenField.placeholder = 'Токен от @BotFather';
                    usernameField.placeholder = 'username бота (без @)';
                    break;
                case 'whatsapp':
                    tokenField.placeholder = 'WhatsApp Business API токен';
                    usernameField.placeholder = 'Номер телефона';
                    break;
                case 'amocrm':
                    tokenField.placeholder = 'API ключ AmoCRM';
                    usernameField.placeholder = 'Домен (example.amocrm.ru)';
                    break;
                case 'retailcrm':
                    tokenField.placeholder = 'API ключ RetailCRM';
                    usernameField.placeholder = 'URL магазина';
                    break;
                case 'discord':
                    tokenField.placeholder = 'Discord Bot Token';
                    usernameField.placeholder = 'Application ID';
                    break;
                case 'slack':
                    tokenField.placeholder = 'Slack Bot Token';
                    usernameField.placeholder = 'App ID';
                    break;
                case 'web':
                    tokenField.placeholder = 'Не требуется';
                    usernameField.placeholder = 'Название чата';
                    tokenField.disabled = true;
                    break;
                case 'api':
                    tokenField.placeholder = 'API ключ (опционально)';
                    usernameField.placeholder = 'Название API';
                    break;
                case 'viber':
                    tokenField.placeholder = 'Viber API токен';
                    usernameField.placeholder = 'Имя бота';
                    break;
                case 'vk':
                    tokenField.placeholder = 'VK API токен';
                    usernameField.placeholder = 'ID группы';
                    break;
                default:
                    tokenField.placeholder = 'Токен платформы';
                    usernameField.placeholder = 'Username/ID';
                    break;
            }
        } else {
            configSection.style.display = 'none';
        }
    };

    window.addVariableRow = function() {
        const container = document.getElementById('custom-variables');
        const row = document.createElement('div');
        row.className = 'variable-row';
        row.innerHTML = `
            <input type="text" class="form-control" placeholder="Ключ" 
                   onchange="updateVariableName(this)">
            <input type="text" class="form-control" placeholder="Значение"
                   onchange="updateVariableValue(this)">
            <button class="btn btn-outline-danger btn-sm" onclick="removeVariableRow(this)">
                <i class="bi bi-trash"></i>
            </button>
        `;
        container.appendChild(row);
    };

    window.removeVariableRow = function(button) {
        button.closest('.variable-row').remove();
    };

    window.updateVariableName = function(input) {
        // Можно добавить валидацию ключа
        console.log('Variable name updated:', input.value);
    };

    window.updateVariableValue = function(input) {
        // Можно добавить валидацию значения
        console.log('Variable value updated:', input.value);
    };

    function resetPlatformForm() {
        // Сбрасываем выбранную платформу
        selectedPlatformType = '';
        
        // Сбрасываем отображение dropdown
        const selectText = document.querySelector('.select-text');
        selectText.innerHTML = 'Выберите платформу';
        
        // Закрываем dropdown если открыт
        document.getElementById('platform-dropdown').classList.remove('show');
        document.querySelector('.select-value').classList.remove('active');
        
        // Очищаем поля
        document.getElementById('platform-token').value = '';
        document.getElementById('platform-username').value = '';
        document.getElementById('platform-token').disabled = false;
        
        // Скрываем секцию настроек
        document.getElementById('platform-config-section').style.display = 'none';
        
        // Очищаем кастомные переменные, оставляя только одну строку
        const container = document.getElementById('custom-variables');
        const rows = container.querySelectorAll('.variable-row');
        rows.forEach((row, index) => {
            if (index > 0) {
                row.remove();
            } else {
                row.querySelectorAll('input').forEach(input => input.value = '');
            }
        });
    }

    window.savePlatform = async function(botId) {
        const platformType = selectedPlatformType;
        const token = document.getElementById('platform-token').value;
        const username = document.getElementById('platform-username').value;
        
        if (!platformType) {
            showNotification('Выберите тип платформы', 'warning');
            return;
        }

        // Собираем конфигурацию платформы
        const platformConfig = {};
        
        // Получаем токен (из select или input)
        let finalToken = '';
        const varRadio = document.getElementById('token-type-var');
        if (varRadio && varRadio.checked) {
            // Ссылка на переменную
            const select = document.getElementById('platform-token-select');
            finalToken = select ? select.value : '';
        } else {
            // Хардкод токен
            const input = document.getElementById('platform-token');
            finalToken = input ? input.value : '';
        }
        
        console.log('🔍 DEBUG: finalToken =', finalToken);
        console.log('🔍 DEBUG: username =', username);
        
        if (finalToken) {
            platformConfig.token = finalToken;
        }
        if (username) {
            platformConfig.username = username;
        }
        
        console.log('🔍 DEBUG: platformConfig =', platformConfig);

        // Добавляем кастомные переменные
        const variableRows = document.querySelectorAll('#custom-variables .variable-row');
        variableRows.forEach(row => {
            const keyInput = row.querySelector('input[placeholder="Ключ"]');
            const valueInput = row.querySelector('input[placeholder="Значение"]');
            
            if (keyInput.value && valueInput.value) {
                platformConfig[keyInput.value] = valueInput.value;
            }
        });

        try {
            // Получаем текущие настройки флоу
            const currentFlowResponse = await fetch(`/frontend/api/flows/${botId}`, {
                headers: {
                    'Authorization': `Bearer ${window.app.authToken}`
                }
            });
            
            if (!currentFlowResponse.ok) {
                throw new Error('Не удалось загрузить текущие настройки');
            }

            const currentFlow = await currentFlowResponse.json();
            
            // Добавляем новую платформу
            if (!currentFlow.platforms) {
                currentFlow.platforms = {};
            }
            currentFlow.platforms[platformType] = platformConfig;

            // 1. Сначала сохраняем токен (если есть)
            if (token && username && !document.getElementById('platform-token').disabled) {
                const tokenResponse = await fetch('/api/v1/admin/tokens', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${window.app.authToken}`
                    },
                    body: JSON.stringify({
                        platform: platformType,
                        username: username,
                        token: token
                    })
                });
                
                if (!tokenResponse.ok) {
                    const error = await tokenResponse.json();
                    throw new Error(error.detail || 'Не удалось сохранить токен');
                }
                
                console.log('✅ Токен сохранен');
            }
            

            // 2. Потом обновляем platforms в flow (это вызовет регистрацию)
            const updateResponse = await fetch(`/frontend/api/flows/${botId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${window.app.authToken}`
                },
                body: JSON.stringify({
                    platforms: currentFlow.platforms
                })
            });

            if (!updateResponse.ok) {
                throw new Error('Не удалось сохранить платформу');
            }

            showNotification(`Платформа ${platformType} добавлена`, 'success');
            closeAddPlatformModal();
            
            // Перезагружаем детали бота для отображения новой платформы
            await expandBot(botId);

        } catch (error) {
            console.error('Ошибка добавления платформы:', error);
            showNotification('Ошибка добавления платформы: ' + error.message, 'danger');
        }
    };

    window.removePlatform = async function(botId, platformType) {
        if (!confirm(`Удалить платформу ${platformType}?`)) {
            return;
        }

        try {
            // Получаем текущие настройки флоу
            const currentFlowResponse = await fetch(`/frontend/api/flows/${botId}`, {
                headers: {
                    'Authorization': `Bearer ${window.app.authToken}`
                }
            });
            
            if (!currentFlowResponse.ok) {
                throw new Error('Не удалось загрузить текущие настройки');
            }

            const currentFlow = await currentFlowResponse.json();
            
            // Удаляем платформу
            if (currentFlow.platforms && currentFlow.platforms[platformType]) {
                delete currentFlow.platforms[platformType];
                
                // Сохраняем обновленную конфигурацию
                const updateResponse = await fetch(`/frontend/api/flows/${botId}`, {
                    method: 'PUT',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${window.app.authToken}`
                    },
                    body: JSON.stringify({
                        platforms: currentFlow.platforms
                    })
                });

                if (!updateResponse.ok) {
                    throw new Error('Не удалось удалить платформу');
                }

                showNotification(`Платформа ${platformType} удалена`, 'success');
                
                // Перезагружаем детали бота
                await expandBot(botId);
            }

        } catch (error) {
            console.error('Ошибка удаления платформы:', error);
            showNotification('Ошибка удаления платформы: ' + error.message, 'danger');
        }
    };

    window.createBot = function() {
        window.location.href = '/frontend/builder/';
    };

    function showNotification(message, type = 'info') {
        if (window.app && window.app.showNotification) {
            window.app.showNotification(message, type);
        } else {
            alert(message);
        }
    }

    document.addEventListener('click', (e) => {
        if (e.target.id === 'bot-expanded-modal') {
            window.closeBotModal();
        }
    });

    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            const remigrateModal = document.getElementById('remigrate-confirm-modal');
            if (remigrateModal && remigrateModal.style.display === 'flex') {
                window.closeRemigrateModal();
            } else if (document.getElementById('add-platform-modal').style.display === 'flex') {
                window.closeAddPlatformModal();
            } else if (currentBotModal) {
                window.closeBotModal();
            }
        }
    });

    // Закрытие модального окна добавления платформы по клику на фон
    document.addEventListener('click', (e) => {
        if (e.target.id === 'add-platform-modal') {
            window.closeAddPlatformModal();
        }
        
        if (e.target.id === 'remigrate-confirm-modal') {
            window.closeRemigrateModal();
        }
        
        const dropdown = document.getElementById('platform-dropdown');
        const customSelect = document.getElementById('platform-type-select');
        
        if (dropdown && customSelect && dropdown.classList.contains('show')) {
            if (!customSelect.contains(e.target)) {
                dropdown.classList.remove('show');
                document.querySelector('.select-value').classList.remove('active');
            }
        }
    });
    
    let pendingRemigrateFlowId = null;
    
    window.remigrateFlowWithDeps = function(flowId) {
        pendingRemigrateFlowId = flowId;
        const modal = document.getElementById('remigrate-confirm-modal');
        const confirmBtn = document.getElementById('confirm-remigrate-btn');
        
        if (modal) {
            modal.style.display = 'flex';
        }
        
        if (confirmBtn) {
            confirmBtn.onclick = () => confirmRemigrate();
        }
    };
    
    window.closeRemigrateModal = function() {
        const modal = document.getElementById('remigrate-confirm-modal');
        if (modal) {
            modal.style.display = 'none';
        }
        pendingRemigrateFlowId = null;
    };
    
    window.confirmRemigrate = async function() {
        if (!pendingRemigrateFlowId) {
            return;
        }
        
        const flowId = pendingRemigrateFlowId;
        const modal = document.getElementById('remigrate-confirm-modal');
        
        if (modal) {
            modal.style.display = 'none';
        }
        
        if (window.app && window.app.showNotification) {
            window.app.showNotification('Выполняется сброс к коду...', 'info');
        }
        
        const response = await fetch(`/api/v1/admin/remigrate-flow-with-deps/${flowId}`, { 
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        
        if (!response.ok) {
            const errorData = await response.json().catch(() => ({}));
            if (window.app && window.app.showNotification) {
                window.app.showNotification('Ошибка: ' + (errorData.detail || `HTTP ${response.status}`), 'danger');
            }
            return;
        }
        
        const data = await response.json();
        if (window.app && window.app.showNotification) {
            window.app.showNotification(data.message, 'success');
        }
        
        setTimeout(async () => {
            const modalDetails = document.getElementById('modal-bot-details');
            if (modalDetails) {
                modalDetails.innerHTML = '<div class="loading-indicator"><div class="spinner"></div><span>Перезагрузка...</span></div>';
                
                const detailsResponse = await fetch(`/frontend/bots/${flowId}/details`);
                const html = await detailsResponse.text();
                modalDetails.innerHTML = html;
                
                initBotSettings();
            }
        }, 500);
    };

})();
