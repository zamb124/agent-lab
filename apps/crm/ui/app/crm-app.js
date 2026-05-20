/**
 * CRMApp — корневой компонент сервиса CRM на event-driven канон.
 *
 * Маршрутизация — через core router.effect. CRM-сервис отдаёт SPA на путях
 * `/crm`, `/crm/<route>`, поэтому router-effect собирается с `baseUrl: '/crm'`.
 */

import { html, css } from 'lit';
import { PlatformApp } from '@platform/lib/base/PlatformApp.js';
import { createRouterEffect } from '@platform/lib/events/effects/router.effect.js';

import {
    namespacesResource,
    namespaceUpdateOp,
    namespaceEditabilityOp,
    namespaceCreateForm,
    namespaceEditForm,
    taskBoardStagesOp,
    taskBoardEditorStateOp,
} from '../events/resources/namespaces.resource.js';
import {
    namespaceIntegrationsListOp,
    namespaceIntegrationAuthorizeOp,
    namespaceIntegrationEntitiesSyncOp,
    namespaceIntegrationAutoSyncOp,
    namespaceIntegrationAutoNoteAiOp,
    namespaceIntegrationCustomFieldsSyncOp,
} from '../events/resources/namespace-integrations.resource.js';
import {
    templatesResource,
    templateUpdateOp,
    templateSchemaOptionsOp,
    templateTypeUpsertOp,
    templateTypeDeleteOp,
    templateTaskBoardEditorStateOp,
} from '../events/resources/templates.resource.js';
import {
    entityTypesResource,
    entityTypeUpdateOp,
    entityTypePublicFieldsOp,
} from '../events/resources/entity-types.resource.js';
import { relationshipTypesResource } from '../events/resources/relationship-types.resource.js';
import {
    entitiesResource,
    entityCardOp,
    entityUpdateOp,
    entitiesListResource,
    entityMergeOp,
    entityBulkDeleteOp,
    entityBulkUpdateOp,
    entityAggregateOp,
    entitySearchOp,
    entitiesLookupOp,
    entityCreateForm,
    entityEditForm,
} from '../events/resources/entities.resource.js';
import {
    notesListResource,
    noteLatestRangeOp,
    noteAnalysisDraftDiscardOp,
    noteAnalysisDraftRepairOp,
    noteAnalysisDraftSaveOp,
    noteAnalysisErrorDismissOp,
    noteAnalyzeStartOp,
    noteMarkdownFormatOp,
    noteVoiceInputOp,
    noteSearchOp,
    entityCardsBulkOp,
} from '../events/resources/notes.resource.js';
import {
    dailySummaryOp,
    periodSummaryOp,
} from '../events/resources/summaries.resource.js';
import {
    relationshipsResource,
    relationshipsListResource,
    relationshipShortestPathOp,
} from '../events/resources/relationships.resource.js';
import {
    tasksResource,
    taskGetOp,
    taskCreatedEntitiesOp,
    taskKnowledgeImportStartOp,
    taskDailySummaryStartOp,
    taskPeriodSummaryStartOp,
    taskReviewCompleteOp,
    taskCancelOp,
    taskRollbackOp,
    taskRetryOp,
} from '../events/resources/tasks.resource.js';
import {
    suggestsListOp,
    suggestResolveOp,
    suggestDismissOp,
} from '../events/resources/suggests.resource.js';
import {
    entityGrantsListOp,
    entityGrantCreateOp,
    namespaceGrantsListOp,
    namespaceGrantCreateOp,
    grantRevokeOp,
} from '../events/resources/grants.resource.js';
import { accessRequestsResource, accessRequestUpdateOp } from '../events/resources/access-requests.resource.js';
import { teamSearchFacets } from '../events/resources/team-search.resource.js';
import {
    overviewGraphOp,
    influenceGraphOp,
    relatedEntitiesOp,
    entityRelationshipsOp,
    shortestPathOp,
    timelineBoundsOp,
    personEntitySelfOp,
} from '../events/resources/graph.resource.js';
import { laraSummaryOp } from '../events/resources/workspace.resource.js';
import {
    attachmentsListOp,
    attachmentUploadOp,
    attachmentDeleteOp,
} from '../events/resources/attachments.resource.js';
import { fileUploadOp } from '../events/resources/files.resource.js';

import '../components/crm-sidebar.js';
import '../components/sheets/crm-workspace-picker-sheet.js';
import '@platform/lib/embed-chat/platform-lara-assistant.js';
import '../pages/settings-hub-page.js';
import '../pages/daily-notes-page.js';
import '../pages/entities-page.js';
import '../pages/graph-page.js';
import '../pages/tasks-page.js';
import '../pages/suggests-page.js';
import '../pages/templates-page.js';
import '../pages/namespace-tasks-page.js';
import '../pages/relationship-types-page.js';
import '../pages/note-page.js';
import '../pages/entity-detail-page.js';
import '../pages/entity-create-page.js';
import '../pages/access-requests-page.js';
import '../pages/spaces-page.js';
import '../pages/space-detail-page.js';
import '../pages/space-integrations-page.js';

