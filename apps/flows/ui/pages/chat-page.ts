/** User-facing Flow UI host. Chat is only the default document template. */

import type { ResourceController } from '@platform/lib/base/use-resource.js';
import { css, html, nothing } from 'lit';
import { PlatformPage } from '@platform/lib/base/PlatformPage.js';
import '@platform/lib/components/platform-breadcrumbs.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/flow-ui/components/platform-flow-ui.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

function presentText(value: unknown): string {
    if (value === undefined || value === null || value === false || value === 0 || value === '') return '';
    if (typeof value === 'number' && !Number.isFinite(value)) return '';
    return String(value);
}

function contextFromSession(flowId: string, sessionId: any) {
    const session = presentText(sessionId).trim();
    if (!session) return '';
    const prefix = `${flowId}:`;
    return session.startsWith(prefix) ? session.slice(prefix.length) : session;
}

export class ChatPage extends PlatformPage {
    static override properties: PropertyDeclarations = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        sessionId: { type: String, attribute: 'session-id' },
        _contextId: { state: true },
        _openingNewContext: { state: true },
    }
    declare flowId: string;
    declare branchId: string;
    declare sessionId: string;
    declare _contextId: string;
    declare _openingNewContext: boolean;
;

    static override styles: CSSResultGroup = [PlatformPage.styles, css`
        :host { flex: 1; min-width: 0; min-height: 0; height: 100%; display: flex; flex-direction: column; overflow: hidden; }
        .chat-topbar {
            flex: 0 0 auto;
            display: flex;
            align-items: center;
            justify-content: space-between;
            gap: var(--space-3);
            min-height: 48px;
            padding: var(--space-2) var(--space-4);
            border-bottom: 1px solid var(--border-subtle);
        }
        .chat-topbar platform-breadcrumbs { min-width: 0; }
        .actions { display: flex; align-items: center; gap: var(--space-2); flex-shrink: 0; }
        platform-flow-ui { flex: 1 1 0; min-height: 0; }
        @media (max-width: 767px) {
            .chat-topbar { padding: var(--space-1) var(--space-2); min-height: 40px; }
        }
    `];
    private _flows: ResourceController;

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this.sessionId = '';
        this._contextId = '';
        this._openingNewContext = false;
        this._flows = this.useResource('flows/flows');
    }

    override willUpdate(changed: PropertyValues<this>): void {
        if (changed.has('flowId') || changed.has('sessionId')) {
            this._contextId = contextFromSession(this.flowId, this.sessionId);
        }
    }

    override updated(changed: PropertyValues<this>): void {
        if (changed.has('flowId') || this._openingNewContext) {
            return;
        }
        // A session belongs to the branch it was created with, so switching branch
        // cannot continue it — open a fresh screen on the selected branch.
        if (changed.has('branchId') && typeof changed.get('branchId') === 'string') {
            void this._newContext();
            return;
        }
        // Sidebar "open chat" navigates to flow_chat (no session). Same flow keeps the
        // platform-flow-ui instance, so we must explicitly start a new context.
        if (!changed.has('sessionId')) {
            return;
        }
        const previousSessionId = changed.get('sessionId');
        const hadSession = typeof previousSessionId === 'string' && previousSessionId.trim() !== '';
        const sessionCleared = !this.sessionId || String(this.sessionId).trim() === '';
        if (!hadSession || !sessionCleared) {
            return;
        }
        void this._newContext();
    }

    _renderer() { return this.renderRoot.querySelector('platform-flow-ui'); }
    _flow() {
        const found = this._flows.items.find((flow: any) => flow && flow.flow_id === this.flowId);
        return found === undefined ? null : found;
    }
    _branch() { return this.branchId && this.branchId !== 'base' ? this.branchId : 'default'; }
    _flowDisplayName() {
        const flow = this._flow();
        if (flow && typeof flow.name === 'string' && flow.name.trim().length > 0) {
            return flow.name.trim();
        }
        if (typeof this.flowId === 'string' && this.flowId.trim().length > 0) {
            return this.flowId.trim();
        }
        return this.t('routes.flow_chat');
    }
    _branchDisplayLabel() {
        if (!this.branchId || this.branchId === 'base') {
            return '';
        }
        const flow = this._flow();
        const branch = flow && flow.branches && typeof flow.branches === 'object'
            ? (flow.branches as any)[this.branchId]
            : null;
        if (branch && typeof branch.name === 'string' && branch.name.trim().length > 0) {
            return branch.name.trim();
        }
        return this.branchId;
    }
    _breadcrumbCurrentLabel() {
        const branchLabel = this._branchDisplayLabel();
        if (branchLabel.length > 0) {
            return branchLabel;
        }
        return this._flowDisplayName();
    }
    _breadcrumbTrail() {
        const branchLabel = this._branchDisplayLabel();
        if (branchLabel.length === 0) {
            return [];
        }
        if (typeof this.flowId !== 'string' || this.flowId.trim().length === 0) {
            throw new Error('chat-page: flowId required for branch breadcrumb trail');
        }
        return [{
            label: this._flowDisplayName(),
            routeKey: 'flow_chat',
            params: { flowId: this.flowId },
        }];
    }
    _back() { this.navigate('list', {}); }
    _sessionId() {
        const renderer = this._renderer();
        const rendererContext = renderer !== null && typeof renderer === 'object' && 'contextId' in renderer
            ? (renderer as Record<string, unknown>).contextId
            : undefined;
        const ownContext = presentText(this._contextId);
        const contextId = ownContext.length > 0 ? ownContext : presentText(rendererContext);
        return contextId ? `${this.flowId}:${contextId}` : '';
    }
    _openHistory() {
        const sessionId = this._sessionId();
        if (!sessionId) {
            throw new Error('chat-page: durable history requires an active session');
        }
        this.openModal('flows.durable_history', { sessionId });
    }

    _onBrowserPreviewOpen(e: CustomEvent) {
        e.preventDefault();
        const detail = e.detail && typeof e.detail === 'object' ? e.detail : {};
        const viewerUrl = typeof detail.viewerUrl === 'string' ? detail.viewerUrl : '';
        this.openModal('flows.browser_preview', {
            viewerUrl,
            sessionId: typeof detail.sessionId === 'string' ? detail.sessionId : '',
            currentUrl: typeof detail.currentUrl === 'string' ? detail.currentUrl : '',
            status: typeof detail.status === 'string' ? detail.status : '',
        });
    }
    /** Кнопки «трейс»/«логи» у ответа ассистента: модалки по session_id и task_id хода. */
    _onOpenObservability(event: CustomEvent) {
        const detail = event.detail;
        if (!detail || (detail.kind !== 'tracing' && detail.kind !== 'logs')) {
            throw new Error('chat-page: flow-ui-open-observability requires kind tracing|logs');
        }
        if (typeof detail.contextId !== 'string' || detail.contextId === '') {
            throw new Error('chat-page: flow-ui-open-observability requires contextId');
        }
        const props: any = { sessionId: `${this.flowId}:${detail.contextId}` };
        if (typeof detail.taskId === 'string' && detail.taskId !== '') props.taskId = detail.taskId;
        this.openModal(detail.kind === 'tracing' ? 'flows.tracing' : 'flows.logs', props);
    }
    _editor() {
        if (this.branchId && this.branchId !== 'base') this.navigate('flow_editor_branch', { flowId: this.flowId, branchId: this.branchId });
        else this.navigate('flow_editor', { flowId: this.flowId });
    }
    async _newContext() {
        if (this._openingNewContext) {
            return;
        }
        const renderer = this._renderer();
        if (renderer === null) {
            throw new Error('chat-page: platform-flow-ui is required for New screen');
        }
        this._openingNewContext = true;
        try {
            await (renderer as Record<string, any>).startNewContext();
            const contextId = (renderer as Record<string, any>).contextId;
            if (typeof contextId !== 'string' || !contextId.trim()) {
                throw new Error('chat-page: New screen did not produce contextId');
            }
            this._navigateToSession(`${this.flowId}:${contextId}`);
        } finally {
            this._openingNewContext = false;
        }
    }

    /** Keep the branch in the session URL so reload and New screen stay on it. */
    _navigateToSession(sessionId: any) {
        if (this.branchId && this.branchId !== 'base') {
            this.navigate('flow_chat_branch_session', {
                flowId: this.flowId,
                branchId: this.branchId,
                sessionId,
            });
            return;
        }
        this.navigate('flow_chat_session', { flowId: this.flowId, sessionId });
    }

    _onReady(event: CustomEvent) {
        const contextId = event.detail?.contextId || (this._renderer() as Record<string, any>)?.contextId;
        if (!contextId) return;
        const sessionId = `${this.flowId}:${contextId}`;
        if (this.sessionId === sessionId) return;
        this._navigateToSession(sessionId);
    }

    override render(): TemplateResult {
        return html`
            <div class="chat-topbar">
                <platform-breadcrumbs
                    compact
                    current-label=${this._breadcrumbCurrentLabel()}
                    .trail=${this._breadcrumbTrail()}
                ></platform-breadcrumbs>
                <div class="actions">
                    <platform-button
                        variant="ghost"
                        density="compact"
                        icon-only
                        title=${this.t('platform_chat.btn_history')}
                        aria-label=${this.t('platform_chat.btn_history')}
                        ?disabled=${!this._contextId}
                        @click=${() => this._openHistory()}
                    >
                        <platform-icon name="trace-timeline" size="15"></platform-icon>
                    </platform-button>
                    <platform-button variant="ghost" density="compact" @click=${() => this._newContext()}>
                        <platform-icon name="plus" size="15"></platform-icon> ${this.t('chat_page.new_screen')}
                    </platform-button>
                    <platform-button variant="secondary" density="compact" @click=${() => this._editor()}>
                        <platform-icon name="edit" size="15"></platform-icon> ${this.t('chat_page.interface_editor')}
                    </platform-button>
                </div>
            </div>
            <platform-flow-ui
                flow-id=${this.flowId}
                branch-id=${this._branch()}
                context-id=${this._contextId}
                base-url="/flows"
                display="page"
                profile="spa"
                theme="auto"
                @flow-ui-ready=${this._onReady}
                @browser-preview-open=${this._onBrowserPreviewOpen}
                @flow-ui-open-observability=${this._onOpenObservability}
            ></platform-flow-ui>
        `;
    }
}

if (!customElements.get('chat-page')) customElements.define('chat-page', ChatPage);
