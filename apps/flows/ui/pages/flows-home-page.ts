/**
 * FlowsHomePage — рабочая главная страница сервиса flows.
 */

import type { AuthUser } from '@platform/lib/events/reducers/auth.js';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController, ResourceController } from '@platform/lib/base/use-resource.js';
import { html, css, nothing } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { buildServiceEntryUrl } from '@platform/lib/utils/build-service-entry-url.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/platform-empty-state.js';
import '@platform/lib/components/platform-metric-card.js';
import { marketingHeroStyles } from '@platform/lib/styles/shared/marketing-section.styles.js';
import '../components/flows-catalog-list.js';
import { asArray, asString, isPlainObject } from '../_helpers/flows-resolvers.js';
import { AGENT_SKILL_ICON } from '../_helpers/agent-skill-map.js';
import { flowSessionRoute } from '../_helpers/flow-session-route.js';
import type {CSSResultGroup, PropertyDeclarations, TemplateResult} from 'lit';

const QUICK_ACTIONS = Object.freeze([
    Object.freeze({
        id: 'store',
        icon: 'box',
        tone: 'success',
        titleKey: 'flows_home.quick_store_title',
        descKey: 'flows_home.quick_store_desc',
    }),
    Object.freeze({
        id: 'sessions',
        icon: 'chat',
        tone: 'info',
        titleKey: 'flows_home.quick_sessions_title',
        descKey: 'flows_home.quick_sessions_desc',
    }),
    Object.freeze({
        id: 'operator',
        icon: 'inbox',
        tone: 'warning',
        titleKey: 'flows_home.quick_operator_title',
        descKey: 'flows_home.quick_operator_desc',
    }),
]);

const CONNECT_ACTIONS = Object.freeze([
    Object.freeze({
        id: 'skills',
        icon: AGENT_SKILL_ICON,
        tone: 'accent',
        titleKey: 'flows_home.connect_skills_title',
        descKey: 'flows_home.connect_skills_desc',
    }),
    Object.freeze({
        id: 'mcp',
        icon: 'mcp',
        tone: 'info',
        titleKey: 'flows_home.connect_mcp_title',
        descKey: 'flows_home.connect_mcp_desc',
    }),
    Object.freeze({
        id: 'variables',
        icon: 'key',
        tone: 'warning',
        titleKey: 'flows_home.connect_variables_title',
        descKey: 'flows_home.connect_variables_desc',
    }),
    Object.freeze({
        id: 'integrations',
        icon: 'link',
        tone: 'success',
        titleKey: 'flows_home.connect_integrations_title',
        descKey: 'flows_home.connect_integrations_desc',
    }),
    Object.freeze({
        id: 'resources',
        icon: 'database',
        tone: 'accent',
        titleKey: 'flows_home.connect_resources_title',
        descKey: 'flows_home.connect_resources_desc',
    }),
]);

const CAPABILITY_GROUPS = Object.freeze([
    Object.freeze({
        id: 'build',
        icon: 'workflow',
        titleKey: 'flows_home.cap_build_title',
        textKey: 'flows_home.cap_build_text',
        chips: Object.freeze(['llm_node', 'code', 'flow', 'resource']),
    }),
    Object.freeze({
        id: 'connect',
        icon: 'globe',
        titleKey: 'flows_home.cap_connect_title',
        textKey: 'flows_home.cap_connect_text',
        chips: Object.freeze(['external_api', 'mcp', 'remote_flow', 'channel']),
    }),
    Object.freeze({
        id: 'operate',
        icon: 'users',
        titleKey: 'flows_home.cap_operate_title',
        textKey: 'flows_home.cap_operate_text',
        chips: Object.freeze(['hitl_node', 'sessions', 'traces', 'logs']),
    }),
    Object.freeze({
        id: 'publish',
        icon: 'send',
        titleKey: 'flows_home.cap_publish_title',
        textKey: 'flows_home.cap_publish_text',
        chips: Object.freeze(['a2a', 'preview', 'voice', 'triggers']),
    }),
]);

interface FlowHomeStats {
    flows: readonly unknown[];
    flowCount: number;
    branchCount: number;
    nodeCount: number;
    activeSessionCount: number;
    bundleUpdateCount: number;
}

interface FlowsHomeAuth {
    user: AuthUser | null;
    companyId: string;
}

function resultItems(result: unknown): unknown[] {
    if (Array.isArray(result)) {
        return result;
    }
    if (isPlainObject(result) && Array.isArray(result.items)) {
        return result.items;
    }
    return [];
}

function countBranches(flows: readonly unknown[]) {
    let total = 0;
    for (const flow of flows) {
        total += 1;
        if (isPlainObject(flow) && isPlainObject(flow.branches)) {
            total += Object.keys(flow.branches).length;
        }
    }
    return total;
}

function countFlowNodes(flows: readonly unknown[]) {
    let total = 0;
    for (const flow of flows) {
        if (!isPlainObject(flow)) {
            continue;
        }
        if (!isPlainObject(flow.nodes)) {
            continue;
        }
        total += Object.keys(flow.nodes).length;
    }
    return total;
}

function flowRecord(flow: unknown): Record<string, unknown> {
    if (!isPlainObject(flow)) {
        throw new Error('flows-home-page: flow required');
    }
    return flow;
}