import '../modals/namespace-modal.js';
import '../modals/share-modal.js';
import '../modals/access-request-modal.js';
import '../modals/ai-analysis-modal.js';
import '../modals/entity-merge-modal.js';
import '../modals/note-graph-modal.js';
import '../modals/entity-delete-modal.js';
import '../modals/knowledge-import-modal.js';
import '../modals/entity-type-create-mode-modal.js';
import '../modals/entity-type-preset-picker-modal.js';

import { graphUiSlice } from '../events/resources/graph-ui.resource.js';
import { graphViewSlice } from '../events/resources/graph-view.resource.js';
import { dailyNotesUiSlice } from '../events/resources/daily-notes-ui.resource.js';
import { createCrmPersistEffect } from '../events/crm-persist.effect.js';
import { createCrmGraphLegacyRoutesEffect } from '../events/crm-graph-legacy-routes.effect.js';
import { resolveVoiceHttpOrigin } from '@platform/lib/voice/voice-http-origin.js';
import { applyCompanyHostRedirectIfNeeded } from '@platform/lib/utils/company-host-guard.js';
import { getPlatformBus } from '@platform/lib/events/bus-singleton.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import { getPlatformNamespaceSidebarSelection } from '@platform/lib/utils/platform-namespace.js';
import { COMPANIES_EVENTS } from '@platform/lib/events/reducers/companies.js';

import '@platform/lib/components/layout/platform-island.js';

const CRM_ROUTES = [
    { key: 'notes',               path: '',                 titleKey: 'routes.notes' },
    { key: 'platform_services',   path: 'services',         parent: 'notes', titleKey: 'routes.platform_services' },
    { key: 'settings',            path: 'settings',         titleKey: 'routes.settings' },
    { key: 'notes',               path: 'notes',            titleKey: 'routes.notes' },
    { key: 'note',                path: 'notes/:itemId',    parent: 'notes', titleKey: 'routes.note' },
    { key: 'entities',            path: 'entities',         titleKey: 'routes.entities' },
    { key: 'entity_new',          path: 'entities/new',     parent: 'entities', titleKey: 'routes.entity_new' },
    { key: 'entity',              path: 'entities/:itemId', parent: 'entities', titleKey: 'routes.entity' },
    { key: 'graph',               path: 'graph',            titleKey: 'routes.graph' },
    { key: 'tasks',               path: 'tasks',            titleKey: 'routes.tasks' },
    { key: 'suggests',            path: 'suggests',         titleKey: 'routes.suggests' },
    { key: 'access_requests',     path: 'access-requests',  titleKey: 'routes.access_requests' },
    { key: 'spaces',              path: 'spaces',           parent: 'settings', titleKey: 'routes.spaces' },
    { key: 'space',               path: 'spaces/:itemId',   parent: 'spaces', titleKey: 'routes.space' },
    { key: 'space_integrations',  path: 'spaces/:itemId/integrations', parent: 'space', titleKey: 'routes.space_integrations' },
    { key: 'templates',           path: 'templates',        parent: 'settings', titleKey: 'routes.templates' },
    { key: 'namespace_imports',   path: 'namespace_imports', parent: 'settings', titleKey: 'routes.namespace_imports' },
    { key: 'relationship_types',  path: 'relationship_types', parent: 'settings', titleKey: 'routes.relationship_types' },
];

/**
 * Mobile bottom-nav (mobile shell 2026): 4 первичных вкладки сервиса + профиль (service-switcher).
 * Видна только на ≤767px. На fullscreen-маршрутах (нет таких в CRM сегодня) скрывается через bottomNavHideOnRoutes.
 */
const CRM_BOTTOM_NAV_ITEMS = [
    { key: 'notes',    routeKey: 'notes',    icon: 'note',         labelKey: 'bottom_nav.notes' },
    { key: 'tasks',    routeKey: 'tasks',    icon: 'check-square', labelKey: 'bottom_nav.tasks' },
    { key: 'graph',    routeKey: 'graph',    icon: 'share',        labelKey: 'bottom_nav.graph' },
    { key: 'entities', routeKey: 'entities', icon: 'box',          labelKey: 'bottom_nav.entities' },
    { key: 'profile',  sheet: 'platform.service_switcher', icon: 'user', labelKey: 'bottom_nav.profile' },
];

export class CRMApp extends PlatformApp {
    static defaultI18nNamespace = 'crm';
    static bottomNavItems = CRM_BOTTOM_NAV_ITEMS;
    static bottomNavHideOnRoutes = [];

