/**
 * flows-editor-header — шапка редактора flow.
 *
 * Desktop: одна chrome-row (~60px) — back / title / branches / workspace / contextual tools / actions.
 * Interface-инструменты приходят слотом ``workspace-tools``; Publish и статус общие на все ракурсы.
 * Mobile: branches — вторая строка; overflow-menu для tiered actions.
 *
 * Источники state:
 *   - useOp('flows/editor').state.flowConfig — текущая модель flow.
 *   - useOp('flows/editor').state: isDirty, isSaving, workspace, publishedAt.
 *   - useResource('flows/flows') — флаг has_bundle_update и список branches.
 *
 * Ops:
 *   - editor-save — публикация (страница → saveEditorFlow / flows/flow_update);
 *   - flows/flow_reload_from_bundle — переинициализация из bundle;
 *   - flows/branch_remove — удаление ветки.
 */

import type { OpController, ResourceController, ControllerFor } from '@platform/lib/base/use-resource.js';
import { html, css, nothing, unsafeCSS } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-help-hint.js';
import { PlatformPopover } from '@platform/lib/components/platform-popover.js';
import '@platform/lib/components/fields/platform-field.js';
import {
    asArray,
    isPlainObject,
    buildFlowPublishBody,
    getBranchNodes,
} from '../../_helpers/flows-resolvers.js';
import type { DocumentProblem } from '../../_helpers/interface-editor-domain.js';
import { openPlatformLaraAssistant } from '@platform/lib/flow-ui/shell/preferences.js';
import type {CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult} from 'lit';

const MENU_PORTAL_GAP_PX = 4;
const MENU_PORTAL_VIEWPORT_INSET_PX = 16;

type WorkspaceId = 'logic' | 'interface' | 'run';

interface StatusBadge {
    key: 'dirty' | 'published' | 'idle';
    textKey: string;
}

interface ChromeIssue {
    kind: 'dataflow' | 'interface';
    nodeId: string;
    nodeName: string;
    severity: 'error' | 'warning';
    message: string;
    pageId?: string | null;
    blockId?: string | null;
}

interface BranchTabItem {
    value: string;
    label: string;
    title: string;
    closable?: boolean;
}

interface HeaderIconButtonArgs {
    title: string;
    icon: string;
    iconSize?: string;
    onClick: (event: Event) => void;
    dataAction?: string;
}

interface MenuButtonArgs {
    label: string;
    icon: string;
    onClick: () => void;
}

function requireEditorState(state: unknown): Record<string, unknown> {
    if (!isPlainObject(state)) throw new Error('flows-editor-header: editor state required');
    return state;
}

function workspaceId(value: unknown): WorkspaceId {
    if (value !== 'logic' && value !== 'interface' && value !== 'run') {
        throw new Error(`flows-editor-header: unsupported workspace ${String(value)}`);
    }
    return value;
}

function problemParams(params: Record<string, unknown>): Record<string, string | number> {
    const out: Record<string, string | number> = {};
    for (const [key, value] of Object.entries(params)) {
        if (typeof value !== 'string' && typeof value !== 'number') {
            throw new Error('flows-editor-header: problem param must be a string or number');
        }
        out[key] = value;
    }
    return out;
}

function issueText(value: unknown): string {
    if (value === undefined || value === null || value === '') return '';
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') return String(value);
    throw new Error('flows-editor-header: issue text must be a scalar');
}

const HEADER_MENU_CSS = `
        .flows-editor-header-menu-portal {
            width: min(320px, calc(100vw - 2 * var(--space-4, 16px)));
            max-width: calc(100vw - 2 * var(--space-4, 16px));
            box-sizing: border-box;
            display: flex;
            flex-direction: column;
            gap: var(--space-1, 4px);
            padding: var(--space-1, 4px);
        }
        .flows-editor-header-menu-portal.problems-flyout {
            max-height: min(60vh, 420px);
            overflow-y: auto;
            scrollbar-width: thin;
        }
        .flows-editor-header-menu-portal .problems-header {
            padding: var(--space-1, 4px) var(--space-2, 8px);
            font-size: var(--text-xs, 12px);
            font-weight: var(--font-semibold, 600);
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.04em;
        }
        .flows-editor-header-menu-portal .problem-item {
            display: flex;
            align-items: flex-start;
            gap: var(--space-2, 8px);
            width: 100%;
            text-align: left;
            padding: var(--space-2, 8px);
            border: none;
            border-radius: var(--radius-sm, 8px);
            background: transparent;
            color: var(--text-primary);
            cursor: pointer;
        }
        .flows-editor-header-menu-portal .problem-item:hover {
            background: var(--glass-solid-subtle);
        }
        .flows-editor-header-menu-portal .problem-item[data-severity="error"] platform-icon {
            color: var(--error);
        }
        .flows-editor-header-menu-portal .problem-item[data-severity="warning"] platform-icon {
            color: var(--warning);
        }
        .flows-editor-header-menu-portal .problem-body {
            display: flex;
            flex-direction: column;
            gap: 1px;
            min-width: 0;
        }
        .flows-editor-header-menu-portal .problem-node {
            font-size: var(--text-xs, 12px);
            font-weight: var(--font-semibold, 600);
        }
        .flows-editor-header-menu-portal .problem-msg {
            font-size: var(--text-xs, 12px);
            color: var(--text-secondary);
        }
`;


