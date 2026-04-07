/**
 * FlowsStore - Состояние редактора flows приложения
 */
import { BaseStore } from '@platform/lib/store/BaseStore.js';
import { removeUrlParams } from '../utils/url-sync.js';

const baseStore = new BaseStore('flows', {
    app: {
        isAuthenticated: false,
        user: null,
        theme: 'dark',
        currentRoute: '/',
        authChecking: true,
        flowName: '',
        skillId: '',
        skillName: '',
    },
    
    flows: {
        list: [],
        currentId: null,
        loading: false,
        error: null,
    },
    
    editor: {
        flowId: null,
        flowConfig: null,
        currentSkillId: null,
        selectedNodeId: null,
        selectedResourceId: null,
        skillsData: { nodes: {}, edges: [], entry: null, variables: {}, resources: {} },
        inheritedData: null,
        panelOpen: false,
        panelExpanded: false,
        variablesPanelOpen: false,
        executionPanelOpen: false,
        agentExecutionRunning: false,
        activeTool: 'select',
        canUndo: false,
        canRedo: false,
        historyStack: [],
        historyPosition: -1,
        isDirty: false,
        isSaving: false,
        loading: false,
        previewExecutionState: null,
    },
    
    chat: {
        messages: [],
        loading: false,
        streamPending: false,
        contextId: null,
        currentTaskId: null,
    },
    
    modals: {
        confirmModal: { open: false, data: null },
        toolPickerModal: { open: false, data: null },
        sessionsModal: { open: false, data: null },
        flowEditModal: { open: false, data: null },
    },
    
    ui: {
        toasts: [],
        expandedFlows: {},
        flowDetails: {},
    },
}, {
    persist: true,
    devtools: true,
    partialize: (state) => ({
        app: {
            theme: state.app.theme,
        },
        ui: {
            expandedFlows: state.ui.expandedFlows,
        }
    })
});

