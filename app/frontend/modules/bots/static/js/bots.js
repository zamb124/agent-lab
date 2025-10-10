/**
 * Управление ботами
 */

import { slugify, generateUniqueId } from '/static/js/utils/slugify.js';
import { showNotification } from '/static/js/components/notification.js';

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
        
        if (!modal || !modalDetails) {
            console.error('Modal elements not found!');
            alert('Модалка не найдена в DOM');
            return;
        }
        
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        
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
    
    document.body.addEventListener('htmx:beforeSwap', function(event) {
        if (event.detail.target.id === 'content') {
            const modal = document.getElementById('bot-expanded-modal');
            if (modal && modal.style.display === 'flex') {
                closeBotModal();
            }
        }
    });

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
    
    let llmProvidersData = null;

    async function loadLLMProviders() {
        if (llmProvidersData) return llmProvidersData;
        
        try {
            const response = await fetch('/api/v1/admin/llm/providers', {
                headers: {
                    'Authorization': `Bearer ${window.app.authToken}`
                }
            });
            
            if (!response.ok) {
                throw new Error('Не удалось загрузить список LLM провайдеров');
            }
            
            llmProvidersData = await response.json();
            return llmProvidersData;
        } catch (error) {
            console.error('Ошибка загрузки LLM провайдеров:', error);
            return null;
        }
    }

    window.updateLLMModels = async function() {
        const provider = document.getElementById('bot-llm-provider')?.value;
        const modelSelect = document.getElementById('bot-llm-model');
        
        if (!modelSelect) return;
        
        const currentValue = modelSelect.dataset.currentValue || modelSelect.value;
        
        const providersData = await loadLLMProviders();
        
        let models = [{ value: '', label: 'По умолчанию' }];
        
        if (providersData && provider && providersData.providers[provider]) {
            models = providersData.providers[provider].models;
        }
        
        modelSelect.innerHTML = '';
        models.forEach(model => {
            const option = document.createElement('option');
            option.value = model.value;
            option.textContent = model.label;
            if (model.value === currentValue) {
                option.selected = true;
            }
            modelSelect.appendChild(option);
        });
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
                    
                    if (targetPanel === 'main' && !promptEditor) {
                        initPromptEditor();
                    }
                    
                    if (targetPanel === 'abilities') {
                        const toolsSelector = document.getElementById('bot-tools-selector');
                        if (toolsSelector && !toolsSelector.dataset.loaded) {
                            loadBotTools();
                            toolsSelector.dataset.loaded = 'true';
                        }
                    }
                    
                    if (targetPanel === 'knowledge') {
                        const flowIdElement = document.querySelector('[data-flow-id]');
                        if (flowIdElement) {
                            const flowId = flowIdElement.dataset.flowId;
                            if (flowId && flowId !== 'new') {
                                loadKnowledgeBaseDocuments(flowId);
                            }
                        }
                    }
                }
            });
        });
        
        const activePanel = document.querySelector('.settings-panel.active');
        if (activePanel && activePanel.dataset.panel === 'main') {
            initPromptEditor();
        }
        
        updateLLMModels();
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

    async function loadBotTools() {
        const toolsSelector = document.getElementById('bot-tools-selector');
        if (!toolsSelector) {
            return;
        }
        
        try {
            const [publicToolsResponse, publicAgentsResponse] = await Promise.all([
                fetch('/frontend/api/tools?public_only=true'),
                fetch('/frontend/api/agents?public_only=true')
            ]);
            
            if (!publicToolsResponse.ok) {
                throw new Error('Не удалось загрузить список тулов');
            }
            
            const publicTools = await publicToolsResponse.json();
            const publicAgents = publicAgentsResponse.ok ? await publicAgentsResponse.json() : [];
            
            const flowIdElement = document.querySelector('[data-flow-id]');
            const flowId = flowIdElement?.dataset?.flowId;
            let agentTools = [];
            let selectedToolIds = [];
            
            if (flowId && flowId !== 'new') {
                const entryPointElement = document.querySelector('[data-entry-point]');
                const entryPoint = entryPointElement?.dataset?.entryPoint;
                
                if (entryPoint) {
                    try {
                        const agentResponse = await fetch(`/frontend/api/agents/${encodeURIComponent(entryPoint)}`);
                        if (agentResponse.ok) {
                            const agentData = await agentResponse.json();
                            agentTools = agentData.tools || [];
                            selectedToolIds = agentTools.map(t => t.tool_id);
                        }
                    } catch (error) {
                        console.error('Не удалось загрузить текущие тулы агента:', error);
                    }
                }
            }
            
            const toolsMap = new Map();
            
            publicTools.forEach(tool => {
                toolsMap.set(tool.id, {
                    ...tool,
                    type: 'tool'
                });
            });
            
            publicAgents.forEach(agent => {
                const agentId = `agent:${agent.agent_id}`;
                toolsMap.set(agentId, {
                    id: agentId,
                    name: agent.name,
                    title: agent.title || agent.name,
                    description: agent.description || 'Агент как инструмент',
                    cost: 0,
                    is_public: true,
                    type: 'agent'
                });
            });
            
            for (const agentTool of agentTools) {
                if (!toolsMap.has(agentTool.tool_id)) {
                    try {
                        const toolResponse = await fetch(`/frontend/api/tools/${encodeURIComponent(agentTool.tool_id)}`);
                        if (toolResponse.ok) {
                            const toolData = await toolResponse.json();
                            toolsMap.set(agentTool.tool_id, {
                                id: toolData.id,
                                name: toolData.name,
                                title: toolData.title || toolData.name,
                                description: toolData.description || 'Уже добавленная функция',
                                cost: toolData.cost || 0,
                                is_public: false
                            });
                        } else {
                            toolsMap.set(agentTool.tool_id, {
                                id: agentTool.tool_id,
                                name: agentTool.tool_id.split('.').pop(),
                                title: agentTool.title || agentTool.tool_id.split('.').pop(),
                                description: agentTool.description || 'Уже добавленная функция',
                                cost: agentTool.cost || 0,
                                is_public: false
                            });
                        }
                    } catch (error) {
                        console.warn(`Не удалось загрузить информацию о туле ${agentTool.tool_id}:`, error);
                        toolsMap.set(agentTool.tool_id, {
                            id: agentTool.tool_id,
                            name: agentTool.tool_id.split('.').pop(),
                            title: agentTool.title || agentTool.tool_id.split('.').pop(),
                            description: agentTool.description || 'Уже добавленная функция',
                            cost: agentTool.cost || 0,
                            is_public: false
                        });
                    }
                }
            }
            
            if (toolsMap.size === 0) {
                toolsSelector.innerHTML = '<div class="tools-empty"><i class="bi bi-info-circle"></i> Нет доступных функций</div>';
                return;
            }
            
            const toolsList = document.createElement('div');
            toolsList.className = 'tools-list';
            
            Array.from(toolsMap.values()).forEach(tool => {
                const toolItem = document.createElement('div');
                toolItem.className = 'tool-item';
                
                const isChecked = selectedToolIds.includes(tool.id);
                const isNonPublic = !tool.is_public;
                const isAgent = tool.type === 'agent';
                const badge = isAgent 
                    ? '<span class="tool-type-badge agent">Агент</span>' 
                    : '<span class="tool-type-badge function">Функция</span>';
                const lockIcon = isNonPublic ? ' 🔒' : '';
                
                toolItem.innerHTML = `
                    <input type="checkbox" 
                           id="tool-${tool.id.replace(/\./g, '-').replace(/:/g, '-')}" 
                           data-tool-id="${tool.id}"
                           ${isChecked ? 'checked' : ''}>
                    <div class="tool-item-content">
                        <label class="tool-item-name" for="tool-${tool.id.replace(/\./g, '-').replace(/:/g, '-')}">
                            ${badge}
                            <span>${tool.title || tool.name}${lockIcon}</span>
                        </label>
                        ${tool.description ? `<div class="tool-item-description">${tool.description}</div>` : ''}
                        ${tool.cost > 0 ? `<div class="tool-item-cost">Стоимость: ${tool.cost} ₽</div>` : ''}
                    </div>
                `;
                
                toolsList.appendChild(toolItem);
            });
            
            toolsSelector.innerHTML = '';
            toolsSelector.appendChild(toolsList);
            
        } catch (error) {
            console.error('Ошибка загрузки тулов:', error);
            toolsSelector.innerHTML = '<div class="tools-empty"><i class="bi bi-exclamation-triangle"></i> Ошибка загрузки функций</div>';
        }
    }

    window.saveBotSettings = async function(botId) {
        const isNewBot = botId === 'new';
        
        const botName = document.getElementById('bot-name')?.value?.trim();
        const botDescription = document.getElementById('bot-description-main')?.value?.trim();
        
        if (isNewBot) {
            if (!botName) {
                showNotification('Введите название бота', 'warning');
                return;
            }
            if (!botDescription) {
                showNotification('Введите описание бота', 'warning');
                return;
            }
        }
        
        const flowData = {
            name: botName,
            description: botDescription,
            timeout: document.getElementById('bot-timeout')?.value || null,
            max_retries: parseInt(document.getElementById('bot-max-retries')?.value) || 3,
        };
        
        if (isNewBot) {
            const flowId = generateUniqueId(botName);
            const agentSlug = slugify(botName);
            const agentName = agentSlug.charAt(0).toUpperCase() + agentSlug.slice(1);
            
            flowData.flow_id = flowId;
            flowData.entry_point_agent = `${agentName}Agent`;
            flowData.platforms = {};
        }
        
        const promptValue = promptEditor ? promptEditor.getValue() : null;
        const flowVariables = promptEditor ? promptEditor.getFlowVariables() : null;
        
        console.log('🔍 DEBUG: flowVariables до добавления =', flowVariables);
        
        if (flowVariables && Object.keys(flowVariables).length > 0) {
            flowData.variables = flowVariables;
        }
        
        const namespaceScope = document.getElementById('rag-namespace-scope')?.value || 'flow';
        const searchScopes = [];
        document.querySelectorAll('.rag-search-scope:checked').forEach(checkbox => {
            searchScopes.push(checkbox.value);
        });
        
        flowData.rag_config = {
            enabled: true,
            namespace_scope: namespaceScope,
            search_scopes: searchScopes.length > 0 ? searchScopes : ['flow'],
            auto_index_messages: false
        };
        
        console.log('💾 Сохранение настроек бота:', {
            botId: botId,
            isNewBot: isNewBot,
            flowData: flowData,
            promptValue: promptValue ? `${promptValue.substring(0, 100)}...` : null,
            flowVariables: flowVariables,
            hasPromptEditor: !!promptEditor
        });
        
        try {
            const method = isNewBot ? 'POST' : 'PUT';
            const url = isNewBot ? '/frontend/api/flows' : `/frontend/api/flows/${botId}`;
            
            const flowResponse = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${window.app.authToken}`
                },
                body: JSON.stringify(flowData)
            });
            
            if (!flowResponse.ok) {
                const error = await flowResponse.json().catch(() => ({}));
                const errorMsg = error.detail || `HTTP ${flowResponse.status}: ${flowResponse.statusText}`;
                console.error('❌ Ошибка сохранения flow:', error);
                showNotification(`Ошибка: ${errorMsg}`, 'danger');
                return;
            }
            
            const savedFlow = await flowResponse.json();
            const actualBotId = isNewBot ? savedFlow.flow_id : botId;
            console.log('✅ Flow сохранен:', actualBotId);
            
            // Сохраняем настройки агента (промпт, LLM и тулы)
            const entryPoint = savedFlow.entry_point_agent;
            if (entryPoint) {
                const agentUpdates = {};
                
                if (promptValue !== undefined && promptValue !== null && promptValue.trim()) {
                    agentUpdates.prompt = promptValue;
                }
                
                const selectedTools = [];
                document.querySelectorAll('#bot-tools-selector input[type="checkbox"]:checked').forEach(checkbox => {
                    const toolId = checkbox.dataset.toolId;
                    if (toolId) {
                        selectedTools.push({
                            tool_id: toolId,
                            params: {},
                            code_mode: "code_reference",
                            is_public: true
                        });
                    }
                });
                
                if (selectedTools.length > 0) {
                    agentUpdates.tools = selectedTools;
                }
                
                const llmProvider = document.getElementById('bot-llm-provider')?.value;
                const llmModel = document.getElementById('bot-llm-model')?.value;
                const llmTemperature = document.getElementById('bot-llm-temperature')?.value;
                
                if (llmProvider || llmModel || llmTemperature) {
                    const llmConfig = {};
                    
                    if (llmProvider) {
                        llmConfig.provider = llmProvider;
                    }
                    if (llmModel) {
                        llmConfig.model = llmModel;
                    }
                    if (llmTemperature !== '' && llmTemperature !== null) {
                        llmConfig.temperature = parseFloat(llmTemperature);
                    }
                    
                    if (Object.keys(llmConfig).length > 0) {
                        agentUpdates.llm_config = llmConfig;
                    }
                }
                
                if (Object.keys(agentUpdates).length > 0) {
                    console.log('💾 Сохраняем настройки агента:', entryPoint, agentUpdates);
                    const agentResponse = await fetch(`/frontend/api/agents/${encodeURIComponent(entryPoint)}`, {
                        method: 'PUT',
                        headers: {
                            'Content-Type': 'application/json',
                            'Authorization': `Bearer ${window.app.authToken}`
                        },
                        body: JSON.stringify(agentUpdates)
                    });
                    
                    if (!agentResponse.ok) {
                        const agentError = await agentResponse.json().catch(() => ({}));
                        console.warn('❌ Не удалось сохранить настройки агента:', agentResponse.status, agentError);
                    } else {
                        console.log('✅ Настройки агента сохранены успешно');
                    }
                }
            }
            
            if (isNewBot) {
                showNotification('Бот успешно создан', 'success');
                closeBotModal();
                htmx.ajax('GET', '/frontend/bots/list', {
                    target: '#bots-list-view',
                    swap: 'innerHTML'
                });
            } else {
                showNotification('Настройки бота сохранены', 'success');
            }
            
        } catch (error) {
            console.error('❌❌❌ Ошибка сохранения:', error);
            console.error('Stack trace:', error.stack);
            showNotification(
                (isNewBot ? 'Ошибка создания бота: ' : 'Ошибка сохранения настроек: ') + error.message, 
                'danger'
            );
        }
    };

    window.addPlatform = async function(botId) {
        const modal = document.getElementById('add-platform-modal');
        
        if (!modal) {
            console.error('Модальное окно add-platform-modal не найдено');
            return;
        }
        
        // Сначала сбрасываем форму для чистого состояния
        resetPlatformForm();
        
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
                
                if (select) {
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
            }
        } catch (err) {
            console.error('Ошибка загрузки переменных:', err);
        }
        
        // Перемещаем модальное окно в body если оно не там
        if (modal.parentElement !== document.body) {
            document.body.appendChild(modal);
        }
        
        // Показываем модалку
        modal.style.display = 'flex';
        modal.style.position = 'fixed';
        modal.style.top = '0';
        modal.style.left = '0';
        modal.style.width = '100%';
        modal.style.height = '100%';
        modal.style.zIndex = '9999';
        
        // Блокируем прокрутку body
        document.body.style.overflow = 'hidden';
        
        console.log('🔧 Модалка открыта, parent:', modal.parentElement.tagName);
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
        const modal = document.getElementById('add-platform-modal');
        if (modal) {
            modal.style.display = 'none';
        }
        document.body.style.overflow = 'auto';
        
        // Сбрасываем форму
        resetPlatformForm();
        
        // Удаляем WhatsApp контейнер если он был создан
        const whatsappContainer = document.getElementById('whatsapp-fields-container');
        if (whatsappContainer) {
            whatsappContainer.remove();
        }
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

    window.updatePlatformFields = async function() {
        const platformType = selectedPlatformType;
        const configSection = document.getElementById('platform-config-section');
        
        if (platformType) {
            configSection.style.display = 'block';
            
            // Для WhatsApp показываем специальные поля
            if (platformType === 'whatsapp') {
                await showWhatsAppFields();
            } else {
                // Для остальных платформ показываем стандартные поля
                showStandardPlatformFields(platformType);
            }
        } else {
            configSection.style.display = 'none';
        }
    };

    function showStandardPlatformFields(platformType) {
        const configSection = document.getElementById('platform-config-section');
        
        const tokenField = document.getElementById('platform-token');
        const usernameField = document.getElementById('platform-username');
        
        // Показываем стандартные поля
        document.getElementById('platform-token').closest('.form-group').style.display = 'block';
        document.getElementById('platform-username').closest('.form-group').style.display = 'block';
        
        // Скрываем WhatsApp поля если они были
        const whatsappFields = document.getElementById('whatsapp-fields-container');
        if (whatsappFields) whatsappFields.style.display = 'none';
        
        // Сбрасываем состояние полей
        tokenField.disabled = false;
        
        switch(platformType) {
            case 'telegram':
                tokenField.placeholder = 'Токен от @BotFather';
                usernameField.placeholder = 'username бота (без @)';
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
    }

    async function showWhatsAppFields() {
        // Скрываем стандартные поля токена и username
        document.getElementById('platform-token').closest('.form-group').style.display = 'none';
        document.getElementById('platform-username').closest('.form-group').style.display = 'none';
        
        // Создаем или показываем WhatsApp поля
        let whatsappContainer = document.getElementById('whatsapp-fields-container');
        
        if (!whatsappContainer) {
            // Загружаем HTML с бэкенда
            try {
                const response = await fetch('/frontend/bots/platform-fields/whatsapp');
                if (!response.ok) {
                    throw new Error('Не удалось загрузить поля для WhatsApp');
                }
                
                const html = await response.text();
                
                // Создаем контейнер и вставляем HTML
                const customVarsSection = document.getElementById('custom-variables').closest('.form-group');
                customVarsSection.insertAdjacentHTML('beforebegin', html);
                
                // Загружаем переменные для select'ов
                await loadVariablesForWhatsAppSelects();
            } catch (error) {
                console.error('Ошибка загрузки WhatsApp полей:', error);
                showNotification('Не удалось загрузить поля для WhatsApp', 'error');
            }
        } else {
            whatsappContainer.style.display = 'block';
        }
    }
    
    window.toggleWhatsAppTokenInput = function() {
        const isVar = document.getElementById('wa-token-type-var').checked;
        document.getElementById('wa-token-var-select-group').style.display = isVar ? 'block' : 'none';
        document.getElementById('wa-token-hardcoded-group').style.display = isVar ? 'none' : 'block';
    };
    
    window.toggleWhatsAppVerifyInput = function() {
        const isVar = document.getElementById('wa-verify-type-var').checked;
        document.getElementById('wa-verify-var-select-group').style.display = isVar ? 'block' : 'none';
        document.getElementById('wa-verify-hardcoded-group').style.display = isVar ? 'none' : 'block';
    };
    
    async function loadVariablesForWhatsAppSelects() {
        try {
            const response = await fetch('/api/v1/admin/variables', {
                headers: {
                    'Authorization': `Bearer ${window.app.authToken}`
                }
            });
            
            if (response.ok) {
                const varsData = await response.json();
                const variables = Object.entries(varsData).map(([key, info]) => ({
                    key: key,
                    is_secret: info.is_secret || false
                }));
                
                // Наполняем select для access_token
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
                
                // Наполняем select для verify_token
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
    
    function collectWhatsAppConfig() {
        const config = {};
        
        // Phone Number ID (обязательно)
        const phoneNumberId = document.getElementById('whatsapp-phone-number-id')?.value;
        if (phoneNumberId) {
            config.phone_number_id = phoneNumberId;
        }
        
        // Access Token (обязательно)
        const tokenVarRadio = document.getElementById('wa-token-type-var');
        if (tokenVarRadio && tokenVarRadio.checked) {
            // Ссылка на переменную
            const select = document.getElementById('whatsapp-access-token-select');
            if (select && select.value) {
                config.access_token = select.value;
            }
        } else {
            // Хардкод токен
            const input = document.getElementById('whatsapp-access-token');
            if (input && input.value) {
                config.access_token = input.value;
            }
        }
        
        // Verify Token (обязательно)
        const verifyVarRadio = document.getElementById('wa-verify-type-var');
        if (verifyVarRadio && verifyVarRadio.checked) {
            // Ссылка на переменную
            const select = document.getElementById('whatsapp-verify-token-select');
            if (select && select.value) {
                config.verify_token = select.value;
            }
        } else {
            // Хардкод токен
            const input = document.getElementById('whatsapp-verify-token');
            if (input && input.value) {
                config.verify_token = input.value;
            }
        }
        
        // Business Account ID (опционально)
        const businessAccountId = document.getElementById('whatsapp-business-account-id')?.value;
        if (businessAccountId) {
            config.business_account_id = businessAccountId;
        }
        
        // Display Name (опционально)
        const displayName = document.getElementById('whatsapp-display-name')?.value;
        if (displayName) {
            config.display_name = displayName;
        }
        
        return config;
    }
    
    window.registerWhatsApp = async function(flowId) {
        try {
            showNotification('Регистрация WhatsApp...', 'info');
            
            const response = await fetch(`/api/v1/admin/whatsapp/register/${flowId}`, {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${window.app.authToken}`
                }
            });
            
            if (response.ok) {
                const result = await response.json();
                showNotification('WhatsApp успешно зарегистрирован!', 'success');
                
                // Показываем webhook URL
                if (result.result && result.result.webhook_url) {
                    const urlElement = document.getElementById('whatsapp-webhook-url');
                    if (urlElement) {
                        urlElement.textContent = result.result.webhook_url;
                    }
                }
                
                // Перезагружаем детали бота
                await expandBot(flowId);
            } else {
                const error = await response.json();
                showNotification(`Ошибка регистрации: ${error.detail}`, 'error');
            }
        } catch (error) {
            console.error('Ошибка регистрации WhatsApp:', error);
            showNotification('Ошибка регистрации WhatsApp', 'error');
        }
    }

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
        if (selectText) {
            selectText.innerHTML = 'Выберите платформу';
        }
        
        // Закрываем dropdown если открыт
        const dropdown = document.getElementById('platform-dropdown');
        if (dropdown) {
            dropdown.classList.remove('show');
        }
        
        const selectValue = document.querySelector('.select-value');
        if (selectValue) {
            selectValue.classList.remove('active');
        }
        
        // Очищаем стандартные поля
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
        
        // Скрываем секцию настроек
        const configSection = document.getElementById('platform-config-section');
        if (configSection) {
            configSection.style.display = 'none';
        }
        
        // Удаляем WhatsApp контейнер если был создан
        const whatsappContainer = document.getElementById('whatsapp-fields-container');
        if (whatsappContainer) {
            whatsappContainer.remove();
        }
        
        // Очищаем кастомные переменные, оставляя только одну строку
        const container = document.getElementById('custom-variables');
        if (container) {
            const rows = container.querySelectorAll('.variable-row');
            rows.forEach((row, index) => {
                if (index > 0) {
                    row.remove();
                } else {
                    row.querySelectorAll('input').forEach(input => input.value = '');
                }
            });
        }
    }

    window.savePlatform = async function(botId) {
        const platformType = selectedPlatformType;
        
        if (!platformType) {
            showNotification('Выберите тип платформы', 'warning');
            return;
        }

        let platformConfig = {};
        let savedToken = null;
        let savedUsername = null;
        
        if (platformType === 'whatsapp') {
            platformConfig = collectWhatsAppConfig();
            
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
                showNotification('Введите username/ID для платформы', 'warning');
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
                    showNotification('Введите токен для платформы', 'warning');
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
        
        console.log('🔍 DEBUG: botId =', botId);
        console.log('🔍 DEBUG: platformType =', platformType);
        console.log('🔍 DEBUG: platformConfig =', platformConfig);
        console.log('🔍 DEBUG: savedToken =', savedToken ? '***' : null);
        console.log('🔍 DEBUG: savedUsername =', savedUsername);

        if (botId === 'new') {
            showNotification('Сначала создайте бота, затем добавляйте платформы', 'warning');
            return;
        }

        try {
            const currentFlowResponse = await fetch(`/frontend/api/flows/${botId}`, {
                headers: {
                    'Authorization': `Bearer ${window.app.authToken}`
                }
            });
            
            if (!currentFlowResponse.ok) {
                const errorData = await currentFlowResponse.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Не удалось загрузить текущие настройки');
            }

            const currentFlow = await currentFlowResponse.json();
            
            // Добавляем новую платформу
            if (!currentFlow.platforms) {
                currentFlow.platforms = {};
            }
            currentFlow.platforms[platformType] = platformConfig;
            
            console.log('📤 Обновляем platforms в flow:', currentFlow.platforms);

            if (savedToken && savedUsername) {
                console.log('💾 Сохраняем токен для платформы:', platformType);
                const tokenResponse = await fetch('/api/v1/admin/tokens', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${window.app.authToken}`
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
                
                console.log('✅ Токен сохранен');
            }
            
            console.log('📤 Отправляем PUT /frontend/api/flows/' + botId);
            const updatePayload = { platforms: currentFlow.platforms };
            console.log('📦 Payload:', JSON.stringify(updatePayload, null, 2));

            const updateResponse = await fetch(`/frontend/api/flows/${botId}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${window.app.authToken}`
                },
                body: JSON.stringify(updatePayload)
            });

            if (!updateResponse.ok) {
                const errorData = await updateResponse.json().catch(() => ({}));
                const errorMessage = errorData.detail || `HTTP ${updateResponse.status}: ${updateResponse.statusText}`;
                console.error('❌ Ошибка обновления flow:', errorData);
                throw new Error(errorMessage);
            }

            showNotification(`Платформа ${platformType} добавлена`, 'success');
            closeAddPlatformModal();
            
            await expandBot(botId);

        } catch (error) {
            console.error('❌ Ошибка добавления платформы:', error);
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
        expandBot('new');
    };


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

    window.uploadDocumentToKnowledgeBase = async function(flowId) {
        const input = document.createElement('input');
        input.type = 'file';
        input.accept = '.pdf,.txt,.docx,.html,.md,.csv';
        
        input.onchange = async (e) => {
            const file = e.target.files[0];
            if (!file) return;
            
            const formData = new FormData();
            formData.append('file', file);
            formData.append('flow_id', flowId);
            
            try {
                showNotification('Загрузка документа...', 'info');
                
                const response = await fetch(`/api/v1/knowledge-base/flows/${flowId}/documents`, {
                    method: 'POST',
                    body: formData
                });
                
                if (!response.ok) {
                    throw new Error('Ошибка загрузки документа');
                }
                
                const result = await response.json();
                showNotification('Документ успешно загружен и добавлен в базу знаний', 'success');
                
                await loadKnowledgeBaseDocuments(flowId);
                
            } catch (error) {
                console.error('Ошибка загрузки документа:', error);
                showNotification('Не удалось загрузить документ: ' + error.message, 'danger');
            }
        };
        
        input.click();
    };
    
    window.loadKnowledgeBaseDocuments = async function(flowId) {
        const listContainer = document.getElementById('knowledge-base-docs-list');
        if (!listContainer) return;
        
        listContainer.innerHTML = '<div class="loading-indicator"><div class="spinner"></div></div>';
        
        try {
            const response = await fetch(`/api/v1/knowledge-base/flows/${flowId}/documents`);
            
            if (!response.ok) {
                throw new Error('Ошибка получения списка документов');
            }
            
            const data = await response.json();
            const documents = data.documents || [];
            
            if (documents.length === 0) {
                listContainer.innerHTML = `
                    <div class="empty-state">
                        <i class="bi bi-inbox"></i>
                        <p>В базе знаний пока нет документов</p>
                        <p class="text-muted">Загрузите документы чтобы бот мог использовать их для ответов</p>
                    </div>
                `;
                return;
            }
            
            const escapeAttr = (value) => String(value)
                .replace(/&/g, '&amp;')
                .replace(/"/g, '&quot;');
            
            let html = '<div class="documents-grid">';
            
            documents.forEach(doc => {
                const statusIcon = {
                    'ready': '<i class="bi bi-check-circle-fill text-success"></i>',
                    'processing': '<i class="bi bi-hourglass-split text-warning"></i>',
                    'failed': '<i class="bi bi-x-circle-fill text-danger"></i>'
                }[doc.status] || '<i class="bi bi-question-circle"></i>';
                
                const downloadUrl = doc.metadata && doc.metadata.source_url ? doc.metadata.source_url : null;
                const safeDownloadAttr = downloadUrl ? escapeAttr(downloadUrl) : '';
                const cardClasses = downloadUrl ? 'document-card document-card-clickable' : 'document-card';
                const dataDownloadAttr = downloadUrl ? ` data-download-url="${safeDownloadAttr}"` : '';
                
                html += `
                    <div class="${cardClasses}"${dataDownloadAttr}>
                        <div class="document-header">
                            <div class="document-icon">
                                <i class="bi bi-file-earmark-pdf"></i>
                            </div>
                            <div class="document-info">
                                <div class="document-name">${doc.name}</div>
                                <div class="document-meta">
                                    ${statusIcon}
                                    <span class="status-text">${doc.status}</span>
                                    ${doc.created_at ? `• ${new Date(doc.created_at).toLocaleDateString('ru')}` : ''}
                                </div>
                            </div>
                        </div>
                        <div class="document-actions">
                            <button class="btn btn-sm btn-outline-danger" 
                                    onclick="deleteKnowledgeBaseDocument('${flowId}', '${doc.document_id}', event)"
                                    title="Удалить">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </div>
                `;
            });
            
            html += '</div>';
            listContainer.innerHTML = html;
            
            listContainer.querySelectorAll('.document-card-clickable').forEach(card => {
                card.addEventListener('click', (e) => {
                    const url = card.dataset.downloadUrl;
                    if (!url) {
                        return;
                    }
                    const withinActions = e.target.closest('.document-actions');
                    if (withinActions) {
                        return;
                    }
                    window.open(url, '_blank', 'noopener');
                });
            });
            
        } catch (error) {
            console.error('Ошибка загрузки документов:', error);
            listContainer.innerHTML = `
                <div class="error-state">
                    <i class="bi bi-exclamation-triangle"></i>
                    <p>Не удалось загрузить документы</p>
                </div>
            `;
        }
    };
    
    window.deleteKnowledgeBaseDocument = async function(flowId, documentId, event) {
        if (event) {
            event.stopPropagation();
        }
        if (!confirm('Удалить этот документ из базы знаний?')) {
            return;
        }
        
        try {
            const response = await fetch(`/api/v1/knowledge-base/flows/${flowId}/documents/${documentId}`, {
                method: 'DELETE'
            });
            
            if (!response.ok) {
                throw new Error('Ошибка удаления документа');
            }
            
            showNotification('Документ удален из базы знаний', 'success');
            await loadKnowledgeBaseDocuments(flowId);
            
        } catch (error) {
            console.error('Ошибка удаления документа:', error);
            showNotification('Не удалось удалить документ: ' + error.message, 'danger');
        }
    };
    
    const originalInitBotSettings = window.initBotSettings;
    window.initBotSettings = function() {
        if (originalInitBotSettings) {
            originalInitBotSettings();
        }
        
        const knowledgeTab = document.querySelector('[data-tab="knowledge"]');
        if (knowledgeTab && knowledgeTab.classList.contains('active')) {
            const flowIdElement = document.querySelector('[data-flow-id]');
            if (flowIdElement) {
                const flowId = flowIdElement.dataset.flowId;
                if (flowId && flowId !== 'new') {
                    loadKnowledgeBaseDocuments(flowId);
                }
            }
        }
    };

    window.copyToClipboard = async function(text) {
        try {
            await navigator.clipboard.writeText(text);
            if (window.app) {
                window.app.showNotification('Скопировано в буфер обмена', 'success');
            }
        } catch (err) {
            console.error('Ошибка копирования:', err);
            if (window.app) {
                window.app.showNotification('Не удалось скопировать текст', 'danger');
            }
        }
    };

})();
