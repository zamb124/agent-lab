/**
 * WorktrackerWorkItemCard — единая карточка задачи в списках и на доске.
 */

import { html, css } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { openWorkItemDetail, isMobileViewport } from '@platform/lib/utils/work-item-deeplink.js';
import { worktrackerListStyles } from '../styles/worktracker-list.styles.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-work-item-badge.js';

const TERMINAL_STATES = new Set(['done', 'cancelled', 'failed']);

function _assigneeIsQueue(item) {
    const assignment = item && item.assignment;
    return assignment && typeof assignment === 'object' && assignment.assignee_kind === 'queue';
}

function _queueUnclaimed(item) {
    if (!_assigneeIsQueue(item)) {
        return false;
    }
    const claimed = item.assignment.claimed_by_user_id;
    return typeof claimed !== 'string' || claimed.length === 0;
}

export class WorktrackerWorkItemCard extends PlatformElement {
    static i18nNamespace = 'worktracker';

    static properties = {
        item: { attribute: false },
        variant: { type: String },
        selected: { type: Boolean, reflect: true },
        showPreview: { type: Boolean, attribute: 'show-preview' },
        _menuOpen: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        worktrackerListStyles,
        css`
            :host {
                display: block;
                min-width: 0;
            }
            :host([variant="row"]) {
                display: contents;
            }
            .shell {
                display: flex;
                align-items: stretch;
                gap: var(--space-1);
                min-width: 0;
                min-height: var(--worktracker-row-min-height);
                padding: 0 var(--worktracker-row-padding-x);
                transition: background 120ms ease;
            }
            :host([variant="row"]) .shell {
                border: none;
                border-radius: 0;
                background: transparent;
            }
            :host([variant="card"]) .shell {
                border: var(--worktracker-divider);
                background: var(--bg-primary);
                border-radius: var(--radius-md);
                padding: var(--space-2);
                min-height: auto;
            }
            :host([selected]) .shell {
                background: var(--glass-tint-medium);
                box-shadow: inset 2px 0 0 var(--work-item-state-in_progress);
            }
            :host([variant="row"][selected]) .shell {
                box-shadow: inset 2px 0 0 var(--work-item-state-in_progress);
            }
            :host(:not([selected])) .shell:hover {
                background: var(--glass-tint-subtle);
            }
            :host([variant="card"]:not([selected])) .shell:hover {
                border-color: var(--glass-border-medium);
            }
            .body {
                flex: 1;
                min-width: 0;
                cursor: pointer;
                overflow: hidden;
                border-radius: var(--radius-md) 0 0 var(--radius-md);
            }
            .menu-wrap {
                position: relative;
                flex-shrink: 0;
                align-self: center;
            }
            .menu-trigger {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                width: 2rem;
                height: 2rem;
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-secondary);
                cursor: pointer;
                transition: var(--motion-transition-interactive);
            }
            .menu-trigger:hover,
            .menu-wrap[data-open="true"] .menu-trigger {
                background: var(--glass-solid-medium);
                color: var(--text-primary);
            }
            .menu {
                position: absolute;
                top: calc(100% + 4px);
                right: 0;
                z-index: var(--z-popover, 1100);
                min-width: 11rem;
                padding: var(--space-1);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-medium);
            }
            .menu-item {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                width: 100%;
                padding: var(--space-2) var(--space-3);
                border: none;
                border-radius: var(--radius-md);
                background: transparent;
                color: var(--text-primary);
                font-size: var(--text-sm);
                text-align: left;
                cursor: pointer;
            }
            .menu-item:hover {
                background: var(--glass-solid-medium);
            }
            .menu-item.danger {
                color: var(--danger);
            }
        `,
    ];