function flowTitle(flow: unknown) {
    const record = flowRecord(flow);
    if (typeof record.name === 'string' && record.name.length > 0) {
        return record.name;
    }
    if (typeof record.flow_id === 'string' && record.flow_id.length > 0) {
        return record.flow_id;
    }
    throw new Error('flows-home-page: flow name required');
}

function flowDescription(flow: unknown) {
    const record = flowRecord(flow);
    return typeof record.description === 'string' ? record.description : '';
}

function resourceTypeCount(items: readonly unknown[], type: string) {
    let total = 0;
    for (const item of items) {
        if (isPlainObject(item) && item.type === type) {
            total += 1;
        }
    }
    return total;
}

function activeSessionCount(items: readonly unknown[]) {
    let total = 0;
    for (const item of items) {
        if (!isPlainObject(item)) {
            continue;
        }
        if (typeof item.status !== 'string') {
            continue;
        }
        if (['active', 'processing', 'waiting_input'].includes(item.status)) {
            total += 1;
        }
    }
    return total;
}

export class FlowsHomePage extends PlatformPage {
    static i18nNamespace = 'flows';

    static override properties: PropertyDeclarations = {
        mobileCatalogOpen: { type: Boolean, reflect: true, attribute: 'mobile-catalog-open' },
        _isMobile: { state: true },
        _toolsCount: { state: true },
    }
    declare mobileCatalogOpen: boolean;
    declare _isMobile: boolean;
    declare _toolsCount: number;
;

