/**
 * AgentEditorPage - главный компонент редактора агента
 * Layout: sidebar | canvas с плавающей property panel
 * Property panel может разворачиваться в полноэкранную модалку
 * Интегрирует: ExecutionRunner, BreakpointManager, ExecutionPanel, VariablesPanel, SkillsTabsBar
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { AgentsStore } from '../../store/agents.store.js';
import { injectEditorStyles } from './agent-editor-styles.js';
import '../../modals/confirm-modal.js';
import '../../modals/code-modal.js';

export class AgentEditorPage extends PlatformElement {
    // Light DOM для совместимости с глобальными стилями Drawflow
    createRenderRoot() {
        return this;
    }

    static properties = {
        agentId: { type: String, attribute: 'agent-id' },
        skillId: { type: String, attribute: 'skill-id' },
        editorMode: { type: String },
    };

    constructor() {
        super();
        this.agentId = '';
        this.skillId = '';
        this.editorMode = 'visual';
        
        this.state = this.use(s => ({
            agentConfig: s.editor.agentConfig,
            selectedNodeId: s.editor.selectedNodeId,
            currentSkillId: s.editor.currentSkillId,
            skillsData: s.editor.skillsData,
            inheritedData: s.editor.inheritedData,
            panelOpen: s.editor.panelOpen,
            panelExpanded: s.editor.panelExpanded,
            executionPanelOpen: s.editor.executionPanelOpen,
            variablesPanelOpen: s.editor.variablesPanelOpen,
            isDirty: s.editor.isDirty,
            isSaving: s.editor.isSaving,
            loading: s.editor.loading,
        }));
        
        this._panelEntering = false;
        this._confirmModal = null;
    }

    async connectedCallback() {
        super.connectedCallback();
        injectEditorStyles();
        console.log('[AgentEditorPage] connectedCallback, agentId:', this.agentId, 'skillId:', this.skillId);
        
        if (this.agentId) {
            console.log('[AgentEditorPage] Loading agent...');
            
            try {
                await AgentsStore.loadAgent(this.agentId, this.a2a, this.skillId || null);
                console.log('[AgentEditorPage] Agent loaded, initializing canvas...');
                
                await this.updateComplete;
                
                const data = this.state.value.skillsData;
                const inherited = this.state.value.inheritedData;
                
                if (data && Object.keys(data.nodes || {}).length > 0) {
                    this._updateCanvasDirectly(data, inherited);
                }
            } catch (error) {
                console.error('[AgentEditorPage] Failed to load agent:', error);
                this.error('Ошибка загрузки агента: ' + error.message);
            }
        } else {
            console.warn('[AgentEditorPage] No agentId provided!');
        }
        
        this._handleDocumentClick = this._handleDocumentClick.bind(this);
        document.addEventListener('click', this._handleDocumentClick);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._handleDocumentClick);
    }

    _handleDocumentClick(e) {
        if (!this.state.value.variablesPanelOpen) return;

        const variablesPanel = this.querySelector('variables-panel');
        if (!variablesPanel) return;

        const path = e.composedPath();
        const clickInsidePanel = path.includes(variablesPanel);
        
        const clickOnVariablesButton = path.some(el => 
            el.nodeType === 1 && (
                el.getAttribute?.('title') === 'Variables' ||
                el.closest?.('[title="Variables"]')
            )
        );
        
        const clickOnModal = path.some(el => 
            el.nodeType === 1 && el.tagName === 'VARIABLE-EDITOR-MODAL'
        );

        console.log('[AgentEditorPage] Document click:', {
            clickInsidePanel,
            clickOnVariablesButton,
            clickOnModal,
            path_length: path.length,
            target: e.target,
        });

        if (!clickInsidePanel && !clickOnVariablesButton && !clickOnModal) {
            console.log('[AgentEditorPage] Closing variables panel');
            AgentsStore.toggleVariablesPanel();
        }
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        
        console.log('[AgentEditorPage] updated() called, changed:', Array.from(changedProperties.keys()));
        
        if (changedProperties.has('agentConfig') && this.state.value.agentConfig) {
            this._setupComponentReferences();
        }
    }
    
    async _updateCanvasDirectly(data, inherited) {
        await this.updateComplete;
        const canvas = this.querySelector('agent-canvas');
        
        if (!canvas) {
            console.warn('[AgentEditorPage] Canvas not found');
            return;
        }
        
        await canvas.updateComplete;
        
        if (!canvas._editor) {
            console.warn('[AgentEditorPage] Canvas editor not initialized yet');
            return;
        }
        
        console.log('[AgentEditorPage] Direct canvas update with data:', {
            nodes: Object.keys(data?.nodes || {}),
            edges: data?.edges?.length,
            entry: data?.entry
        });
        
        canvas.loadData(data, inherited);
    }

    _setupComponentReferences() {
        const canvas = this.querySelector('agent-canvas');
        const breakpointManager = this.querySelector('breakpoint-manager');
        
        if (canvas && breakpointManager) {
            canvas.setBreakpointManager(breakpointManager);
        }
    }

    async _loadAgent() {
        if (!this.agentId) return;
        
        this._loading = true;
        
        const config = await this.a2a.getAgentConfig(this.agentId);
        this.state.value.agentConfig = config;
        
        this.state.value.skillsData = {
            nodes: config.nodes || {},
            edges: config.edges || [],
            entry: config.entry || null,
            variables: config.variables || {},
        };
        
        this._loading = false;
        
        // Сохраняем хеш начального состояния
        this._initialConfigHash = this._calculateConfigHash();
        this._hasUnsavedChanges = false;
        
        // Инициализируем канвас с базовыми данными
        await this.updateComplete;
        const canvas = this.querySelector('agent-canvas');
        console.log('[AgentEditorPage] Canvas after load:', canvas, 'Data:', this.state.value.skillsData);
        if (canvas) {
            await canvas.updateComplete;
            console.log('[AgentEditorPage] Loading data to canvas:', {
                nodes: Object.keys(this.state.value.skillsData.nodes || {}),
                edges: this.state.value.skillsData.edges?.length,
                entry: this.state.value.skillsData.entry
            });
            canvas.loadData(this.state.value.skillsData, null);
        } else {
            console.error('[AgentEditorPage] Canvas element not found!');
        }
    }
    
    _calculateConfigHash() {
        const canvas = this.querySelector('agent-canvas');
        const canvasData = canvas?.getData() || this.state.value.skillsData;
        const header = this.querySelector('editor-header');
        const agentName = header?.getAgentName() || this.state.value.agentConfig?.name || '';
        
        const dataToHash = JSON.stringify({
            name: agentName,
            nodes: canvasData.nodes,
            edges: canvasData.edges,
            entry: canvasData.entry,
            variables: this.state.value.skillsData.variables,
        });
        
        let hash = 0;
        for (let i = 0; i < dataToHash.length; i++) {
            const char = dataToHash.charCodeAt(i);
            hash = ((hash << 5) - hash) + char;
            hash = hash & hash;
        }
        return hash.toString();
    }
    
    _checkForChanges() {
        const currentHash = this._calculateConfigHash();
        const hasChanges = currentHash !== this._initialConfigHash;
        
        if (hasChanges !== this._hasUnsavedChanges) {
            this._hasUnsavedChanges = hasChanges;
        }
    }

    _onModeChanged(e) {
        const { mode } = e.detail;
        this.editorMode = mode;
        
        if (mode === 'run') {
            AgentsStore.setExecutionPanelOpen(true);
            this._panelOpen = false;
        } else {
            AgentsStore.setExecutionPanelOpen(false);
        }
    }

    _onSkillSwitched(e) {
        const { skillId, data, inherited } = e.detail;
        AgentsStore.setCurrentSkill(skillId);
        AgentsStore.updateSkillsData(data, inherited);
        
        console.log(`[AgentEditorPage] Skill switched to "${skillId}":`, {
            variables: data.variables,
            variables_keys: Object.keys(data.variables || {}),
        });
        
        this._updateCanvasDirectly(data, inherited);
        
        this.success(`Переключено на ${skillId === 'base' ? 'базовый флоу' : 'skill: ' + skillId}`);
    }

    _onSaveCurrentSkillData(e) {
        const { skillId } = e.detail;
        const canvas = this.querySelector('agent-canvas');
        const skillsTabsBar = this.querySelector('skills-tabs-bar');
        
        if (canvas && skillsTabsBar) {
            const canvasData = canvas.getData();
            skillsTabsBar.updateSkillData(skillId, canvasData);
        }
    }

    _onVariablesChanged(e) {
        const { variables } = e.detail;
        const skillsTabsBar = this.querySelector('skills-tabs-bar');
        
        if (skillsTabsBar) {
            skillsTabsBar.updateSkillVariables(this.state.value.currentSkillId, variables);
        }
        
        AgentsStore.updateVariables(variables);
        this._checkForChanges();
    }

    _onRunAgent(e) {
        const { message, files, mocks } = e.detail;
        const executionRunner = this.querySelector('execution-runner');
        const breakpointManager = this.querySelector('breakpoint-manager');
        
        if (executionRunner && breakpointManager) {
            const breakpoints = breakpointManager.getBreakpointsObject();
            executionRunner.run(message, files, breakpoints, mocks);
        }
    }

    _onStopAgent() {
        const executionRunner = this.querySelector('execution-runner');
        if (executionRunner) {
            executionRunner.stop();
        }
    }

    _onResumeAgent(e) {
        const { answer, contextId } = e.detail;
        const executionRunner = this.querySelector('execution-runner');
        const breakpointManager = this.querySelector('breakpoint-manager');
        
        if (breakpointManager) {
            breakpointManager.clearActiveBreakpoint();
        }
        
        if (executionRunner) {
            executionRunner.resume(answer, contextId);
        }
    }

    _onNodeStatusUpdate(e) {
        const { nodeId, status } = e.detail;
        const canvas = this.querySelector('agent-canvas');
        
        if (canvas) {
            if (status === 'running') {
                canvas.highlightNode(nodeId, 'running');
            } else if (status === 'completed') {
                setTimeout(() => {
                    canvas.highlightNode(nodeId, 'completed');
                    setTimeout(() => {
                        canvas.clearNodeHighlight(nodeId);
                    }, 1500);
                }, 300);
            } else if (status === 'error') {
                canvas.highlightNode(nodeId, 'error');
            }
        }
    }

    _onNodeErrorDetails(e) {
        const { nodeId, error } = e.detail;
        const canvas = this.querySelector('agent-canvas');
        
        if (canvas) {
            canvas.showNodeError(nodeId, error);
        }
        
        this.error(`Ошибка в ноде "${nodeId}"`);
    }

    _onBreakpointHit(e) {
        const { nodeId, stateSnapshot } = e.detail;
        const breakpointManager = this.querySelector('breakpoint-manager');
        const canvas = this.querySelector('agent-canvas');
        const executionPanel = this.querySelector('execution-panel');
        
        if (breakpointManager) {
            breakpointManager.handleBreakpointHit(nodeId, null, stateSnapshot);
        }
        
        if (canvas) {
            canvas.setBreakpointStatus(nodeId, true, true);
        }
        
        if (executionPanel) {
            executionPanel.setBreakpoint(nodeId);
        }
        
        this.info(`Breakpoint hit на ноде "${nodeId}". Нажмите "Продолжить выполнение" для resume.`);
    }

    _onExecutionComplete(e) {
        const { result } = e.detail;
        const executionPanel = this.querySelector('execution-panel');
        const breakpointManager = this.querySelector('breakpoint-manager');
        
        if (executionPanel) {
            executionPanel.setRunning(false);
            executionPanel.showResult(result || 'Выполнение завершено');
            executionPanel.clearBreakpoint();
        }
        
        if (breakpointManager) {
            breakpointManager.clearActiveBreakpoint();
        }
        
        const canvas = this.querySelector('agent-canvas');
        if (canvas) {
            canvas.clearAllHighlights();
        }
        
        this.success('Выполнение завершено');
    }

    _onInputRequired(e) {
        const { question, contextId } = e.detail;
        const executionPanel = this.querySelector('execution-panel');
        
        if (executionPanel) {
            executionPanel.setInputRequired(question, contextId);
        }
    }

    _onExecutionStarted(e) {
        const { contextId, taskId } = e.detail;
        const executionPanel = this.querySelector('execution-panel');
        const canvas = this.querySelector('agent-canvas');
        
        if (executionPanel) {
            executionPanel.setRunning(true);
            executionPanel.setExecutionData(contextId, taskId);
        }
        
        if (canvas) {
            canvas.clearAllHighlights();
        }
    }

    _onExecutionError(e) {
        const { error } = e.detail;
        const executionPanel = this.querySelector('execution-panel');
        
        if (executionPanel) {
            executionPanel.setRunning(false);
            executionPanel.showError(error);
        }
        
        this.error('Ошибка выполнения');
    }

    _onBreakpointsChanged(e) {
        const { breakpoints } = e.detail;
        const canvas = this.querySelector('agent-canvas');
        
        if (canvas) {
            for (const [nodeId, enabled] of Object.entries(breakpoints)) {
                canvas.setBreakpointStatus(nodeId, enabled, false);
            }
        }
    }

    _onVariableAdd() {
        const modal = this.querySelector('variable-editor-modal');
        if (modal) {
            modal.showCreate();
        }
    }

    _onVariableEdit(e) {
        const { name, value, isInherited } = e.detail;
        const data = this.state.value.skillsData.variables[name];
        
        const modal = this.querySelector('variable-editor-modal');
        if (modal) {
            modal.showEdit(name, data, isInherited);
        }
    }

    _onVariableDelete(e) {
        const { name } = e.detail;

        const newVariables = { ...this.state.value.skillsData.variables };
        delete newVariables[name];
        
        AgentsStore.updateVariables(newVariables);
        this._checkForChanges();
        this.success(`Переменная "${name}" удалена`);
    }

    _onVariableSaved(e) {
        const { name, value, public: isPublic, title, description, order } = e.detail;
        const { skillsData, inheritedData } = this.state.value;

        const newVariables = {
            ...skillsData.variables,
            [name]: {
                value: value,
                public: isPublic,
                title: title,
                description: description,
                order: order,
            },
        };

        if (inheritedData && inheritedData.variableKeys && inheritedData.variableKeys.has(name)) {
            const newInheritedKeys = new Set(inheritedData.variableKeys);
            newInheritedKeys.delete(name);
            const newInherited = {
                ...inheritedData,
                variableKeys: newInheritedKeys,
            };
            AgentsStore.updateSkillsData({ ...skillsData, variables: newVariables }, newInherited);
        } else {
            AgentsStore.updateVariables(newVariables);
        }

        this._checkForChanges();
        this.success(`Переменная "${name}" сохранена`);
    }

    _onBreakpointCleared(e) {
        const { nodeId } = e.detail;
        const canvas = this.querySelector('agent-canvas');
        
        if (canvas) {
            canvas.setBreakpointStatus(nodeId, true, false);
        }
    }

    _onShowState(e) {
        const { contextId, taskId } = e.detail;
        this.info(`Opening state viewer for context: ${contextId}, task: ${taskId}`);
        
        const modal = document.createElement('state-modal');
        modal.contextId = contextId;
        modal.taskId = taskId;
        modal.agentId = this.agentId;
        document.body.appendChild(modal);
        modal.showModal();
        
        modal.addEventListener('close', () => {
            modal.remove();
        }, { once: true });
    }

    _onShowTracing(e) {
        const { contextId, taskId } = e.detail;
        this.info(`Opening tracing viewer for context: ${contextId}, task: ${taskId}`);
        
        const modal = document.createElement('tracing-modal');
        modal.agentId = this.agentId;
        modal.taskId = taskId;
        document.body.appendChild(modal);
        modal.showModal();
        
        modal.addEventListener('close', () => {
            modal.remove();
        }, { once: true });
    }

    _onToggleMocks(e) {
        this.info('Mocks panel toggled');
    }

    _onCloseExecutionPanel() {
        AgentsStore.setExecutionPanelOpen(false);
        this.editorMode = 'visual';
    }

    _onShowCode() {
        const canvas = this.querySelector('agent-canvas');
        const skillsTabsBar = this.querySelector('skills-tabs-bar');
        const header = this.querySelector('editor-header');
        
        const canvasData = canvas?.getData() || { nodes: {}, edges: [], entry: null };
        
        if (skillsTabsBar) {
            skillsTabsBar.updateSkillData(this.state.value.currentSkillId, canvasData);
        }
        
        const currentSkillData = {
            nodes: canvasData.nodes,
            edges: canvasData.edges,
            entry: canvasData.entry,
            variables: this.state.value.skillsData.variables || {},
        };
        
        const agentName = header?.getAgentName() || this.state.value.agentConfig?.name || '';
        const skills = skillsTabsBar?.getSkillsForSubmit() || {};
        
        const fullConfig = {
            ...this.state.value.agentConfig,
            name: agentName,
            nodes: currentSkillData.nodes,
            edges: currentSkillData.edges,
            entry: currentSkillData.entry,
            variables: currentSkillData.variables,
            skills,
        };
        
        const modal = document.createElement('code-modal');
        document.body.appendChild(modal);
        modal.showModal(fullConfig);
        
        modal.addEventListener('close', () => {
            modal.remove();
        }, { once: true });
    }

    _toggleVariablesPanel() {
        AgentsStore.toggleVariablesPanel();
    }

    _onNodeSelected(e) {
        const { nodeId, nodeConfig } = e.detail;
        
        console.log('[AgentEditorPage] Node selected:', {
            nodeId,
            nodeConfig,
            skillsData: this.state.value.skillsData,
            nodeInSkillsData: this.state.value.skillsData?.nodes?.[nodeId]
        });
        
        if (!nodeId) {
            console.error('[AgentEditorPage] Node selected but nodeId is missing!');
            return;
        }
        
        AgentsStore.selectNode(nodeId);
        this._panelEntering = true;
        
        setTimeout(() => {
            this._panelEntering = false;
        }, 300);
    }

    _onNodeAdded(e) {
        console.log('[AgentEditorPage] Node added, syncing with store');
        this._syncCanvasToAgentsStore();
        this._checkForChanges();
    }

    _syncCanvasToAgentsStore() {
        // Синхронизируем данные с canvas в store
        const canvas = this.querySelector('agent-canvas');
        if (!canvas) return;
        
        const canvasData = canvas.getData();
        console.log('[AgentEditorPage] Syncing canvas data to store:', canvasData);
        
        AgentsStore.updateSkillsData(canvasData, this.state.value.inheritedData);
    }

    _onNodeUnselected() {
        // Не закрываем панель автоматически при снятии выделения
    }

    _closePanel() {
        AgentsStore.closePanel();
    }

    _toggleExpanded() {
        AgentsStore.togglePanelExpanded();
    }

    _onBackdropClick() {
        if (this.state.value.panelExpanded) {
            AgentsStore.togglePanelExpanded();
        }
    }

    _onNodeUpdated(e) {
        const { nodeId, nodeConfig } = e.detail;
        
        console.log('[AgentEditorPage] _onNodeUpdated called:', { nodeId, nodeConfig });
        
        const canvas = this.querySelector('agent-canvas');
        if (canvas) {
            canvas.updateNodeConfig(nodeId, nodeConfig);
        } else {
            console.error('[AgentEditorPage] Canvas not found!');
        }
        
        // Также обновляем Store чтобы property-panel видел изменения
        const currentSkillsData = this.state.value.skillsData;
        if (currentSkillsData && currentSkillsData.nodes && currentSkillsData.nodes[nodeId]) {
            const updatedNodes = {
                ...currentSkillsData.nodes,
                [nodeId]: {
                    ...currentSkillsData.nodes[nodeId],
                    ...nodeConfig
                }
            };
            
            AgentsStore.updateSkillsData({
                ...currentSkillsData,
                nodes: updatedNodes
            });
            
            console.log('[AgentEditorPage] Updated skillsData for node:', nodeId);
        }
        
        this._checkForChanges();
        this.emit('agent-changed');
    }

    _onNodeDeleted(e) {
        const { nodeId } = e.detail;
        
        const canvas = this.querySelector('agent-canvas');
        if (canvas) {
            canvas.removeNode(nodeId);
        }
        
        if (this.state.value.selectedNodeId === nodeId) {
            AgentsStore.closePanel();
        }
        
        this._checkForChanges();
        this.emit('agent-changed');
    }

    _onNodeIdChanged(e) {
        const { oldId, newId } = e.detail;
        const canvas = this.querySelector('agent-canvas');
        
        if (canvas?.updateNodeId(oldId, newId)) {
            const data = this.state.value.skillsData;
            if (data?.nodes?.[oldId]) {
                const nodeData = data.nodes[oldId];
                delete data.nodes[oldId];
                data.nodes[newId] = { ...nodeData, nodeId: newId };
                
                if (data.entry === oldId) {
                    data.entry = newId;
                }
                
                data.edges = data.edges.map(edge => ({
                    ...edge,
                    from: edge.from === oldId ? newId : edge.from,
                    to: edge.to === oldId ? newId : edge.to,
                }));
                
                AgentsStore.updateSkillsData(data, this.state.value.inheritedData);
            }
            
            if (this.state.value.selectedNodeId === oldId) {
                AgentsStore.selectNode(newId);
            }
            
            this._checkForChanges();
            this.success(`Node ID: ${oldId} → ${newId}`);
        }
    }

    async _handleSave() {
        try {
            const canvas = this.querySelector('agent-canvas');
            const skillsTabsBar = this.querySelector('skills-tabs-bar');
            const header = this.querySelector('editor-header');
            
            const canvasData = canvas?.getData() || { nodes: {}, edges: [], entry: null };
            
            console.log('[AgentEditorPage] _handleSave - canvasData:', canvasData);
            console.log('[AgentEditorPage] _handleSave - canvasData.nodes:', Object.keys(canvasData.nodes));
            
            if (skillsTabsBar) {
                skillsTabsBar.updateSkillData(this.state.value.currentSkillId, canvasData);
            }
            
            const currentSkillData = {
                nodes: canvasData.nodes,
                edges: canvasData.edges,
                entry: canvasData.entry,
                variables: this.state.value.skillsData.variables || {},
            };
            
            const agentName = header?.getAgentName() || this.state.value.agentConfig?.name || '';
            const skills = skillsTabsBar?.getSkillsForSubmit() || {};
            
            const updatedConfig = {
                ...this.state.value.agentConfig,
                name: agentName,
                nodes: currentSkillData.nodes,
                edges: currentSkillData.edges,
                entry: currentSkillData.entry,
                variables: currentSkillData.variables,
                skills,
            };
            
            console.log('[AgentEditorPage] _handleSave - updatedConfig.nodes:', Object.keys(updatedConfig.nodes));
            console.log('[AgentEditorPage] _handleSave - order_processor node:', updatedConfig.nodes.order_processor);
            
            await this.a2a.saveAgentConfig(this.agentId, updatedConfig);
            
            this.success('Агент сохранен, перезагрузка...');
            
            const currentSkillId = this.state.value.currentSkillId;
            await AgentsStore.loadAgent(this.agentId, this.a2a, currentSkillId);
            
            AgentsStore.setDirty(false);
            this.success('Агент успешно обновлен');
            this.emit('agent-saved', { agentId: this.agentId });
        } catch (error) {
            console.error('[AgentEditorPage] Save error:', error);
            this.error('Ошибка сохранения: ' + error.message);
        }
    }

    _handleClose() {
        if (this._hasUnsavedChanges) {
            this._showUnsavedChangesDialog();
        } else {
            this._closeEditor();
        }
    }
    
    _showUnsavedChangesDialog() {
        if (!this._confirmModal) {
            this._confirmModal = document.createElement('confirm-modal');
            document.body.appendChild(this._confirmModal);
            
            this._confirmModal.addEventListener('confirm', () => {
                this._handleSaveAndClose();
            });
            
            this._confirmModal.addEventListener('cancel', () => {
                // Ничего не делаем, просто закрываем модалку
            });
        }
        
        this._confirmModal.showModal({
            title: 'Несохраненные изменения',
            subtitle: 'У вас есть несохраненные изменения',
            message: 'Вы хотите сохранить изменения перед выходом из редактора?',
            variant: 'warning',
            confirmText: 'Сохранить и выйти',
            cancelText: 'Отменить',
            confirmVariant: 'primary',
        });
        
        // Добавляем третью кнопку "Выйти без сохранения"
        const footer = this._confirmModal.shadowRoot.querySelector('.modal-footer');
        if (footer && !footer.querySelector('.discard-btn')) {
            const discardBtn = document.createElement('button');
            discardBtn.type = 'button';
            discardBtn.className = 'modal-btn danger discard-btn';
            discardBtn.textContent = 'Выйти без сохранения';
            discardBtn.addEventListener('click', () => {
                this._confirmModal.close();
                this._closeEditor();
            });
            footer.insertBefore(discardBtn, footer.firstChild);
        }
    }
    
    async _handleSaveAndClose() {
        await this._handleSave();
        this._closeEditor();
    }
    
    _closeEditor() {
        this.emit('editor-close');
    }

    _getNodeColor() {
        return this.selectedNode?.color || '#6b7280';
    }

    _renderFloatingPanel() {
        const { panelOpen, panelExpanded, selectedNodeId, agentConfig, currentSkillId, skillsData } = this.state.value;
        
        console.log('[AgentEditorPage] _renderFloatingPanel:', {
            panelOpen,
            selectedNodeId,
            hasSkillsData: !!skillsData,
            nodeCount: Object.keys(skillsData?.nodes || {}).length
        });
        
        if (!panelOpen || !selectedNodeId) {
            return null;
        }
        
        // Берем ноду из skillsData (актуальные данные с canvas)
        const selectedNode = skillsData?.nodes?.[selectedNodeId];
        if (!selectedNode) {
            console.error('[AgentEditorPage] Selected node not found in skillsData:', {
                selectedNodeId,
                availableNodes: Object.keys(skillsData?.nodes || {})
            });
            return null;
        }
        
        console.log('[AgentEditorPage] Rendering panel for node:', selectedNode);
        
        const color = selectedNode.color || '#6b7280';
        const bgColor = color + '20';
        
        const panelClasses = ['floating-panel'];
        if (panelExpanded) panelClasses.push('expanded');
        if (this._panelEntering) panelClasses.push('entering');

        return html`
            <div 
                class="panel-backdrop ${panelExpanded ? 'visible' : ''}"
                @click=${this._onBackdropClick}
            ></div>
            <div class="${panelClasses.join(' ')}">
                <div class="floating-panel-header">
                    <div class="floating-panel-title">
                        <div class="floating-panel-icon" style="background: ${bgColor}; color: ${color};">
                            <platform-icon name="agent" size="${panelExpanded ? 18 : 14}"></platform-icon>
                        </div>
                        <span class="floating-panel-name">${selectedNode.name || selectedNode.nodeId || selectedNodeId}</span>
                    </div>
                    <div class="floating-panel-actions">
                        <button 
                            class="floating-panel-btn expand-btn" 
                            @click=${this._toggleExpanded} 
                            title="${panelExpanded ? 'Свернуть' : 'Развернуть'}"
                        >
                            <platform-icon name="${panelExpanded ? 'minimize' : 'maximize'}" size="16"></platform-icon>
                        </button>
                        <button class="floating-panel-btn" @click=${this._closePanel} title="Закрыть">
                            <platform-icon name="x" size="16"></platform-icon>
                        </button>
                    </div>
                </div>
                <div class="floating-panel-body">
                    <property-panel
                        .node=${{ id: selectedNodeId, ...selectedNode }}
                        .agentId=${this.agentId}
                        .skillId=${currentSkillId}
                        .agentConfig=${agentConfig}
                        .agentVariables=${agentConfig?.variables || {}}
                        ?expanded=${panelExpanded}
                        @node-updated=${this._onNodeUpdated}
                        @node-deleted=${this._onNodeDeleted}
                        @node-id-changed=${this._onNodeIdChanged}
                    ></property-panel>
                </div>
            </div>
        `;
    }

    render() {
        const { agentConfig, loading, isSaving, currentSkillId } = this.state.value;
        
        if (loading) {
            return html`
                <div class="editor-layout" style="align-items: center; justify-content: center;">
                    <platform-spinner variant="ai" size="80"></platform-spinner>
                </div>
            `;
        }

        return html`
            <div class="editor-layout">
                <editor-header
                    agent-name=${agentConfig?.name || 'New Agent'}
                    ?saving=${isSaving}
                    .mode=${this.editorMode}
                    @save=${this._handleSave}
                    @close=${this._handleClose}
                    @mode-changed=${this._onModeChanged}
                    @show-code=${this._onShowCode}
                ></editor-header>
                
                <skills-tabs-bar
                    .agentConfig=${agentConfig}
                    .currentSkillId=${currentSkillId}
                    @skill-switched=${this._onSkillSwitched}
                    @save-current-skill-data=${this._onSaveCurrentSkillData}
                ></skills-tabs-bar>
                
                <div class="editor-body">
                    <node-types-sidebar
                        class="node-types-sidebar"
                    ></node-types-sidebar>
                    
                    <div class="canvas-area">
                        <agent-canvas
                            @node-selected=${this._onNodeSelected}
                            @node-unselected=${this._onNodeUnselected}
                            @node-added=${this._onNodeAdded}
                            @connection-created=${() => this._checkForChanges()}
                            @connection-removed=${() => this._checkForChanges()}
                        ></agent-canvas>
                        <bottom-toolbar></bottom-toolbar>
                        
                        ${this._renderFloatingPanel()}
                        ${this._renderExecutionPanel()}
                        ${this._renderVariablesPanel()}
                        ${this._renderHiddenComponents()}
                    </div>
                </div>
            </div>
        `;
    }

    _renderExecutionPanel() {
        if (!this.state.value.executionPanelOpen) return null;
        
        return html`
            <div style="
                position: absolute;
                top: 80px;
                right: var(--space-4);
                z-index: 100;
            ">
                <execution-panel
                    .agentId=${this.agentId}
                    .skillId=${this.state.value.currentSkillId}
                    show-state
                    show-tracing
                    show-mocks
                    @run-requested=${this._onRunAgent}
                    @stop-requested=${this._onStopAgent}
                    @resume-agent=${this._onResumeAgent}
                    @state-requested=${this._onShowState}
                    @tracing-requested=${this._onShowTracing}
                    @mocks-requested=${this._onToggleMocks}
                    @close-requested=${this._onCloseExecutionPanel}
                ></execution-panel>
            </div>
        `;
    }

    _renderVariablesPanel() {
        if (!this.state.value.variablesPanelOpen) return null;
        
        const inheritedData = this.state.value.inheritedData || { 
            nodeIds: new Set(), 
            edgeKeys: new Set(), 
            variableKeys: new Set() 
        };
        
        return html`
            <div style="
                position: absolute;
                bottom: var(--space-4);
                left: calc(180px + var(--space-4));
                width: 360px;
                max-height: 400px;
                z-index: 30;
            ">
                <variables-panel
                    .variables=${this.state.value.skillsData.variables || {}}
                    .inheritedKeys=${inheritedData.variableKeys}
                    @variable-add-requested=${this._onVariableAdd}
                    @variable-edit-requested=${this._onVariableEdit}
                    @variable-deleted=${this._onVariableDelete}
                ></variables-panel>
            </div>
        `;
    }

    _renderHiddenComponents() {
        return html`
            <execution-runner
                style="display: none;"
                .agentId=${this.agentId}
                .skillId=${this.state.value.currentSkillId}
                @node-status=${this._onNodeStatusUpdate}
                @node-error-details=${this._onNodeErrorDetails}
                @breakpoint-hit=${this._onBreakpointHit}
                @execution-completed=${this._onExecutionComplete}
                @execution-error=${this._onExecutionError}
                @input-required=${this._onInputRequired}
                @execution-started=${this._onExecutionStarted}
            ></execution-runner>
            
            <breakpoint-manager
                style="display: none;"
                .agentId=${this.agentId}
                @breakpoints-changed=${this._onBreakpointsChanged}
                @breakpoint-cleared=${this._onBreakpointCleared}
            ></breakpoint-manager>

            <variable-editor-modal
                @variable-saved=${this._onVariableSaved}
            ></variable-editor-modal>
        `;
    }
}

customElements.define('agent-editor-page', AgentEditorPage);

