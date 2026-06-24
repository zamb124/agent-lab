/**
 * WorkItemDetailPanel — боковая панель quick view (desktop).
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { navigateToWorkItemPage } from '@platform/lib/utils/work-item-deeplink.js';
import { WorktrackerUiEvents } from '../events/worktracker-ui-events.js';
import '@platform/lib/components/platform-icon.js';
import './work-item-detail-editor.js';

export class WorkItemDetailPanel extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static properties = {
        workItemId: { type: String, attribute: 'work-item-id' },
        panelOpen: { type: Boolean, reflect: true, attribute: 'panel-open' },
        _isMobile: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: flex;
                flex-direction: column;
                min-height: 0;
                min-width: 0;
                background: var(--bg-primary);
                border-left: var(--worktracker-divider);
                overflow: hidden;
            }
            :host(:not([panel-open])) { display: none; }
            .head {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                padding: var(--space-3) var(--space-4);
                border-bottom: 1px solid var(--glass-border-subtle);
                flex-shrink: 0;
            }
            .head-title {
                font-size: var(--text-sm);
                font-weight: var(--font-semibold);
                color: var(--text-secondary);
            }
            .head-actions {
                display: flex;
                align-items: center;
                gap: var(--space-1);
            }
            .icon-btn {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 32px;
                height: 32px;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
            }
            .icon-btn:hover {
                background: var(--glass-tint-medium);
                color: var(--text-primary);
            }
            .body {
                flex: 1;
                min-height: 0;
                overflow-y: auto;
                padding: var(--space-4);
                display: flex;
                flex-direction: column;
            }
            work-item-detail-editor {
                flex: 1;
                min-height: 0;
            }
        `,
    ];

    constructor() {
        super();
        this.workItemId = '';
        this.panelOpen = false;
        this._isMobile = false;
        this._routeSel = this.select((state) => state.router.routeKey);
        this._onMqlChange = this._onMqlChange.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        if (typeof window !== 'undefined' && typeof window.matchMedia === 'function') {
            this._mql = window.matchMedia('(max-width: 767px)');
            this._isMobile = this._mql.matches;
            this._mql.addEventListener('change', this._onMqlChange);
        }
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        if (this._mql) {
            this._mql.removeEventListener('change', this._onMqlChange);
        }
    }

    _onMqlChange(event) {
        this._isMobile = event.matches;
    }

    _close() {
        this.dispatch(WorktrackerUiEvents.DETAIL_CLOSE, null);
    }

    _openFullPage() {
        if (!this.workItemId) {
            return;
        }
        const routeKey = this._routeSel.value;
        const from = typeof routeKey === 'string' && routeKey.length > 0 && routeKey !== 'work_item_detail'
            ? routeKey
            : 'inbox';
        navigateToWorkItemPage(this.workItemId, this.bus, { from });
        this._close();
    }

    render() {
        return html`
            <div class="head">
                <span class="head-title">${this.t('detail_panel.title')}</span>
                <div class="head-actions">
                    ${!this._isMobile ? html`
                        <button
                            type="button"
                            class="icon-btn"
                            @click=${() => this._openFullPage()}
                            aria-label=${this.t('detail_page.open_full')}
                            title=${this.t('detail_page.open_full')}
                        >
                            <platform-icon name="expand" size="18"></platform-icon>
                        </button>
                    ` : null}
                    <button type="button" class="icon-btn" @click=${() => this._close()} aria-label=${this.t('detail_panel.close')}>
                        <platform-icon name="x" size="18"></platform-icon>
                    </button>
                </div>
            </div>
            <div class="body">
                <work-item-detail-editor
                    layout="panel"
                    work-item-id=${this.workItemId}
                    ?active=${this.panelOpen}
                ></work-item-detail-editor>
            </div>
        `;
    }
}

customElements.define('work-item-detail-panel', WorkItemDetailPanel);