    constructor() {
        super();
        this.item = null;
        this.variant = 'row';
        this.selected = false;
        this.showPreview = true;
        this._menuOpen = false;
        this._claimOp = this.useOp('worktracker/work_item_claim');
        this._completeOp = this.useOp('worktracker/work_item_complete');
        this._cancelOp = this.useOp('worktracker/work_item_cancel');
        this._routeSel = this.select((state) => state.router.routeKey);
        this._onDocClick = this._onDocClick.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._onDocClick, true);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._onDocClick, true);
    }

    updated(changed) {
        super.updated(changed);
        if (typeof this.variant !== 'string' || (this.variant !== 'row' && this.variant !== 'card')) {
            throw new Error(`WorktrackerWorkItemCard: invalid variant "${this.variant}"`);
        }
    }

    _onDocClick(event) {
        if (!this._menuOpen) {
            return;
        }
        const path = event.composedPath();
        if (path.includes(this)) {
            return;
        }
        this._menuOpen = false;
    }

    _workItemId() {
        if (!this.item || typeof this.item !== 'object' || typeof this.item.work_item_id !== 'string') {
            throw new Error('WorktrackerWorkItemCard: item.work_item_id required');
        }
        return this.item.work_item_id;
    }

    _isTerminal() {
        return Boolean(this.item && TERMINAL_STATES.has(this.item.state));
    }

    _showClaim() {
        return Boolean(this.item && _queueUnclaimed(this.item));
    }

    _openDetail(event) {
        if (event) {
            event.stopPropagation();
        }
        this._menuOpen = false;
        const routeKey = this._routeSel.value;
        const from = typeof routeKey === 'string' && routeKey.length > 0 && routeKey !== 'work_item_detail'
            ? routeKey
            : 'inbox';
        openWorkItemDetail(this._workItemId(), this.bus, {
            mode: isMobileViewport() ? 'page' : 'panel',
            from,
        });
    }

    _toggleMenu(event) {
        event.stopPropagation();
        this._menuOpen = !this._menuOpen;
    }

    async _runAction(action) {
        this._menuOpen = false;
        const workItemId = this._workItemId();
        if (action === 'open') {
            const routeKey = this._routeSel.value;
            const from = typeof routeKey === 'string' && routeKey.length > 0 && routeKey !== 'work_item_detail'
                ? routeKey
                : 'inbox';
            openWorkItemDetail(workItemId, this.bus, {
                mode: isMobileViewport() ? 'page' : 'panel',
                from,
            });
            return;
        }
        if (action === 'claim') {
            await this._claimOp.run({ work_item_id: workItemId });
        } else if (action === 'complete') {
            await this._completeOp.run({ work_item_id: workItemId, resolution_text: '' });
        } else if (action === 'cancel') {
            await this._cancelOp.run({ work_item_id: workItemId });
        } else {
            throw new Error(`WorktrackerWorkItemCard: unknown action "${action}"`);
        }
        this.emit('changed', { work_item_id: workItemId, action });
    }

    _renderMenuItems() {
        const items = [];
        items.push(html`
            <button type="button" class="menu-item" role="menuitem" @click=${() => this._runAction('open')}>
                <platform-icon name="doc-detail" size="14"></platform-icon>
                ${this.t('work_item_card.open')}
            </button>
        `);
        if (this._showClaim()) {
            items.push(html`
                <button type="button" class="menu-item" role="menuitem" @click=${() => this._runAction('claim')}>
                    <platform-icon name="user-plus" size="14"></platform-icon>
                    ${this.t('work_item_card.claim')}
                </button>
            `);
        }
        if (!this._isTerminal()) {
            items.push(html`
                <button type="button" class="menu-item" role="menuitem" @click=${() => this._runAction('complete')}>
                    <platform-icon name="check" size="14"></platform-icon>
                    ${this.t('work_item_card.complete')}
                </button>
            `);
            items.push(html`
                <button type="button" class="menu-item danger" role="menuitem" @click=${() => this._runAction('cancel')}>
                    <platform-icon name="close" size="14"></platform-icon>
                    ${this.t('work_item_card.cancel')}
                </button>
            `);
        }
        return items;
    }

    render() {
        const workItemId = this._workItemId();
        const badgeVariant = this.variant === 'card' ? 'card' : 'row';
        return html`
            <div class="shell">
                <div class="body" @click=${(e) => this._openDetail(e)}>
                    <platform-work-item-badge
                        work-item-id=${workItemId}
                        variant=${badgeVariant}
                        .item=${this.item}
                        .interactive=${false}
                        embedded
                        ?show-preview=${this.showPreview}
                    ></platform-work-item-badge>
                </div>
                <div class="menu-wrap" data-open=${this._menuOpen ? 'true' : 'false'}>
                    <button
                        type="button"
                        class="menu-trigger"
                        title=${this.t('work_item_card.actions')}
                        aria-expanded=${String(this._menuOpen)}
                        @click=${(e) => this._toggleMenu(e)}
                    >
                        <platform-icon name="more-vert" size="16"></platform-icon>
                    </button>
                    ${this._menuOpen ? html`
                        <div class="menu" role="menu" @click=${(e) => e.stopPropagation()}>
                            ${this._renderMenuItems()}
                        </div>
                    ` : null}
                </div>
            </div>
        `;
    }
}

customElements.define('worktracker-work-item-card', WorktrackerWorkItemCard);
