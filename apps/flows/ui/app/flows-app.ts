/**
 * FlowsApp — корневой Lit-компонент сервиса flows.
 *
 * Все доменные операции описаны фабриками в `apps/flows/ui/events/resources/*`.
 * Runtime UI — единый `<platform-flow-ui>` (core/lib/flow-ui): document/tasks/
 * artifacts, A2A SSE и voice внутри компонента, не в фабриках. Задачи
 * (включая HITL) ведутся в сервисе worktracker, а не во flows UI.
 *
 * Маршруты заданы декларативно через `createRouterEffect` (см. SYNC_ROUTES
 * для образца). `renderRoute` — switch по routeKey.
 */

import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { CompanyRecord } from '@platform/lib/events/reducers/companies.js';
import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css } from 'lit';
import { PlatformApp, renderPlatformAppShell } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';

import { flowsResource, flowUpdateOp, flowReloadFromBundleOp, flowVersionsListOp,
         flowStoreBundlesOp, flowValidateOp, branchCreateOp, branchUpdateOp,
         branchRemoveOp, flowVoiceSessionQueryOp, flowPreviewShareOp } from '../events/resources/flows.resource.js';
import { flowUiSchemaOp, flowUiTemplatesOp, flowUiAssistOp } from '../events/resources/flow-ui.resource.js';
import { toolsResource, toolsAllOp } from '../events/resources/tools.resource.js';
import { toolTagGroupsOp } from '../events/resources/tool-tag-groups.resource.js';
import { workQueuesResource } from '@platform/lib/events/resources/work-queues.resource.js';
import { flowsVoiceProvidersCatalogLoadOp } from '@platform/lib/events/resources/voice-providers-catalog.resource.js';
import {
    agentSkillsResource,
    agentSkillImportOp,
    agentSkillsEnsureSeedOp,
} from '../events/resources/agent-skills.resource.js';
import { resourcesBundleResource } from '../events/resources/resources-bundle.resource.js';
import { mcpServersResource, mcpServersListOp, mcpServerSyncOp, mcpServerTestOp, mcpServerResetCatalogDefaultsOp, mcpBrandingLoadOp, mcpBrandingSlugSuggestOp, mcpBrandingUpsertOp, mcpBrandingRemoveOp, mcpCatalogStoreLoadOp, mcpCatalogInstallOp, mcpCatalogUninstallOp } from '../events/resources/mcp.resource.js';
import {
    datasourcesResource,
    datasourceTestOp,
    datasourceIntrospectOp,
    datasourceQueryOp,
    datasourceExecuteOp,
} from '../events/resources/datasources.resource.js';
import { triggersListOp, triggerGetOp, triggerCreateOp, triggerUpdateOp,
         triggerRemoveOp, triggerVerifyOp, triggerReregisterOp, triggerTestOp,
         platformEventsCatalogOp } from '../events/resources/triggers.resource.js';
import { secretsVariablesResource } from '@platform/lib/events/resources/secrets-variables.resource.js';
import { secretsVariablesResolveOp } from '@platform/lib/events/resources/secrets-variables-resolve.resource.js';
import { secretsVariableVersionsLoadOp } from '@platform/lib/events/resources/secrets-variable-versions.resource.js';
import { nodesCatalogResource } from '../events/resources/nodes-catalog.resource.js';
import { sessionsResource, sessionStateOp } from '../events/resources/sessions.resource.js';
import { tracesBySessionOp, tracesByTaskOp, tracesByTraceOp, tracesByHandoffChainOp } from '../events/resources/traces.resource.js';
import {
    durableHistoryOp,
    durableBranchesOp,
    durableStateAtOp,
    durableForkOp,
    durableRewindOp,
    durableRetryFromFailureOp,
    durableManualPatchOp,
} from '../events/resources/durable-history.resource.js';
import {
    logsByTraceOp,
    logsBySessionOp,
    logsByRequestOp,
    logsBySpanOp,
    logsByUserOp,
} from '../events/resources/logs.resource.js';
import {
    nodeTypesOp,
    resourceTypesOp,
    exceptionAbsorbAllowNamesOp,
    executionLimitsOp,
} from '../events/resources/metadata.resource.js';
import { modelsListOp } from '../events/resources/models.resource.js';
import { providersListOp } from '../events/resources/providers.resource.js';
import { codeLspSessionOp, codeDocumentationOp, codeTemplatesOp,
         codeEditorStateOp, codeSourceOp, codeFlowFunctionsOp,
         codeToolSourceOp, codeParseSignatureOp, codeValidateOp,
         codeExecuteOp } from '../events/resources/code.resource.js';
