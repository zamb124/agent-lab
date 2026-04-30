/**
 * graph-toolbar — вертикальная панель действий и тогглов панелей графа.
 *
 * Композиционный child-компонент: эмитит DOM-события `toolbar-action`
 * (detail = { actionId }) и `panel-toggle` (detail = { panelId }).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

const TOOLBAR_ICONS = {
    fit: html`<platform-icon name="fullscreen" size="14"></platform-icon>`,
    path_mode: html`<svg viewBox="0 0 24 24"><circle cx="5" cy="18" r="2"/><circle cx="19" cy="6" r="2"/><path d="M7 17c4-6 5-9 10-10"/></svg>`,
    swap_path: html`<platform-icon name="swap-horiz" size="14"></platform-icon>`,
    reset_path: html`<platform-icon name="trash" size="14"></platform-icon>`,
    depth_plus: html`<platform-icon name="plus" size="14"></platform-icon>`,
    depth_minus: html`<svg viewBox="0 0 24 24"><path d="M4 12h16"/></svg>`,
    filter_rel_type: html`<platform-icon name="filter" size="14"></platform-icon>`,
    labels_mode: html`<platform-icon name="text-fields" size="14"></platform-icon>`,
    reset_view: html`<platform-icon name="refresh" size="14"></platform-icon>`,
    toggle_search: html`<platform-icon name="search" size="14"></platform-icon>`,
    toggle_timeline: html`<svg viewBox="0 0 24 24"><path d="M12 3v18"/><path d="M8 7l4-4 4 4"/><path d="M8 17l4 4 4-4"/></svg>`,
    toggle_legend: html`<platform-icon name="list" size="14"></platform-icon>`,
    toggle_meta: html`<platform-icon name="info" size="14"></platform-icon>`,
    merge_entities: html`<platform-icon name="circular-connection" size="14"></platform-icon>`,
    view_3d: html`<platform-icon name="share" size="14"></platform-icon>`,
    view_mindmap: html`<platform-icon name="git-branch" size="14"></platform-icon>`,
};

export class CRMGraphToolbar extends PlatformElement {
    static i18nNamespace = 'crm';

    static properties = {
        actions: { type: Array },
        toggles: { type: Array },
        labelMode: { type: String, attribute: 'label-mode' },
        canvasView: { type: String, attribute: 'canvas-view' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                position: relative;
                z-index: 14;
                display: flex;
                flex-direction: column;
                gap: 4px;
                padding: 6px;
                border-radius: 12px;
                background: var(--glass-solid-subtle);
                border: 1px solid var(--glass-border-subtle);
                backdrop-filter: blur(6px);
                pointer-events: auto;
                max-height: calc(100% - var(--graph-toolbar-max-height-slop, 88px));
                overflow-y: auto;
                scrollbar-width: none;
            }

            :host::-webkit-scrollbar {
                display: none;
            }

            .view-switch {
                display: flex;
                flex-direction: column;
                align-items: center;
                gap: 4px;
            }

            .separator {
                height: 1px;
                width: 18px;
                background: var(--accent);
                opacity: 0.4;
                border-radius: 1px;
                margin: 4px auto;
            }

            .icon-btn {
                width: 28px;
                height: 28px;
                border-radius: 7px;
                border: 1px solid var(--glass-border-medium);
                background: var(--glass-solid-medium);
                display: inline-flex;
                align-items: center;
                justify-content: center;
                color: var(--text-secondary);
                cursor: pointer;
                transition: background 0.16s ease, transform 0.16s ease;
            }

            .icon-btn:hover {
                background: var(--glass-solid-strong);
                color: var(--text-primary);
                transform: translateY(-1px);
            }

            .icon-btn.active {
                border-color: var(--accent);
                background: var(--accent-subtle);
                color: var(--text-primary);
            }

            .icon-btn svg {
                width: 14px;
                height: 14px;
                fill: none;
                stroke: currentColor;
                stroke-width: 1.8;
                stroke-linecap: round;
                stroke-linejoin: round;
            }

            .toggle-btn {
                border-style: dashed;
                border-color: var(--glass-border-medium);
            }

            .toggle-btn.active {
                border-style: solid;
                border-color: var(--accent);
            }

            @media (max-width: 767px) {
                :host { padding: 4px; gap: 4px; }
            }
        `,
    ];

    constructor() {
        super();
        this.actions = [];
        this.toggles = [];
        this.labelMode = 'fixed';
        this.canvasView = 'mindmap';
    }

    _getIcon(iconKey) {
        const icon = TOOLBAR_ICONS[iconKey];
        if (!icon) {
            throw new Error(`graph-toolbar: unknown icon "${iconKey}"`);
        }
        return icon;
    }

    _isActionActive(actionId) {
        return actionId === 'labels_mode' && this.labelMode === 'adaptive';
    }

    _onAction(actionId) {
        this.emit('toolbar-action', { actionId });
    }

    _onToggle(panelId) {
        this.emit('panel-toggle', { panelId });
    }

    _onCanvasViewChange(mode) {
        if (mode !== '3d' && mode !== 'mindmap') {
            throw new Error(`graph-toolbar: invalid canvas view "${mode}"`);
        }
        this.emit('view-mode-change', { canvasView: mode });
    }

    render() {
        return html`
            <div class="view-switch" role="group" aria-label=${this.t('graph.canvas_view_group_label')}>
                <button
                    class="icon-btn ${this.canvasView === '3d' ? 'active' : ''}"
                    type="button"
                    title=${this.t('graph.view_mode_3d')}
                    aria-label=${this.t('graph.view_mode_3d')}
                    @click=${() => this._onCanvasViewChange('3d')}
                >
                    ${this._getIcon('view_3d')}
                </button>
                <button
                    class="icon-btn ${this.canvasView === 'mindmap' ? 'active' : ''}"
                    type="button"
                    title=${this.t('graph.view_mode_mindmap')}
                    aria-label=${this.t('graph.view_mode_mindmap')}
                    @click=${() => this._onCanvasViewChange('mindmap')}
                >
                    ${this._getIcon('view_mindmap')}
                </button>
            </div>
            <div class="separator"></div>
            ${this.actions.map((action) => html`
                <button
                    class="icon-btn ${this._isActionActive(action.id) ? 'active' : ''}"
                    type="button"
                    title=${action.label}
                    aria-label=${action.label}
                    @click=${() => this._onAction(action.id)}
                >
                    ${this._getIcon(action.id)}
                </button>
            `)}
            <div class="separator"></div>
            ${this.toggles.map((toggle) => html`
                <button
                    class="icon-btn toggle-btn ${toggle.active ? 'active' : ''}"
                    type="button"
                    title=${toggle.label}
                    aria-label=${toggle.label}
                    @click=${() => this._onToggle(toggle.id)}
                >
                    ${this._getIcon(`toggle_${toggle.id}`)}
                </button>
            `)}
        `;
    }
}

customElements.define('crm-graph-toolbar', CRMGraphToolbar);