    static override styles: CSSResultGroup = [
        PlatformPage.styles,
        marketingHeroStyles,
        css`
            :host {
                display: block;
                min-width: 0;
                color: var(--text-primary);
            }
            :host([mobile-catalog-open]) {
                display: flex;
                flex: 1;
                flex-direction: column;
                height: 100%;
                min-height: 0;
            }
            .home-scroll {
                display: flex;
                flex-direction: column;
                gap: var(--space-5);
                min-width: 0;
                box-sizing: border-box;
            }
            .mobile-catalog-shell {
                display: flex;
                flex: 1;
                min-width: 0;
                min-height: 0;
                flex-direction: column;
            }
            flows-catalog-list[mode='page'] {
                flex: 1;
                min-width: 0;
                min-height: 0;
            }
            page-header {
                flex-shrink: 0;
            }
            .header-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
            }
            .hero-download-link {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-height: 32px;
                padding: 6px 14px;
                border-radius: var(--btn-radius, 22px);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: var(--leading-tight);
                text-decoration: none;
                transition: var(--motion-transition-interactive);
            }
            .hero-download-link:hover {
                color: var(--text-primary);
                background: var(--glass-tint-subtle);
            }
            .hero-download-link:focus-visible {
                outline: none;
                box-shadow: var(--focus-ring);
            }
            .hero-band {
                display: grid;
                grid-template-columns: minmax(0, 1.12fr) minmax(320px, 0.88fr);
                gap: var(--space-6);
                align-items: stretch;
                padding: var(--space-6);
                border-radius: var(--radius-md);
                background:
                    linear-gradient(135deg, color-mix(in oklab, var(--accent) 14%, transparent), transparent 48%),
                    var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                overflow: hidden;
            }
            .hero-copy {
                display: flex;
                flex-direction: column;
                justify-content: center;
                gap: var(--space-4);
                min-width: 0;
            }
            .hero-eyebrow {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                width: fit-content;
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                text-transform: uppercase;
                letter-spacing: 0.08em;
            }
            .hero-logo {
                width: 24px;
                height: 24px;
            }
            h1 {
                margin: 0;
                font-size: var(--text-4xl);
                line-height: var(--leading-tight);
                font-weight: var(--font-bold);
                letter-spacing: 0;
            }
            .hero-subtitle {
                max-width: 680px;
                margin: 0;
                color: var(--text-secondary);
                font-size: var(--text-lg);
                line-height: var(--leading-relaxed);
            }
            .hero-actions {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
            }
            .hero-map {
                position: relative;
                min-height: 260px;
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                grid-template-rows: repeat(3, minmax(0, 1fr));
                gap: var(--space-3);
            }
            .map-line {
                position: absolute;
                inset: 14%;
                border: 1px solid var(--border-subtle);
                border-radius: var(--radius-md);
                transform: rotate(-6deg);
            }
            .map-node {
                position: relative;
                z-index: 1;
                display: flex;
                flex-direction: column;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-3);
                min-height: 82px;
                border-radius: var(--radius-md);
                background: var(--glass-solid-medium);
                border: 1px solid var(--border-subtle);
                box-sizing: border-box;
            }
            .map-node:nth-child(2) { grid-column: 1; grid-row: 1; }
            .map-node:nth-child(3) { grid-column: 2; grid-row: 2; }
            .map-node:nth-child(4) { grid-column: 3; grid-row: 1; }
            .map-node:nth-child(5) { grid-column: 3; grid-row: 3; }
            .map-node:nth-child(6) { grid-column: 1; grid-row: 3; }
            .map-node-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .map-node-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-primary);
            }
            .map-node-kind {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .metric-grid,
            .action-grid,
            .connect-grid,
            .capability-grid {
                display: grid;
                gap: var(--space-3);
            }
            .metric-grid {
                grid-template-columns: repeat(5, minmax(0, 1fr));
            }
            .action-grid {
                grid-template-columns: repeat(4, minmax(0, 1fr));
            }
            .connect-grid,
            .capability-grid {
                grid-template-columns: repeat(4, minmax(0, 1fr));
            }
            .metric-shell {
                min-height: 112px;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .metric-shell .metric-caption {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: var(--leading-normal);
                padding: 0 var(--space-1);
            }
            .glass-card,
            .action-card,
            .connect-card,
            .capability-card,
            .flow-card {
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                box-sizing: border-box;
            }
            .action-card,
                display: flex;
                align-items: flex-end;
                justify-content: space-between;
                gap: var(--space-3);
            }
            .section-title {
                margin: 0;
                font-size: var(--text-xl);
                line-height: var(--leading-tight);
                font-weight: var(--font-semibold);
            }
            .section-title-wrap {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                min-width: 0;
            }
            .section-subtitle {
                margin: var(--space-1) 0 0;
                color: var(--text-secondary);
                font-size: var(--text-sm);
            }
            .flow-grid {
                display: grid;
                grid-template-columns: repeat(3, minmax(0, 1fr));
                gap: var(--space-3);
            }
            .flow-card {
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }
            .flow-media {
                aspect-ratio: 16 / 9;
                flex-shrink: 0;
                width: 100%;
                display: flex;
                align-items: center;
                justify-content: center;
                background: var(--glass-solid-medium);
                color: var(--accent);
                border-bottom: 1px solid var(--border-subtle);
                overflow: hidden;
            }
            .flow-media img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }
            .flow-body {
                flex: 1;
                min-height: 0;
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
                padding: var(--space-3);
            }
            .flow-title {
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .flow-desc {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: var(--leading-normal);
                display: -webkit-box;
                -webkit-line-clamp: 2;
                -webkit-box-orient: vertical;
                overflow: hidden;
                min-height: calc(var(--text-sm) * 2.8);
            }
            .flow-meta {
                margin-top: auto;
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            .flow-meta > span:first-child {
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .flow-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }
            .action-card,
            .connect-card,
            .capability-card {
                min-height: 156px;
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
                padding: var(--space-4);
                text-align: left;
            }
            .card-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .card-head-end {
                display: inline-flex;
                align-items: center;
                gap: var(--space-1);
                margin-left: auto;
            }
            .tone-icon {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                color: var(--platform-btn-primary-text);
            }
            .tone-accent { background: var(--accent); }
            .tone-success { background: var(--success); }
            .tone-info { background: var(--info); }
            .tone-warning { background: var(--warning); }
            .card-title {
                font-weight: var(--font-semibold);
                color: var(--text-primary);
                line-height: var(--leading-tight);
            }
            .card-desc {
                color: var(--text-secondary);
                font-size: var(--text-sm);
                line-height: var(--leading-normal);
            }
            .capability-chips {
                display: flex;
                flex-wrap: wrap;
                gap: var(--space-1);
                margin-top: auto;
            }
            .chip {
                display: inline-flex;
                align-items: center;
                min-height: 24px;
                padding: 0 var(--space-2);
                border-radius: var(--radius-md);
                color: var(--text-secondary);
                background: var(--glass-solid-medium);
                font-size: var(--text-xs);
            }
            .activity-layout {
                display: grid;
                grid-template-columns: minmax(0, 1fr) minmax(280px, 0.42fr);
                gap: var(--space-3);
            }
            .session-list,
            .readiness-list {
                display: flex;
                flex-direction: column;
                gap: var(--space-2);
            }
            .session-row,
            .readiness-row {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-3);
                min-height: 54px;
                padding: var(--space-3);
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
            }
            .readiness-row-link {
                cursor: pointer;
                transition: border-color var(--transition-fast), background var(--transition-fast);
            }
            .readiness-row-link:hover {
                border-color: var(--border-strong);
                background: var(--glass-solid);
            }
            .row-main {
                min-width: 0;
                display: flex;
                align-items: center;
                gap: var(--space-3);
            }
            .row-copy {
                min-width: 0;
            }
            .row-title {
                color: var(--text-primary);
                font-weight: var(--font-medium);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            .row-subtitle {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
            platform-empty-state { min-height: 120px; }
            @media (max-width: 1200px) {
                .metric-grid,
                .action-grid,
                .connect-grid,
                .capability-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
                .flow-grid {
                    grid-template-columns: repeat(2, minmax(0, 1fr));
                }
                .hero-band,
                .activity-layout {
                    grid-template-columns: 1fr;
                }
            }
            @media (max-width: 767px) {
                :host([mobile-catalog-open]) {
                    overflow: hidden;
                }
                .home-scroll {
                    padding: var(--space-3);
                    padding-bottom: max(var(--space-6), env(safe-area-inset-bottom, 0px));
                }
                .hero-band {
                    padding: var(--space-4);
                    gap: var(--space-4);
                }
                h1 {
                    font-size: var(--text-3xl);
                }
                .hero-subtitle {
                    font-size: var(--text-base);
                }
                .hero-map {
                    min-height: 220px;
                }
                .metric-grid,
                .action-grid,
                .connect-grid,
                .capability-grid,
                .flow-grid {
                    grid-template-columns: 1fr;
                }
            }
        `,
    ];
    private _flows: ResourceController;
    private _sessions: ResourceController;
    private _resources: ResourceController;
    private _mcpServers: ResourceController;
    private _agentSkills: ResourceController;
    private _variables: ResourceController;
    private _tools: ResourceController;
    private _bundles: OpController;
    private _integrations: OpController;
    private _workItemCounts: OpController;
    private _authSel: SelectController<FlowsHomeAuth>;
    private _localeSel: SelectController<string>;
    private _flowsHomeMql: MediaQueryList | null;
    private _onFlowsHomeMql: (() => void) | null;

