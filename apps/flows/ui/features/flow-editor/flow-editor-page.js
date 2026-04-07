/**
 * FlowEditorPage - главный компонент редактора flow
 * Layout: sidebar | canvas с плавающей property panel
 * Property panel может разворачиваться в полноэкранную модалку
 * Интегрирует: ExecutionRunner, BreakpointManager, ExecutionPanel, VariablesPanel, SkillsTabsBar
 */
import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { FlowsStore } from '../../store/flows.store.js';
import { setUrlParam } from '../../utils/url-sync.js';
import { injectEditorStyles } from './flow-editor-styles.js';
import { confirm } from '../../modals/confirm-modal.js';
import '../../modals/code-modal.js';
import '../../modals/trigger-editor-modal.js';
import '../../modals/tool-picker-modal.js';
import './resource-property-panel.js';

export class FlowEditorPage extends PlatformElement {
    // Light DOM для совместимости с глобальными стилями Drawflow
    createRenderRoot() {
        return this;
    }

    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        skillId: { type: String, attribute: 'skill-id' },
        editorMode: { type: String },
    };

    constructor() {
        super();
        this.flowId = '';
        this.skillId = '';
        this.editorMode = 'visual';
        
        this.state = this.use(s => ({
            flowConfig: s.editor.flowConfig,
            selectedNodeId: s.editor.selectedNodeId,
            selectedResourceId: s.editor.selectedResourceId,
            currentSkillId: s.editor.currentSkillId,
            skillsData: s.editor.skillsData,
            inheritedData: s.editor.inheritedData,
            panelOpen: s.editor.panelOpen,
            panelExpanded: s.editor.panelExpanded,
            executionPanelOpen: s.editor.executionPanelOpen,
            agentExecutionRunning: s.editor.agentExecutionRunning,
            variablesPanelOpen: s.editor.variablesPanelOpen,
            isDirty: s.editor.isDirty,
            isSaving: s.editor.isSaving,
            loading: s.editor.loading,
            previewExecutionState: s.editor.previewExecutionState,
        }));
        
        this._panelEntering = false;
        this._confirmModal = null;
        this._reloadFromBundleBusy = false;
    }

    async connectedCallback() {
        super.connectedCallback();
        injectEditorStyles();
        console.log('[FlowEditorPage] connectedCallback, flowId:', this.flowId, 'skillId:', this.skillId);
        
        if (this.flowId) {
            console.log('[FlowEditorPage] Loading flow...');
            
            try {
                await FlowsStore.loadFlow(this.flowId, this.a2a, this.skillId || null);
                console.log('[FlowEditorPage] Flow loaded, initializing canvas...');
                
                await this.updateComplete;
                
                const data = this.state.value.skillsData;
                const inherited = this.state.value.inheritedData;
                
                if (data && Object.keys(data.nodes || {}).length > 0) {
                    this._updateCanvasDirectly(data, inherited);
                }
            } catch (error) {
                console.error('[FlowEditorPage] Failed to load flow:', error);
                this.error(this.i18n.t('editor.load_agent_error', { message: error.message }));
            }
        } else {
            console.warn('[FlowEditorPage] No flowId provided!');
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

        console.log('[FlowEditorPage] Document click:', {
            clickInsidePanel,
            clickOnVariablesButton,
            clickOnModal,
            path_length: path.length,
            target: e.target,
        });

        if (!clickInsidePanel && !clickOnVariablesButton && !clickOnModal) {
            console.log('[FlowEditorPage] Closing variables panel');
            FlowsStore.toggleVariablesPanel();
        }
    }

    updated(changedProperties) {
        super.updated(changedProperties);
        
        console.log('[FlowEditorPage] updated() called, changed:', Array.from(changedProperties.keys()));

        const panelBody = this.querySelector('.floating-panel-body');
        if (panelBody?.classList.contains('editor-fullscreen-embed-clip')) {
            panelBody.classList.remove('editor-fullscreen-embed-clip');
        }

        if (this.state.value.loading) {
            return;
        }
        const canvas = this.querySelector('flow-canvas');
        const breakpointManager = this.querySelector('breakpoint-manager');
        if (canvas && breakpointManager && canvas.breakpointManager !== breakpointManager) {
            canvas.setBreakpointManager(breakpointManager);
        }
    }
    
    async _updateCanvasDirectly(data, inherited) {
        await this.updateComplete;
        const canvas = this.querySelector('flow-canvas');
        
        if (!canvas) {
            console.warn('[FlowEditorPage] Canvas not found');
            return;
        }
        
        await canvas.updateComplete;
        
        if (!canvas._editor) {
            console.warn('[FlowEditorPage] Canvas editor not initialized yet');
            return;
        }
        
        console.log('[FlowEditorPage] Direct canvas update with data:', {
            nodes: Object.keys(data?.nodes || {}),
            edges: data?.edges?.length,
            entry: data?.entry
        });
        
        canvas.loadData(data, inherited);
    }

    async _loadFlow() {
        if (!this.flowId) return;
        
        this._loading = true;
        
        const config = await this.a2a.getFlowConfig(this.flowId);
        this.state.value.flowConfig = config;
        
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
        const canvas = this.querySelector('flow-canvas');
        console.log('[FlowEditorPage] Canvas after load:', canvas, 'Data:', this.state.value.skillsData);
        if (canvas) {
            await canvas.updateComplete;
            console.log('[FlowEditorPage] Loading data to canvas:', {
                nodes: Object.keys(this.state.value.skillsData.nodes || {}),
                edges: this.state.value.skillsData.edges?.length,
                entry: this.state.value.skillsData.entry
            });
            canvas.loadData(this.state.value.skillsData, null);
        } else {
            console.error('[FlowEditorPage] Canvas element not found!');
        }
    }
    
    _calculateConfigHash() {
        const canvas = this.querySelector('flow-canvas');
        const canvasData = canvas?.getData() || this.state.value.skillsData;
        const header = this.querySelector('editor-header');
        const flowName = header?.getFlowName() || this.state.value.flowConfig?.name || '';
        
        const dataToHash = JSON.stringify({
            name: flowName,
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
            FlowsStore.setExecutionPanelOpen(true);
            this._panelOpen = false;
        } else {
            FlowsStore.setExecutionPanelOpen(false);
        }
    }

    async _onSkillSwitched(e) {
        const { skillId, data, inherited } = e.detail;
        FlowsStore.setCurrentSkill(skillId);
        FlowsStore.updateSkillsData(data, inherited);
        
        console.log(`[FlowEditorPage] Skill switched to "${skillId}":`, {
            variables: data.variables,
            variables_keys: Object.keys(data.variables || {}),
        });
        
        this._updateCanvasDirectly(data, inherited);

        const urlSkillId = (skillId && skillId !== 'base') ? skillId : null;
        setUrlParam('skill', urlSkillId);

        if (this.flowId) {
            await FlowsStore.refreshPreviewExecutionState(this.flowId, this.a2a, skillId);
        }
        
        if (skillId === 'base') {
            this.success(this.i18n.t('editor.skill_switched_base'));
        } else {
            this.success(this.i18n.t('editor.skill_switched_named', { id: skillId }));
        }
    }

    _onSaveCurrentSkillData(e) {
        const { skillId } = e.detail;
        const canvas = this.querySelector('flow-canvas');
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
        
        FlowsStore.updateVariables(variables);
        this._checkForChanges();
    }

    _onRunAgent(e) {
        const { message, files, mocks, reuseContext } = e.detail;
        const executionRunner = this.querySelector('execution-runner');
        const breakpointManager = this.querySelector('breakpoint-manager');
        const canvas = this.querySelector('flow-canvas');

        if (!executionRunner || !breakpointManager) {
            return;
        }

        let flowNodes = this.state.value.skillsData?.nodes || {};
        if (canvas && typeof canvas.getData === 'function') {
            const canvasData = canvas.getData();
            if (canvasData && canvasData.nodes && typeof canvasData.nodes === 'object') {
                flowNodes = canvasData.nodes;
            }
        }

        const breakpoints = breakpointManager.getBreakpointsObject();
        const reuse = reuseContext !== false;
        executionRunner.run(message, files, breakpoints, mocks, flowNodes, { reuseContext: reuse });
    }

    _onStopAgent() {
        const executionRunner = this.querySelector('execution-runner');
        if (executionRunner) {
            executionRunner.stop();
        }
        const executionPanel = this.querySelector('execution-panel');
        if (executionPanel) {
            executionPanel.setRunning(false);
        }
        FlowsStore.setAgentExecutionRunning(false);
    }

    _onResumeFlow(e) {
        const { answer, contextId } = e.detail;
        const executionRunner = this.querySelector('execution-runner');
        const breakpointManager = this.querySelector('breakpoint-manager');
        
        if (breakpointManager) {
            breakpointManager.clearActiveBreakpoint();
        }
        
        if (executionRunner) {
            executionRunner.resume(answer, contextId);
        }
        FlowsStore.setAgentExecutionRunning(true);
    }

    _onNodeStatusUpdate(e) {
        const { nodeId, status } = e.detail;
        const canvas = this.querySelector('flow-canvas');
        
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
        const canvas = this.querySelector('flow-canvas');
        
        if (canvas) {
            canvas.showNodeError(nodeId, error);
        }
        
        this.error(this.i18n.t('editor.node_error', { nodeId }));
    }

    _onBreakpointHit(e) {
        const { nodeId, stateSnapshot } = e.detail;
        const breakpointManager = this.querySelector('breakpoint-manager');
        const canvas = this.querySelector('flow-canvas');
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
        FlowsStore.setAgentExecutionRunning(false);

        if (
            stateSnapshot != null &&
            typeof stateSnapshot === 'object' &&
            Object.keys(stateSnapshot).length > 0
        ) {
            FlowsStore.setPreviewExecutionStateFromBreakpoint(stateSnapshot);
        }
        
        this.info(this.i18n.t('editor.breakpoint_hit', { nodeId }));
    }

    _onExecutionComplete(e) {
        const { result } = e.detail;
        const executionPanel = this.querySelector('execution-panel');
        const breakpointManager = this.querySelector('breakpoint-manager');
        
        if (executionPanel) {
            executionPanel.setRunning(false);
            executionPanel.showResult(result || this.i18n.t('editor.execution_done_fallback'));
            executionPanel.clearBreakpoint();
        }
        FlowsStore.setAgentExecutionRunning(false);

        if (breakpointManager) {
            breakpointManager.clearActiveBreakpoint();
        }
        
        const canvas = this.querySelector('flow-canvas');
        if (canvas) {
            canvas.clearAllHighlights();
        }

        const fid = this.flowId;
        const skill = this.state.value.currentSkillId;
        if (fid && this.a2a) {
            FlowsStore.refreshPreviewExecutionState(fid, this.a2a, skill).catch((err) => {
                console.error('[FlowEditorPage] refreshPreviewExecutionState after run:', err);
            });
        }
        
        this.success(this.i18n.t('editor.execution_finished_toast'));
    }

    _onInputRequired(e) {
        const { question, contextId } = e.detail;
        const executionPanel = this.querySelector('execution-panel');
        
        if (executionPanel) {
            executionPanel.setInputRequired(question, contextId);
        }
        FlowsStore.setAgentExecutionRunning(false);
    }

    _onExecutionStarted(e) {
        const { contextId, taskId } = e.detail;
        const executionPanel = this.querySelector('execution-panel');
        const canvas = this.querySelector('flow-canvas');
        
        if (executionPanel) {
            executionPanel.setRunning(true);
            executionPanel.setExecutionData(contextId, taskId);
        }
        FlowsStore.setAgentExecutionRunning(true);

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
        FlowsStore.setAgentExecutionRunning(false);

        const fid = this.flowId;
        const skill = this.state.value.currentSkillId;
        if (fid && this.a2a) {
            FlowsStore.refreshPreviewExecutionState(fid, this.a2a, skill).catch((err) => {
                console.error('[FlowEditorPage] refreshPreviewExecutionState after error:', err);
            });
        }
        
        this.error(this.i18n.t('editor.execution_error'));
    }

    _onBreakpointsChanged(e) {
        const { breakpoints } = e.detail;
        const canvas = this.querySelector('flow-canvas');
        
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
        
        FlowsStore.updateVariables(newVariables);
        this._checkForChanges();
        this.success(this.i18n.t('editor.variable_deleted', { name }));
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
            FlowsStore.updateSkillsData({ ...skillsData, variables: newVariables }, newInherited);
        } else {
            FlowsStore.updateVariables(newVariables);
        }

        this._checkForChanges();
        this.success(this.i18n.t('editor.variable_saved', { name }));
    }

    _onBreakpointCleared(e) {
        const { nodeId } = e.detail;
        const canvas = this.querySelector('flow-canvas');
        
        if (canvas) {
            canvas.setBreakpointStatus(nodeId, true, false);
        }
    }

    _onShowState(e) {
        const { contextId, taskId } = e.detail;
        this.info(this.i18n.t('editor.state_viewer_opening', { contextId, taskId }));
        
        const modal = document.createElement('state-modal');
        modal.contextId = contextId;
        modal.taskId = taskId;
        modal.flowId = this.flowId;
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
        modal.flowId = this.flowId;
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
        if (this.state.value.agentExecutionRunning) {
            this._onStopAgent();
        }
        FlowsStore.setExecutionPanelOpen(false);
        this.editorMode = 'visual';
    }

    _onShowCode() {
        const canvas = this.querySelector('flow-canvas');
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
        
        const flowName = header?.getFlowName() || this.state.value.flowConfig?.name || '';
        const skills = skillsTabsBar?.getSkillsForSubmit() || {};
        
        const fullConfig = {
            ...this.state.value.flowConfig,
            name: flowName,
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
        FlowsStore.toggleVariablesPanel();
    }

    _onNodeSelected(e) {
        const { nodeId, nodeConfig } = e.detail;
        
        console.log('[FlowEditorPage] Node selected:', {
            nodeId,
            nodeConfig,
            skillsData: this.state.value.skillsData,
            nodeInSkillsData: this.state.value.skillsData?.nodes?.[nodeId]
        });
        
        if (!nodeId) {
            console.error('[FlowEditorPage] Node selected but nodeId is missing!');
            return;
        }
        
        FlowsStore.selectNode(nodeId);
        this._panelEntering = true;
        
        setTimeout(() => {
            this._panelEntering = false;
        }, 300);
    }

    _onNodeAdded(e) {
        console.log('[FlowEditorPage] Node added, syncing with store');
        this._syncCanvasToFlowsStore();
        this._checkForChanges();
    }

    async _addGraphCodeNodeAfterDrop(canvas, item, posX, posY, nodeConfig) {
        let addedNodeId = null;
        canvas.addEventListener(
            'node-added',
            (ev) => {
                addedNodeId = ev.detail.nodeId;
            },
            { once: true },
        );
        await canvas._addNode(item, posX, posY);
        if (!addedNodeId) {
            throw new Error('[FlowEditorPage] code-node-drop: node-added without nodeId');
        }
        if (nodeConfig) {
            this._onNodeUpdated({ detail: { nodeId: addedNodeId, nodeConfig } });
        }
        FlowsStore.selectNode(addedNodeId);
    }

    async _fillCodeNodeFromCatalogTool(canvas, item, posX, posY, toolIds) {
        if (!toolIds.length) {
            await this._addGraphCodeNodeAfterDrop(canvas, item, posX, posY, null);
            return;
        }
        const toolId = toolIds[0];
        const toolData = await this.a2a.get(`/api/v1/tools/${encodeURIComponent(toolId)}`);
        const code = toolData?.code;
        if (!code || !String(code).trim()) {
            throw new Error(
                `[FlowEditorPage] Tool "${toolId}" has no inline code; graph code node requires Python code`,
            );
        }
        const title = typeof toolData.title === 'string' ? toolData.title.trim() : '';
        const nodeConfig = {
            type: 'code',
            name: title || toolData.tool_id,
            code,
            language: 'python',
        };
        if (toolData.args_schema && typeof toolData.args_schema === 'object') {
            nodeConfig.args_schema = toolData.args_schema;
        }
        if (toolData.parameters_schema && typeof toolData.parameters_schema === 'object') {
            nodeConfig.parameters_schema = toolData.parameters_schema;
        }
        if (typeof toolData.description === 'string' && toolData.description.trim()) {
            nodeConfig.description = toolData.description.trim();
        }
        if (typeof toolData.tool_id === 'string' && toolData.tool_id.trim()) {
            nodeConfig.tool_id = toolData.tool_id.trim();
        }
        await this._addGraphCodeNodeAfterDrop(canvas, item, posX, posY, nodeConfig);
    }

    _onCodeNodeDrop(e) {
        const { item, posX, posY } = e.detail;
        const canvas = this.querySelector('flow-canvas');
        if (!canvas) {
            throw new Error('[FlowEditorPage] flow-canvas not found for code-node-drop');
        }

        const modal = document.createElement('tool-picker-modal');
        modal.codeNodePlacement = true;
        modal.initialSelection = [];

        let committed = false;

        const onToolsSelected = (ev) => {
            committed = true;
            const toolIds = ev.detail?.tools || [];
            void this._fillCodeNodeFromCatalogTool(canvas, item, posX, posY, toolIds).catch((err) => {
                this.error(err instanceof Error ? err.message : String(err));
            });
        };

        const onClose = () => {
            modal.removeEventListener('tools-selected', onToolsSelected);
            if (!committed) {
                void this._addGraphCodeNodeAfterDrop(canvas, item, posX, posY, null);
            }
            modal.remove();
        };

        modal.addEventListener('tools-selected', onToolsSelected);
        modal.addEventListener('close', onClose, { once: true });

        document.body.appendChild(modal);
        modal.showModal();
    }

    _onResourceSelected(e) {
        const { resourceId, resourceConfig } = e.detail;
        
        console.log('[FlowEditorPage] Resource selected:', { resourceId, resourceConfig });
        
        if (!resourceId) {
            console.error('[FlowEditorPage] Resource selected but resourceId is missing!');
            return;
        }
        
        FlowsStore.selectResource(resourceId);
        this._panelEntering = true;
        
        setTimeout(() => {
            this._panelEntering = false;
        }, 300);
    }

    _onResourceAdded(e) {
        console.log('[FlowEditorPage] Resource added, syncing with store');
        this._syncCanvasToFlowsStore();
        this._checkForChanges();
    }

    _onResourceDeleted(e) {
        const { resourceId } = e.detail;
        console.log('[FlowEditorPage] Resource deleted:', resourceId);
        
        const canvas = this.querySelector('flow-canvas');
        if (canvas) {
            canvas.removeResource(resourceId);
        }
        
        FlowsStore.deleteResource(resourceId);
        this._checkForChanges();
    }

    _onResourceUpdated(e) {
        const { resourceId, resourceConfig } = e.detail;
        console.log('[FlowEditorPage] Resource updated:', { resourceId, resourceConfig });
        
        const canvas = this.querySelector('flow-canvas');
        if (canvas) {
            canvas.updateResourceConfig(resourceId, resourceConfig);
        }
        
        FlowsStore.updateResource(resourceId, {
            ...this.state.value.skillsData?.resources?.[resourceId],
            config: resourceConfig,
        });
        this._checkForChanges();
    }

    _syncCanvasToFlowsStore() {
        // Синхронизируем данные с canvas в store
        const canvas = this.querySelector('flow-canvas');
        if (!canvas) return;
        
        const canvasData = canvas.getData();
        console.log('[FlowEditorPage] Syncing canvas data to store:', canvasData);
        
        FlowsStore.updateSkillsData(canvasData, this.state.value.inheritedData);
    }

    _onNodeUnselected() {
        // Не закрываем панель автоматически при снятии выделения
    }

    _closePanel() {
        FlowsStore.closePanel();
    }

    _toggleExpanded() {
        FlowsStore.togglePanelExpanded();
    }

    _onBackdropClick() {
        if (this.state.value.panelExpanded) {
            FlowsStore.togglePanelExpanded();
        }
    }

    _onNodeUpdated(e) {
        const { nodeId, nodeConfig } = e.detail;
        
        console.log('[FlowEditorPage] _onNodeUpdated called:', { nodeId, nodeConfig });
        
        const canvas = this.querySelector('flow-canvas');
        if (canvas) {
            canvas.updateNodeConfig(nodeId, nodeConfig);
        } else {
            console.error('[FlowEditorPage] Canvas not found!');
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
            
            FlowsStore.updateSkillsData({
                ...currentSkillsData,
                nodes: updatedNodes
            });
            
            console.log('[FlowEditorPage] Updated skillsData for node:', nodeId);
        }
        
        this._checkForChanges();
        this.emit('flow-changed');
    }

    async _completeReloadFromBundle(flowId) {
        if (!flowId) {
            return;
        }
        await FlowsStore.loadFlow(flowId, this.a2a, this.state.value.currentSkillId);
        const editorState = FlowsStore.state.editor;
        await this._updateCanvasDirectly(editorState.skillsData, editorState.inheritedData);
        this._initialConfigHash = this._calculateConfigHash();
        this._hasUnsavedChanges = false;
        this.success(this.i18n.t('editor.reinit_success'));
    }

    async _onReloadFromBundleRequested() {
        const flowId = this.flowId;
        if (!flowId || this.state.value.flowConfig?.source !== 'file') {
            return;
        }
        const agreed = await confirm(
            this.i18n.t('editor.reinit_confirm_message'),
            {
                title: this.i18n.t('editor.reinit_confirm_title'),
                variant: 'warning',
                confirmText: this.i18n.t('editor.reinit_confirm_ok'),
                cancelText: this.i18n.t('editor.cancel'),
            },
        );
        if (!agreed) {
            return;
        }
        this._reloadFromBundleBusy = true;
        this.requestUpdate();
        try {
            await this.a2a.reloadFlowFromBundle(flowId);
            await this._completeReloadFromBundle(flowId);
        } catch (err) {
            console.error('[FlowEditorPage] reload from bundle (header):', err);
            this.error(err.message || String(err));
        } finally {
            this._reloadFromBundleBusy = false;
            this.requestUpdate();
        }
    }

    _onNodeDeleted(e) {
        const { nodeId } = e.detail;
        
        const canvas = this.querySelector('flow-canvas');
        if (canvas) {
            canvas.removeNode(nodeId);
        }
        
        if (this.state.value.selectedNodeId === nodeId) {
            FlowsStore.closePanel();
        }
        
        this._checkForChanges();
        this.emit('flow-changed');
    }

    _onNodeIdChanged(e) {
        const { oldId, newId } = e.detail;
        const canvas = this.querySelector('flow-canvas');
        
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
                
                FlowsStore.updateSkillsData(data, this.state.value.inheritedData);
            }
            
            if (this.state.value.selectedNodeId === oldId) {
                FlowsStore.selectNode(newId);
            }
            
            this._checkForChanges();
            this.success(this.i18n.t('editor.node_id_renamed', { oldId, newId }));
        }
    }

    async _handleSave() {
        try {
            const canvas = this.querySelector('flow-canvas');
            const skillsTabsBar = this.querySelector('skills-tabs-bar');
            const header = this.querySelector('editor-header');
            
            const canvasData = canvas?.getData() || { nodes: {}, edges: [], entry: null };
            
            console.log('[FlowEditorPage] _handleSave - canvasData:', canvasData);
            console.log('[FlowEditorPage] _handleSave - canvasData.nodes:', Object.keys(canvasData.nodes));
            
            if (skillsTabsBar) {
                skillsTabsBar.updateSkillData(this.state.value.currentSkillId, canvasData);
            }
            
            const currentSkillData = {
                nodes: canvasData.nodes,
                edges: canvasData.edges,
                entry: canvasData.entry,
                variables: this.state.value.skillsData.variables || {},
            };
            
            const flowName = header?.getFlowName() || this.state.value.flowConfig?.name || '';
            const skills = skillsTabsBar?.getSkillsForSubmit() || {};
            
            const updatedConfig = {
                ...this.state.value.flowConfig,
                name: flowName,
                nodes: currentSkillData.nodes,
                edges: currentSkillData.edges,
                entry: currentSkillData.entry,
                variables: currentSkillData.variables,
                skills,
            };
            
            console.log('[FlowEditorPage] _handleSave - updatedConfig.nodes:', Object.keys(updatedConfig.nodes));
            console.log('[FlowEditorPage] _handleSave - order_processor node:', updatedConfig.nodes.order_processor);
            
            await this.a2a.saveFlowConfig(this.flowId, updatedConfig);
            
            this.success(this.i18n.t('editor.save_reloading'));
            
            const currentSkillId = this.state.value.currentSkillId;
            await FlowsStore.loadFlow(this.flowId, this.a2a, currentSkillId);
            
            FlowsStore.setDirty(false);
            this.success(this.i18n.t('editor.save_updated'));
            this.emit('flow-saved', { flowId: this.flowId });
        } catch (error) {
            console.error('[FlowEditorPage] Save error:', error);
            this.error(this.i18n.t('editor.save_error', { message: error.message }));
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
            title: this.i18n.t('editor.unsaved_title'),
            subtitle: this.i18n.t('editor.unsaved_subtitle'),
            message: this.i18n.t('editor.unsaved_message'),
            variant: 'warning',
            confirmText: this.i18n.t('editor.unsaved_confirm'),
            cancelText: this.i18n.t('editor.unsaved_cancel'),
            confirmVariant: 'primary',
        });
        
        const footer = this._confirmModal.shadowRoot.querySelector('.modal-footer');
        if (footer && !footer.querySelector('.discard-btn')) {
            const discardBtn = document.createElement('button');
            discardBtn.type = 'button';
            discardBtn.className = 'modal-btn danger discard-btn';
            discardBtn.textContent = this.i18n.t('editor.unsaved_discard');
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
        const { panelOpen, panelExpanded, selectedNodeId, selectedResourceId, flowConfig, currentSkillId, skillsData, previewExecutionState } = this.state.value;
        
        console.log('[FlowEditorPage] _renderFloatingPanel:', {
            panelOpen,
            selectedNodeId,
            selectedResourceId,
            hasSkillsData: !!skillsData,
            nodeCount: Object.keys(skillsData?.nodes || {}).length
        });
        
        if (!panelOpen) {
            return null;
        }
        
        // Если выбран ресурс, показываем панель ресурса
        if (selectedResourceId) {
            return this._renderResourcePanel();
        }
        
        if (!selectedNodeId) {
            return null;
        }
        
        // Берем ноду из skillsData (актуальные данные с canvas)
        const selectedNode = skillsData?.nodes?.[selectedNodeId];
        if (!selectedNode) {
            console.error('[FlowEditorPage] Selected node not found in skillsData:', {
                selectedNodeId,
                availableNodes: Object.keys(skillsData?.nodes || {})
            });
            return null;
        }

        const canvas = this.querySelector('flow-canvas');
        const allowNodeIdRenameOnce =
            typeof canvas?.getAllowNodeIdRenameOnce === 'function'
                ? canvas.getAllowNodeIdRenameOnce(selectedNodeId)
                : false;

        console.log('[FlowEditorPage] Rendering panel for node:', selectedNode);
        
        const color = selectedNode.color || '#6b7280';
        const bgColor = color + '20';
        
        const panelClasses = ['floating-panel'];
        if (panelExpanded) panelClasses.push('expanded');
        if (this._panelEntering && !panelExpanded) panelClasses.push('entering');

        return html`
            <div 
                class="panel-backdrop ${panelExpanded ? 'visible' : ''}"
                @click=${this._onBackdropClick}
            ></div>
            <div class="${panelClasses.join(' ')}">
                <div class="floating-panel-header">
                    <div class="floating-panel-title">
                        <div class="floating-panel-icon" style="background: ${bgColor}; color: ${color};">
                            <platform-icon name="${this._getNodeIcon(selectedNode.type)}" size="${panelExpanded ? 18 : 14}"></platform-icon>
                        </div>
                        <span class="floating-panel-name">${selectedNode.name || selectedNode.nodeId || selectedNodeId}</span>
                    </div>
                    <div class="floating-panel-actions">
                        <button 
                            class="floating-panel-btn expand-btn" 
                            @click=${this._toggleExpanded} 
                            title="${panelExpanded ? this.i18n.t('editor.panel_collapse') : this.i18n.t('editor.panel_expand')}"
                        >
                            <platform-icon name="${panelExpanded ? 'minimize' : 'maximize'}" size="16"></platform-icon>
                        </button>
                        <button class="floating-panel-btn" @click=${this._closePanel} title="${this.i18n.t('editor.panel_close')}">
                            <platform-icon name="x" size="16"></platform-icon>
                        </button>
                    </div>
                </div>
                <div class="floating-panel-body">
                    <property-panel
                        .node=${{ id: selectedNodeId, ...selectedNode, allowNodeIdRenameOnce }}
                        .flowId=${this.flowId}
                        .skillId=${currentSkillId}
                        .flowConfig=${flowConfig}
                        .flowVariables=${flowConfig?.variables || {}}
                        .previewExecutionState=${previewExecutionState}
                        ?expanded=${panelExpanded}
                        @node-updated=${this._onNodeUpdated}
                        @node-deleted=${this._onNodeDeleted}
                        @node-id-changed=${this._onNodeIdChanged}
                    ></property-panel>
                </div>
            </div>
        `;
    }

    _renderResourcePanel() {
        const { panelExpanded, selectedResourceId, skillsData } = this.state.value;
        
        const canvas = this.querySelector('flow-canvas');
        const resourceConfig = canvas?.resourceConfigs?.get(selectedResourceId);
        
        if (!resourceConfig) {
            console.error('[FlowEditorPage] Selected resource not found:', selectedResourceId);
            return null;
        }
        
        const color = resourceConfig.color || '#6b7280';
        const bgColor = color + '20';
        
        const panelClasses = ['floating-panel'];
        if (panelExpanded) panelClasses.push('expanded');
        if (this._panelEntering && !panelExpanded) panelClasses.push('entering');

        return html`
            <div 
                class="panel-backdrop ${panelExpanded ? 'visible' : ''}"
                @click=${this._onBackdropClick}
            ></div>
            <div class="${panelClasses.join(' ')}">
                <div class="floating-panel-header">
                    <div class="floating-panel-title">
                        <div class="floating-panel-icon" style="background: ${bgColor}; color: ${color}; border-radius: 50%;">
                            <platform-icon name="${this._getResourceIcon(resourceConfig.type)}" size="${panelExpanded ? 18 : 14}"></platform-icon>
                        </div>
                        <span class="floating-panel-name">${selectedResourceId}</span>
                    </div>
                    <div class="floating-panel-actions">
                        <button 
                            class="floating-panel-btn expand-btn" 
                            @click=${this._toggleExpanded} 
                            title="${panelExpanded ? this.i18n.t('editor.panel_collapse') : this.i18n.t('editor.panel_expand')}"
                        >
                            <platform-icon name="${panelExpanded ? 'minimize' : 'maximize'}" size="16"></platform-icon>
                        </button>
                        <button class="floating-panel-btn" @click=${this._closePanel} title="${this.i18n.t('editor.panel_close')}">
                            <platform-icon name="x" size="16"></platform-icon>
                        </button>
                    </div>
                </div>
                <div class="floating-panel-body">
                    <resource-property-panel
                        .resource=${resourceConfig}
                        ?expanded=${panelExpanded}
                        @resource-updated=${this._onResourceUpdated}
                        @resource-deleted=${this._onResourceDeleted}
                    ></resource-property-panel>
                </div>
            </div>
        `;
    }

    _getNodeIcon(type) {
        const icons = {
            'llm_node': 'llm_node',
            'code': 'code',
            'flow': 'workflow',
            'remote_flow': 'cloud',
            'external_api': 'globe',
            'mcp': 'mcp',
            'channel': 'send',
        };
        return icons[type] || 'box';
    }

    _getResourceIcon(type) {
        const icons = {
            'code': 'code',
            'rag': 'search',
            'files': 'folder',
            'prompt': 'chat',
            'llm': 'bot',
            'secret': 'key',
            'http': 'globe',
            'cache': 'database',
        };
        return icons[type] || 'box';
    }

    render() {
        const { flowConfig, loading, isSaving, currentSkillId } = this.state.value;
        
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
                    flow-name=${flowConfig?.name || 'New Flow'}
                    flow-source=${flowConfig?.source || ''}
                    ?reload-from-bundle-loading=${this._reloadFromBundleBusy}
                    ?saving=${isSaving}
                    .mode=${this.editorMode}
                    ?agent-execution-running=${this.state.value.agentExecutionRunning}
                    @save=${this._handleSave}
                    @close=${this._handleClose}
                    @mode-changed=${this._onModeChanged}
                    @stop-agent-requested=${this._onStopAgent}
                    @show-code=${this._onShowCode}
                    @reload-from-bundle-requested=${this._onReloadFromBundleRequested}
                ></editor-header>
                
                <skills-tabs-bar
                    .flowConfig=${flowConfig}
                    .currentSkillId=${currentSkillId}
                    @skill-switched=${this._onSkillSwitched}
                    @save-current-skill-data=${this._onSaveCurrentSkillData}
                ></skills-tabs-bar>
                
                <div class="editor-body">
                    <node-types-sidebar
                        class="node-types-sidebar"
                        .triggers=${flowConfig?.triggers || {}}
                        @trigger-add-requested=${this._onTriggerAdd}
                        @trigger-edit-requested=${this._onTriggerEdit}
                    ></node-types-sidebar>
                    
                    <div class="canvas-area">
                        <flow-canvas
                            @node-selected=${this._onNodeSelected}
                            @node-unselected=${this._onNodeUnselected}
                            @node-updated=${this._onNodeUpdated}
                            @code-node-drop=${this._onCodeNodeDrop}
                            @node-added=${this._onNodeAdded}
                            @resource-selected=${this._onResourceSelected}
                            @resource-added=${this._onResourceAdded}
                            @resource-deleted=${this._onResourceDeleted}
                            @connection-created=${() => this._checkForChanges()}
                            @connection-removed=${() => this._checkForChanges()}
                        ></flow-canvas>
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
                    .flowId=${this.flowId}
                    .skillId=${this.state.value.currentSkillId}
                    .flowNodes=${this.state.value.skillsData?.nodes || {}}
                    show-state
                    show-tracing
                    show-mocks
                    @run-requested=${this._onRunAgent}
                    @stop-requested=${this._onStopAgent}
                    @resume-flow=${this._onResumeFlow}
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

    _onTriggerAdd() {
        const modal = this.querySelector('trigger-editor-modal');
        if (modal) {
            modal.flowId = this.flowId;
            modal.flowVariables = this._getFlowVariablesList();
            modal.showModal();
        }
    }

    _onTriggerEdit(e) {
        const { triggerId } = e.detail;
        const { flowConfig } = this.state.value;
        const triggerConfig = flowConfig?.triggers?.[triggerId];
        
        if (triggerConfig) {
            const modal = this.querySelector('trigger-editor-modal');
            if (modal) {
                modal.flowId = this.flowId;
                modal.flowVariables = this._getFlowVariablesList();
                modal.showModal(triggerId, triggerConfig);
            }
        }
    }

    _getFlowVariablesList() {
        const { flowConfig } = this.state.value;
        const variables = flowConfig?.variables || {};
        return Object.entries(variables).map(([name, config]) => ({
            name,
            type: config.type || 'string',
            description: config.description || '',
        }));
    }

    async _onTriggerToggle(e) {
        const { triggerId, enabled } = e.detail;
        const { flowConfig } = this.state.value;
        
        if (flowConfig?.triggers?.[triggerId]) {
            const updatedTriggers = {
                ...flowConfig.triggers,
                [triggerId]: {
                    ...flowConfig.triggers[triggerId],
                    enabled,
                }
            };
            
            const updatedConfig = { ...flowConfig, triggers: updatedTriggers };
            await this.a2a.saveFlowConfig(this.flowId, updatedConfig);
            await FlowsStore.loadFlow(this.flowId, this.a2a, this.state.value.currentSkillId);
            
            this.success(enabled ? this.i18n.t('editor.trigger_enabled') : this.i18n.t('editor.trigger_disabled'));
        }
    }

    async _onTriggerDelete(e) {
        const { triggerId } = e.detail;
        const { flowConfig } = this.state.value;
        
        if (flowConfig?.triggers?.[triggerId]) {
            const updatedTriggers = { ...flowConfig.triggers };
            delete updatedTriggers[triggerId];
            
            const updatedConfig = { ...flowConfig, triggers: updatedTriggers };
            await this.a2a.saveFlowConfig(this.flowId, updatedConfig);
            await FlowsStore.loadFlow(this.flowId, this.a2a, this.state.value.currentSkillId);
            
            this.success(this.i18n.t('editor.trigger_deleted', { id: triggerId }));
        }
    }

    async _onTriggerSave(e) {
        const { triggerId, config } = e.detail;
        const { flowConfig } = this.state.value;
        
        const updatedTriggers = {
            ...(flowConfig?.triggers || {}),
            [triggerId]: config,
        };
        
        const updatedConfig = { ...flowConfig, triggers: updatedTriggers };
        await this.a2a.saveFlowConfig(this.flowId, updatedConfig);
        await FlowsStore.loadFlow(this.flowId, this.a2a, this.state.value.currentSkillId);
        
        this.success(this.i18n.t('editor.trigger_saved', { id: triggerId }));
    }

    _renderHiddenComponents() {
        return html`
            <execution-runner
                style="display: none;"
                .flowId=${this.flowId}
                .skillId=${this.state.value.currentSkillId}
                .flowNodes=${this.state.value.skillsData?.nodes || {}}
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
                .flowId=${this.flowId}
                @breakpoints-changed=${this._onBreakpointsChanged}
                @breakpoint-cleared=${this._onBreakpointCleared}
            ></breakpoint-manager>

            <variable-editor-modal
                @variable-saved=${this._onVariableSaved}
            ></variable-editor-modal>

            <trigger-editor-modal
                @trigger-save=${this._onTriggerSave}
            ></trigger-editor-modal>
        `;
    }
}

customElements.define('flow-editor-page', FlowEditorPage);

