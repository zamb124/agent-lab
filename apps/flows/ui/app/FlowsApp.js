/**
 * FlowsApp - главное приложение Flows Builder
 */
import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { AppEvents } from '@platform/lib/utils/types.js';
import { A2AService } from '../services/a2a.service.js';
import { FlowsStore } from '../store/flows.store.js';
import { readUrlState, updateUrl, removeUrlParams } from '../utils/url-sync.js';
import { canManageOperatorWorkbench } from '../utils/operator-workbench-access.js';
import '../components/sidebar/flows-sidebar.js';
import '../features/operator/operator-workbench-page.js';
import '@platform/lib/embed-chat/platform-lara-assistant.js';

export class FlowsApp extends PlatformApp {
    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }

            flows-sidebar {
                flex-shrink: 0;
                height: 100%;
            }

            platform-chat {
                flex: 1;
                min-width: 0;
                height: calc(var(--app-vh, 100vh) - 2rem);
                margin: 1rem;
                margin-left: 0.5rem;
            }

            operator-workbench-page {
                flex: 1;
                min-width: 0;
                height: calc(var(--app-vh, 100vh) - 2rem);
                margin: 1rem;
            }

            .operator-access-denied {
                text-align: center;
                max-width: 28rem;
                margin: 0 auto;
            }

            .operator-access-denied .denied-title {
                font-size: var(--text-lg);
                color: var(--text-primary);
                margin-bottom: var(--space-3);
            }

            .operator-access-denied .denied-text {
                font-size: var(--text-sm);
                color: var(--text-muted);
                margin-bottom: var(--space-4);
            }

            .operator-access-denied .denied-link {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                padding: var(--space-2) var(--space-4);
                border-radius: var(--radius-lg);
                font-size: var(--text-sm);
                color: var(--text-primary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-medium);
                text-decoration: none;
            }

            .operator-access-denied .denied-link:hover {
                background: var(--glass-solid-medium);
            }

            @media (max-width: 768px) {
                platform-chat {
                    margin: 0;
                    height: var(--app-vh, 100vh);
                }

                operator-workbench-page {
                    margin: 0;
                    height: var(--app-vh, 100vh);
                }
            }
        `
    ];

    static properties = {
        ...PlatformApp.properties,
    };

    constructor() {
        super();
        this._onOperatorAuthChange = () => this.requestUpdate();
        this._laraInvocationContext = null;
        this._onLaraOpenRequested = (event) => {
            const detail = event?.detail && typeof event.detail === 'object' ? event.detail : {};
            this._setLaraInvocationContext(detail);
        };
        this._laraHandledEventKeys = new Set();
        this._onLaraUiEvent = (event) => {
            const detail = event?.detail && typeof event.detail === 'object' ? event.detail : null;
            if (!detail || detail.source === 'flows_app') {
                return;
            }
            const eventType = typeof detail.type === 'string' ? detail.type.trim() : '';
            if (!eventType) {
                return;
            }
            const payload = detail.payload && typeof detail.payload === 'object' ? detail.payload : {};
            const eventId =
                detail.id != null && String(detail.id).trim()
                    ? String(detail.id).trim()
                    : `${eventType}:${JSON.stringify(payload)}`;
            if (this._laraHandledEventKeys.has(eventId)) {
                return;
            }
            this._laraHandledEventKeys.add(eventId);
            if (eventType === 'patch_applied') {
                void this._handleLaraPatchApplied(payload);
                return;
            }
            if (eventType === 'patch_proposed') {
                this._emitLaraEvent('patch_proposed', payload);
                return;
            }
            if (eventType === 'navigate') {
                this._handleLaraNavigate(payload);
            }
        };
        this._laraActionHandlers = {
            'lara:context_requested': (payload) => this._emitLaraEvent('context_requested', payload),
            'lara:navigate': (payload) => this._emitLaraEvent('navigate', payload),
            'lara:patch_proposed': (payload) => this._emitLaraEvent('patch_proposed', payload),
            'lara:patch_applied': (payload) => this._emitLaraEvent('patch_applied', payload),
        };
    }

    async connectedCallback() {
        await super.connectedCallback();
        window.addEventListener(AppEvents.AUTH_CHANGE, this._onOperatorAuthChange);
        window.addEventListener('flows-lara-open', this._onLaraOpenRequested);
        this.addEventListener('lara:event', this._onLaraUiEvent);
    }

    disconnectedCallback() {
        window.removeEventListener(AppEvents.AUTH_CHANGE, this._onOperatorAuthChange);
        window.removeEventListener('flows-lara-open', this._onLaraOpenRequested);
        this.removeEventListener('lara:event', this._onLaraUiEvent);
        super.disconnectedCallback();
    }

    _emitLaraEvent(type, payload = {}) {
        const detail = {
            type,
            version: '1.0',
            payload,
            source: 'flows_app',
            timestamp: new Date().toISOString(),
        };
        this.dispatchEvent(
            new CustomEvent('lara:event', {
                detail,
                bubbles: true,
                composed: true,
            }),
        );
        this.dispatchEvent(
            new CustomEvent(`lara:${type}`, {
                detail,
                bubbles: true,
                composed: true,
            }),
        );
    }

    _inferLaraScreen(explicitScreen, context) {
        if (typeof explicitScreen === 'string' && explicitScreen) {
            return explicitScreen;
        }
        if (context.node_id) {
            return 'flow_editor_node';
        }
        if (context.flow_id && context.selection_source !== 'global_launcher') {
            return 'flow_editor';
        }
        if (context.flow_id) {
            return 'flow_chat';
        }
        return 'flow_list';
    }

    _buildLaraFlowsContext(options = {}) {
        const state = FlowsStore.state;
        const editorState = state.editor || {};
        const flowsState = state.flows || {};
        const appState = state.app || {};

        // Источник правды для состояния экрана — store на момент отправки сообщения.
        // detail из launcher используем только как fallback, если в store ещё нет данных.
        const resolvedFlowId =
            editorState.flowId || flowsState.currentId || options.flow_id || options.flowId || null;
        const resolvedSkillId =
            editorState.currentSkillId ||
            appState.currentSkillId ||
            options.skill_id ||
            options.skillId ||
            'base';
        const resolvedNodeId = editorState.selectedNodeId || options.node_id || options.nodeId || null;
        const skillsData = editorState.skillsData || { nodes: {}, edges: [], entry: null, variables: {}, resources: {} };
        const selectedNode = resolvedNodeId ? skillsData.nodes?.[resolvedNodeId] || null : null;
        const flowConfig = editorState.flowConfig || null;
        const flowFromList = flowsState.list?.find((item) => item.flow_id === resolvedFlowId) || null;
        const flowPayload = flowConfig && flowConfig.flow_id === resolvedFlowId ? flowConfig : flowFromList;
        const selectionSource = options.selection_source || options.selectionSource || 'global_launcher';

        const context = {
            app_surface: 'flows',
            flow_id: resolvedFlowId,
            skill_id: resolvedSkillId || 'base',
            node_id: resolvedNodeId,
            node_type: selectedNode?.type || null,
            selection_source: selectionSource,
            node_payload: selectedNode || null,
            flow_payload: flowPayload || null,
            context_version: Date.now(),
        };
        context.screen = this._inferLaraScreen(options.screen, context);
        return context;
    }

    _flattenLaraContext(context) {
        const nodePayloadJson = context.node_payload ? JSON.stringify(context.node_payload) : '';
        const flowPayloadJson = context.flow_payload ? JSON.stringify(context.flow_payload) : '';
        const contextJson = JSON.stringify(context);
        return {
            lara_ui_context: context,
            lara_ui_context_json: contextJson,
            app_surface: context.app_surface,
            screen: context.screen,
            flow_id: context.flow_id || '',
            skill_id: context.skill_id || 'base',
            node_id: context.node_id || '',
            node_type: context.node_type || '',
            selection_source: context.selection_source,
            node_payload_json: nodePayloadJson,
            flow_payload_json: flowPayloadJson,
            context_version: context.context_version,
        };
    }

    _setLaraInvocationContext(options = {}) {
        this._laraInvocationContext = this._buildLaraFlowsContext(options);
    }

    _laraEmbedContextVariables = async () => {
        const context = this._buildLaraFlowsContext(this._laraInvocationContext || {});
        this._laraInvocationContext = context;
        return this._flattenLaraContext(context);
    };

    _resolveTargetNode(flowConfig, skillId, nodeId) {
        if (!nodeId) {
            throw new Error('node_id is required for node patch');
        }
        if (skillId && skillId !== 'base') {
            const skill = flowConfig.skills?.[skillId];
            if (!skill) {
                throw new Error(`Skill "${skillId}" not found`);
            }
            const node = skill.nodes?.[nodeId];
            if (!node) {
                throw new Error(`Node "${nodeId}" not found in skill "${skillId}"`);
            }
            return { target: node, scope: 'skill' };
        }
        const node = flowConfig.nodes?.[nodeId];
        if (!node) {
            throw new Error(`Node "${nodeId}" not found`);
        }
        return { target: node, scope: 'base' };
    }

    async _handleLaraPatchApplied(payload = {}) {
        try {
            const a2a = this.services.get('a2a');
            const flowId = payload.flow_id || payload.flowId || this._laraInvocationContext?.flow_id;
            if (!flowId) {
                throw new Error('flow_id is required');
            }
            const skillId = payload.skill_id || payload.skillId || this._laraInvocationContext?.skill_id || 'base';
            const nodeId = payload.node_id || payload.nodeId || this._laraInvocationContext?.node_id || null;
            const patchKind = payload.patch_kind || payload.patchKind || (nodeId ? 'node' : 'flow');

            const flowConfig = await a2a.getFlow(flowId);
            const nextFlowConfig = structuredClone(flowConfig);

            if (patchKind === 'flow') {
                const flowChanges = payload.flow_changes || payload.flowChanges || {};
                if (!flowChanges || typeof flowChanges !== 'object') {
                    throw new Error('flow_changes must be an object');
                }
                Object.assign(nextFlowConfig, flowChanges);
            } else {
                const changes = payload.changes || {};
                if (!changes || typeof changes !== 'object') {
                    throw new Error('changes must be an object');
                }
                const resolved = this._resolveTargetNode(nextFlowConfig, skillId, nodeId);
                Object.assign(resolved.target, changes);
            }

            await a2a.saveFlowConfig(flowId, nextFlowConfig);

            const editorFlowId = FlowsStore.state.editor?.flowId;
            if (editorFlowId === flowId) {
                await FlowsStore.loadFlow(flowId, a2a, skillId);
                if (nodeId) {
                    FlowsStore.selectNode(nodeId);
                }
            }
            window.dispatchEvent(
                new CustomEvent('flows-editor-node-updated-by-lara', {
                    detail: {
                        flow_id: flowId,
                        skill_id: skillId,
                        node_id: nodeId,
                        patch_kind: patchKind,
                    },
                    bubbles: true,
                    composed: true,
                }),
            );

            this._setLaraInvocationContext({
                flow_id: flowId,
                skill_id: skillId,
                node_id: nodeId,
                selection_source: 'panel_launcher',
            });
            this._emitLaraEvent('patch_applied', {
                flow_id: flowId,
                skill_id: skillId,
                node_id: nodeId,
                patch_kind: patchKind,
            });
        } catch (error) {
            this._emitLaraEvent('error', {
                source: 'flows-app.patch_applied',
                message: error instanceof Error ? error.message : String(error),
            });
        }
    }

    _handleLaraNavigate(payload = {}) {
        const flowId = payload.flow_id || payload.flowId || null;
        const skillId = payload.skill_id || payload.skillId || 'base';
        const nodeId = payload.node_id || payload.nodeId || null;
        const openEditor = payload.open_editor !== false;

        if (flowId) {
            if (skillId && skillId !== 'base') {
                FlowsStore.setCurrentFlowAndSkill(flowId, skillId);
            } else {
                FlowsStore.setCurrentFlow(flowId);
            }
        }
        if (flowId && openEditor) {
            this._openEditorFromUrl(flowId, skillId === 'base' ? null : skillId);
        }
        if (nodeId) {
            window.dispatchEvent(
                new CustomEvent('flows-editor-select-node', {
                    detail: { flowId, skillId, nodeId },
                    bubbles: true,
                    composed: true,
                }),
            );
        }
        this._setLaraInvocationContext({
            flow_id: flowId,
            skill_id: skillId,
            node_id: nodeId,
            selection_source: 'panel_launcher',
        });
        this._emitLaraEvent('navigate', {
            flow_id: flowId,
            skill_id: skillId,
            node_id: nodeId,
        });
    }

    _toggleMobileMenu() {
        const sidebar = this.shadowRoot.querySelector('flows-sidebar');
        sidebar?.toggleMobile();
    }

    _closeMobileMenu() {
        const sidebar = this.shadowRoot.querySelector('flows-sidebar');
        sidebar?.closeMobile();
    }

    setupStore() {
        return FlowsStore;
    }

    getBaseUrl() {
        return '/flows';
    }

    async initServices() {
        await super.initServices();
        
        const a2a = new A2AService('/flows');
        this.services.register('a2a', a2a);
        
        this.state = this.use(s => {
            const currentFlow = s.flows.list.find(a => a.flow_id === s.flows.currentId);
            const currentSkill = currentFlow?.skills?.[s.app.currentSkillId];
            return {
                currentFlowId: s.flows.currentId,
                currentFlowName: currentFlow?.name || '',
                currentSkillId: s.app.currentSkillId,
                currentSkillName: currentSkill?.name || '',
            };
        });
        
        const path = window.location.pathname.replace(/\/$/, '') || '';
        this._operatorWorkbench = path.endsWith('/operator');

        if (this._operatorWorkbench) return;

        const urlState = readUrlState();
        const flowId = urlState.flowId;

        if (flowId) {
            if (urlState.skillId) {
                FlowsStore.setCurrentFlowAndSkill(flowId, urlState.skillId);
            } else {
                FlowsStore.setCurrentFlow(flowId);
            }
        }

        if (flowId && urlState.sessionId) {
            this._restoreSessionFromUrl(a2a, urlState.sessionId, flowId);
        }

        if (flowId && urlState.edit) {
            this._pendingEditFlowId = flowId;
            this._pendingEditSkillId = urlState.skillId;
        }

        this._setupUrlSync();
        this._setupChatSessionUrlSync();
    }

    /**
     * После первого сообщения в чате добавляет в URL session={flow_id}:{context_id},
     * чтобы ссылку можно было передать. Пустой чат — параметр session убирается.
     */
    _setupChatSessionUrlSync() {
        let lastSig = '';

        FlowsStore.subscribe(() => {
            const s = FlowsStore.state;
            const flowId = s.flows.currentId;
            const skillId = s.app.currentSkillId;
            const contextId = s.chat.contextId;
            const msgLen = s.chat.messages.length;

            if (!flowId) return;

            const params = new URLSearchParams(window.location.search);
            const edit = params.get('edit') === '1';

            const sessionId =
                msgLen > 0 && contextId ? `${flowId}:${contextId}` : null;

            const sig = `${flowId}|${skillId ?? ''}|${sessionId ?? ''}|${edit}|${msgLen}`;
            if (sig === lastSig) return;
            lastSig = sig;

            updateUrl({
                flowId,
                skillId,
                sessionId,
                edit,
            });
        });
    }

    /**
     * Восстановить сессию из URL-параметра session=...
     */
    async _restoreSessionFromUrl(a2a, sessionId, flowId) {
        try {
            const state = await a2a.getSessionState(sessionId);
            const messages = state?.messages || [];
            const taskId = state?.task_id || null;
            FlowsStore.loadSession(sessionId, messages, flowId, taskId);
        } catch (err) {
            console.error('[FlowsApp] Failed to restore session from URL:', err);
        }
    }

    _openEditorFromUrl(flowId, skillId) {
        const modal = document.createElement('flow-edit-modal');
        modal.flowId = flowId;
        if (skillId) modal.skillId = skillId;
        document.body.appendChild(modal);
        requestAnimationFrame(() => modal.setAttribute('open', ''));
        modal.addEventListener('close', () => {
            modal.remove();
            removeUrlParams('edit');
        });
    }

    _setupUrlSync() {
        let prevFlowId = FlowsStore.state.flows.currentId;
        let prevSkillId = FlowsStore.state.app.currentSkillId;

        FlowsStore.subscribe(() => {
            const s = FlowsStore.state;
            const flowId = s.flows.currentId;
            const skillId = s.app.currentSkillId;

            if (flowId === prevFlowId && skillId === prevSkillId) return;

            const flowChanged = flowId !== prevFlowId;
            prevFlowId = flowId;
            prevSkillId = skillId;

            if (!flowId) return;

            const params = new URLSearchParams(window.location.search);
            const keepEdit = params.get('edit') === '1';
            // При смене flow сессия становится невалидной
            const keepSession = flowChanged ? null : params.get('session');

            updateUrl({
                flowId,
                skillId,
                sessionId: keepSession,
                edit: keepEdit,
            });
        });
    }

    async checkAuth() {
        try {
            const response = await this.auth.validateToken();
            return response !== null;
        } catch (error) {
            console.error('[FlowsApp] Auth check failed:', error);
            return false;
        }
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) {
            return shell;
        }

        if (!this._servicesInitialized || !this._authChecked) {
            return html`
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">${this.i18n.t('flows_app.loading')}</div>
                </div>
            `;
        }

        if (!this._isAuthenticated) {
            return html`
                <div class="loading-container">
                    <div class="loading-text">${this.i18n.t('flows_app.redirect_auth')}</div>
                </div>
            `;
        }

        if (this._operatorWorkbench) {
            if (!canManageOperatorWorkbench(this.auth)) {
                return html`
                    <div class="loading-container operator-access-denied">
                        <p class="denied-title">${this.i18n.t('flows_app.operator_denied_title')}</p>
                        <p class="denied-text">${this.i18n.t('flows_app.operator_denied_body')}</p>
                        <a class="denied-link" href="/flows/example_react">${this.i18n.t('flows_app.operator_denied_back')}</a>
                    </div>
                `;
            }
            return html`<operator-workbench-page></operator-workbench-page>`;
        }

        if (this._pendingEditFlowId) {
            this._openEditorFromUrl(this._pendingEditFlowId, this._pendingEditSkillId);
            this._pendingEditFlowId = null;
            this._pendingEditSkillId = null;
        }

        const { currentFlowId, currentFlowName, currentSkillId, currentSkillName } = this.state.value;

        return html`
            <flows-sidebar></flows-sidebar>
            <platform-chat 
                .flowId=${currentFlowId}
                .flowName=${currentFlowName}
                .skillId=${currentSkillId || ''}
                .skillName=${currentSkillName}
            ></platform-chat>
            <platform-lara-assistant
                toggle-event-name="flows-lara-open"
                flow-id="lara"
                skill-id="flows"
                .flowsBaseUrl=${'/flows'}
                ?use-credentials=${true}
                .assistantTitle=${'Lara'}
                .locale=${this.services.get('i18n').getCurrentLocale()}
                .getExtraMetadataVariables=${this._laraEmbedContextVariables}
                .getContextVariables=${this._laraEmbedContextVariables}
                .actionHandlers=${this._laraActionHandlers}
            ></platform-lara-assistant>
        `;
    }
}

customElements.define('flows-app', FlowsApp);
