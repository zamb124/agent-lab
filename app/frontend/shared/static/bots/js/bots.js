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
        
        const telegramToken = document.getElementById(`telegram-token-${botId}`);
        if (telegramToken && telegramToken.value) {
            if (!flowData.platforms) flowData.platforms = {};
            flowData.platforms.telegram = { token: telegramToken.value };
        }
        
        // Получаем значение из Prompt Editor
        const promptValue = promptEditor ? promptEditor.getValue() : null;
        
        try {
            const flowResponse = await fetch(`/api/v1/flows/${botId}`, {
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
            
            if (promptValue !== undefined && promptValue !== null) {
                const placeholder = document.querySelector('.embedded-chat-placeholder');
                const entryPoint = placeholder?.dataset?.entryPoint;
                
                if (entryPoint) {
                    const agentResponse = await fetch(`/frontend/api/models/agent/${encodeURIComponent(entryPoint)}`, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${window.app.authToken}`
                        },
                        body: JSON.stringify({ prompt: promptValue })
                    });
                    
                    if (!agentResponse.ok) {
                        console.warn('Не удалось сохранить промпт агента');
                    }
                }
            }
            
            showNotification('Настройки бота сохранены', 'success');
            
            setTimeout(() => {
                htmx.ajax('GET', '/frontend/bots/list', {
                    target: '.bots-content',
                    swap: 'innerHTML'
                });
            }, 1000);
            
            window.closeBotModal();
            
        } catch (error) {
            console.error('Ошибка сохранения:', error);
            showNotification('Ошибка сохранения настроек', 'danger');
        }
    };

    window.addPlatform = function(botId) {
        showNotification('Функция добавления платформ будет реализована позже', 'info');
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
        if (e.key === 'Escape' && currentBotModal) {
            window.closeBotModal();
        }
    });

})();