export class FlowsEditorHeader extends PlatformElement {
    static override properties: PropertyDeclarations = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        interfaceDirty: { type: Boolean },
        interfaceProblems: { attribute: false },
        _isMobile: { state: true },
        _overflowOpen: { state: true },
        _problemsOpen: { state: true },
    }
    declare flowId: string;
    declare branchId: string;
    declare interfaceDirty: boolean;
    declare interfaceProblems: readonly DocumentProblem[];
    declare _isMobile: boolean;
    declare _overflowOpen: boolean;
    declare _problemsOpen: boolean;
;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        unsafeCSS(HEADER_MENU_CSS),
        css`
            :host {
                display: flex;
                flex-direction: column;
                gap: var(--flows-editor-chrome-gap);
                min-height: var(--flows-editor-chrome-stack-height);
                padding: var(--space-2) var(--space-4);
                box-sizing: border-box;
                background: var(--glass-solid-medium);
                border-bottom: 1px solid var(--border-subtle);
                box-shadow: var(--glass-shadow-subtle);
            }

            @media (min-width: 768px) {
                :host {
                    gap: 0;
                }
            }

            :host(.editor-chrome-panel) {
                background: transparent;
                border-bottom: none;
                box-shadow: none;
                padding-top: 0;
            }

            .chrome-row {
                display: flex;
                align-items: center;
                gap: var(--flows-editor-chrome-gap);
                min-height: var(--flows-editor-chrome-row-min-height);
                min-width: 0;
            }

            .chrome-row-primary {
                gap: var(--space-3);
            }

            .row-left,
            .row-center,
            .row-right {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }

            .row-left {
                flex: 0 1 auto;
                max-width: min(420px, 34vw);
            }

            .row-center {
                flex: 0 0 auto;
            }

            .row-right {
                flex: 0 0 auto;
                position: relative;
            }

            .title-group {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                flex: 1 1 auto;
            }

            .flow-name-field {
                flex: 1 1 auto;
                min-width: 120px;
                max-width: min(320px, 40vw);
            }

            .status-badge {
                display: inline-flex;
                align-items: center;
                flex-shrink: 0;
                padding: 2px var(--space-2);
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
                font-weight: var(--font-medium);
                color: var(--text-secondary);
                background: var(--glass-solid-subtle);
                border: 1px solid var(--border-subtle);
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }

            .status-badge[data-status="dirty"] {
                color: var(--warning);
                background: var(--warning-bg);
                border-color: var(--warning-border);
            }

            .status-badge[data-status="published"] {
                color: var(--success);
                background: var(--success-bg);
                border-color: var(--success-border);
            }

            .chrome-row-branches {
                min-width: 0;
                gap: var(--space-2);
            }

            .branches-slot {
                display: none;
                flex: 1 1 0;
                min-width: 0;
                align-items: center;
                gap: var(--space-2);
                overflow: hidden;
            }

            .branches-scroll {
                flex: 1 1 auto;
                min-width: 0;
                overflow-x: auto;
                overflow-y: hidden;
                scrollbar-width: thin;
            }

            .branches-scroll platform-segmented-control {
                display: block;
                width: max-content;
                max-width: none;
            }

            .branches-add {
                flex: 0 0 auto;
            }

            @media (min-width: 768px) {
                .chrome-row-primary {
                    min-height: var(--flows-editor-chrome-stack-height);
                }

                .branches-slot {
                    display: flex;
                }

                .chrome-row-branches {
                    display: none;
                }
            }

            .branches-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                width: 100%;
            }

            .branches-row .branches-scroll {
                flex: 1 1 auto;
            }

            .header-actions {
                position: relative;
                display: flex;
                align-items: center;
                gap: var(--space-2);
                isolation: isolate;
            }

            .workspace-tools {
                display: inline-flex;
                align-items: center;
                min-width: 0;
            }

            .overflow-anchor {
                position: relative;
            }

            .overflow-btn-wrap {
                position: relative;
                display: inline-flex;
            }

            .problems-anchor {
                position: relative;
                display: inline-flex;
            }

            .problems-btn {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 3px var(--space-2);
                border-radius: var(--radius-full);
                border: 1px solid var(--warning-border);
                background: var(--warning-bg);
                color: var(--warning);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                cursor: pointer;
            }

            .problems-btn[data-severity="error"] {
                border-color: var(--error-border, var(--border-subtle));
                background: var(--error-bg, color-mix(in oklab, var(--error) 12%, transparent));
                color: var(--error);
            }

            .reload-dot {
                position: absolute;
                top: 2px;
                right: 2px;
                width: 8px;
                height: 8px;
                border-radius: 50%;
                background: var(--warning);
                box-shadow: 0 0 6px var(--warning);
                pointer-events: none;
            }

            .employee-chip {
                display: inline-flex;
                align-items: center;
                gap: 6px;
                height: var(--flows-chrome-control-size);
                padding: 0 var(--space-2) 0 var(--space-1);
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-xs);
                font-weight: var(--font-semibold);
                letter-spacing: 0.02em;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }

            .employee-chip:hover {
                border-color: var(--flows-employee-chip-active-border);
                color: var(--text-primary);
                background: var(--glass-solid-medium);
            }

            .employee-chip[data-active='true'] {
                color: var(--accent);
                border-color: var(--flows-employee-chip-active-border);
                background: var(--flows-employee-chip-active-bg);
                box-shadow: var(--flows-employee-badge-glow);
            }

            .employee-chip-label {
                max-width: 9rem;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }

            @media (max-width: 767px) {
                .desktop-only-actions {
                    display: none;
                }

                .flow-name-field {
                    max-width: min(180px, 42vw);
                }

                .chrome-row-primary {
                    flex-wrap: wrap;
                }

                .row-center {
                    order: 3;
                    width: 100%;
                    justify-content: flex-start;
                }
            }
        `,
    ];
    private _editor: ControllerFor<'flows/editor'>;
    private _reload: OpController;
    private _flows: ResourceController;
    private _branchRemove: OpController;
    private _overflowAnchor: HTMLElement | null;
    private _problemsAnchor: HTMLElement | null;
    private _outsideCloseArmed: boolean;
    private _outsideCloseFrame: number | null;
    private _editorMql: MediaQueryList | null;
    private _onEditorMobileMql: (() => void) | null;
    private _onDocPointer: (event: Event) => void;
    private _overflowPortalHost: HTMLElement | null;
    private _problemsPortalHost: HTMLElement | null;

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this.interfaceDirty = false;
        this.interfaceProblems = [];
        this._isMobile =
            typeof window !== 'undefined' &&
            typeof window.matchMedia === 'function' &&
            window.matchMedia('(max-width: 767px)').matches;
        this._overflowOpen = false;
        this._problemsOpen = false;
        /** @type {HTMLElement | null} */
        this._overflowAnchor = null;
        /** @type {HTMLElement | null} */
        this._problemsAnchor = null;
        this._outsideCloseArmed = false;
        this._outsideCloseFrame = null;
        this._editorMql = null;
        this._onEditorMobileMql = null;
        this._overflowPortalHost = null;
        this._problemsPortalHost = null;
        this._onDocPointer = (e: Event) => {
            if (!this._overflowOpen && !this._problemsOpen) {
                return;
            }
            if (!this._outsideCloseArmed) {
                return;
            }
            const path = e.composedPath();
            for (const n of path) {
                if (n === this) {
                    break;
                }
                if (n === this._overflowPortalHost || n === this._problemsPortalHost) {
                    return;
                }
                if (!(n instanceof Element)) {
                    continue;
                }
                if (
                    n.classList.contains('header-actions')
                    || n.classList.contains('overflow-anchor')
                    || n.classList.contains('problems-anchor')
                ) {
                    return;
                }
            }
            this._overflowOpen = false;
            this._problemsOpen = false;
        };
        this._editor = this.useOp('flows/editor');
        this._reload = this.useOp('flows/flow_reload_from_bundle');
        this._flows = this.useResource('flows/flows');
        this._branchRemove = this.useOp('flows/branch_remove');
        this.useEvent(CoreEvents.UI_MODAL_OPEN, () => {
            if (this._overflowOpen) {
                this._overflowOpen = false;
            }
            if (this._problemsOpen) {
                this._problemsOpen = false;
            }
        });
    }

    override connectedCallback(): void {
        super.connectedCallback();
        document.addEventListener('pointerdown', this._onDocPointer);
        if (typeof window !== 'undefined') {
        }
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return;
        }
        const editorMql = window.matchMedia('(max-width: 767px)');
        this._editorMql = editorMql;
        const onEditorMobileMql = () => {
            const nextMobile = editorMql.matches;
            if (nextMobile !== this._isMobile) {
                this._isMobile = nextMobile;
            }
        };
        this._onEditorMobileMql = onEditorMobileMql;
        editorMql.addEventListener('change', onEditorMobileMql);
        const next = editorMql.matches;
        if (next !== this._isMobile) {
            this._isMobile = next;
        }
    }

    override disconnectedCallback(): void {
        const editorMql = this._editorMql;
        const onEditorMobileMql = this._onEditorMobileMql;
        if (editorMql !== null && onEditorMobileMql !== null) {
            editorMql.removeEventListener('change', onEditorMobileMql);
        }
        document.removeEventListener('pointerdown', this._onDocPointer);
        if (typeof window !== 'undefined') {
        }
        if (this._outsideCloseFrame !== null) {
            cancelAnimationFrame(this._outsideCloseFrame);
            this._outsideCloseFrame = null;
        }
        this._outsideCloseArmed = false;
        super.disconnectedCallback();
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated?.(changed);
        if (this._overflowAnchor === null) {
            const anchor = this.renderRoot?.querySelector('.overflow-anchor');
            if (anchor instanceof HTMLElement) {
                this._overflowAnchor = anchor;
            }
        }
        if (this._problemsAnchor === null) {
            const anchor = this.renderRoot?.querySelector('.problems-anchor');
            if (anchor instanceof HTMLElement) {
                this._problemsAnchor = anchor;
            }
        }
        if (this._overflowOpen || this._problemsOpen) {
            const root = this.renderRoot;
            const popovers = root === undefined || root === null ? [] : root.querySelectorAll('platform-popover');
            for (const popover of popovers) {
                if (popover instanceof PlatformPopover) {
                    popover.reposition();
                }
            }
        }
    }

    _renderOverflowPortalContent() {
        return html`
            ${this._isMobile
                ? this._renderMenuButton({
                    label: this.t('editor_header.menu_employee'),
                    icon: 'ai',
                    onClick: this._openEmployeeSettings,
                })
                : nothing}
            ${this._isMobile
                ? this._renderMenuButton({
                    label: this.t('editor_header.menu_settings'),
                    icon: 'settings',
                    onClick: this._openFlowSettings,
                })
                : nothing}
            ${this._isMobile
                ? this._renderMenuButton({
                    label: this.t('editor_header.menu_lara'),
                    icon: 'ai',
                    onClick: this._openLara,
                })
                : nothing}
            ${this._renderMenuButton({
                label: this.t('editor_header.menu_share'),
                icon: 'share',
                onClick: this._openPreviewShare,
            })}
            ${this._renderMenuButton({
                label: this.t('editor_header.menu_triggers'),
                icon: 'zap',
                onClick: this._openTriggers,
            })}
            ${this._renderMenuButton({
                label: this.t('editor_header.menu_api'),
                icon: 'api',
                onClick: this._openApiConsole,
            })}
            ${this._renderMenuButton({
                label: this.t('editor_header.menu_eval'),
                icon: 'science',
                onClick: this._openEvaluationLab,
            })}
            ${this._renderMenuButton({
                label: this.t('editor_header.menu_code'),
                icon: 'code',
                onClick: this._openCodeView,
            })}
            ${this._renderMenuButton({
                label: this.t('editor_header.menu_reload'),
                icon: 'refresh',
                onClick: this._reloadBundle,
            })}
        `;
    }

    _renderProblemsPortalContent(issues: readonly ChromeIssue[]) {
        return html`
            <div class="problems-header">${this.t('canvas.dataflow.problems_title')}</div>
            ${issues.map((item) => html`
                <article
                    class="problem-item"
                    role="button"
                    tabindex="0"
                    data-severity=${item.severity}
                    @click=${() => this._goToProblem(item)}
                    @keydown=${(e: Event) => {
                        if (!(e instanceof KeyboardEvent)) return;
                        if (e.key === 'Enter' || e.key === ' ') {
                            e.preventDefault();
                            this._goToProblem(item);
                        }
                    }}
                >
                    <platform-icon name=${item.severity === 'error' ? 'notification-error' : 'alert-triangle'} size="12"></platform-icon>
                    <span class="problem-body">
                        <span class="problem-node">${item.nodeName}</span>
                        <span class="problem-msg">${item.message}</span>
                    </span>
                </article>
            `)}
        `;
    }

    _resolveStatusBadge(state: Record<string, unknown>): StatusBadge {
        if ((state && state.isDirty) || this.interfaceDirty) return { key: 'dirty', textKey: 'editor_header.status_draft' };
        if (state && state.publishedAt) return { key: 'published', textKey: 'editor_header.status_published' };
        return { key: 'idle', textKey: 'editor_header.status_draft' };
    }

    _onNameChange(e: CustomEvent) {
        const detail = e.detail;
        if (!isPlainObject(detail) || typeof detail.value !== 'string') {
            throw new Error('flows-editor-header: name string required');
        }
        this._editor.setName({ name: detail.value });
    }

    _setWorkspace(workspace: WorkspaceId) {
        this._editor.setWorkspace({ workspace });
    }

    _toggleExecutionPanel() {
        const state = requireEditorState(this._editor.state);
        this._editor.setExecutionPanelOpen({ open: state.executionPanelOpen !== true });
    }

    _back() {
        if (!this.flowId) {
            this.navigate('list', {});
            return;
        }
        // Leaving a branch editor returns to that branch, not to the base flow.
        if (typeof this.branchId === 'string' && this.branchId !== '' && this.branchId !== 'base') {
            this.navigate('flow_chat_branch', { flowId: this.flowId, branchId: this.branchId });
            return;
        }
        this.navigate('flow_chat', { flowId: this.flowId });
    }

    async _save() {
        this.emit('editor-save');
    }

    async _reloadBundle() {
        this._overflowOpen = false;
        if (!this.flowId) return;
        await this._reload.run({ flow_id: this.flowId });
    }

    _closeOverflow() {
        this._overflowOpen = false;
    }

    _toggleOverflow(e: Event) {
        e.stopPropagation();
        const next = !this._overflowOpen;
        if (next) {
            this._problemsOpen = false;
        }
        this._overflowOpen = next;
    }

    _openCodeView() {
        this._closeOverflow();
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        const state = requireEditorState(this._editor.state);
        const body = buildFlowPublishBody(state);
        if (!body) {
            return;
        }
        this.openModal('flows.raw_json', {
            value: body,
            downloadFileName: `${this.flowId}.json`,
        });
    }

    _openLara() {
        this._closeOverflow();
        openPlatformLaraAssistant();
    }

    _openTriggers() {
        this._closeOverflow();
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        this.openModal('flows.triggers', { flowId: this.flowId });
    }

    _openFlowSettings() {
        this._closeOverflow();
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        this.openModal('flows.flow_edit', { flowId: this.flowId });
    }

    _openEmployeeSettings() {
        this._closeOverflow();
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        this.openModal('flows.employee_settings', { flowId: this.flowId });
    }

    _isEmployeeEnabled(state: Record<string, unknown>, flow: unknown) {
        const fromConfig =
            isPlainObject(state.flowConfig) && isPlainObject(state.flowConfig.employee)
                ? state.flowConfig.employee.enabled === true
                : false;
        if (fromConfig) {
            return true;
        }
        if (!isPlainObject(flow)) return false;
        const employee = flow.employee;
        return isPlainObject(employee) && employee.enabled === true;
    }

    _renderEmployeeChip(active: boolean) {
        const title = active
            ? this.t('editor_header.employee_active_aria')
            : this.t('editor_header.employee_settings');
        const label = active
            ? this.t('editor_header.employee_chip_active')
            : this.t('editor_header.employee_chip');
        return html`
            <article
                class="employee-chip"
                role="button"
                tabindex="0"
                data-active=${active ? 'true' : 'false'}
                data-action="employee-settings"
                aria-label=${title}
                title=${title}
                @click=${this._openEmployeeSettings}
                @keydown=${(e: KeyboardEvent) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this._openEmployeeSettings();
                    }
                }}
            >
                <platform-icon name="ai" size="14"></platform-icon>
                <span class="employee-chip-label">${label}</span>
            </article>
        `;
    }

    _openPreviewShare() {
        this._closeOverflow();
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        const raw =
            typeof this.branchId === 'string' && this.branchId.trim() !== '' ? this.branchId.trim() : 'base';
        const bid = raw === 'base' ? 'default' : raw;
        this.openModal('flows.preview_share', { flowId: this.flowId, branchId: bid });
    }

    _openApiConsole() {
        this._closeOverflow();
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        this.openModal('flows.api_console', {
            flowId: this.flowId,
            branchId: this.branchId,
        });
    }

    _openEvaluationLab() {
        this._closeOverflow();
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        const raw =
            typeof this.branchId === 'string' && this.branchId.trim() !== '' ? this.branchId.trim() : 'base';
        const bid = raw === 'base' ? 'default' : raw;
        this.navigate('flow_evaluation_branch', { flowId: this.flowId, branchId: bid });
    }

    _selectBranch(branchId: string) {
        if (branchId === 'base') {
            this.navigate('flow_editor', { flowId: this.flowId });
        } else {
            this.navigate('flow_editor_branch', { flowId: this.flowId, branchId });
        }
    }

    _createBranch() {
        this.openModal('flows.branch_create', { flowId: this.flowId });
    }

    async _deleteBranch(branchId: string) {
        if (!this.flowId || branchId === 'base') return;
        await this._branchRemove.run({ flow_id: this.flowId, branch_id: branchId });
        if (this.branchId === branchId) {
            this.navigate('flow_editor', { flowId: this.flowId });
        }
    }

    _branchItems(flow: unknown, branchIds: readonly string[]): BranchTabItem[] {
        const items: BranchTabItem[] = [
            {
                value: 'base',
                label: this.t('branches_tabs.base'),
                title: this.t('branches_tabs.base'),
            },
        ];
        const branches = isPlainObject(flow) && isPlainObject(flow.branches) ? flow.branches : null;
        for (const bid of branchIds) {
            const branch = branches === null ? null : branches[bid];
            const branchRecord = isPlainObject(branch) ? branch : null;
            const label = branchRecord !== null && typeof branchRecord.name === 'string' && branchRecord.name.length > 0
                ? branchRecord.name
                : bid;
            items.push({
                value: bid,
                label,
                title: label,
                closable: true,
            });
        }
        return items;
    }

    _renderHeaderIconButton({ title, icon, iconSize = '16', onClick, dataAction }: HeaderIconButtonArgs) {
        return html`
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                aria-label=${title}
                title=${title}
                data-action=${typeof dataAction === 'string' && dataAction.length > 0 ? dataAction : nothing}
                @click=${onClick}
            >
                <platform-icon name=${icon} size=${iconSize}></platform-icon>
            </platform-button>
        `;
    }

    _renderMenuButton({ label, icon, onClick }: MenuButtonArgs) {
        const host = this;
        return html`
            <platform-button
                variant="ghost"
                density="compact"
                block
                @click=${(e: Event) => {
                    e.stopPropagation();
                    onClick.call(host);
                }}
            >
                <platform-icon name=${icon} size="16"></platform-icon>
                ${label}
            </platform-button>
        `;
    }

    _dataflowIssues(state: Record<string, unknown>): ChromeIssue[] {
        const dataflow = isPlainObject(state.dataflow) ? state.dataflow : null;
        const nodes = dataflow !== null && isPlainObject(dataflow.nodes) ? dataflow.nodes : null;
        if (nodes === null) return [];
        const branchNodes = getBranchNodes(state);
        const out: ChromeIssue[] = [];
        for (const [nodeId, info] of Object.entries(nodes)) {
            if (!isPlainObject(info)) continue;
            const issues = Array.isArray(info.issues) ? info.issues : [];
            for (const issue of issues) {
                if (!isPlainObject(issue)) continue;
                const severity = issue.severity;
                if (severity !== 'error' && severity !== 'warning') continue;
                const node = isPlainObject(branchNodes) ? branchNodes[nodeId] : null;
                const nodeName = isPlainObject(node) && typeof node.name === 'string' && node.name.length > 0
                    ? node.name
                    : nodeId;
                const issueMessage = issueText(issue.message).length > 0 ? issueText(issue.message) : issueText(issue.code);
                out.push({ kind: 'dataflow', nodeId, nodeName, severity, message: issueMessage });
            }
        }
        out.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'error' ? -1 : 1));
        return out;
    }

    _chromeIssues(state: Record<string, unknown>): ChromeIssue[] {
        const graph = this._dataflowIssues(state);
        const uiIssues: ChromeIssue[] = this.interfaceProblems.map((problem) => {
            const nodeName = typeof problem.blockId === 'string' && problem.blockId.length > 0
                ? problem.blockId
                : (typeof problem.pageId === 'string' && problem.pageId.length > 0
                    ? problem.pageId
                    : this.t('editor_header.mode_interface'));
            return {
                kind: 'interface',
                nodeId: nodeName,
                nodeName,
                severity: problem.severity,
                message: this.t(`interface_editor.problem_${problem.code}`, problemParams(problem.params)),
                pageId: problem.pageId,
                blockId: problem.blockId,
            };
        });
        const out = [...graph, ...uiIssues];
        out.sort((a, b) => (a.severity === b.severity ? 0 : a.severity === 'error' ? -1 : 1));
        return out;
    }

    _toggleProblems(e: Event) {
        e.stopPropagation();
        const next = !this._problemsOpen;
        if (next) {
            this._overflowOpen = false;
        }
        this._problemsOpen = next;
    }

    _goToProblem(item: ChromeIssue) {
        this._problemsOpen = false;
        if (item.kind === 'interface') {
            this._editor.setWorkspace({ workspace: 'interface' });
            this.emit('interface-problem-select', { pageId: item.pageId, blockId: item.blockId });
            return;
        }
        if (item.nodeId.length > 0) {
            this._editor.selectNode({ nodeId: item.nodeId });
        }
    }

    _renderProblemsButton(issues: readonly ChromeIssue[]) {
        if (issues.length === 0) return '';
        const errorCount = issues.filter((issue) => issue.severity === 'error').length;
        const severity = errorCount > 0 ? 'error' : 'warning';
        const count = issues.length;
        return html`
            <div class="problems-anchor" ?data-open=${this._problemsOpen}>
                <article
                    class="problems-btn"
                    role="button"
                    tabindex="0"
                    data-severity=${severity}
                    title=${this.t('canvas.dataflow.problems_title')}
                    @click=${this._toggleProblems}
                    @keydown=${(e: KeyboardEvent) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); this._toggleProblems(e); } }}
                >
                    <platform-icon name="alert-triangle" size="14"></platform-icon>
                    <span class="problems-count">${count > 99 ? '99+' : count}</span>
                </article>
                <platform-popover
                    trigger="manual"
                    role="dialog"
                    placement="bottom-end"
                    offset=${MENU_PORTAL_GAP_PX}
                    viewport-padding=${MENU_PORTAL_VIEWPORT_INSET_PX}
                    .anchor=${this._problemsAnchor}
                    ?open=${this._problemsOpen}
                    @popover-dismiss=${() => { this._problemsOpen = false; }}
                >
                    ${this._problemsOpen
                        ? html`<div class="flows-editor-header-menu-portal problems-flyout">
                              ${this._renderProblemsPortalContent(issues)}
                          </div>`
                        : nothing}
                </platform-popover>
            </div>
        `;
    }

    _renderOverflowMenu(hasBundleUpdate: boolean) {
        return html`
            <div class="overflow-anchor" ?data-open=${this._overflowOpen}>
                <span class="overflow-btn-wrap">
                    ${this._renderHeaderIconButton({
                        title: this.t('editor_header.overflow_aria'),
                        icon: 'more-vertical',
                        iconSize: '20',
                        onClick: this._toggleOverflow,
                    })}
                    ${hasBundleUpdate ? html`<span class="reload-dot"></span>` : nothing}
                </span>
                <platform-popover
                    trigger="manual"
                    role="menu"
                    placement="bottom-end"
                    offset=${MENU_PORTAL_GAP_PX}
                    viewport-padding=${MENU_PORTAL_VIEWPORT_INSET_PX}
                    .anchor=${this._overflowAnchor}
                    ?open=${this._overflowOpen}
                    @popover-dismiss=${() => { this._overflowOpen = false; }}
                >
                    ${this._overflowOpen
                        ? html`<div class="flows-editor-header-menu-portal">
                              ${this._renderOverflowPortalContent()}
                          </div>`
                        : nothing}
                </platform-popover>
            </div>
        `;
    }

    _renderBranchTabs(branchItems: readonly BranchTabItem[]) {
        return html`
            <platform-segmented-control
                density="compact"
                .value=${this.branchId}
                .items=${branchItems}
                aria-label=${this.t('branches_tabs.group_aria')}
                @change=${(e: CustomEvent) => {
                    if (!isPlainObject(e.detail) || typeof e.detail.value !== 'string') {
                        throw new Error('flows-editor-header: branch id required');
                    }
                    this._selectBranch(e.detail.value);
                }}
                @segment-close=${(e: CustomEvent) => {
                    if (!isPlainObject(e.detail) || typeof e.detail.value !== 'string') {
                        throw new Error('flows-editor-header: branch id required');
                    }
                    void this._deleteBranch(e.detail.value);
                }}
            ></platform-segmented-control>
        `;
    }

    _renderBranchAddButton() {
        return html`
            <platform-button
                class="branches-add-btn"
                variant="ghost"
                density="compact"
                aria-label=${this.t('branches_tabs.add')}
                title=${this.t('branches_tabs.add')}
                @click=${this._createBranch}
            >
                <platform-icon name="plus" size="14"></platform-icon>
                ${this.t('branches_tabs.add')}
            </platform-button>
        `;
    }

    _renderBranchesControls(branchItems: readonly BranchTabItem[]) {
        return html`
            <div class="branches-scroll">${this._renderBranchTabs(branchItems)}</div>
            <div class="branches-add">${this._renderBranchAddButton()}</div>
        `;
    }

    _renderPrimaryRow(
        state: Record<string, unknown>,
        flowName: string,
        workspace: WorkspaceId,
        saving: boolean,
        status: StatusBadge,
        hasBundleUpdate: boolean,
        branchItems: readonly BranchTabItem[],
        issues: readonly ChromeIssue[],
        employeeActive: boolean,
    ) {
        const showBranches = typeof this.flowId === 'string' && this.flowId.length > 0;
        return html`
            <div class="chrome-row chrome-row-primary">
                <div class="row-left">
                    <platform-button
                        variant="ghost"
                        icon-only
                        density="dense"
                        aria-label=${this.t('editor_header.back')}
                        @click=${this._back}
                    >
                        <platform-icon name="arrow-left" size="16"></platform-icon>
                    </platform-button>
                    <div class="title-group">
                        <platform-field
                            class="flow-name-field"
                            type="string"
                            mode="edit"
                            label=""
                            pill-density="dense"
                            pill-embed
                            .value=${flowName}
                            placeholder=${this.t('editor_header.flow_name_placeholder')}
                            @change=${this._onNameChange}
                        ></platform-field>
                        <span class="status-badge" data-status=${status.key}>${this.t(status.textKey)}</span>
                    </div>
                </div>

                ${showBranches && !this._isMobile
                    ? html`<div class="branches-slot">${this._renderBranchesControls(branchItems)}</div>`
                    : nothing}

                <div class="row-center">
                    <platform-segmented-control
                        icon-only
                        density="dense"
                        .value=${workspace}
                        .items=${[
                            { value: 'logic', icon: 'workflow', title: this.t('editor_header.mode_logic') },
                            { value: 'interface', icon: 'layers', title: this.t('editor_header.mode_interface') },
                            { value: 'run', icon: 'play', title: this.t('editor_header.mode_run') },
                        ]}
                        aria-label=${this.t('editor_header.mode_group_aria')}
                        @change=${(e: CustomEvent) => this._setWorkspace(e.detail.value)}
                    ></platform-segmented-control>
                    ${workspace === 'logic'
                        ? this._renderHeaderIconButton({
                            title: Boolean(state.executionPanelOpen)
                                ? this.t('editor_header.close_execution_panel')
                                : this.t('editor_header.open_execution_panel'),
                            icon: 'chat',
                            dataAction: 'execution-panel',
                            onClick: () => this._toggleExecutionPanel(),
                        })
                        : nothing}
                </div>

                <div class="row-right">
                    <div class="header-actions" @click=${(e: Event) => e.stopPropagation()}>
                        <platform-help-hint
                            .label=${this.t('editor_header.editor_help_label')}
                            .summary=${this.t('editor_header.editor_help_summary')}
                            .details=${this.t('editor_header.editor_help_details')}
                            .docHref=${'/documentation/scenarios/flows/edit-llm-flow/'}
                            .docLabel=${this.t('help_hints.open_scenario')}
                        ></platform-help-hint>
                        ${this._renderProblemsButton(issues)}
                        ${workspace === 'interface'
                            ? html`<div class="workspace-tools"><slot name="workspace-tools"></slot></div>`
                            : nothing}
                        <div class="desktop-only-actions">
                            ${typeof this.flowId === 'string' && this.flowId.length > 0
                                ? this._renderEmployeeChip(employeeActive)
                                : nothing}
                            ${this._renderHeaderIconButton({
                                title: this.t('editor_header.flow_settings'),
                                icon: 'settings',
                                dataAction: 'flow-settings',
                                onClick: this._openFlowSettings,
                            })}
                            ${this._renderHeaderIconButton({
                                title: this.t('editor_header.lara'),
                                icon: 'ai',
                                onClick: this._openLara,
                            })}
                        </div>
                        ${this._renderOverflowMenu(hasBundleUpdate)}
                        <platform-button variant="primary" density="compact" data-action="publish" ?disabled=${saving} @click=${this._save}>
                            <platform-icon name="save" size="14"></platform-icon>
                            ${saving ? this.t('editor_header.saving') : this.t('editor_header.publish')}
                        </platform-button>
                    </div>
                </div>
            </div>
        `;
    }

    _renderBranchesRow(branchItems: readonly BranchTabItem[]) {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return '';
        }
        if (!this._isMobile) {
            return '';
        }
        return html`
            <div class="chrome-row chrome-row-branches">
                <div class="branches-row">${this._renderBranchesControls(branchItems)}</div>
            </div>
        `;
    }

    override render(): TemplateResult {
        const state = requireEditorState(this._editor.state);
        const flowConfig = state.flowConfig;
        let flowName = '';
        if (isPlainObject(flowConfig) && typeof flowConfig.name === 'string' && flowConfig.name.length > 0) {
            flowName = flowConfig.name;
        } else if (this.flowId.length > 0) {
            flowName = this.flowId;
        }
        const workspace = workspaceId(state.workspace);
        const saving = state.isSaving === true;
        const status = this._resolveStatusBadge(state);
        const flowItem = asArray(this._flows.items).find((item) => isPlainObject(item) && item.flow_id === this.flowId);
        const flow = isPlainObject(flowItem) ? flowItem : null;
        const hasBundleUpdate = flow !== null && flow.has_bundle_update === true;
        const branchIds = flow !== null && isPlainObject(flow.branches) ? Object.keys(flow.branches) : [];
        const branchItems = this._branchItems(flow, branchIds);
        const issues = this._chromeIssues(state);
        const employeeActive = this._isEmployeeEnabled(state, flow);

        // Проблемы могли уйти, пока список открыт: держать пустой флайаут нечем.
        if (this._problemsOpen && issues.length === 0) {
            this._problemsOpen = false;
        }

        return html`
            ${this._renderPrimaryRow(state, flowName, workspace, saving, status, hasBundleUpdate, branchItems, issues, employeeActive)}
            ${this._renderBranchesRow(branchItems)}
        `;
    }
}

customElements.define('flows-editor-header', FlowsEditorHeader);
