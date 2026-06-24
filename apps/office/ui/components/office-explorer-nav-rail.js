/**
 * office-explorer-nav-rail — All / Recent / Starred / Shared / Deleted views.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import '@platform/lib/components/platform-icon.js';

export class OfficeExplorerNavRail extends PlatformElement {
    static i18nNamespace = 'documents';

    static properties = {
        activeView: { type: String, attribute: 'active-view' },
        deletedEnabled: { type: Boolean, attribute: 'deleted-enabled' },
        sharedEnabled: { type: Boolean, attribute: 'shared-enabled' },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                padding: var(--space-2) var(--space-2) 0;
            }
            .section-title {
                padding: var(--space-1) var(--space-2);
                font-size: var(--text-xs);
                font-weight: 700;
                text-transform: uppercase;
                letter-spacing: 0.04em;
                color: var(--text-tertiary);
            }
            .item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                margin-bottom: var(--space-1);
                border: 1px solid transparent;
                border-radius: var(--radius-lg);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                font-weight: 500;
                text-align: left;
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .item:hover:not(:disabled) {
                background: var(--glass-solid-subtle);
            }
            .item.active {
                background: var(--documents-selected-bg, var(--accent-subtle));
                border-color: var(--documents-selected-stroke, var(--accent));
                color: var(--documents-selected-text, var(--accent));
                font-weight: 600;
            }
            .item:disabled {
                opacity: 0.45;
                cursor: not-allowed;
            }
            .label {
                flex: 1;
                min-width: 0;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
            }
        `,
    ];

    constructor() {
        super();
        this.activeView = 'catalog';
        this.deletedEnabled = false;
        this.sharedEnabled = false;
    }

    _select(view) {
        if (view === 'shared' && !this.sharedEnabled) return;
        if (view === 'deleted' && !this.deletedEnabled) return;
        this.emit('view-change', { explorerView: view });
    }

    _renderItem(view, icon, labelKey, disabled) {
        return html`
            <button
                class="item ${this.activeView === view ? 'active' : ''}"
                type="button"
                ?disabled=${disabled}
                title=${disabled ? this.t('nav.comingSoon') : ''}
                @click=${() => this._select(view)}
            >
                <platform-icon name=${icon} size="16"></platform-icon>
                <span class="label">${this.t(labelKey)}</span>
            </button>
        `;
    }

    render() {
        return html`
            <div class="section-title">${this.t('nav.sectionViews')}</div>
            ${this._renderItem('catalog', 'folder', 'nav.allDocuments', false)}
            ${this._renderItem('recent', 'clock', 'nav.recent', false)}
            ${this._renderItem('starred', 'star', 'nav.starred', false)}
            ${this._renderItem('shared', 'users', 'nav.shared', !this.sharedEnabled)}
            ${this._renderItem('deleted', 'trash', 'nav.deleted', !this.deletedEnabled)}
        `;
    }
}

customElements.define('office-explorer-nav-rail', OfficeExplorerNavRail);