import { promptRenderOp } from '../events/resources/prompts.resource.js';
import { dataflowInspectOp } from '../events/resources/dataflow.resource.js';
import { llmContextResolveParentOp } from '../events/resources/llm-context.resource.js';
import { namespacesResource } from '@platform/lib/events/resources/rag-namespaces.resource.js';
import {
    documentsResource,
    documentUploadOp,
    documentRemoveOp,
} from '@platform/lib/events/resources/rag-documents.resource.js';
import { documentStatusResource } from '@platform/lib/events/resources/rag-document-status.resource.js';
import { searchOp, searchDefaultsOp } from '@platform/lib/events/resources/rag-search.resource.js';
import { flowsRagNodeTestSlice } from '../events/resources/rag-node-test.resource.js';
import { registerNodeTestRunHandler } from '../_helpers/node-test-run-registry.js';
import { codeExecuteTestRunHandler } from '../_helpers/node-test-run-code-execute.js';
import { ragSearchTestRunHandler } from '../_helpers/node-test-run-rag-search.js';
import {
    flowsDataTableCreateOp,
    flowsDataTableSnapshotOp,
} from '../events/resources/data-tables.resource.js';
import {
    flowsCodeAgentEnsureSourceOp,
    flowsCodeAgentImportGitOp,
    flowsCodeAgentImportArchiveOp,
    flowsCodeAgentCopyTreeOp,
    flowsCodeAgentRebuildOp,
    flowsCodeAgentStatusOp,
    flowsCodeAgentLogsOp,
    flowsCodeAgentDeleteOp,
} from '../events/resources/code-agent.resource.js';
import { catalogItemsOp } from '@platform/lib/events/resources/office-catalog-items.resource.js';
import {
    integrationsListOp,
    integrationsRemoveOp,
    googleWorkspaceAuthorizeOp,
    googleWorkspaceCompanyGetOp,
    googleWorkspaceCompanyPutOp,
    googleWorkspaceCompanyDeleteOp,
} from '../events/resources/integrations.resource.js';
import { platformFileCreateOp } from '@platform/lib/events/factories/platform-file-create.js';
import { apiConsoleRunOp } from '../events/resources/api-console.resource.js';
import { editorResource, editorBulkDeleteOp, stickyNoteUpsertOp } from '../events/resources/editor.resource.js';
import { executionUiSlice } from '../events/resources/execution-ui.resource.js';
import { interfaceEditorSlice } from '../events/resources/interface-editor.resource.js';
import {
    evaluationUiSlice,
    evaluationEvaluatorCatalogOp,
    evaluationSuitesListOp,
    evaluationSuiteCreateOp,
    evaluationSuiteUpdateOp,
    evaluationSuiteArchiveOp,
    evaluationCasesListOp,
    evaluationCaseCreateOp,
    evaluationCaseUpdateOp,
    evaluationCaseDeleteOp,
    evaluationCaseImportOp,
    evaluationCaseFromDialogOp,
    evaluationCaseFromTraceOp,
    evaluationRunsListOp,
    evaluationRunCreateOp,
    evaluationRunGetOp,
    evaluationRunCancelOp,
    evaluationRunCasesOp,
    evaluationRunEventsOp,
    evaluationRunEventsPageOp,
    evaluationMatrixGetOp,
    evaluationCompareRunsOp,
    evaluationCaseRunTraceOp,
    evaluationAnnotationsListOp,
    evaluationAnnotationCreateOp,
    evaluationBaselinesListOp,
    evaluationBaselineSetOp,
    evaluationGatePoliciesListOp,
    evaluationMonitorsListOp,
    evaluationMonitorObservationsOp,
    evaluationMonitorObservationCaseCreateOp,
    evaluationPairwiseJudgmentCreateOp,
    evaluationRubricsListOp,
    evaluationRubricCreateOp,
    evaluationRubricVersionsListOp,
    evaluationRubricVersionCreateOp,
} from '../events/resources/evaluation.resource.js';
import { asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import {
    LARA_FLOWS_BRANCH_ID,
    buildLaraFlowsContext,
    flattenLaraFlowsContext,
} from '../_helpers/lara-node-helper.js';
import { applyCompanyHostRedirectIfNeeded, type CompanyListEntry } from '@platform/lib/utils/company-host-guard.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';
import '@platform/lib/components/layout/platform-island.js';
import '../components/flows-catalog-list.js';
import '../components/flows-sidebar.js';
import type {CSSResultGroup, PropertyValues, TemplateResult} from 'lit';
import '@platform/lib/components/platform-empty-state.js';

registerNodeTestRunHandler(codeExecuteTestRunHandler);
registerNodeTestRunHandler(ragSearchTestRunHandler);

const FLOWS_ROUTES = [
    { key: 'list',                 path: '',                              titleKey: 'routes.list' },
    { key: 'platform_services',    path: 'services', parent: 'list',      titleKey: 'routes.platform_services' },
    { key: 'agent_skills',         path: 'skills', parent: 'list',        titleKey: 'routes.agent_skills' },
    { key: 'flow_chat',            path: ':flowId',                       parent: 'list', titleKey: 'routes.flow_chat' },
    // Chat branch/session parent is list (not flow_chat): crumbs are Overview / <flow> [/ <branch>],
    // not Overview / Flow / Flow. Entity names come from chat-page current-label + trail.
    { key: 'flow_chat_branch',     path: ':flowId/branch/:branchId',      parent: 'list', titleKey: 'routes.flow_chat_branch' },
    { key: 'flow_chat_session',    path: ':flowId/session/:sessionId',    parent: 'list', titleKey: 'routes.flow_chat_session' },
    // A session belongs to the branch it was created with, so the branch stays in the
    // URL: reload and "New screen" must not fall back to the base flow.
    { key: 'flow_chat_branch_session', path: ':flowId/branch/:branchId/session/:sessionId', parent: 'list', titleKey: 'routes.flow_chat_branch_session' },
    { key: 'flow_editor',          path: ':flowId/editor',                parent: 'flow_chat', titleKey: 'routes.flow_editor' },
    { key: 'flow_editor_branch',   path: ':flowId/editor/:branchId',      parent: 'flow_editor', titleKey: 'routes.flow_editor_branch' },
    { key: 'flow_evaluation',      path: ':flowId/evaluation',            parent: 'flow_chat', titleKey: 'routes.flow_evaluation' },
    { key: 'flow_evaluation_branch', path: ':flowId/evaluation/:branchId', parent: 'flow_evaluation', titleKey: 'routes.flow_evaluation_branch' },
];

/**
 * Нижняя навигация (mobile shell 2026): список, Профиль.
 * На маршруте чата или редактора капсула скрыта; из чата возврат — кнопка в шапке.
 */
const FLOWS_BOTTOM_NAV_ITEMS = [
    { key: 'flows',    routeKey: 'list',     icon: 'workflow',  labelKey: 'bottom_nav.flows' },
    { key: 'profile',  sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.profile' },
];

/** Чат/editing канвас без нижней капсулы: назад через шапку чата или выход из редактора. */
const FLOWS_BOTTOM_NAV_HIDE_ON_ROUTES = [
    'flow_chat',
    'flow_chat_branch',
    'flow_chat_session',
    'flow_chat_branch_session',
    'flow_editor',
    'flow_editor_branch',
    'flow_evaluation',
    'flow_evaluation_branch',
];

function companyListEntries(companies: readonly CompanyRecord[]): CompanyListEntry[] {
    const entries: CompanyListEntry[] = [];
    for (const company of companies) {
        const companyId = company.company_id;
        if (typeof companyId !== 'string' || companyId === '') {
            throw new Error('flows-app: company_id required');
        }
        const entry: CompanyListEntry = { company_id: companyId };
        if (typeof company.subdomain === 'string' && company.subdomain !== '') {
            entry.subdomain = company.subdomain;
        }
        entries.push(entry);
    }
    return entries;
}

export class FlowsApp extends PlatformApp {
    static defaultI18nNamespace = 'flows';
    static bottomNavItems = FLOWS_BOTTOM_NAV_ITEMS;
    static bottomNavHideOnRoutes = FLOWS_BOTTOM_NAV_HIDE_ON_ROUTES;
    static platformAssistant = {
        serviceId: 'flows',
        branchId: LARA_FLOWS_BRANCH_ID,
        showLauncher: true,
    };

    static factories = [
        flowsResource,
        flowUpdateOp,
        flowReloadFromBundleOp,
        flowVersionsListOp,
        flowStoreBundlesOp,
        flowValidateOp,
        branchCreateOp,
        branchUpdateOp,
        branchRemoveOp,
        flowsVoiceProvidersCatalogLoadOp,
        flowVoiceSessionQueryOp,
        flowPreviewShareOp,
        flowUiSchemaOp,
        flowUiTemplatesOp,
        flowUiAssistOp,
        toolsResource,
        toolsAllOp,
        toolTagGroupsOp,
        workQueuesResource,
        agentSkillsResource,
        agentSkillImportOp,
        agentSkillsEnsureSeedOp,
        resourcesBundleResource,
        mcpServersResource,
        mcpServersListOp,
        mcpServerSyncOp,
        mcpServerTestOp,
        mcpServerResetCatalogDefaultsOp,
        mcpBrandingLoadOp,
        mcpBrandingSlugSuggestOp,
        mcpBrandingUpsertOp,
        mcpBrandingRemoveOp,
        mcpCatalogStoreLoadOp,
        mcpCatalogInstallOp,
        mcpCatalogUninstallOp,
        datasourcesResource,
        datasourceTestOp,
        datasourceIntrospectOp,
        datasourceQueryOp,
        datasourceExecuteOp,
        triggersListOp,
        triggerGetOp,
        triggerCreateOp,
        triggerUpdateOp,
        triggerRemoveOp,
        triggerVerifyOp,
        triggerReregisterOp,
        triggerTestOp,
        platformEventsCatalogOp,
        secretsVariablesResource,
        secretsVariablesResolveOp,
        secretsVariableVersionsLoadOp,
        nodesCatalogResource,
        sessionsResource,
        sessionStateOp,
        tracesBySessionOp,
        tracesByTaskOp,
        tracesByTraceOp,
        tracesByHandoffChainOp,
        durableHistoryOp,
        durableBranchesOp,
        durableStateAtOp,
        durableForkOp,
        durableRewindOp,
        durableRetryFromFailureOp,
        durableManualPatchOp,
        logsByTraceOp,
        logsBySessionOp,
        logsByRequestOp,
        logsBySpanOp,
        logsByUserOp,
        nodeTypesOp,
        resourceTypesOp,
        exceptionAbsorbAllowNamesOp,
        executionLimitsOp,
        modelsListOp,
        providersListOp,
        codeLspSessionOp,
        codeDocumentationOp,
        codeTemplatesOp,
        codeEditorStateOp,
        codeSourceOp,
        codeFlowFunctionsOp,
        codeToolSourceOp,
        codeParseSignatureOp,
        codeValidateOp,
        codeExecuteOp,
        dataflowInspectOp,
        llmContextResolveParentOp,
        namespacesResource,
        searchDefaultsOp,
        documentsResource,
        documentUploadOp,
        documentStatusResource,
        documentRemoveOp,
        searchOp,
        flowsRagNodeTestSlice,
        flowsDataTableCreateOp,
        flowsDataTableSnapshotOp,
        flowsCodeAgentEnsureSourceOp,
        flowsCodeAgentImportGitOp,
        flowsCodeAgentImportArchiveOp,
        flowsCodeAgentCopyTreeOp,
        flowsCodeAgentRebuildOp,
        flowsCodeAgentStatusOp,
        flowsCodeAgentLogsOp,
        flowsCodeAgentDeleteOp,
        catalogItemsOp,
        promptRenderOp,
        integrationsListOp,
        integrationsRemoveOp,
        googleWorkspaceAuthorizeOp,
        googleWorkspaceCompanyGetOp,
        googleWorkspaceCompanyPutOp,
        googleWorkspaceCompanyDeleteOp,
        platformFileCreateOp,
        apiConsoleRunOp,
        editorResource,
        editorBulkDeleteOp,
        stickyNoteUpsertOp,
        executionUiSlice,
        interfaceEditorSlice,
        evaluationUiSlice,
        evaluationEvaluatorCatalogOp,
        evaluationSuitesListOp,
        evaluationSuiteCreateOp,
        evaluationSuiteUpdateOp,
        evaluationSuiteArchiveOp,
        evaluationCasesListOp,
        evaluationCaseCreateOp,
        evaluationCaseUpdateOp,
        evaluationCaseDeleteOp,
        evaluationCaseImportOp,
        evaluationCaseFromDialogOp,
        evaluationCaseFromTraceOp,
        evaluationRunsListOp,
        evaluationRunCreateOp,
        evaluationRunGetOp,
        evaluationRunCancelOp,
        evaluationRunCasesOp,
        evaluationRunEventsOp,
        evaluationRunEventsPageOp,
        evaluationMatrixGetOp,
        evaluationCompareRunsOp,
        evaluationCaseRunTraceOp,
        evaluationAnnotationsListOp,
        evaluationAnnotationCreateOp,
        evaluationBaselinesListOp,
        evaluationBaselineSetOp,
        evaluationGatePoliciesListOp,
        evaluationMonitorsListOp,
        evaluationMonitorObservationsOp,
        evaluationMonitorObservationCaseCreateOp,
        evaluationPairwiseJudgmentCreateOp,
        evaluationRubricsListOp,
        evaluationRubricCreateOp,
        evaluationRubricVersionsListOp,
        evaluationRubricVersionCreateOp,
    ];

    static override styles: CSSResultGroup = [
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
            flows-evaluation-page {
                flex: 1;
                min-width: 0;
                min-height: 0;
                height: 100%;
            }
            flows-home-page,
            flows-agent-skills-page {
                min-width: 0;
            }
            flows-agent-skills-page {
                flex: 1;
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
    private _editor: ControllerFor<'flows/editor'>;
    private _flows: ResourceController;
    private _companiesListSel: SelectController<readonly CompanyRecord[]>;
    private _companiesLoadingSel: SelectController<boolean>;
    private _flowsMql: MediaQueryList | null;
    private _onFlowsMobileMql: (() => void) | null;
    private _flowsMobile: boolean;

    constructor() {
        super();
        this._editor = this.useOp('flows/editor');
        this._flows = this.useResource('flows/flows');
        this._companiesListSel = this.select((s) => s.companies.list);
        this._companiesLoadingSel = this.select((s) => s.companies.loading);
        this._flowsMql = null;
        this._onFlowsMobileMql = null;
        this._flowsMobile =
            typeof window !== 'undefined' &&
            typeof window.matchMedia === 'function' &&
            window.matchMedia('(max-width: 767px)').matches;
    }

    override async connectedCallback(): Promise<void> {
        super.connectedCallback();
        if (typeof window === 'undefined') {
            return;
        }
        if (typeof window.matchMedia !== 'function') {
            return;
        }
        const media = window.matchMedia('(max-width: 767px)');
        this._flowsMql = media;
        this._onFlowsMobileMql = () => {
            const next = media.matches;
            if (next !== this._flowsMobile) {
                this._flowsMobile = next;
                this.requestUpdate();
            }
        };
        media.addEventListener('change', this._onFlowsMobileMql);
        const next = media.matches;
        if (next !== this._flowsMobile) {
            this._flowsMobile = next;
            this.requestUpdate();
        }
    }

    override disconnectedCallback(): void {
        const media = this._flowsMql;
        const onChange = this._onFlowsMobileMql;
        if (media !== null && onChange !== null) {
            media.removeEventListener('change', onChange);
        }
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (!this._bootstrapped) {
            return;
        }
        const auth = this._authSelect.value;
        applyCompanyHostRedirectIfNeeded(
            auth,
            companyListEntries(this._companiesListSel.value),
            this._companiesLoadingSel.value,
            { loadCompanies: () => this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null) },
        );
    }

    override getBaseUrl() {
        return '/flows';
    }

    override getRoutes() {
        return [];
    }

    override getServiceEffects() {
        return [createRouterEffect({ baseUrl: '/flows', routes: FLOWS_ROUTES })];
    }

    _flowsDesktopSidebarColumn() {
        if (this._flowsMobile) return html``;
        return html`<div class="sidebar"><flows-sidebar></flows-sidebar></div>`;
    }

    override renderRoute(routeKey: string, params: Record<string, string>) {
        switch (routeKey) {
            case 'platform_services':
                return html`
                    ${this._flowsDesktopSidebarColumn()}
                    <div class="main">
                        <platform-island padding=${this._flowsMobile ? 'none' : 'md'} ?safe-bottom=${this._flowsMobile}>
                            <platform-services-page></platform-services-page>
                        </platform-island>
                    </div>
                `;
            case 'flow_chat':
            case 'flow_chat_branch':
            case 'flow_chat_session':
            case 'flow_chat_branch_session':
                return html`
                    ${this._flowsDesktopSidebarColumn()}
                    <div class="main">
                        <platform-island
                            padding="none"
                            ?safe-bottom=${this._flowsMobile}
                            ?content-no-scroll=${true}
                        >
                            <flows-chat-page
                                .flowId=${params.flowId}
                                .branchId=${typeof params.branchId === 'string' && params.branchId.length > 0 ? params.branchId : 'base'}
                                .sessionId=${asString(params.sessionId)}
                            ></flows-chat-page>
                        </platform-island>
                    </div>
                `;
            case 'flow_editor':
            case 'flow_editor_branch':
                return html`
                    <flow-editor-page
                        .flowId=${params.flowId}
                        .branchId=${typeof params.branchId === 'string' && params.branchId.length > 0 ? params.branchId : 'base'}
                    ></flow-editor-page>
                `;
            case 'flow_evaluation':
            case 'flow_evaluation_branch':
                return html`
                    <flows-evaluation-page
                        .flowId=${params.flowId}
                        .branchId=${typeof params.branchId === 'string' && params.branchId.length > 0 ? params.branchId : 'default'}
                    ></flows-evaluation-page>
                `;
            case 'agent_skills':
                return html`
                    ${this._flowsDesktopSidebarColumn()}
                    <div class="main">
                        <platform-island
                            padding=${this._flowsMobile ? 'none' : 'md'}
                            ?safe-bottom=${this._flowsMobile}
                            ?content-no-scroll=${true}
                        >
                            <flows-agent-skills-page></flows-agent-skills-page>
                        </platform-island>
                    </div>
                `;
            case 'list':
            default:
                return html`
                    ${this._flowsDesktopSidebarColumn()}
                    <div class="main">
                        <platform-island
                            padding=${this._flowsMobile ? 'none' : 'md'}
                            ?safe-bottom=${this._flowsMobile}
                        >
                            <flows-home-page></flows-home-page>
                        </platform-island>
                    </div>
                `;
        }
    }

    override async getPlatformAssistantContextVariables() {
        return flattenLaraFlowsContext(this._buildLaraFlowsContext({
            assistant_branch_id: LARA_FLOWS_BRANCH_ID,
            request_kind: 'chat',
        }));
    }

    _buildLaraFlowsContext(options = {}) {
        const routerValue = this._routerSelect ? this._routerSelect.value : null;
        const routeParams = routerValue === null ? null : routerValue.params;
        const params = isPlainObject(routeParams) ? routeParams : {};
        return buildLaraFlowsContext(this._editor?.state, params, options);
    }

    override render(): TemplateResult {
        const shell = renderPlatformAppShell(this);
        if (shell !== null) return shell;
        if (!this._bootstrapped) {
            return html`
                <platform-empty-state class="loading-container" loading></platform-empty-state>
            `;
        }
        return super.render();
    }
}

customElements.define('flows-app', FlowsApp);