    constructor() {
        super();
        this.mobileCatalogOpen = false;
        this._isMobile = false;
        this._flowsHomeMql = null;
        this._onFlowsHomeMql = null;
        this._flows = this.useResource('flows/flows', { autoload: true });
        this._sessions = this.useResource('flows/sessions');
        this._resources = this.useResource('flows/resources');
        this._mcpServers = this.useResource('flows/mcp_servers');
        this._agentSkills = this.useResource('flows/agent_skills');
        this._variables = this.useResource('secrets/variables');
        this._tools = this.useResource('flows/tools', { autoload: false });
        this._toolsCount = 0;
        this._bundles = this.useOp('flows/flow_store_bundles');
        this._integrations = this.useOp('flows/integrations_list');
        this._workItemCounts = this.useOp('worktracker/work_item_counts');
        this._authSel = this.select((state): FlowsHomeAuth => ({
            user: state.auth.user,
            companyId: state.auth.activeCompanyId === null ? '' : state.auth.activeCompanyId,
        }));
        this._localeSel = this.select((state) => {
            if (state.i18n.locale.length === 0) {
                throw new Error('flows-home-page: i18n.locale is required');
            }
            return state.i18n.locale;
        });
        if (typeof window !== 'undefined') {
            if (typeof window.matchMedia === 'function') {
                this._isMobile = window.matchMedia('(max-width: 767px)').matches;
            }
        }
    }

    override connectedCallback(): void {
        super.connectedCallback();
        void this._sessions.load({ limit: 8, offset: 0 });
        void this._resources.load({ limit: 200, offset: 0 });
        void this._mcpServers.load();
        void this._agentSkills.load({ limit: 200, offset: 0 });
        void this._variables.load({ limit: 200, offset: 0 });
        void this._loadToolsCount();
        void this._bundles.run({});
        void this._integrations.run({});
        void this._workItemCounts.run({});
        this._installMobileModeListener();
    }

    override disconnectedCallback(): void {
        if (this._flowsHomeMql !== null) {
            if (this._onFlowsHomeMql !== null) {
                this._flowsHomeMql.removeEventListener('change', this._onFlowsHomeMql);
            }
        }
        this._flowsHomeMql = null;
        this._onFlowsHomeMql = null;
        super.disconnectedCallback();
    }

    async _loadToolsCount() {
        const ctl = this._tools;
        const okType = ctl.resource.events.LIST_LOADED;
        const failType = ctl.resource.events.LIST_FAILED;
        await new Promise<void>((resolve) => {
            let unsubOk: (() => void) | null = null;
            let unsubFail: (() => void) | null = null;
            const cleanup = () => {
                if (typeof unsubOk === 'function') {
                    unsubOk();
                }
                if (typeof unsubFail === 'function') {
                    unsubFail();
                }
            };
            unsubOk = this.bus.subscribeType(okType, (event) => {
                cleanup();
                if (!isPlainObject(event.payload) || typeof event.payload.total !== 'number' || event.payload.total < 0) {
                    throw new Error('flows-home-page: tools total required');
                }
                this._toolsCount = event.payload.total;
                resolve();
            });
            unsubFail = this.bus.subscribeType(failType, () => {
                cleanup();
                this._toolsCount = 0;
                resolve();
            });
            ctl.load({ limit: 1, offset: 0 });
        });
    }

    _installMobileModeListener() {
        if (this._flowsHomeMql !== null) {
            return;
        }
        if (typeof window === 'undefined') {
            return;
        }
        if (typeof window.matchMedia !== 'function') {
            return;
        }
        this._flowsHomeMql = window.matchMedia('(max-width: 767px)');
        this._onFlowsHomeMql = () => this._syncMobileMode();
        this._flowsHomeMql.addEventListener('change', this._onFlowsHomeMql);
        this._syncMobileMode();
    }

    _syncMobileMode() {
        if (this._flowsHomeMql === null) {
            return;
        }
        const next = this._flowsHomeMql.matches;
        if (next !== this._isMobile) {
            this._isMobile = next;
        }
        if (next) {
            return;
        }
        if (this.mobileCatalogOpen) {
            this.mobileCatalogOpen = false;
        }
    }

    _openMobileCatalog() {
        if (this._isMobile !== true) {
            return;
        }
        this.mobileCatalogOpen = true;
    }

    _closeMobileCatalog() {
        this.mobileCatalogOpen = false;
    }

    _openQuickAction(id: string) {
        if (id === 'store') {
            this.openModal('flows.flow_create', {});
            return;
        }
        if (id === 'sessions') {
            this.openModal('flows.sessions', {});
            return;
        }
        if (id === 'operator') {
            this._openOperatorInbox();
            return;
        }
        throw new Error(`flows-home-page: unknown quick action "${id}"`);
    }

    _worktrackerInboxHref() {
        return buildServiceEntryUrl('worktracker');
    }

    _openOperatorInbox() {
        window.location.assign(this._worktrackerInboxHref());
    }

