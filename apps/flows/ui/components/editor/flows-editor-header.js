/**
 * flows-editor-header — шапка редактора flow.
 *
 * Desktop: одна chrome-row (~60px) — back / title / branches / mode / actions.
 * Mobile: branches — вторая строка; overflow-menu для tiered actions.
 *
 * Источники state:
 *   - useOp('flows/editor').state.flowConfig — текущая модель flow.
 *   - useOp('flows/editor').state.{isDirty, isSaving, mode, publishedAt}.
 *   - useResource('flows/flows') — флаг has_bundle_update и список branches.
 *
 * Ops:
 *   - flows/flow_update — публикация;
 *   - flows/flow_reload_from_bundle — переинициализация из bundle;
 *   - flows/branch_remove — удаление ветки.
 */

import { html, css, nothing } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { CoreEvents } from '@platform/lib/events/contract.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-segmented-control.js';
import '@platform/lib/components/platform-help-hint.js';
import '@platform/lib/components/fields/platform-field.js';
import {
    asArray,
    asObject,
    isPlainObject,
    buildFlowPublishBody,
} from '../../_helpers/flows-resolvers.js';
import { dispatchEmbedChatWindowToggle } from '@platform/lib/chat/chat-window-toggle.js';

export class FlowsEditorHeader extends PlatformElement {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        branchId: { type: String, attribute: 'branch-id' },
        _isMobile: { state: true },
        _overflowOpen: { state: true },
    };

    static styles = [
        PlatformElement.styles,
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
                justify-content: space-between;
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
                flex: 1 1 auto;
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
                min-width: min(200px, 28vw);
                flex: 1 1 0;
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
                flex: 0 1 auto;
                min-width: 0;
                max-width: min(400px, 34vw);
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

            .overflow-anchor {
                position: relative;
            }

            .overflow-anchor[data-open] {
                z-index: 1;
            }

            .menu-flyout {
                position: absolute;
                right: 0;
                top: 100%;
                margin-top: 4px;
                width: min(320px, calc(100vw - 2 * var(--space-4)));
                max-width: calc(100vw - 2 * var(--space-4));
                box-sizing: border-box;
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border, var(--border-subtle));
                border-radius: var(--radius-md);
                box-shadow: var(--glass-shadow-strong);
                z-index: 2;
                display: flex;
                flex-direction: column;
                gap: var(--space-1);
                padding: var(--space-1);
                overflow: hidden;
            }

            .overflow-btn-wrap {
                position: relative;
                display: inline-flex;
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

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this._isMobile =
            typeof window !== 'undefined' &&
            typeof window.matchMedia === 'function' &&
            window.matchMedia('(max-width: 767px)').matches;
        this._overflowOpen = false;
        this._editorMql = null;
        this._onEditorMobileMql = null;
        this._onDocPointer = (e) => {
            if (!this._overflowOpen) {
                return;
            }
            const path = e.composedPath();
            for (const n of path) {
                if (n === this) {
                    break;
                }
                if (n == null || typeof n !== 'object' || !('classList' in n) || !n.classList) {
                    continue;
                }
                if (n.classList.contains('header-actions')) {
                    return;
                }
            }
            this._overflowOpen = false;
        };
        this._editor = this.useOp('flows/editor');
        this._update = this.useOp('flows/flow_update');
        this._reload = this.useOp('flows/flow_reload_from_bundle');
        this._flows = this.useResource('flows/flows');
        this._branchRemove = this.useOp('flows/branch_remove');
        this.useEvent(CoreEvents.UI_MODAL_OPEN, () => {
            if (this._overflowOpen) {
                this._overflowOpen = false;
            }
        });
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
            return;
        }
        this._editorMql = window.matchMedia('(max-width: 767px)');
        this._onEditorMobileMql = () => {
            const next = this._editorMql.matches;
            if (next !== this._isMobile) {
                this._isMobile = next;
            }
        };
        this._editorMql.addEventListener('change', this._onEditorMobileMql);
        const next = this._editorMql.matches;
        if (next !== this._isMobile) {
            this._isMobile = next;
        }
        document.addEventListener('pointerdown', this._onDocPointer);
    }

    disconnectedCallback() {
        if (this._editorMql && this._onEditorMobileMql) {
            this._editorMql.removeEventListener('change', this._onEditorMobileMql);
        }
        document.removeEventListener('pointerdown', this._onDocPointer);
        super.disconnectedCallback();
    }

    _resolveStatusBadge(state) {
        if (state && state.isDirty) return { key: 'dirty', textKey: 'editor_header.status_draft' };
        if (state && state.publishedAt) return { key: 'published', textKey: 'editor_header.status_published' };
        return { key: 'idle', textKey: 'editor_header.status_draft' };
    }

    _onNameChange(e) {
        const detail = e.detail;
        if (!detail || typeof detail.value !== 'string') {
            return;
        }
        this._editor.setName({ name: detail.value });
    }

    _setMode(mode) {
        this._editor.setMode({ mode });
        this._editor.setExecutionPanelOpen({ open: mode === 'run' });
    }

    _back() {
        if (this.flowId) this.navigate('flow_chat', { flowId: this.flowId });
        else this.navigate('list', {});
    }

    async _save() {
        const state = this._editor.state;
        if (!state || !state.flowConfig || !this.flowId) return;
        const body = buildFlowPublishBody(state);
        if (!body) return;
        this._editor.setSaving({ saving: true });
        await this._update.run({ flow_id: this.flowId, body });
        this._editor.setSaving({ saving: false });
        this._editor.setDirty({ dirty: false });
    }

    async _reloadBundle() {
        this._overflowOpen = false;
        if (!this.flowId) return;
        await this._reload.run({ flow_id: this.flowId });
    }

    _closeOverflow() {
        this._overflowOpen = false;
    }

    _toggleOverflow(e) {
        e.stopPropagation();
        this._overflowOpen = !this._overflowOpen;
    }

    _openCodeView() {
        this._closeOverflow();
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        const state = asObject(this._editor.state);
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
        dispatchEmbedChatWindowToggle('flows-lara-open', { open: true });
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

    _selectBranch(branchId) {
        if (branchId === 'base') {
            this.navigate('flow_editor', { flowId: this.flowId });
        } else {
            this.navigate('flow_editor_branch', { flowId: this.flowId, branchId });
        }
    }

    _createBranch() {
        this.openModal('flows.branch_create', { flowId: this.flowId });
    }

    async _deleteBranch(branchId) {
        if (!this.flowId || branchId === 'base') return;
        await this._branchRemove.run({ flow_id: this.flowId, branch_id: branchId });
        if (this.branchId === branchId) {
            this.navigate('flow_editor', { flowId: this.flowId });
        }
    }

    _branchItems(flow, branchIds) {
        const items = [
            {
                value: 'base',
                label: this.t('branches_tabs.base'),
                title: this.t('branches_tabs.base'),
            },
        ];
        for (const bid of branchIds) {
            const branch = flow && flow.branches && flow.branches[bid] ? flow.branches[bid] : null;
            const label = branch && typeof branch.name === 'string' && branch.name.length > 0
                ? branch.name
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

    _renderHeaderIconButton({ title, icon, iconSize = '16', onClick, dataAction }) {
        return html`
            <platform-button
                variant="ghost"
                icon-only
                density="dense"
                aria-label=${title}
                title=${title}
                data-action=${dataAction || nothing}
                @click=${onClick}
            >
                <platform-icon name=${icon} size=${iconSize}></platform-icon>
            </platform-button>
        `;
    }

    _renderMenuButton({ label, icon, onClick }) {
        return html`
            <platform-button variant="ghost" density="compact" block @click=${onClick}>
                <platform-icon name=${icon} size="16"></platform-icon>
                ${label}
            </platform-button>
        `;
    }

    _renderOverflowMenu(hasBundleUpdate) {
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
                ${this._overflowOpen
                    ? html`
                        <div class="menu-flyout" @click=${(e) => e.stopPropagation()}>
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
                        </div>
                    `
                    : nothing}
            </div>
        `;
    }

    _renderBranchTabs(branchItems) {
        return html`
            <platform-segmented-control
                density="compact"
                .value=${this.branchId}
                .items=${branchItems}
                aria-label=${this.t('branches_tabs.group_aria')}
                @change=${(e) => this._selectBranch(e.detail.value)}
                @segment-close=${(e) => { void this._deleteBranch(e.detail.value); }}
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

    _renderBranchesControls(branchItems) {
        return html`
            <div class="branches-scroll">${this._renderBranchTabs(branchItems)}</div>
            <div class="branches-add">${this._renderBranchAddButton()}</div>
        `;
    }

    _renderPrimaryRow(state, flowName, mode, saving, status, hasBundleUpdate, branchItems) {
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
                        .value=${mode}
                        .items=${[
                            { value: 'edit', icon: 'edit', title: this.t('editor_header.mode_edit') },
                            { value: 'run', icon: 'play', title: this.t('editor_header.mode_run') },
                        ]}
                        aria-label=${this.t('editor_header.mode_group_aria')}
                        @change=${(e) => this._setMode(e.detail.value)}
                    ></platform-segmented-control>
                </div>

                <div class="row-right">
                    <div class="header-actions" @click=${(e) => e.stopPropagation()}>
                        <platform-help-hint
                            .label=${this.t('editor_header.editor_help_label')}
                            .summary=${this.t('editor_header.editor_help_summary')}
                            .details=${this.t('editor_header.editor_help_details')}
                            .docHref=${'/documentation/scenarios/flows/edit-llm-flow/'}
                            .docLabel=${this.t('help_hints.open_scenario')}
                        ></platform-help-hint>
                        <div class="desktop-only-actions">
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
                        <platform-button variant="primary" density="compact" ?disabled=${saving} @click=${this._save}>
                            <platform-icon name="save" size="14"></platform-icon>
                            ${saving ? this.t('editor_header.saving') : this.t('editor_header.publish')}
                        </platform-button>
                    </div>
                </div>
            </div>
        `;
    }

    _renderBranchesRow(branchItems) {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return nothing;
        }
        if (!this._isMobile) {
            return nothing;
        }
        return html`
            <div class="chrome-row chrome-row-branches">
                <div class="branches-row">${this._renderBranchesControls(branchItems)}</div>
            </div>
        `;
    }

    render() {
        const state = asObject(this._editor.state);
        let flowName;
        if (isPlainObject(state.flowConfig) && typeof state.flowConfig.name === 'string' && state.flowConfig.name.length > 0) {
            flowName = state.flowConfig.name;
        } else if (typeof this.flowId === 'string' && this.flowId.length > 0) {
            flowName = this.flowId;
        } else {
            flowName = '';
        }
        const mode = typeof state.mode === 'string' && state.mode.length > 0 ? state.mode : 'edit';
        const saving = Boolean(state.isSaving);
        const status = this._resolveStatusBadge(state);
        const flow = asArray(this._flows.items).find((f) => f && f.flow_id === this.flowId);
        const hasBundleUpdate = Boolean(flow && flow.has_bundle_update);
        const branchIds = flow && flow.branches ? Object.keys(flow.branches) : [];
        const branchItems = this._branchItems(flow, branchIds);

        return html`
            ${this._renderPrimaryRow(state, flowName, mode, saving, status, hasBundleUpdate, branchItems)}
            ${this._renderBranchesRow(branchItems)}
        `;
    }
}

customElements.define('flows-editor-header', FlowsEditorHeader);
