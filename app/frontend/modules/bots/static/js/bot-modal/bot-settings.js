/**
 * Bot Settings Manager
 */

export class BotSettingsManager {
    constructor(app, toolsManager, kbManager, mcpManager) {
        this.app = app;
        this.toolsManager = toolsManager;
        this.kbManager = kbManager;
        this.mcpManager = mcpManager;
        this.promptEditor = null;
        this.llmModelsData = null;
    }
    
    init() {
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
                    
                    if (targetPanel === 'main' && !this.promptEditor) {
                        this.initPromptEditor();
                    }
                    
                    if (targetPanel === 'abilities') {
                        const toolsSelector = document.getElementById('bot-tools-selector');
                        if (toolsSelector && !toolsSelector.dataset.loaded) {
                            this.toolsManager.loadTools();
                            toolsSelector.dataset.loaded = 'true';
                        }
                    }
                    
                    if (targetPanel === 'mcp') {
                        const mcpSelector = document.getElementById('bot-mcp-selector');
                        if (mcpSelector && !mcpSelector.dataset.loaded) {
                            this.mcpManager.loadMCPTools();
                            mcpSelector.dataset.loaded = 'true';
                        }
                    }
                    
                    if (targetPanel === 'knowledge') {
                        const flowIdElement = document.querySelector('[data-flow-id]');
                        if (flowIdElement) {
                            const flowId = flowIdElement.dataset.flowId;
                            if (flowId && flowId !== 'new') {
                                this.kbManager.loadDocuments(flowId);
                            }
                        }
                    }
                }
            });
        });
        
        const activePanel = document.querySelector('.settings-panel.active');
        if (activePanel && activePanel.dataset.panel === 'main') {
            this.initPromptEditor();
        }
        
        this.updateLLMModels();

        const platformCards = document.querySelectorAll('.platform-settings');
        platformCards.forEach(card => {
            if (!card.classList.contains('collapsed')) {
                card.classList.add('collapsed');
            }
        });

        // Инлайн-редактирование имени бота в заголовке
        const nameDisplay = document.getElementById('bot-name-display');
        const nameInput = document.getElementById('bot-name');
        if (nameDisplay && nameInput) {
            const startEdit = () => {
                nameInput.style.display = '';
                nameInput.value = (nameDisplay.textContent || '').trim();
                nameInput.focus();
                nameInput.select();
                nameDisplay.style.display = 'none';
            };
            const finishEdit = () => {
                const newName = nameInput.value?.trim();
                if (newName) {
                    nameDisplay.textContent = newName;
                }
                nameInput.style.display = 'none';
                nameDisplay.style.display = '';
            };
            nameDisplay.addEventListener('click', startEdit);
            nameInput.addEventListener('blur', finishEdit);
            nameInput.addEventListener('keydown', (e) => {
                if (e.key === 'Enter') {
                    e.preventDefault();
                    finishEdit();
                } else if (e.key === 'Escape') {
                    e.preventDefault();
                    nameInput.style.display = 'none';
                    nameDisplay.style.display = '';
                }
            });
        }
    }
    
    initPromptEditor() {
        const container = document.getElementById('bot-prompt-editor-container');
        if (!container) {
            console.error('Контейнер для prompt editor не найден');
            return;
        }
        
        const botModal = this.app.botsModule.modal;
        const flowId = botModal.getCurrentBotId();
        const promptData = container.dataset.prompt || '';
        
        if (this.app.createPromptEditor) {
            this.promptEditor = this.app.createPromptEditor(container, {
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
    
    async loadLLMModels() {
        if (this.llmModelsData) return this.llmModelsData;
        
        try {
            const response = await fetch('/api/v1/admin/llm/models', {
                headers: {
                    'Authorization': `Bearer ${this.app.authToken}`
                }
            });
            
            if (!response.ok) {
                throw new Error('Не удалось загрузить список LLM моделей');
            }
            
            this.llmModelsData = await response.json();
            return this.llmModelsData;
        } catch (error) {
            console.error('Ошибка загрузки LLM моделей:', error);
            return null;
        }
    }
    
    async updateLLMModels() {
        const modelSelect = document.getElementById('bot-llm-model');
        
        if (!modelSelect) return;
        
        const currentValue = modelSelect.dataset.currentValue || modelSelect.value;
        
        const modelsData = await this.loadLLMModels();
        
        modelSelect.innerHTML = '';
        
        const defaultOption = document.createElement('option');
        defaultOption.value = '';
        defaultOption.textContent = 'По умолчанию';
        modelSelect.appendChild(defaultOption);
        
        if (modelsData && modelsData.models) {
            modelsData.models.forEach(model => {
                const option = document.createElement('option');
                option.value = model.value;
                option.textContent = model.label;
                if (model.value === currentValue) {
                    option.selected = true;
                }
                modelSelect.appendChild(option);
            });
        }
    }
}