    _openConnectAction(id: string) {
        if (id === 'skills') {
            this.navigate('agent_skills');
            return;
        }
        if (id === 'mcp') {
            this.openModal('flows.mcp_servers', {});
            return;
        }
        if (id === 'variables') {
            this.openModal('flows.variables', { scope: 'company' });
            return;
        }
        if (id === 'integrations') {
            this.openModal('flows.integrations', {});
            return;
        }
        if (id === 'resources') {
            return;
        }
        throw new Error(`flows-home-page: unknown connect action "${id}"`);
    }

    _openFlowChat(flowId: string) {
        if (typeof flowId !== 'string') {
            return;
        }
        if (flowId.length === 0) {
            return;
        }
        this.navigate('flow_chat', { flowId });
    }

    _openFlowEditor(flowId: string) {
        if (typeof flowId !== 'string') {
            return;
        }
        if (flowId.length === 0) {
            return;
        }
        this.navigate('flow_editor', { flowId });
    }

    _openSession(session: unknown) {
        if (!isPlainObject(session)) {
            return;
        }
        const route = flowSessionRoute(session);
        if (route === null) {
            return;
        }
        const params: Record<string, string> = {};
        for (const [key, value] of Object.entries(route.params)) {
            if (typeof value !== 'string') {
                throw new Error('flows-home-page: session route param must be a string');
            }
            params[key] = value;
        }
        this.navigate(route.routeKey, params);
    }

    _formatDateTime(value: unknown) {
        if (typeof value !== 'string') {
            return this.t('flows_home.value_empty');
        }
        if (value.length === 0) {
            return this.t('flows_home.value_empty');
        }
        const locale = this._localeSel.value;
        if (locale !== 'ru' && locale !== 'en') {
            return this.t('flows_home.value_empty');
        }
        return formatPlatformDateTime(value, locale);
    }

    _flowStats(): FlowHomeStats {
        const flows: unknown[] = asArray(this._flows.items).filter((flow) => isPlainObject(flow) && flow.hidden !== true);
        const sessions: unknown[] = asArray(this._sessions.items);
        return {
            flows,
            flowCount: flows.length,
            branchCount: countBranches(flows),
            nodeCount: countFlowNodes(flows),
            activeSessionCount: activeSessionCount(sessions),
            bundleUpdateCount: flows.filter((flow) => isPlainObject(flow) && flow.has_bundle_update === true).length,
        };
    }

    _renderHeaderActions() {
        return html`
            <div class="header-actions" slot="actions">
                ${this._isMobile
                    ? html`
                        <platform-button
                            variant="ghost"
                            icon-only
                            density="dense"
                            aria-label=${this.t('flows_home.mobile_open_catalog')}
                            @click=${() => this._openMobileCatalog()}
                        >
                            <platform-icon name="list" size="16"></platform-icon>
                        </platform-button>
                    `
                    : ''}
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    aria-label=${this.t('flows_home.header_sessions')}
                    @click=${() => this.openModal('flows.sessions', {})}
                >
                    <platform-icon name="chat" size="16"></platform-icon>
                </platform-button>
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    aria-label=${this.t('flows_home.header_operator')}
                    @click=${() => this._openOperatorInbox()}
                >
                    <platform-icon name="inbox" size="16"></platform-icon>
                </platform-button>
                <platform-help-hint
                    .label=${this.t('flows_home.header_help_label')}
                    .summary=${this.t('flows_home.header_help_summary')}
                    .details=${this.t('flows_home.header_help_details')}
                    .docHref=${'/documentation/scenarios/flows/flows-home-overview/'}
                    .docLabel=${this.t('help_hints.open_scenario')}
                ></platform-help-hint>
            </div>
        `;
    }

    _renderMobileCatalog() {
        return html`
            <page-header title=${this.t('flows_home.mobile_catalog_title')}>
                <platform-button
                    slot="leading"
                    variant="ghost"
                    icon-only
                    density="dense"
                    title=${this.t('flows_home.mobile_back_home')}
                    aria-label=${this.t('flows_home.mobile_back_home')}
                    @click=${() => this._closeMobileCatalog()}
                >
                    <platform-icon name="chevron-left" size="20"></platform-icon>
                </platform-button>
            </page-header>
            <div class="mobile-catalog-shell">
                <flows-catalog-list
                    mode="page"
                    @flows-catalog-dismiss-mobile=${() => this._closeMobileCatalog()}
                ></flows-catalog-list>
            </div>
        `;
    }

