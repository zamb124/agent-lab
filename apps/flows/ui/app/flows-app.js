/**
 * FlowsApp — корневой Lit-компонент сервиса flows.
 *
 * Все доменные операции описаны фабриками в `apps/flows/ui/events/resources/*`.
 * Чат и operator команды используют `transport: 'ws'` с REST-зеркалом;
 * сами стриминговые события чата приходят push-ами `flows/chat/*` через
 * единый WebSocket `/flows/api/ws/notifications`.
 *
 * Маршруты заданы декларативно через `createRouterEffect` (см. SYNC_ROUTES
 * для образца). `renderRoute` — switch по routeKey.
 */

import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';
import '@platform/lib/embed-chat/platform-lara-assistant.js';

import { flowsResource, flowUpdateOp, flowReloadFromBundleOp, flowVersionsListOp,
         flowStoreBundlesOp, flowValidateOp, skillCreateOp, skillUpdateOp,
         skillRemoveOp } from '../events/resources/flows.resource.js';
import { toolsResource, toolsAllOp } from '../events/resources/tools.resource.js';
import { resourcesBundleResource, resourceUpdateOp } from '../events/resources/resources-bundle.resource.js';
import { mcpServersResource, mcpServerUpdateOp, mcpServerSyncOp, mcpServerTestOp } from '../events/resources/mcp.resource.js';
import { triggersListOp, triggerGetOp, triggerCreateOp, triggerUpdateOp,
         triggerRemoveOp, triggerVerifyOp, triggerReregisterOp, triggerTestOp } from '../events/resources/triggers.resource.js';
import { variablesResource } from '../events/resources/variables.resource.js';
import { nodesCatalogResource, nodeCatalogUpdateOp } from '../events/resources/nodes-catalog.resource.js';
import { sessionsResource, sessionStateOp } from '../events/resources/sessions.resource.js';
import { tracesBySessionOp, tracesByTaskOp, tracesByTraceOp } from '../events/resources/traces.resource.js';
import { logsByTraceOp, logsBySessionOp } from '../events/resources/logs.resource.js';
import {
    nodeTypesOp,
    resourceTypesOp,
    exceptionAbsorbAllowNamesOp,
    executionLimitsOp,
} from '../events/resources/metadata.resource.js';
import { modelsListOp } from '../events/resources/models.resource.js';
import { providersListOp } from '../events/resources/providers.resource.js';
import { codeCompletionsOp, codeDocumentationOp, codeTemplatesOp,
         codeEditorStateOp, codeSourceOp, codeFlowFunctionsOp,
         codeToolSourceOp, codeParseSignatureOp, codeValidateOp,
         codeExecuteOp } from '../events/resources/code.resource.js';
import { promptRenderOp } from '../events/resources/prompts.resource.js';
import { integrationsListOp, integrationsRemoveOp } from '../events/resources/integrations.resource.js';
import { fileUploadOp } from '../events/resources/files.resource.js';
import { chatResource, chatSendOp, chatCancelOp } from '../events/resources/chat.resource.js';
import { operatorQueuesResource, operatorQueueAddMemberOp, operatorQueueRemoveMemberOp,
         operatorTasksListOp, operatorTaskGetOp, operatorTaskClaimOp,
         operatorTaskPostMessageOp, operatorTaskCompleteOp } from '../events/resources/operator.resource.js';