export const FlowsStore = {
    get state() {
        return baseStore.state;
    },
    
    subscribe(callback) {
        return baseStore.subscribe(callback);
    },
    
    setState(updater) {
        return baseStore.setState(updater);
    },
    
    initChat() {
        const contextId = `${Date.now()}`;
        baseStore.setState((s) => ({
            chat: { ...s.chat, contextId, messages: [], streamPending: false }
        }));
        removeUrlParams('session');
    },
    
    setAuth(isAuth, user = null) {
        baseStore.setState((s) => ({
            app: { ...s.app, isAuthenticated: isAuth, user, authChecking: false }
        }));
    },
    
    setFlows(list) {
        baseStore.setState((s) => ({
            flows: { ...s.flows, list, loading: false }
        }));
    },
    
    setCurrentFlow(id) {
        const contextId = `${Date.now()}`;
        baseStore.setState((s) => ({
            flows: { ...s.flows, currentId: id },
            app: { ...s.app, currentSkillId: null },
            chat: { ...s.chat, messages: [], contextId, loading: false, streamPending: false, currentTaskId: null },
        }));
    },
    
    setCurrentFlowAndSkill(flowId, skillId) {
        const contextId = `${Date.now()}`;
        baseStore.setState((s) => ({
            flows: { ...s.flows, currentId: flowId },
            app: { ...s.app, currentSkillId: skillId },
            chat: { ...s.chat, messages: [], contextId, loading: false, streamPending: false, currentTaskId: null },
        }));
    },
    
    async createFlow(config, a2aService) {
        baseStore.setState((s) => ({
            flows: { ...s.flows, loading: true }
        }));
        
        try {
            const createdFlow = await a2aService.createFlow(config);
            
            baseStore.setState((s) => ({
                flows: {
                    ...s.flows,
                    list: [...s.flows.list, createdFlow],
                    loading: false
                }
            }));
            
            return createdFlow;
        } catch (error) {
            baseStore.setState((s) => ({
                flows: { ...s.flows, loading: false }
            }));
            console.error('[Store] Failed to create flow:', error);
            throw error;
        }
    },
    
    async deleteFlow(flowId, a2aService) {
        const prevList = baseStore.state.flows.list;
        
        baseStore.setState((s) => ({
            flows: {
                ...s.flows,
                list: s.flows.list.filter(a => a.flow_id !== flowId)
            }
        }));
        
        try {
            await a2aService.deleteFlow(flowId);
        } catch (error) {
            baseStore.setState((s) => ({
                flows: { ...s.flows, list: prevList }
            }));
            console.error('[Store] Failed to delete flow:', error);
            throw error;
        }
    },
    
    async deleteSkill(flowId, skillId, a2aService) {
        const flow = baseStore.state.flows.list.find(a => a.flow_id === flowId);
        if (!flow) {
            throw new Error(`Flow ${flowId} not found`);
        }
        
        const prevSkills = flow.skills || {};
        
        baseStore.setState((s) => ({
            flows: {
                ...s.flows,
                list: s.flows.list.map(a => {
                    if (a.flow_id === flowId) {
                        const { [skillId]: removed, ...remainingSkills } = a.skills || {};
                        return { ...a, skills: remainingSkills };
                    }
                    return a;
                })
            }
        }));
        
        try {
            await a2aService.deleteSkill(flowId, skillId);
        } catch (error) {
            baseStore.setState((s) => ({
                flows: {
                    ...s.flows,
                    list: s.flows.list.map(a =>
                        a.flow_id === flowId ? { ...a, skills: prevSkills } : a
                    )
                }
            }));
            console.error('[Store] Failed to delete skill:', error);
            throw error;
        }
    },
    
    addMessage(message) {
        baseStore.setState((s) => ({
            chat: { ...s.chat, messages: [...s.chat.messages, message] }
        }));
    },
    
    updateMessage(messageId, updates) {
        baseStore.setState((s) => ({
            chat: {
                ...s.chat,
                messages: s.chat.messages.map(m =>
                    m.id === messageId ? { ...m, ...updates } : m
                )
            }
        }));
    },
    
    appendToMessage(messageId, text) {
        baseStore.setState((s) => ({
            chat: {
                ...s.chat,
                messages: s.chat.messages.map(m =>
                    m.id === messageId ? { ...m, content: m.content + text } : m
                )
            }
        }));
    },
    
    appendToMessageField(messageId, field, text) {
        baseStore.setState((s) => ({
            chat: {
                ...s.chat,
                messages: s.chat.messages.map(m =>
                    m.id === messageId ? { ...m, [field]: (m[field] || '') + text } : m
                )
            }
        }));
    },
    
    setLoading(loading) {
        baseStore.setState((s) => ({
            chat: { ...s.chat, loading }
        }));
    },

    setStreamPending(streamPending) {
        baseStore.setState((s) => ({
            chat: { ...s.chat, streamPending }
        }));
    },
    
    clearChat() {
        const contextId = `${Date.now()}`;
        baseStore.setState((s) => ({
            chat: { ...s.chat, messages: [], contextId, streamPending: false }
        }));
        removeUrlParams('session');
    },
    
    loadSession(sessionId, stateMessages, flowId, sessionTaskId = null) {
        // sessionId format: {flow_id}:{context_id}
        const parts = sessionId.split(':');
        const contextId = parts.length > 1 ? parts.slice(1).join(':') : sessionId;
        
        // Конвертируем messages из state формата в chat формат
        const messages = (stateMessages || []).map((msg, idx) => {
            const role = typeof msg.role === 'string' ? msg.role.toLowerCase() : 
                         (msg.role?.value || 'assistant');
            
            let content = msg.content || '';
            if (!content && msg.parts) {
                content = msg.parts
                    .filter(p => p.kind === 'text' || p.text)
                    .map(p => p.text || '')
                    .join('');
            }
            
            return {
                id: msg.messageId || msg.id || `msg-${idx}`,
                role: role === 'user' ? 'user' : 'assistant',
                content: content,
                timestamp: msg.timestamp || new Date().toISOString(),
                taskId: msg.taskId || sessionTaskId
            };
        });
        
        baseStore.setState((s) => ({
            flows: { ...s.flows, currentId: flowId },
            chat: {
                ...s.chat,
                messages,
                contextId,
                loading: false,
                streamPending: false,
                currentTaskId: sessionTaskId,
            }
        }));
    },
    
    _skillIdForEditorStateApi(skillId) {
        if (skillId == null || skillId === '' || skillId === 'base') {
            return 'default';
        }
        return skillId;
    },

    async refreshPreviewExecutionState(flowId, a2aService, skillId) {
        const apiSkill = this._skillIdForEditorStateApi(skillId);
        const preview = await a2aService.getEditorState(flowId, apiSkill);
        baseStore.setState((s) => ({
            editor: { ...s.editor, previewExecutionState: preview },
        }));
    },

    /**
     * Полный снимок ExecutionState с воркера при breakpoint (metadata.state_snapshot).
     * Подставляется в previewExecutionState для панелей нод и тестового state.
     */
    setPreviewExecutionStateFromBreakpoint(snapshot) {
        if (snapshot == null || typeof snapshot !== 'object') {
            return;
        }
        baseStore.setState((s) => ({
            editor: { ...s.editor, previewExecutionState: snapshot },
        }));
    },

    async loadFlow(flowId, a2aService, skillId = null) {
        baseStore.setState((s) => ({
            editor: { ...s.editor, loading: true, flowId, previewExecutionState: null }
        }));
        
        try {
            const flow = await a2aService.getFlow(flowId);
            
            console.log('[Store] loadFlow received:', flow);
            console.log('[Store] flow.nodes:', flow?.nodes);
            console.log('[Store] flow.skills:', flow?.skills);
            console.log('[Store] skillId param:', skillId);
            
            if (!flow) {
                throw new Error('Flow not found');
            }
            
            if (!flow.flow_id) {
                throw new Error('Response is missing flow_id');
            }

            const apiSkill = this._skillIdForEditorStateApi(skillId ?? 'base');
            const previewExecutionState = await a2aService.getEditorState(flowId, apiSkill);
            
            const skillsData = {
                nodes: flow.nodes ?? {},
                edges: flow.edges ?? [],
                entry: flow.entry ?? null,
                variables: flow.variables ?? {},
                resources: flow.resources ?? {}
            };
            
            baseStore.setState((s) => ({
                editor: {
                    ...s.editor,
                    flowConfig: flow,
                    skillsData,
                    currentSkillId: skillId,
                    loading: false,
                    previewExecutionState,
                    agentExecutionRunning: false,
                },
                app: {
                    ...s.app,
                    flowName: flow.name || ''
                }
            }));
            
            console.log('[Store] State after loadFlow:', baseStore.state.editor.flowConfig);
            console.log('[Store] skillsData set to:', skillsData);
            console.log('[Store] currentSkillId set to:', skillId);
        } catch (error) {
            console.error('[Store] Failed to load flow:', error);
            baseStore.setState((s) => ({
                editor: { ...s.editor, loading: false, previewExecutionState: null }
            }));
            throw error;
        }
    },
    
    loadFlows(a2aService) {
        baseStore.setState((s) => ({
            flows: { ...s.flows, loading: true }
        }));
        
        a2aService.listFlows().then(items => {
            if (!Array.isArray(items)) {
                throw new Error('API returned invalid flows list');
            }
            baseStore.setState((s) => ({
                flows: { ...s.flows, list: items, loading: false }
            }));
        }).catch(error => {
            console.error('[Store] Failed to load flows:', error);
            baseStore.setState((s) => ({
                flows: { ...s.flows, loading: false, error: error.message }
            }));
        });
    },
    
    setCurrentSkill(skillId) {
        baseStore.setState((s) => ({
            editor: { ...s.editor, currentSkillId: skillId }
        }));
    },
    
    updateSkillsData(data, inherited = {}) {
        baseStore.setState((s) => ({
            editor: { ...s.editor, skillsData: data, inheritedData: inherited }
        }));
    },
    
    updateVariables(variables) {
        baseStore.setState((s) => ({
            editor: {
                ...s.editor,
                skillsData: { ...s.editor.skillsData, variables }
            }
        }));
    },
    
    selectNode(nodeId) {
        baseStore.setState((s) => ({
            editor: { 
                ...s.editor, 
                selectedNodeId: nodeId, 
                selectedResourceId: null,
                panelOpen: !!nodeId 
            }
        }));
    },
    
    selectResource(resourceId) {
        baseStore.setState((s) => ({
            editor: { 
                ...s.editor, 
                selectedResourceId: resourceId, 
                selectedNodeId: null,
                panelOpen: !!resourceId 
            }
        }));
    },
    
    closePanel() {
        baseStore.setState((s) => ({
            editor: { 
                ...s.editor, 
                panelOpen: false, 
                selectedNodeId: null,
                selectedResourceId: null 
            }
        }));
    },
    
    updateResources(resources) {
        baseStore.setState((s) => ({
            editor: {
                ...s.editor,
                skillsData: { ...s.editor.skillsData, resources }
            }
        }));
    },
    
    addResource(resourceId, resourceConfig) {
        baseStore.setState((s) => ({
            editor: {
                ...s.editor,
                skillsData: {
                    ...s.editor.skillsData,
                    resources: {
                        ...s.editor.skillsData.resources,
                        [resourceId]: resourceConfig
                    }
                }
            }
        }));
    },
    
    updateResource(resourceId, resourceConfig) {
        baseStore.setState((s) => ({
            editor: {
                ...s.editor,
                skillsData: {
                    ...s.editor.skillsData,
                    resources: {
                        ...s.editor.skillsData.resources,
                        [resourceId]: resourceConfig
                    }
                }
            }
        }));
    },
    
    deleteResource(resourceId) {
        baseStore.setState((s) => {
            const { [resourceId]: removed, ...remainingResources } = s.editor.skillsData.resources || {};
            return {
                editor: {
                    ...s.editor,
                    skillsData: {
                        ...s.editor.skillsData,
                        resources: remainingResources
                    },
                    selectedResourceId: s.editor.selectedResourceId === resourceId ? null : s.editor.selectedResourceId,
                    panelOpen: s.editor.selectedResourceId === resourceId ? false : s.editor.panelOpen
                }
            };
        });
    },
    
    togglePanelExpanded() {
        baseStore.setState((s) => ({
            editor: { ...s.editor, panelExpanded: !s.editor.panelExpanded }
        }));
    },
    
    toggleVariablesPanel() {
        baseStore.setState((s) => ({
            editor: { ...s.editor, variablesPanelOpen: !s.editor.variablesPanelOpen }
        }));
    },
    
    setExecutionPanelOpen(isOpen) {
        baseStore.setState((s) => ({
            editor: { ...s.editor, executionPanelOpen: isOpen }
        }));
    },

    setAgentExecutionRunning(isRunning) {
        baseStore.setState((s) => ({
            editor: { ...s.editor, agentExecutionRunning: isRunning }
        }));
    },
    
    setDirty(isDirty) {
        baseStore.setState((s) => ({
            editor: { ...s.editor, isDirty }
        }));
    },
    
    toggleExpandedFlow(flowId) {
        baseStore.setState((s) => ({
            ui: {
                ...s.ui,
                expandedFlows: {
                    ...s.ui.expandedFlows,
                    [flowId]: !s.ui.expandedFlows[flowId]
                }
            }
        }));
    },
    
    openModal(modalName, data = null) {
        baseStore.setState((s) => ({
            modals: {
                ...s.modals,
                [modalName]: { open: true, data }
            }
        }));
    },
    
    closeModal(modalName) {
        baseStore.setState((s) => ({
            modals: {
                ...s.modals,
                [modalName]: { open: false, data: null }
            }
        }));
    },
    
    setActiveTool(tool) {
        baseStore.setState((s) => ({
            editor: { ...s.editor, activeTool: tool }
        }));
    },
    
    pushHistory(snapshot) {
        baseStore.setState((s) => {
            const newStack = s.editor.historyStack.slice(0, s.editor.historyPosition + 1);
            newStack.push(snapshot);
            
            if (newStack.length > 50) {
                newStack.shift();
            }
            
            return {
                editor: {
                    ...s.editor,
                    historyStack: newStack,
                    historyPosition: newStack.length - 1,
                    canUndo: newStack.length > 0,
                    canRedo: false
                }
            };
        });
    },
    
    undo() {
        baseStore.setState((s) => {
            if (s.editor.historyPosition < 0) return s;
            
            const newPosition = s.editor.historyPosition - 1;
            
            return {
                editor: {
                    ...s.editor,
                    historyPosition: newPosition,
                    canUndo: newPosition >= 0,
                    canRedo: true
                }
            };
        });
    },
    
    redo() {
        baseStore.setState((s) => {
            const maxPosition = s.editor.historyStack.length - 1;
            if (s.editor.historyPosition >= maxPosition) return s;
            
            const newPosition = s.editor.historyPosition + 1;
            
            return {
                editor: {
                    ...s.editor,
                    historyPosition: newPosition,
                    canUndo: true,
                    canRedo: newPosition < maxPosition
                }
            };
        });
    },
    
    getCurrentHistorySnapshot() {
        const { historyStack, historyPosition } = baseStore.state.editor;
        return historyPosition >= 0 ? historyStack[historyPosition] : null;
    },
    
    clearHistory() {
        baseStore.setState((s) => ({
            editor: {
                ...s.editor,
                historyStack: [],
                historyPosition: -1,
                canUndo: false,
                canRedo: false
            }
        }));
    },
};