    _renderHero() {
        return html`
            <section class="hero-band">
                <div class="hero-copy">
                    <div class="hero-eyebrow">
                        <img class="hero-logo" src="/static/core/assets/service_logos/agents_logo.svg" alt="" aria-hidden="true" />
                        <span>${this.t('flows_home.eyebrow')}</span>
                        <platform-help-hint
                            .label=${this.t('flows_home.hero_help_label')}
                            .summary=${this.t('flows_home.hero_help_summary')}
                            .details=${this.t('flows_home.hero_help_details')}
                            .docHref=${'/documentation/scenarios/flows/flows-home-overview/'}
                            .docLabel=${this.t('help_hints.open_scenario')}
                        ></platform-help-hint>
                    </div>
                    <h1>${this.t('flows_home.title')}</h1>
                    <p class="hero-subtitle">${this.t('flows_home.subtitle')}</p>
                    <div class="hero-actions">
                        <platform-button variant="primary" density="compact" @click=${() => this.openModal('flows.flow_create', {})}>
                            <platform-icon name="plus" size="16"></platform-icon>
                            <span>${this.t('flows_home.hero_create')}</span>
                        </platform-button>
                        <platform-button variant="ghost" density="compact" @click=${() => this.openModal('flows.sessions', {})}>
                            <platform-icon name="chat" size="16"></platform-icon>
                            <span>${this.t('flows_home.hero_sessions')}</span>
                        </platform-button>
                        <platform-button variant="ghost" density="compact" @click=${() => this._openOperatorInbox()}>
                            <platform-icon name="inbox" size="16"></platform-icon>
                            <span>${this.t('flows_home.hero_operator')}</span>
                        </platform-button>
                        <platform-button variant="ghost" density="compact" @click=${() => this.openModal('flows.mcp_servers', {})}>
                            <platform-icon name="mcp" size="16"></platform-icon>
                            <span>${this.t('flows_home.hero_mcp')}</span>
                        </platform-button>
                    </div>
                </div>
                <div class="hero-map" aria-hidden="true">
                    <div class="map-line"></div>
                    ${this._renderMapNode('llm_node', 'LLM', 'ReAct')}
                    ${this._renderMapNode('code', 'Code', 'Python')}
                    ${this._renderMapNode('mcp', 'MCP', 'Tools')}
                    ${this._renderMapNode('send', 'Channel', 'Webhook')}
                    ${this._renderMapNode('users', 'HITL', 'Operator')}
                </div>
            </section>
        `;
    }

    _renderMapNode(icon: string, title: string, kind: string) {
        return html`
            <div class="map-node">
                <div class="map-node-head">
                    <platform-icon name=${icon} size="20"></platform-icon>
                    <span class="map-node-kind">${kind}</span>
                </div>
                <div class="map-node-title">${title}</div>
            </div>
        `;
    }

    _renderMetric(icon: string, labelKey: string, value: unknown, captionKey: string) {
        const numericValue = Number(value);
        return html`
            <div class="metric-shell">
                <platform-metric-card
                    .label=${this.t(labelKey)}
                    .value=${Number.isFinite(numericValue) ? numericValue : 0}
                ></platform-metric-card>
                <div class="metric-caption">${this.t(captionKey)}</div>
            </div>
        `;
    }

    _renderMetrics(stats: FlowHomeStats) {
        return html`
            <section class="metric-grid" aria-label=${this.t('flows_home.metrics_aria')}>
                ${this._renderMetric('workflow', 'flows_home.metric_flows', String(stats.flowCount), 'flows_home.metric_flows_caption')}
                ${this._renderMetric('git-branch', 'flows_home.metric_scenarios', String(stats.branchCount), 'flows_home.metric_scenarios_caption')}
                ${this._renderMetric('box', 'flows_home.metric_nodes', String(stats.nodeCount), 'flows_home.metric_nodes_caption')}
                ${this._renderMetric('chat', 'flows_home.metric_sessions', String(stats.activeSessionCount), 'flows_home.metric_sessions_caption')}
                ${this._renderMetric('refresh', 'flows_home.metric_updates', String(stats.bundleUpdateCount), 'flows_home.metric_updates_caption')}
            </section>
        `;
    }

    _visibleQuickActions() {
        return [...QUICK_ACTIONS];
    }

    _renderActionCard(action: (typeof QUICK_ACTIONS)[number]) {
        const title = this.t(action.titleKey);
        return html`
            <glass-card compact>
                <div class="card-head">
                    <span class="tone-icon tone-${action.tone}">
                        <platform-icon name=${action.icon} size="18"></platform-icon>
                    </span>
                    <platform-button
                        variant="ghost"
                        density="compact"
                        icon-only
                        aria-label=${title}
                        @click=${() => this._openQuickAction(action.id)}
                    >
                        <platform-icon name="chevron-right" size="16"></platform-icon>
                    </platform-button>
                </div>
                <div class="card-title">${title}</div>
                <div class="card-desc">${this.t(action.descKey)}</div>
            </glass-card>
        `;
    }

    _renderQuickActions() {
        const actions = this._visibleQuickActions();
        return html`
            <section>
                ${this._renderSectionHead('flows_home.quick_title', 'flows_home.quick_subtitle', '', 'flows_home.quick_help')}
                <div class="action-grid">
                    ${repeat(actions, (action) => action.id, (action) => this._renderActionCard(action))}
                </div>
            </section>
        `;
    }

    _renderSectionHead(titleKey: string, subtitleKey: string, actionTemplate = '', hintKey = '') {
        return html`
            <div class="section-head">
                <div>
                    <div class="section-title-wrap">
                        <h2 class="section-title">${this.t(titleKey)}</h2>
                        ${hintKey
                            ? html`
                                <platform-help-hint
                                    .label=${this.t('help_hints.open_help')}
                                    .summary=${this.t(titleKey)}
                                    .details=${this.t(hintKey)}
                                    .docHref=${'/documentation/scenarios/flows/flows-home-overview/'}
                                    .docLabel=${this.t('help_hints.open_scenario')}
                                ></platform-help-hint>
                            `
                            : ''}
                    </div>
                    <p class="section-subtitle">${this.t(subtitleKey)}</p>
                </div>
                ${actionTemplate}
            </div>
        `;
    }