    constructor() {
        super();
        this._companiesListSel = this.select((s) => s.companies.list);
        this._companiesLoadingSel = this.select((s) => s.companies.loading);
        this._laraActiveCompanySel = this.select((s) => s.auth.activeCompanyId);
        this._laraVoiceBaseUrl =
            typeof window !== 'undefined' && typeof window.location !== 'undefined'
                ? resolveVoiceHttpOrigin()
                : '';
        this._crmMql = null;
        this._onCrmMobileMql = null;
        this._crmMobile =
            typeof window !== 'undefined' &&
            typeof window.matchMedia === 'function' &&
            window.matchMedia('(max-width: 767px)').matches;
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return;
        }
        this._crmMql = window.matchMedia('(max-width: 767px)');
        this._onCrmMobileMql = () => {
            const next = this._crmMql.matches;
            if (next !== this._crmMobile) {
                this._crmMobile = next;
                this.requestUpdate();
            }
        };
        this._crmMql.addEventListener('change', this._onCrmMobileMql);
        const next = this._crmMql.matches;
        if (next !== this._crmMobile) {
            this._crmMobile = next;
            this.requestUpdate();
        }
    }

    disconnectedCallback() {
        if (this._crmMql && this._onCrmMobileMql) {
            this._crmMql.removeEventListener('change', this._onCrmMobileMql);
        }
        super.disconnectedCallback();
    }

    static factories = [
        namespacesResource,
        namespaceUpdateOp,
        namespaceEditabilityOp,
        namespaceCreateForm,
        namespaceEditForm,
        taskBoardStagesOp,
        taskBoardEditorStateOp,
        namespaceIntegrationsListOp,
        namespaceIntegrationAuthorizeOp,
        namespaceIntegrationEntitiesSyncOp,
        namespaceIntegrationAutoSyncOp,
        namespaceIntegrationAutoNoteAiOp,
        namespaceIntegrationCustomFieldsSyncOp,
        templatesResource,
        templateUpdateOp,
        templateSchemaOptionsOp,
        templateTypeUpsertOp,
        templateTypeDeleteOp,
        templateTaskBoardEditorStateOp,
        entityTypesResource,
        entityTypeUpdateOp,
        entityTypePublicFieldsOp,
        relationshipTypesResource,
        entitiesResource,
        entityCardOp,
        entityUpdateOp,
        entitiesListResource,
        entityMergeOp,
        entityBulkDeleteOp,
        entityBulkUpdateOp,
        entityAggregateOp,
        entitySearchOp,
        entitiesLookupOp,
        entityCreateForm,
        entityEditForm,
        notesListResource,
        noteLatestRangeOp,
        noteAnalysisDraftSaveOp,
        noteAnalysisDraftDiscardOp,
        noteAnalysisErrorDismissOp,
        noteAnalysisDraftRepairOp,
        noteAnalyzeStartOp,
        noteMarkdownFormatOp,
        noteVoiceInputOp,
        noteSearchOp,
        entityCardsBulkOp,
        dailySummaryOp,
        periodSummaryOp,
        relationshipsResource,
        relationshipsListResource,
        relationshipShortestPathOp,
        tasksResource,
        taskGetOp,
        taskCreatedEntitiesOp,
        taskKnowledgeImportStartOp,
        taskDailySummaryStartOp,
        taskPeriodSummaryStartOp,
        taskReviewCompleteOp,
        taskCancelOp,
        taskRollbackOp,
        taskRetryOp,
        suggestsListOp,
        suggestResolveOp,
        suggestDismissOp,
        entityGrantsListOp,
        entityGrantCreateOp,
        namespaceGrantsListOp,
        namespaceGrantCreateOp,
        grantRevokeOp,
        accessRequestsResource,
        accessRequestUpdateOp,
        teamSearchFacets,
        overviewGraphOp,
        influenceGraphOp,
        relatedEntitiesOp,
        entityRelationshipsOp,
        shortestPathOp,
        timelineBoundsOp,
        personEntitySelfOp,
        laraSummaryOp,
        attachmentsListOp,
        attachmentUploadOp,
        attachmentDeleteOp,
        fileUploadOp,
        graphUiSlice,
        graphViewSlice,
        dailyNotesUiSlice,
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
            @media (max-width: 767px) {
                .main { padding: 0; }
                .sidebar { position: absolute; width: 0; height: 0; overflow: visible; }
            }
        `,
    ];

    getBaseUrl() { return '/crm'; }

    getRoutes() { return []; }

    getServiceEffects() {
        return [
            createRouterEffect({ baseUrl: '/crm', routes: CRM_ROUTES }),
            createCrmGraphLegacyRoutesEffect(),
            createCrmPersistEffect(),
        ];
    }

    updated(changed) {
        super.updated(changed);
        const auth = this._authSelect.value;
        applyCompanyHostRedirectIfNeeded(
            auth,
            this._companiesListSel.value,
            this._companiesLoadingSel.value,
            { loadCompanies: () => this.dispatch(COMPANIES_EVENTS.LOAD_REQUESTED, null) },
        );
        this._hydrateCrmNamespaceSelection(auth);
    }

    /**
     * Сайдбар читает выбор из localStorage сразу; state.ui.namespace заполняется здесь.
     * Страницы с **`CRMNamespacePage`** берут фильтр через **`selectCrmApiNamespace`** (тот же
     * тот же источник), чтобы первый запрос после F5 совпадал с сайдбаром.
     */
    _hydrateCrmNamespaceSelection(auth) {
        if (!auth || auth.status !== 'authenticated' || !auth.user) {
            return;
        }
        const cid = auth.user.company_id;
        if (typeof cid !== 'string' || cid.trim().length === 0) {
            return;
        }
        const trimmed = cid.trim();
        const bus = getPlatformBus();
        const map = bus.getState().ui.namespace.selectionByCompany;
        if (Object.prototype.hasOwnProperty.call(map, trimmed)) {
            return;
        }
        const selection = getPlatformNamespaceSidebarSelection(trimmed);
        this.dispatch(
            CoreEvents.UI_NAMESPACE_CHANGED,
            { company_id: trimmed, selection },
            { source: 'local' },
        );
    }

    renderRoute(routeKey, params) {
        let content;
        switch (routeKey) {
            case 'platform_services':
                content = html`<platform-services-page></platform-services-page>`;
                break;
            case 'settings':            content = html`<crm-settings-hub-page></crm-settings-hub-page>`; break;
            case 'notes':               content = html`<crm-daily-notes-page></crm-daily-notes-page>`; break;
            case 'note':                content = html`<crm-note-page .noteId=${params.itemId}></crm-note-page>`; break;
            case 'entities':            content = html`<crm-entities-page></crm-entities-page>`; break;
            case 'entity_new':         content = html`<crm-entity-create-page></crm-entity-create-page>`; break;
            case 'entity':              content = html`<crm-entity-detail-page .itemId=${params.itemId}></crm-entity-detail-page>`; break;
            case 'graph':               content = html`<crm-graph-page></crm-graph-page>`; break;
            case 'tasks':               content = html`<crm-tasks-page></crm-tasks-page>`; break;
            case 'suggests':            content = html`<crm-suggests-page></crm-suggests-page>`; break;
            case 'access_requests':     content = html`<crm-access-requests-page></crm-access-requests-page>`; break;
            case 'spaces':              content = html`<crm-spaces-page></crm-spaces-page>`; break;
            case 'space':               content = html`<crm-space-detail-page .itemId=${params.itemId}></crm-space-detail-page>`; break;
            case 'space_integrations':  content = html`<crm-space-integrations-page .itemId=${params.itemId}></crm-space-integrations-page>`; break;
            case 'templates':           content = html`<crm-templates-page></crm-templates-page>`; break;
            case 'namespace_imports':   content = html`<crm-namespace-tasks-page></crm-namespace-tasks-page>`; break;
            case 'relationship_types':  content = html`<crm-relationship-types-page></crm-relationship-types-page>`; break;
            default:                    content = html`<crm-daily-notes-page></crm-daily-notes-page>`; break;
        }
        const mobileIslandFullBleed = this._crmMobile;
        const companyRaw = this._laraActiveCompanySel.value;
        const companyId = typeof companyRaw === 'string' && companyRaw.trim() !== '' ? companyRaw.trim() : '';
        const voiceBase =
            typeof this._laraVoiceBaseUrl === 'string' ? this._laraVoiceBaseUrl.trim() : '';
        const laraDuplex = companyId !== '' && voiceBase !== '';
        const laraShowLauncher = !this._crmMobile;
        return html`
            <div class="sidebar"><crm-sidebar></crm-sidebar></div>
            <div class="main">
                <platform-island
                    padding=${mobileIslandFullBleed ? 'none' : 'md'}
                    ?safe-bottom=${mobileIslandFullBleed}
                    ?content-no-scroll=${routeKey === 'entities' || routeKey === 'entity'}
                >${content}</platform-island>
            </div>
            <platform-lara-assistant
                toggle-event-name="crm-lara-open"
                event-namespace="assistant"
                flow-id="lara"
                skill-id="crm"
                .flowsBaseUrl=${'/flows'}
                ?use-credentials=${true}
                .showLauncher=${laraShowLauncher}
                .assistantTitle=${'Lara'}
                ?voice-enabled=${laraDuplex}
                voice-base-url=${voiceBase}
                company-id=${companyId}
            ></platform-lara-assistant>
        `;
    }
}

customElements.define('crm-app', CRMApp);
