/**
 * flows-editor-header — шапка редактора flow.
 *
 * Раскладка (3 секции):
 *   left:  back / flow-name input / status-badge (Черновик|Опубликован)
 *   center: mode-toggle pill (edit | run | reload-bundle с update-индикатором)
 *   right: AI / Code / Publish (primary)
 *
 * Источники state:
 *   - useOp('flows/editor').state.flowConfig — текущая модель flow.
 *   - useOp('flows/editor').state.{isDirty, isSaving, mode, publishedAt}.
 *   - useOp('flows/editor').state.agentExecutionRunning — индикатор Run.
 *   - useResource('flows/flows') — для обновления флага has_bundle_update.
 *
 * Изменения через ops:
 *   - flows/flow_update — публикация (PATCH с актуальным flowConfig + skillsData);
 *   - flows/flow_reload_from_bundle — переинициализация из bundle.
 *
 * Локальные UI-actions slice'а editor:
 *   - setMode({ mode: 'edit'|'run' })
 *   - setName({ name }) — переименование (isDirty=true).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-button.js';
import '@platform/lib/components/platform-help-hint.js';
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
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: grid;
                grid-template-columns: 1fr auto 1fr;
                align-items: center;
                gap: var(--space-3);
                padding: var(--space-2) var(--space-4);
                height: var(--header-height);
                box-sizing: border-box;
                background: var(--glass-solid-medium);
                border-bottom: 1px solid var(--border-subtle);
                box-shadow: var(--glass-shadow-subtle);
                --platform-button-icon-size: 34px;
            }

            /* LEFT */
            .header-left { display: flex; align-items: center; gap: var(--space-2); min-width: 0; }
            .flow-name-input {
                background: transparent;
                border: 1px solid transparent;
                color: var(--text-primary);
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                padding: 4px var(--space-2);
                border-radius: var(--radius-sm);
                min-width: 220px;
                font: inherit;
                font-weight: var(--font-semibold);
            }
            .flow-name-input:hover { border-color: var(--border-subtle); }
            .flow-name-input:focus { outline: none; border-color: var(--accent); background: var(--glass-solid-subtle); }
            .status-badge {
                display: inline-flex; align-items: center;
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

            /* CENTER pill */
            .header-center { display: flex; justify-content: center; align-items: center; gap: var(--space-2); }
            .mode-pill {
                display: inline-flex;
                gap: 2px;
                padding: 3px;
                border-radius: var(--radius-full);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
            }
            .mode-btn {
                width: 36px; height: 32px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-full);
                border: none;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .mode-btn:hover { background: var(--glass-solid-medium); color: var(--text-primary); }
            .mode-btn[active] {
                background: var(--glass-solid-strong);
                color: var(--accent);
                box-shadow: var(--glass-shadow-subtle);
            }
            .mode-btn.reload { position: relative; }
            .reload-dot {
                position: absolute;
                top: 2px; right: 2px;
                width: 8px; height: 8px;
                border-radius: 50%;
                background: var(--warning);
                box-shadow: 0 0 6px var(--warning);
            }

            /* RIGHT */
            .header-right {
                display: flex;
                justify-content: flex-end;
                align-items: center;
                gap: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.branchId = 'base';
        this._editor = this.useOp('flows/editor');
        this._update = this.useOp('flows/flow_update');
        this._reload = this.useOp('flows/flow_reload_from_bundle');
        this._flows = this.useResource('flows/flows');
    }

    _resolveStatusBadge(state) {
        if (state && state.isDirty) return { key: 'dirty', textKey: 'editor_header.status_draft' };
        if (state && state.publishedAt) return { key: 'published', textKey: 'editor_header.status_published' };
        return { key: 'idle', textKey: 'editor_header.status_draft' };
    }

    _onNameInput(e) {
        this._editor.setName({ name: e.target.value });
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
        if (!this.flowId) return;
        await this._reload.run({ flow_id: this.flowId });
    }

    _openCodeView() {
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
        dispatchEmbedChatWindowToggle('flows-lara-open', { open: true });
    }

    _openTriggers() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        this.openModal('flows.triggers', { flowId: this.flowId });
    }

    _openFlowSettings() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        this.openModal('flows.flow_edit', { flowId: this.flowId });
    }

    _openPreviewShare() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        const raw =
            typeof this.branchId === 'string' && this.branchId.trim() !== '' ? this.branchId.trim() : 'base';
        const bid = raw === 'base' ? 'default' : raw;
        this.openModal('flows.preview_share', { flowId: this.flowId, branchId: bid });
    }

    _openApiConsole() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        this.openModal('flows.api_console', {
            flowId: this.flowId,
            branchId: this.branchId,
        });
    }

    _openEvaluationLab() {
        if (typeof this.flowId !== 'string' || this.flowId.length === 0) {
            return;
        }
        const raw =
            typeof this.branchId === 'string' && this.branchId.trim() !== '' ? this.branchId.trim() : 'base';
        const bid = raw === 'base' ? 'default' : raw;
        this.navigate('flow_evaluation_branch', { flowId: this.flowId, branchId: bid });
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
        return html`
            <div class="header-left">
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    aria-label=${this.t('editor_header.back')}
                    @click=${this._back}
                >
                    <platform-icon name="arrow-left" size="16"></platform-icon>
                </platform-button>
                <input
                    class="flow-name-input"
                    type="text"
                    data-canon="inline-edit"
                    .value=${flowName}
                    placeholder=${this.t('editor_header.flow_name_placeholder')}
                    @input=${this._onNameInput}
                />
                <span class="status-badge" data-status=${status.key}>${this.t(status.textKey)}</span>
            </div>

            <div class="header-center">
                <div class="mode-pill">
                    <button class="mode-btn" type="button" ?active=${mode === 'edit'} title=${this.t('editor_header.mode_edit')} @click=${() => this._setMode('edit')}>
                        <platform-icon name="edit" size="14"></platform-icon>
                    </button>
                    <button class="mode-btn" type="button" ?active=${mode === 'run'} title=${this.t('editor_header.mode_run')} @click=${() => this._setMode('run')}>
                        <platform-icon name="play" size="14"></platform-icon>
                    </button>
                    <button class="mode-btn reload" type="button" title=${this.t('editor_header.reload_bundle')} @click=${this._reloadBundle}>
                        <platform-icon name="refresh" size="14"></platform-icon>
                        ${hasBundleUpdate ? html`<span class="reload-dot"></span>` : ''}
                    </button>
                </div>
                <platform-help-hint
                    .label=${this.t('editor_header.editor_help_label')}
                    .summary=${this.t('editor_header.editor_help_summary')}
                    .details=${this.t('editor_header.editor_help_details')}
                    .docHref=${'/documentation/scenarios/flows/edit-llm-flow/'}
                    .docLabel=${this.t('help_hints.open_scenario')}
                ></platform-help-hint>
            </div>

            <div class="header-right">
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    aria-label=${this.t('editor_header.flow_settings')}
                    data-action="flow-settings"
                    @click=${this._openFlowSettings}
                >
                    <platform-icon name="settings" size="16"></platform-icon>
                </platform-button>
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    aria-label=${this.t('editor_header.share_preview')}
                    @click=${this._openPreviewShare}
                >
                    <platform-icon name="share" size="16"></platform-icon>
                </platform-button>
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    aria-label=${this.t('flows_sidebar.footer_triggers')}
                    @click=${this._openTriggers}
                >
                    <platform-icon name="zap" size="16"></platform-icon>
                </platform-button>
                <platform-button
                    variant="ghost"
                    icon-only
                    density="dense"
                    aria-label=${this.t('editor_header.lara')}
                    @click=${this._openLara}
                >
                    <platform-icon name="ai" size="16"></platform-icon>
                </platform-button>
                <platform-button
                    variant="ghost"
                    density="compact"
                    aria-label=${this.t('editor_header.api_console')}
                    @click=${this._openApiConsole}
                >
                    <platform-icon name="api" size="14"></platform-icon>
                    ${this.t('editor_header.api')}
                </platform-button>
                <platform-button
                    variant="ghost"
                    density="compact"
                    aria-label=${this.t('editor_header.evaluation_lab')}
                    @click=${this._openEvaluationLab}
                >
                    <platform-icon name="science" size="14"></platform-icon>
                    ${this.t('editor_header.evaluation')}
                </platform-button>
                <platform-button variant="ghost" density="compact" @click=${this._openCodeView}>
                    <platform-icon name="code" size="14"></platform-icon>
                    ${this.t('editor_header.code')}
                </platform-button>
                <platform-button variant="primary" density="compact" ?disabled=${saving} @click=${this._save}>
                    <platform-icon name="save" size="14"></platform-icon>
                    ${saving ? this.t('editor_header.saving') : this.t('editor_header.publish')}
                </platform-button>
            </div>
        `;
    }
}

customElements.define('flows-editor-header', FlowsEditorHeader);
