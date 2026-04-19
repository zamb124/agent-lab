/**
 * flows-editor-header — шапка редактора flow.
 *
 * Layout (3 секции):
 *   left:  back / flow-name input / status-badge (Черновик|Опубликован)
 *   center: mode-toggle (Edit|Run|Reload-bundle)
 *   right: AI-кнопка / Код / Опубликовать (primary)
 *
 * Источники:
 *   - useOp('flows/editor').state.flowConfig — текущая модель flow.
 *   - useOp('flows/editor').state.isDirty / isSaving / mode (edit|run).
 *
 * Mutations через ops:
 *   - flows/flow_update — публикация (PATCH с актуальным flowConfig + skillsData).
 *   - flows/flow_reload_from_bundle — переинициализация из bundle.
 *
 * Локальные UI-actions slice'а editor:
 *   - setMode({ mode: 'edit'|'run' })
 *   - setName({ name }) — переименование (isDirty=true)
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class FlowsEditorHeader extends PlatformElement {
    static properties = {
        flowId: { type: String, attribute: 'flow-id' },
        skillId: { type: String, attribute: 'skill-id' },
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
            }

            /* LEFT */
            .header-left {
                display: flex; align-items: center; gap: var(--space-2);
                min-width: 0;
            }
            .icon-only-btn {
                width: 32px; height: 32px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .icon-only-btn:hover { background: var(--glass-solid-strong); color: var(--text-primary); }
            .icon-only-btn:disabled { opacity: 0.4; cursor: not-allowed; }
            .flow-name-input {
                background: transparent;
                border: 1px solid transparent;
                color: var(--text-primary);
                font-size: var(--text-base);
                font-weight: var(--font-semibold);
                padding: 4px var(--space-2);
                border-radius: var(--radius-sm);
                min-width: 200px;
                font: inherit;
                font-weight: var(--font-semibold);
            }
            .flow-name-input:hover { border-color: var(--border-subtle); }
            .flow-name-input:focus { outline: none; border-color: var(--accent); background: var(--glass-solid-subtle); }
            .status-badge {
                display: inline-flex;
                align-items: center;
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

            /* CENTER */
            .header-center { display: flex; justify-content: center; }
            .mode-toggle {
                display: inline-flex;
                gap: 2px;
                padding: 3px;
                border-radius: var(--radius-md);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
            }
            .mode-btn {
                width: 36px; height: 30px;
                display: flex; align-items: center; justify-content: center;
                border-radius: var(--radius-sm);
                border: none;
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .mode-btn:hover { background: var(--glass-solid-medium); color: var(--text-primary); }
            .mode-btn[active] { background: var(--accent); color: var(--text-inverse); box-shadow: var(--glass-shadow-subtle); }

            /* RIGHT */
            .header-right { display: flex; justify-content: flex-end; align-items: center; gap: var(--space-2); }
            .header-btn {
                display: inline-flex; align-items: center; gap: var(--space-1);
                padding: 6px var(--space-2);
                border-radius: var(--radius-sm);
                border: 1px solid var(--border-subtle);
                background: var(--glass-solid-subtle);
                color: var(--text-secondary);
                font-size: var(--text-sm);
                cursor: pointer;
                transition: all var(--duration-fast);
            }
            .header-btn:hover { background: var(--glass-solid-strong); color: var(--text-primary); }
            .header-btn.icon-btn { padding: 6px; }
            .header-btn.primary {
                background: var(--accent);
                color: var(--text-inverse);
                border-color: var(--accent);
                font-weight: var(--font-medium);
                padding: 6px var(--space-3);
            }
            .header-btn.primary:hover { background: var(--accent-hover); border-color: var(--accent-hover); box-shadow: var(--accent-glow); }
            .header-btn:disabled { opacity: 0.5; cursor: not-allowed; }
        `,
    ];

    constructor() {
        super();
        this.flowId = '';
        this.skillId = 'base';
        this._editor = this.useOp('flows/editor');
        this._update = this.useOp('flows/flow_update');
        this._reload = this.useOp('flows/flow_reload_from_bundle');
    }

    _resolveStatusBadge(state) {
        if (state && state.isDirty) return { key: 'dirty', textKey: 'editor_header.status_draft' };
        if (state && state.publishedAt) return { key: 'published', textKey: 'editor_header.status_published' };
        return { key: 'idle', textKey: 'editor_header.status_draft' };
    }

    _onNameInput(e) {
        const value = e.target.value;
        if (typeof this._editor.setName === 'function') {
            this._editor.setName({ name: value });
            return;
        }
        this._editor.actions && this._editor.actions.setName && this._editor.actions.setName({ name: value });
    }

    _setMode(mode) {
        if (typeof this._editor.setMode === 'function') {
            this._editor.setMode({ mode });
            return;
        }
        this._editor.actions && this._editor.actions.setMode && this._editor.actions.setMode({ mode });
    }

    _back() {
        if (this.flowId) this.navigate('flow_chat', { flowId: this.flowId });
        else this.navigate('list', {});
    }

    async _save() {
        const state = this._editor.state;
        if (!state || !state.flowConfig || !this.flowId) return;
        if (typeof this._editor.setSaving === 'function') this._editor.setSaving({ saving: true });
        const body = { ...state.flowConfig, ...(state.skillsData || {}) };
        await this._update.run({ flow_id: this.flowId, body });
        if (typeof this._editor.setSaving === 'function') this._editor.setSaving({ saving: false });
        if (typeof this._editor.setDirty === 'function') this._editor.setDirty({ dirty: false });
    }

    async _reloadBundle() {
        if (!this.flowId) return;
        await this._reload.run({ flow_id: this.flowId });
    }

    _openCodeView() {
        // UI-event: открытие code-view панели — обработчик решает (модалка/drawer).
        this.dispatch('flows/code_view/open_requested', { flowId: this.flowId, skillId: this.skillId });
    }

    _openLara() {
        // UI-event: бесшовная интеграция Lara, обработчик настраивается отдельно.
        this.dispatch('flows/lara/open_requested', { flowId: this.flowId, skillId: this.skillId });
    }

    render() {
        const state = this._editor.state || {};
        const flowName = (state.flowConfig && state.flowConfig.name) || this.flowId || '';
        const mode = state.mode || 'edit';
        const saving = Boolean(state.isSaving);
        const status = this._resolveStatusBadge(state);
        return html`
            <div class="header-left">
                <button class="icon-only-btn" type="button" title=${this.t('editor_header.back')} @click=${this._back}>
                    <platform-icon name="arrow-left" size="18"></platform-icon>
                </button>
                <input
                    class="flow-name-input"
                    type="text"
                    .value=${flowName}
                    placeholder=${this.t('editor_header.flow_name_placeholder')}
                    @input=${this._onNameInput}
                />
                <span class="status-badge" data-status=${status.key}>${this.t(status.textKey)}</span>
            </div>

            <div class="header-center">
                <div class="mode-toggle">
                    <button
                        class="mode-btn"
                        type="button"
                        ?active=${mode === 'edit'}
                        title=${this.t('editor_header.mode_edit')}
                        @click=${() => this._setMode('edit')}
                    >
                        <platform-icon name="edit" size="16"></platform-icon>
                    </button>
                    <button
                        class="mode-btn"
                        type="button"
                        ?active=${mode === 'run'}
                        title=${this.t('editor_header.mode_run')}
                        @click=${() => this._setMode('run')}
                    >
                        <platform-icon name="play" size="16"></platform-icon>
                    </button>
                    <button
                        class="mode-btn"
                        type="button"
                        title=${this.t('editor_header.reload_bundle')}
                        @click=${this._reloadBundle}
                    >
                        <platform-icon name="refresh" size="16"></platform-icon>
                    </button>
                </div>
            </div>

            <div class="header-right">
                <button class="header-btn icon-btn" type="button" title=${this.t('editor_header.lara')} @click=${this._openLara}>
                    <platform-icon name="ai" size="16"></platform-icon>
                </button>
                <button class="header-btn" type="button" @click=${this._openCodeView}>
                    <platform-icon name="code" size="16"></platform-icon>
                    ${this.t('editor_header.code')}
                </button>
                <button class="header-btn primary" type="button" ?disabled=${saving} @click=${this._save}>
                    <platform-icon name="save" size="16"></platform-icon>
                    ${saving ? this.t('editor_header.saving') : this.t('editor_header.publish')}
                </button>
            </div>
        `;
    }
}

customElements.define('flows-editor-header', FlowsEditorHeader);