    _renderFlowMedia(flow: unknown) {
        const record = flowRecord(flow);
        const imageUrl = typeof record.store_card_image_url === 'string' ? record.store_card_image_url : '';
        if (imageUrl.length > 0) {
            return html`<img src=${imageUrl} alt=${flowTitle(flow)} />`;
        }
        return html`<platform-icon name="workflow" size="34"></platform-icon>`;
    }

    _renderFlowCard(flow: unknown) {
        const record = flowRecord(flow);
        const flowId = typeof record.flow_id === 'string' ? record.flow_id : '';
        const branches = isPlainObject(flow) && isPlainObject(flow.branches) ? Object.keys(flow.branches).length : 0;
        const description = flowDescription(flow);
        return html`
            <article class="flow-card">
                <div class="flow-media">${this._renderFlowMedia(flow)}</div>
                <div class="flow-body">
                    <div class="flow-title" title=${flowTitle(flow)}>${flowTitle(flow)}</div>
                    <div class="flow-desc">
                        ${description.length > 0 ? description : this.t('flows_home.flow_desc_empty')}
                    </div>
                    <div class="flow-meta">
                        <span>${this.t('flows_home.flow_meta', { id: flowId, branches })}</span>
                        <span class="flow-actions">
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="dense"
                                title=${this.t('flows_home.flow_chat')}
                                aria-label=${this.t('flows_home.flow_chat')}
                                @click=${() => this._openFlowChat(flowId)}
                            >
                                <platform-icon name="chat" size="14"></platform-icon>
                            </platform-button>
                            <platform-button
                                variant="ghost"
                                icon-only
                                density="dense"
                                title=${this.t('flows_home.flow_edit')}
                                aria-label=${this.t('flows_home.flow_edit')}
                                @click=${() => this._openFlowEditor(flowId)}
                            >
                                <platform-icon name="edit" size="14"></platform-icon>
                            </platform-button>
                        </span>
                    </div>
                </div>
            </article>
        `;
    }

    _renderFlowsSection(flows: readonly unknown[]) {
        const visibleFlows = flows;
        return html`
            <section>
                ${this._renderSectionHead('flows_home.flows_title', 'flows_home.flows_subtitle', '', 'flows_home.flows_help')}
                ${this._flows.loading && visibleFlows.length === 0
                    ? html`<platform-empty-state loading></platform-empty-state>`
                    : visibleFlows.length === 0
                        ? html`<platform-empty-state icon="workflow" title=${this.t('flows_home.flows_empty')}></platform-empty-state>`
                        : html`
                            <div class="flow-grid">
                                ${repeat(visibleFlows, (flow) => {
                                    const record = flowRecord(flow);
                                    if (typeof record.flow_id !== 'string' || record.flow_id.length === 0) {
                                        throw new Error('flows-home-page: flow_id required');
                                    }
                                    return record.flow_id;
                                }, (flow) => this._renderFlowCard(flow))}
                            </div>
                        `}
            </section>
        `;
    }

    _renderConnectCard(action: (typeof CONNECT_ACTIONS)[number], value: unknown) {
        const title = this.t(action.titleKey);
        if (action.id === 'resources') {
            return html`
                <article class="connect-card glass-card">
                    <div class="card-head">
                        <span class="tone-icon tone-${action.tone}">
                            <platform-icon name=${action.icon} size="18"></platform-icon>
                        </span>
                        <span class="metric-value">${value}</span>
                    </div>
                    <div class="card-title">${title}</div>
                    <div class="card-desc">${this.t(action.descKey)}</div>
                </article>
            `;
        }
        return html`
            <article class="connect-card glass-card">
                <div class="card-head">
                    <span class="tone-icon tone-${action.tone}">
                        <platform-icon name=${action.icon} size="18"></platform-icon>
                    </span>
                    <div class="card-head-end">
                        <span class="metric-value">${value}</span>
                        <platform-button
                            variant="ghost"
                            density="compact"
                            icon-only
                            aria-label=${title}
                            @click=${() => this._openConnectAction(action.id)}
                        >
                            <platform-icon name="chevron-right" size="16"></platform-icon>
                        </platform-button>
                    </div>
                </div>
                <div class="card-title">${title}</div>
                <div class="card-desc">${this.t(action.descKey)}</div>
            </article>
        `;
    }

    _renderConnectSection() {
        const resources = asArray(this._resources.items);
        const mcpCount = asArray(this._mcpServers.items).length;
        const variablesCount = asArray(this._variables.items).length;
        const integrationsCount = resultItems(this._integrations.lastResult).length;
        const values = {
            skills: String(asArray(this._agentSkills.items).length),
            mcp: String(mcpCount),
            variables: String(variablesCount),
            integrations: String(integrationsCount),
            resources: `${resourceTypeCount(resources, 'llm')}/${resourceTypeCount(resources, 'files')}/${resourceTypeCount(resources, 'code')}`,
        };
        return html`
            <section>
                ${this._renderSectionHead('flows_home.connect_title', 'flows_home.connect_subtitle', '', 'flows_home.connect_help')}
                <div class="connect-grid">
                    ${repeat(CONNECT_ACTIONS, (action) => action.id, (action) => this._renderConnectCard(action, values[action.id]))}
                </div>
            </section>
        `;
    }