import { editorResource, editorBulkDeleteOp, stickyNoteUpsertOp } from '../events/resources/editor.resource.js';
import { executionUiSlice } from '../events/resources/execution-ui.resource.js';
import { asObject, asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import { applyTenantHostRedirectIfNeeded } from '@platform/lib/utils/tenant-host-guard.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';
import '@platform/lib/components/layout/platform-island.js';

const FLOWS_ROUTES = [
    { key: 'list',                path: '' },
    { key: 'operator',            path: 'operator' },
    { key: 'platform_services',   path: 'services', parent: 'list' },
    { key: 'flow_chat',           path: ':flowId' },
    { key: 'flow_chat_skill',     path: ':flowId/skill/:skillId' },
    { key: 'flow_chat_session',   path: ':flowId/session/:sessionId' },
    { key: 'flow_editor',         path: ':flowId/editor' },
    { key: 'flow_editor_skill',   path: ':flowId/editor/:skillId' },
];

export class FlowsApp extends PlatformApp {
    static defaultI18nNamespace = 'flows';

    static factories = [
        flowsResource,
        flowUpdateOp,
        flowReloadFromBundleOp,
        flowVersionsListOp,
        flowStoreBundlesOp,
        flowValidateOp,
        skillCreateOp,
        skillUpdateOp,
        skillRemoveOp,
        toolsResource,
        toolsAllOp,
        resourcesBundleResource,
        resourceUpdateOp,
        mcpServersResource,
        mcpServerUpdateOp,
        mcpServerSyncOp,
        mcpServerTestOp,
        triggersListOp,
        triggerGetOp,
        triggerCreateOp,
        triggerUpdateOp,
        triggerRemoveOp,
        triggerVerifyOp,
        triggerReregisterOp,
        triggerTestOp,
        variablesResource,
        nodesCatalogResource,
        nodeCatalogUpdateOp,
        sessionsResource,
        sessionStateOp,
        tracesBySessionOp,
        tracesByTaskOp,
        tracesByTraceOp,
        logsByTraceOp,
        logsBySessionOp,
        nodeTypesOp,
        resourceTypesOp,
        exceptionAbsorbAllowNamesOp,
        executionLimitsOp,
        modelsListOp,
        providersListOp,
        codeCompletionsOp,
        codeDocumentationOp,
        codeTemplatesOp,
        codeEditorStateOp,
        codeSourceOp,
        codeFlowFunctionsOp,
        codeToolSourceOp,
        codeParseSignatureOp,
        codeValidateOp,
        codeExecuteOp,
        promptRenderOp,
        integrationsListOp,
        integrationsRemoveOp,
        fileUploadOp,
        chatResource,
        chatSendOp,
        chatCancelOp,
        operatorQueuesResource,
        operatorQueueAddMemberOp,
        operatorQueueRemoveMemberOp,
        operatorTasksListOp,
        operatorTaskGetOp,
        operatorTaskClaimOp,
        operatorTaskPostMessageOp,
        operatorTaskCompleteOp,
        editorResource,
        editorBulkDeleteOp,
        stickyNoteUpsertOp,
        executionUiSlice,
    ];

    static styles = [
        PlatformApp.styles,
        css`
            :host {
                display: flex;
                flex-direction: row;
                width: var(--app-vw, 100vw);
                height: var(--app-vh, 100vh);
                overflow: hidden;
                background: var(--bg-gradient);
            }
            .sidebar {
                height: var(--app-vh, 100vh);
                flex-shrink: 0;
                background: transparent;
            }
            .main {
                flex: 1;
                min-width: 0;
                height: var(--app-vh, 100vh);
                display: flex;
                flex-direction: column;
                padding: var(--space-4);
                overflow: hidden;
            }
            platform-island {
                flex: 1;
                min-height: 0;
                min-width: 0;
            }
            flow-editor-page,
            operator-page {
                flex: 1;
                min-width: 0;
                min-height: 0;
                height: 100%;
            }
            @media (max-width: 767px) {
                .main {
                    padding: 0;
                }
                .sidebar {
                    position: absolute;
                    width: 0;
                    height: 0;
                    overflow: visible;
                }
            }
        `,
    ];

    constructor() {
        super();
        this._editor = this.useOp('flows/editor');
        this._flows = this.useResource('flows/flows');
        this.useEvent('flows/flow/updated', (event) => {
            const id = event?.payload?.flow_id;
            if (typeof id === 'string' && id.length > 0) {
                this._flows.get(id);
            }
        });
        this.useEvent('flows/flow/deleted', () => {
            this._flows.load();
        });
        this.useEvent('flows/skill/created', (event) => {
            const id = event?.payload?.flow_id;
            if (typeof id === 'string' && id.length > 0) {
                this._flows.get(id);
            }
        });
        this.useEvent('flows/skill/updated', (event) => {
            const id = event?.payload?.flow_id;
            if (typeof id === 'string' && id.length > 0) {
                this._flows.get(id);
            }
        });
        this.useEvent('flows/skill/deleted', (event) => {
            const id = event?.payload?.flow_id;
            if (typeof id === 'string' && id.length > 0) {
                this._flows.get(id);
            }
        });
        this._companiesListSel = this.select((s) => s.companies.list);
        this._companiesLoadingSel = this.select((s) => s.companies.loading);
        this._flowsMql = null;
        this._onFlowsMobileMql = null;
        this._flowsMobile =
            typeof window !== 'undefined' &&
            typeof window.matchMedia === 'function' &&
            window.matchMedia('(max-width: 767px)').matches;
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return;
        }
        this._flowsMql = window.matchMedia('(max-width: 767px)');
        this._onFlowsMobileMql = () => {
            const next = this._flowsMql.matches;
            if (next !== this._flowsMobile) {
                this._flowsMobile = next;
                this.requestUpdate();
            }
        };
        this._flowsMql.addEventListener('change', this._onFlowsMobileMql);
        const next = this._flowsMql.matches;
        if (next !== this._flowsMobile) {
            this._flowsMobile = next;
            this.requestUpdate();
        }
    }

    disconnectedCallback() {
        if (this._flowsMql && this._onFlowsMobileMql) {
            this._flowsMql.removeEventListener('change', this._onFlowsMobileMql);
        }
        super.disconnectedCallback();
    }

    updated(changed) {
        super.updated(changed);
        if (!this._bootstrapped) {
            return;
        }
        const auth = this._authSelect.value;
        applyTenantHostRedirectIfNeeded(
            auth,
            this._companiesListSel.value,
            this._companiesLoadingSel.value,
            { loadCompanies: () => this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null) },
        );
    }

    getBaseUrl() {
        return '/flows';
    }

    getRoutes() {
        return [];
    }

    getServiceEffects() {
        return [createRouterEffect({ baseUrl: '/flows', routes: FLOWS_ROUTES })];
    }

    renderRoute(routeKey, params) {
        switch (routeKey) {
            case 'platform_services':
                return html`
                    <div class="sidebar">
                        <flows-list-page></flows-list-page>
                    </div>
                    <div class="main">
                        <platform-island padding=${this._flowsMobile ? 'none' : 'md'} ?safe-bottom=${this._flowsMobile}>
                            <platform-services-page></platform-services-page>
                        </platform-island>
                    </div>
                    ${this._renderLara()}
                `;
            case 'operator':
                return html`<operator-page></operator-page>`;
            case 'flow_chat':
            case 'flow_chat_skill':
            case 'flow_chat_session':
                return html`
                    <div class="sidebar">
                        <flows-list-page></flows-list-page>
                    </div>
                    <div class="main">
                        <platform-island
                            padding=${this._flowsMobile ? 'none' : 'md'}
                            ?safe-bottom=${this._flowsMobile}
                            ?content-no-scroll=${true}
                        >
                            <chat-page
                                .flowId=${params.flowId}
                                .skillId=${typeof params.skillId === 'string' && params.skillId.length > 0 ? params.skillId : 'base'}
                                .sessionId=${asString(params.sessionId)}
                            ></chat-page>
                        </platform-island>
                    </div>
                    ${this._renderLara()}
                `;
            case 'flow_editor':
            case 'flow_editor_skill':
                return html`
                    <flow-editor-page
                        .flowId=${params.flowId}
                        .skillId=${typeof params.skillId === 'string' && params.skillId.length > 0 ? params.skillId : 'base'}
                    ></flow-editor-page>
                    ${this._renderLara()}
                `;
            case 'list':
            default:
                return html`
                    <div class="sidebar">
                        <flows-list-page></flows-list-page>
                    </div>
                    <div class="main">
                        <platform-island
                            padding=${this._flowsMobile ? 'none' : 'md'}
                            ?safe-bottom=${this._flowsMobile}
                        >
                            <flows-empty-state></flows-empty-state>
                        </platform-island>
                    </div>
                    ${this._renderLara()}
                `;
        }
    }

    _renderLara() {
        return html`
            <platform-lara-assistant
                toggle-event-name="flows-lara-open"
                event-namespace="assistant"
                flow-id="lara"
                skill-id="flows"
                .flowsBaseUrl=${'/flows'}
                ?use-credentials=${true}
                .assistantTitle=${'Lara'}
                .getExtraMetadataVariables=${this._laraEmbedContextVariables}
                .getContextVariables=${this._laraEmbedContextVariables}
            ></platform-lara-assistant>
        `;
    }

    _laraEmbedContextVariables = async () => {
        return this._flattenLaraContext(this._buildLaraFlowsContext({}));
    };

    _buildLaraFlowsContext(options = {}) {
        const editorState = isPlainObject(this._editor?.state) ? this._editor.state : {};
        const routerValue = this._routerSelect ? this._routerSelect.value : null;
        const params = isPlainObject(routerValue?.params) ? routerValue.params : {};
        const pickString = (...candidates) => {
            for (const c of candidates) {
                if (typeof c === 'string' && c.length > 0) return c;
            }
            return null;
        };
        const flowId = pickString(editorState.flowId, params.flowId, options.flow_id);
        const skillId = pickString(editorState.currentSkillId, params.skillId, options.skill_id, 'base');
        const nodeId = pickString(editorState.selectedNodeId, options.node_id);
        const skillsData = isPlainObject(editorState.skillsData) ? editorState.skillsData : { nodes: {} };
        const nodes = isPlainObject(skillsData.nodes) ? skillsData.nodes : {};
        const node = nodeId && isPlainObject(nodes[nodeId]) ? nodes[nodeId] : null;
        return {
            app_surface: 'flows',
            flow_id: flowId,
            target_skill_id: skillId,
            node_id: nodeId,
            node_type: node && typeof node.type === 'string' ? node.type : null,
            node_payload: node,
            flow_payload: isPlainObject(editorState.flowConfig) ? editorState.flowConfig : null,
            screen: nodeId ? 'flow_editor_node' : (flowId ? 'flow_editor' : 'flow_list'),
        };
    }

    _flattenLaraContext(context) {
        return {
            lara_ui_context: context,
            lara_ui_context_json: JSON.stringify(context),
            app_surface: context.app_surface,
            screen: context.screen,
            flow_id: asString(context.flow_id),
            target_skill_id: typeof context.target_skill_id === 'string' && context.target_skill_id.length > 0 ? context.target_skill_id : 'base',
            skill_id: typeof context.target_skill_id === 'string' && context.target_skill_id.length > 0 ? context.target_skill_id : 'base',
            assistant_skill_id: 'flows',
            node_id: asString(context.node_id),
            node_type: asString(context.node_type),
            node_payload_json: context.node_payload ? JSON.stringify(context.node_payload) : '',
            flow_payload_json: context.flow_payload ? JSON.stringify(context.flow_payload) : '',
        };
    }

    render() {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) return shell;
        if (!this._bootstrapped) {
            return html`
                <div class="loading-container">
                    <div class="loading-spinner"></div>
                    <div class="loading-text">${this.t('loading', {}, 'common')}</div>
                </div>
            `;
        }
        return super.render();
    }
}

customElements.define('flows-app', FlowsApp);
