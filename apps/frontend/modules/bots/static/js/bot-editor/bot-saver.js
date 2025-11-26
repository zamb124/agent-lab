/**
 * Bot Saver
 */

import { slugify, generateUniqueId } from '/static/js/utils/slugify.js';
import { showNotification } from '/static/js/components/notification.js';

export class BotSaver {
    constructor(app, settingsManager, modalManager) {
        this.app = app;
        this.settingsManager = settingsManager;
        this.modalManager = modalManager;
    }
    
    async save(botId) {
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
            enable_reasoning: document.getElementById('bot-enable-reasoning')?.checked || false,
        };
        
        if (isNewBot) {
            const flowId = generateUniqueId(botName);
            const agentSlug = slugify(botName);
            const agentName = agentSlug.charAt(0).toUpperCase() + agentSlug.slice(1);
            
            flowData.flow_id = flowId;
            flowData.entry_point_agent = `${agentName}Agent`;
            flowData.platforms = {
                web: {},
                api: {}
            };
        }
        
        const promptValue = this.settingsManager.promptEditor ? this.settingsManager.promptEditor.getValue() : null;
        const flowVariables = this.settingsManager.promptEditor ? this.settingsManager.promptEditor.getFlowVariables() : null;
        const sessionStore = this.settingsManager.promptEditor ? this.settingsManager.promptEditor.getSessionStore() : null;
        
        console.log('🔍 DEBUG: flowVariables до добавления =', flowVariables);
        console.log('🔍 DEBUG: sessionStore до добавления =', sessionStore);
        
        if (flowVariables && Object.keys(flowVariables).length > 0) {
            flowData.variables = flowVariables;
        }
        
        if (sessionStore && Object.keys(sessionStore).length > 0) {
            flowData.store = sessionStore;
        }
        
        const namespaceScope = 'flow';
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
            enable_reasoning: flowData.enable_reasoning,
            promptValue: promptValue ? `${promptValue.substring(0, 100)}...` : null,
            flowVariables: flowVariables,
            hasPromptEditor: !!this.settingsManager.promptEditor
        });
        
        try {
            const method = isNewBot ? 'POST' : 'PUT';
            const url = isNewBot ? '/frontend/api/flows' : `/frontend/api/flows/${botId}`;
            
            const flowResponse = await fetch(url, {
                method: method,
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.app.authToken}`
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
            
            const entryPoint = savedFlow.entry_point_agent;
            if (entryPoint) {
                await this.saveAgentSettings(entryPoint, promptValue, sessionStore);
            }
            
            if (isNewBot) {
                showNotification('Бот успешно создан', 'success');
                this.modalManager.close();
                htmx.ajax('GET', '/frontend/bots/list', {
                    target: '#bots-list-view',
                    swap: 'innerHTML'
                });
            } else {
                showNotification('Настройки бота сохранены', 'success');
                await this.modalManager.expand(actualBotId);
            }
            
        } catch (error) {
            console.error('❌❌❌ Ошибка сохранения:', error);
            console.error('Stack trace:', error.stack);
            showNotification(
                (isNewBot ? 'Ошибка создания бота: ' : 'Ошибка сохранения настроек: ') + error.message, 
                'danger'
            );
        }
    }
    
    async saveAgentSettings(entryPoint, promptValue, sessionStore) {
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
        
        document.querySelectorAll('#bot-mcp-selector input[type="checkbox"]:checked').forEach(checkbox => {
            const mcpToolId = checkbox.dataset.mcpToolId;
            const serverName = checkbox.dataset.serverName;
            const toolName = checkbox.dataset.toolName;
            
            if (mcpToolId && serverName && toolName) {
                selectedTools.push({
                    tool_id: mcpToolId,
                    params: {},
                    code_mode: "mcp_tool",
                    is_public: true,
                    server_name: serverName,
                    tool_name: toolName
                });
            }
        });
        
        if (selectedTools.length > 0) {
            agentUpdates.tools = selectedTools;
        }
        
        const llmModel = document.getElementById('bot-llm-model')?.value;
        const llmTemperature = document.getElementById('bot-llm-temperature')?.value;
        
        if (llmModel || llmTemperature) {
            const llmConfig = {};
            
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
        
        if (sessionStore && Object.keys(sessionStore).length > 0) {
            agentUpdates.store = sessionStore;
        }
        
        if (Object.keys(agentUpdates).length > 0) {
            console.log('💾 Сохраняем настройки агента:', entryPoint, agentUpdates);
            const agentResponse = await fetch(`/frontend/api/agents/${encodeURIComponent(entryPoint)}`, {
                method: 'PUT',
                headers: {
                    'Content-Type': 'application/json',
                    'Authorization': `Bearer ${this.app.authToken}`
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
}

