/**
 * FlowsHomePage — рабочая главная страница сервиса flows.
 */

import { html, css } from 'lit';
import { repeat } from 'lit/directives/repeat.js';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import { formatPlatformDateTime } from '@platform/lib/utils/format-platform-date.js';
import { buildFrontendPublicPath } from '@platform/lib/utils/build-service-entry-url.js';
import '@platform/lib/components/layout/page-header.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/glass-spinner.js';
import '../components/flows-catalog-list.js';
import { asArray, asString, isPlainObject } from '../_helpers/flows-resolvers.js';

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
]);

const CONNECT_ACTIONS = Object.freeze([
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

function resultItems(result) {
    if (Array.isArray(result)) {
        return result;
    }
    if (isPlainObject(result) && Array.isArray(result.items)) {
        return result.items;
    }
    return [];
}

function countBranches(flows) {
    let total = 0;
    for (const flow of flows) {
        total += 1;
        if (isPlainObject(flow) && isPlainObject(flow.branches)) {
            total += Object.keys(flow.branches).length;
        }
    }
    return total;
}

function countFlowNodes(flows) {
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

function flowTitle(flow) {
    if (isPlainObject(flow) && typeof flow.name === 'string' && flow.name.length > 0) {
        return flow.name;
    }
    return asString(flow?.flow_id);
}

function flowDescription(flow) {
    if (isPlainObject(flow) && typeof flow.description === 'string' && flow.description.length > 0) {
        return flow.description;
    }
    return '';
}

function resourceTypeCount(items, type) {
    let total = 0;
    for (const item of items) {
        if (isPlainObject(item) && item.type === type) {
            total += 1;
        }
    }
    return total;
}

function activeSessionCount(items) {
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

    static properties = {
        mobileCatalogOpen: { type: Boolean, reflect: true, attribute: 'mobile-catalog-open' },
        _isMobile: { state: true },
    };

    static styles = [
        PlatformPage.styles,
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
            .icon-action,
            .text-action {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                gap: var(--space-2);
                min-height: 36px;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                font: inherit;
                font-size: var(--text-sm);
                transition: background var(--duration-fast), border-color var(--duration-fast), color var(--duration-fast);
            }
            .icon-action {
                width: 36px;
                padding: 0;
            }
            .text-action {
                padding: 0 var(--space-3);
            }
            a.text-action {
                text-decoration: none;
            }
            .icon-action:hover,
            .text-action:hover {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
            }
            .icon-action:focus-visible,
            .text-action:focus-visible,
            .mini-btn:focus-visible,
            button.action-card:focus-visible,
            button.connect-card:focus-visible,
            .session-row:focus-visible {
                outline: none;
                box-shadow: var(--focus-ring);
            }
            .text-action.primary {
                color: var(--text-inverse);
                background: var(--accent);
                border-color: var(--accent);
            }
            .text-action.primary:hover {
                background: var(--accent-hover);
                border-color: var(--accent-hover);
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
            .metric-card,
            .action-card,
            .connect-card,
            .capability-card,
            .flow-card {
                border-radius: var(--radius-md);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                box-sizing: border-box;
            }
            .metric-card {
                min-height: 112px;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
                gap: var(--space-3);
            }
            .metric-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                text-transform: uppercase;
                letter-spacing: 0.06em;
                font-weight: var(--font-semibold);
            }
            .metric-value {
                font-size: var(--text-3xl);
                line-height: var(--leading-tight);
                font-weight: var(--font-bold);
                color: var(--text-primary);
            }
            .metric-caption {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
                line-height: var(--leading-normal);
            }
            .section-head {
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
            .mini-btn {
                width: 30px;
                height: 30px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
            }
            .mini-btn:hover {
                color: var(--text-primary);
                background: var(--glass-solid-medium);
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
            button.action-card,
            button.connect-card {
                color: inherit;
                cursor: pointer;
                font: inherit;
                transition: background var(--duration-fast), border-color var(--duration-fast), transform var(--duration-fast);
            }
            button.action-card:hover,
            button.connect-card:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
                transform: translateY(-1px);
            }
            .card-head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
            }
            .tone-icon {
                width: 36px;
                height: 36px;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                color: var(--text-inverse);
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
            .session-row {
                color: inherit;
                cursor: pointer;
                font: inherit;
                text-align: left;
            }
            .session-row:hover {
                background: var(--glass-solid-medium);
                border-color: var(--glass-border-medium);
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
            .empty-panel {
                min-height: 120px;
                display: flex;
                align-items: center;
                justify-content: center;
                border-radius: var(--radius-md);
                color: var(--text-tertiary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                text-align: center;
                padding: var(--space-4);
                box-sizing: border-box;
            }
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
                .header-actions .text-action span {
                    display: none;
                }
                .header-actions .text-action {
                    width: 36px;
                    padding: 0;
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
        this._variables = this.useResource('secrets/variables');
        this._tools = this.useOp('flows/tools_all');
        this._bundles = this.useOp('flows/flow_store_bundles');
        this._integrations = this.useOp('flows/integrations_list');
        this._authSel = this.select((s) => {
            const auth = isPlainObject(s.auth) ? s.auth : {};
            return {
                user: isPlainObject(auth.user) ? auth.user : null,
                companyId: typeof auth.activeCompanyId === 'string' ? auth.activeCompanyId : '',
            };
        });
        this._localeSel = this.select((s) => {
            if (!isPlainObject(s.i18n)) {
                return '';
            }
            if (typeof s.i18n.locale !== 'string') {
                return '';
            }
            return s.i18n.locale;
        });
        if (typeof window !== 'undefined') {
            if (typeof window.matchMedia === 'function') {
                this._isMobile = window.matchMedia('(max-width: 767px)').matches;
            }
        }
    }

    connectedCallback() {
        super.connectedCallback();
        void this._sessions.load({ limit: 8, offset: 0 });
        void this._resources.load({ limit: 200, offset: 0 });
        void this._mcpServers.load();
        void this._variables.load({ limit: 200, offset: 0 });
        void this._tools.run({ limit: 2000, offset: 0 });
        void this._bundles.run({});
        void this._integrations.run({});
        this._installMobileModeListener();
    }

    disconnectedCallback() {
        if (this._flowsHomeMql !== null) {
            if (this._onFlowsHomeMql !== null) {
                this._flowsHomeMql.removeEventListener('change', this._onFlowsHomeMql);
            }
        }
        this._flowsHomeMql = null;
        this._onFlowsHomeMql = null;
        super.disconnectedCallback();
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

    _openQuickAction(id) {
        if (id === 'store') {
            this.openModal('flows.flow_create', {});
            return;
        }
        if (id === 'sessions') {
            this.openModal('flows.sessions', {});
            return;
        }
        throw new Error(`flows-home-page: unknown quick action "${id}"`);
    }

    _openConnectAction(id) {
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
        throw new Error(`flows-home-page: unknown connect action "${id}"`);
    }

    _openFlowChat(flowId) {
        if (typeof flowId !== 'string') {
            return;
        }
        if (flowId.length === 0) {
            return;
        }
        this.navigate('flow_chat', { flowId });
    }

    _openFlowEditor(flowId) {
        if (typeof flowId !== 'string') {
            return;
        }
        if (flowId.length === 0) {
            return;
        }
        this.navigate('flow_editor', { flowId });
    }

    _openSession(session) {
        if (!isPlainObject(session)) {
            return;
        }
        const flowId = asString(session.flow_id);
        const sessionId = asString(session.session_id);
        if (flowId.length === 0) {
            return;
        }
        if (sessionId.length === 0) {
            return;
        }
        this.navigate('flow_chat_session', { flowId, sessionId });
    }

    _formatDateTime(value) {
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

    _flowStats() {
        const flows = asArray(this._flows.items).filter((flow) => isPlainObject(flow) && flow.hidden !== true);
        const sessions = asArray(this._sessions.items);
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
                        <button
                            type="button"
                            class="icon-action"
                            title=${this.t('flows_home.mobile_open_catalog')}
                            aria-label=${this.t('flows_home.mobile_open_catalog')}
                            @click=${() => this._openMobileCatalog()}
                        >
                            <platform-icon name="list" size="16"></platform-icon>
                        </button>
                    `
                    : ''}
                <button
                    type="button"
                    class="icon-action"
                    title=${this.t('flows_home.header_sessions')}
                    aria-label=${this.t('flows_home.header_sessions')}
                    @click=${() => this.openModal('flows.sessions', {})}
                >
                    <platform-icon name="chat" size="16"></platform-icon>
                </button>
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
                <button
                    type="button"
                    slot="leading"
                    class="page-header-leading-btn"
                    title=${this.t('flows_home.mobile_back_home')}
                    aria-label=${this.t('flows_home.mobile_back_home')}
                    @click=${() => this._closeMobileCatalog()}
                >
                    <platform-icon name="chevron-left" size="20"></platform-icon>
                </button>
            </page-header>
            <div class="mobile-catalog-shell">
                <flows-catalog-list
                    mode="page"
                    @flows-catalog-dismiss-mobile=${() => this._closeMobileCatalog()}
                ></flows-catalog-list>
            </div>
        `;
    }

    _agentDownloadHref() {
        return buildFrontendPublicPath('/agent');
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
                        <button type="button" class="text-action primary" @click=${() => this.openModal('flows.flow_create', {})}>
                            <platform-icon name="plus" size="16"></platform-icon>
                            <span>${this.t('flows_home.hero_create')}</span>
                        </button>
                        <button type="button" class="text-action" @click=${() => this.openModal('flows.sessions', {})}>
                            <platform-icon name="chat" size="16"></platform-icon>
                            <span>${this.t('flows_home.hero_sessions')}</span>
                        </button>
                        <button type="button" class="text-action" @click=${() => this.openModal('flows.mcp_servers', {})}>
                            <platform-icon name="mcp" size="16"></platform-icon>
                            <span>${this.t('flows_home.hero_mcp')}</span>
                        </button>
                        <a
                            class="text-action"
                            href=${this._agentDownloadHref()}
                            title=${this.t('flows_home.hero_download_desc')}
                            aria-label=${this.t('flows_home.hero_download')}
                        >
                            <platform-icon name="download" size="16"></platform-icon>
                            <span>${this.t('flows_home.hero_download')}</span>
                        </a>
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

    _renderMapNode(icon, title, kind) {
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

    _renderMetric(icon, labelKey, value, captionKey) {
        return html`
            <div class="metric-card">
                <div class="metric-head">
                    <span>${this.t(labelKey)}</span>
                    <platform-icon name=${icon} size="16"></platform-icon>
                </div>
                <div class="metric-value">${value}</div>
                <div class="metric-caption">${this.t(captionKey)}</div>
            </div>
        `;
    }

    _renderMetrics(stats) {
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

    _renderActionCard(action) {
        return html`
            <button type="button" class="action-card" @click=${() => this._openQuickAction(action.id)}>
                <div class="card-head">
                    <span class="tone-icon tone-${action.tone}">
                        <platform-icon name=${action.icon} size="18"></platform-icon>
                    </span>
                    <platform-icon name="chevron-right" size="16"></platform-icon>
                </div>
                <div class="card-title">${this.t(action.titleKey)}</div>
                <div class="card-desc">${this.t(action.descKey)}</div>
            </button>
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

    _renderSectionHead(titleKey, subtitleKey, actionTemplate = '', hintKey = '') {
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

    _renderFlowMedia(flow) {
        const imageUrl = asString(flow?.store_card_image_url);
        if (imageUrl.length > 0) {
            return html`<img src=${imageUrl} alt=${flowTitle(flow)} />`;
        }
        return html`<platform-icon name="workflow" size="34"></platform-icon>`;
    }

    _renderFlowCard(flow) {
        const flowId = asString(flow?.flow_id);
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
                            <button
                                type="button"
                                class="mini-btn"
                                title=${this.t('flows_home.flow_chat')}
                                aria-label=${this.t('flows_home.flow_chat')}
                                @click=${() => this._openFlowChat(flowId)}
                            >
                                <platform-icon name="chat" size="14"></platform-icon>
                            </button>
                            <button
                                type="button"
                                class="mini-btn"
                                title=${this.t('flows_home.flow_edit')}
                                aria-label=${this.t('flows_home.flow_edit')}
                                @click=${() => this._openFlowEditor(flowId)}
                            >
                                <platform-icon name="edit" size="14"></platform-icon>
                            </button>
                        </span>
                    </div>
                </div>
            </article>
        `;
    }

    _renderFlowsSection(flows) {
        const visibleFlows = flows;
        return html`
            <section>
                ${this._renderSectionHead('flows_home.flows_title', 'flows_home.flows_subtitle', '', 'flows_home.flows_help')}
                ${this._flows.loading && visibleFlows.length === 0
                    ? html`<div class="empty-panel"><glass-spinner></glass-spinner></div>`
                    : visibleFlows.length === 0
                        ? html`
                            <div class="empty-panel">
                                <span>${this.t('flows_home.flows_empty')}</span>
                            </div>
                        `
                        : html`
                            <div class="flow-grid">
                                ${repeat(visibleFlows, (flow) => asString(flow.flow_id), (flow) => this._renderFlowCard(flow))}
                            </div>
                        `}
            </section>
        `;
    }

    _renderConnectCard(action, value) {
        if (action.id === 'resources') {
            return html`
                <article class="connect-card">
                    <div class="card-head">
                        <span class="tone-icon tone-${action.tone}">
                            <platform-icon name=${action.icon} size="18"></platform-icon>
                        </span>
                        <span class="metric-value">${value}</span>
                    </div>
                    <div class="card-title">${this.t(action.titleKey)}</div>
                    <div class="card-desc">${this.t(action.descKey)}</div>
                </article>
            `;
        }
        return html`
            <button type="button" class="connect-card" @click=${() => this._openConnectAction(action.id)}>
                <div class="card-head">
                    <span class="tone-icon tone-${action.tone}">
                        <platform-icon name=${action.icon} size="18"></platform-icon>
                    </span>
                    <span class="metric-value">${value}</span>
                </div>
                <div class="card-title">${this.t(action.titleKey)}</div>
                <div class="card-desc">${this.t(action.descKey)}</div>
            </button>
        `;
    }

    _renderConnectSection() {
        const resources = asArray(this._resources.items);
        const mcpCount = asArray(this._mcpServers.items).length;
        const variablesCount = asArray(this._variables.items).length;
        const integrationsCount = resultItems(this._integrations.lastResult).length;
        const values = {
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

    _renderSessionRow(session) {
        const flowId = asString(session?.flow_id);
        const status = asString(session?.status);
        return html`
            <button type="button" class="session-row" @click=${() => this._openSession(session)}>
                <span class="row-main">
                    <span class="tone-icon tone-info">
                        <platform-icon name="chat" size="16"></platform-icon>
                    </span>
                    <span class="row-copy">
                        <span class="row-title">${flowId}</span>
                        <span class="row-subtitle">${this._formatDateTime(session?.last_activity)}</span>
                    </span>
                </span>
                <span class="chip">${status}</span>
            </button>
        `;
    }

    _renderReadinessRow(icon, titleKey, value) {
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

    _renderActivitySection() {
        const sessions = asArray(this._sessions.items).slice(0, 5);
        const bundles = resultItems(this._bundles.lastResult);
        const installedBundles = bundles.filter((item) => isPlainObject(item) && item.installed === true).length;
        const toolsCount = resultItems(this._tools.lastResult)
            .filter((item) => isPlainObject(item) && item.item_type === 'tool')
            .length;
        return html`
            <section>
                ${this._renderSectionHead('flows_home.activity_title', 'flows_home.activity_subtitle', '', 'flows_home.activity_help')}
                <div class="activity-layout">
                    <div class="session-list">
                        ${this._sessions.loading && sessions.length === 0
                            ? html`<div class="empty-panel"><glass-spinner></glass-spinner></div>`
                            : sessions.length === 0
                                ? html`<div class="empty-panel">${this.t('flows_home.sessions_empty')}</div>`
                                : repeat(sessions, (session) => asString(session.session_id), (session) => this._renderSessionRow(session))}
                    </div>
                    <div class="readiness-list">
                        ${this._renderReadinessRow('box', 'flows_home.ready_bundles', `${installedBundles}/${bundles.length}`)}
                        ${this._renderReadinessRow('code', 'flows_home.ready_tools', String(toolsCount))}
                    </div>
                </div>
            </section>
        `;
    }

    render() {
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