    _renderCapabilities() {
        return html`
            <section>
                ${this._renderSectionHead('flows_home.capabilities_title', 'flows_home.capabilities_subtitle', '', 'flows_home.capabilities_help')}
                <div class="capability-grid">
                    ${repeat(CAPABILITY_GROUPS, (group) => group.id, (group) => html`
                        <article class="capability-card">
                            <div class="card-head">
                                <span class="tone-icon tone-accent">
                                    <platform-icon name=${group.icon} size="18"></platform-icon>
                                </span>
                            </div>
                            <div class="card-title">${this.t(group.titleKey)}</div>
                            <div class="card-desc">${this.t(group.textKey)}</div>
                            <div class="capability-chips">
                                ${group.chips.map((chip) => html`<span class="chip">${chip}</span>`)}
                            </div>
                        </article>
                    `)}
                </div>
            </section>
        `;
    }

    _renderSessionRow(session: unknown) {
        if (!isPlainObject(session)) {
            throw new Error('flows-home-page: session required');
        }
        const flowId = typeof session.flow_id === 'string' ? session.flow_id : '';
        const status = typeof session.status === 'string' ? session.status : '';
        return html`
            <article class="session-row">
                <span class="row-main">
                    <span class="tone-icon tone-info">
                        <platform-icon name="chat" size="16"></platform-icon>
                    </span>
                    <span class="row-copy">
                        <span class="row-title">${flowId}</span>
                        <span class="row-subtitle">${this._formatDateTime(session.last_activity)}</span>
                    </span>
                </span>
                <span class="chip">${status}</span>
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    aria-label=${this.t('flows_home.flow_chat')}
                    @click=${() => this._openSession(session)}
                >
                    <platform-icon name="chevron-right" size="16"></platform-icon>
                </platform-button>
            </article>
        `;
    }

    _renderReadinessRow(icon: string, titleKey: string, value: unknown) {
        return html`
            <div class="readiness-row">
                <span class="row-main">
                    <span class="tone-icon tone-success">
                        <platform-icon name=${icon} size="16"></platform-icon>
                    </span>
                    <span class="row-title">${this.t(titleKey)}</span>
                </span>
                <span class="metric-value">${value}</span>
            </div>
        `;
    }

    _renderOperatorTasksRow() {
        const counts = this._workItemCounts.state;
        const totalOpen = typeof counts.total_open_count === 'number' ? counts.total_open_count : 0;
        return html`
            <article
                class="readiness-row readiness-row-link"
                role="button"
                tabindex="0"
                aria-label=${this.t('flows_home.ready_operator_tasks_hint')}
                @click=${() => this._openOperatorInbox()}
                @keydown=${(e: KeyboardEvent) => this._onOperatorTasksKeydown(e)}
            >
                <span class="row-main">
                    <span class="tone-icon tone-warning">
                        <platform-icon name="inbox" size="16"></platform-icon>
                    </span>
                    <span class="row-title">${this.t('flows_home.ready_operator_tasks')}</span>
                </span>
                <span class="metric-value">${String(totalOpen)}</span>
            </article>
        `;
    }

    _onOperatorTasksKeydown(e: KeyboardEvent) {
        if (e.key === 'Enter' || e.key === ' ') {
            e.preventDefault();
            this._openOperatorInbox();
        }
    }

    _renderActivitySection() {
        const sessions = asArray(this._sessions.items).slice(0, 5);
        const bundles = resultItems(this._bundles.lastResult);
        const installedBundles = bundles.filter((item) => isPlainObject(item) && item.installed === true).length;
        const toolsCount = this._toolsCount;
        return html`
            <section>
                ${this._renderSectionHead('flows_home.activity_title', 'flows_home.activity_subtitle', '', 'flows_home.activity_help')}
                <div class="activity-layout">
                    <div class="session-list">
                        ${this._sessions.loading && sessions.length === 0
                            ? html`<platform-empty-state loading></platform-empty-state>`
                            : sessions.length === 0
                                ? html`<platform-empty-state icon="chat" title=${this.t('flows_home.sessions_empty')}></platform-empty-state>`
                                : repeat(sessions, (session) => {
                                    if (!isPlainObject(session) || typeof session.session_id !== 'string' || session.session_id.length === 0) {
                                        throw new Error('flows-home-page: session_id required');
                                    }
                                    return session.session_id;
                                }, (session) => this._renderSessionRow(session))}
                    </div>
                    <div class="readiness-list">
                        ${this._renderReadinessRow('box', 'flows_home.ready_bundles', `${installedBundles}/${bundles.length}`)}
                        ${this._renderReadinessRow('code', 'flows_home.ready_tools', String(toolsCount))}
                        ${this._renderOperatorTasksRow()}
                    </div>
                </div>
            </section>
        `;
    }

    override render(): TemplateResult {
        if (this._isMobile && this.mobileCatalogOpen) {
            return this._renderMobileCatalog();
        }
        const stats = this._flowStats();
        return html`
            <page-header title=${this.t('flows_home.page_title')}>
                ${this._renderHeaderActions()}
            </page-header>
            <div class="home-scroll">
                ${this._renderHero()}
                ${this._renderMetrics(stats)}
                ${this._renderQuickActions()}
                ${this._renderFlowsSection(stats.flows)}
                ${this._renderConnectSection()}
                ${this._renderCapabilities()}
                ${this._renderActivitySection()}
            </div>
        `;
    }
}

customElements.define('flows-home-page', FlowsHomePage);
