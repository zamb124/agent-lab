/**
 * WorktrackerWorkItemCard — единая карточка задачи в списках и на доске.
 *
 * Контекстное меню «Действия» порталится в document.body (position:fixed),
 * чтобы не клиппилось overflow/contain у island и списков.
 */

import { html, css, render } from 'lit';
import { PlatformElement } from '@platform/lib/platform-element/index.js';
import { openWorkItemDetail, isMobileViewport } from '@platform/lib/utils/work-item-deeplink.js';
import { worktrackerListStyles } from '../styles/worktracker-list.styles.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-work-item-badge.js';

const TERMINAL_STATES = new Set(['done', 'cancelled', 'failed']);
const MENU_ESTIMATE_PX = 220;

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
        `,
    ];

    constructor() {
        super();
        this.item = null;
        this.variant = 'row';
        this.selected = false;
        this.showPreview = true;
        this._menuOpen = false;
        /** @type {HTMLDivElement|null} */
        this._menuPortal = null;
        /** @type {HTMLDivElement|null} */
        this._menuContent = null;
        this._claimOp = this.useOp('worktracker/work_item_claim');
        this._completeOp = this.useOp('worktracker/work_item_complete');
        this._cancelOp = this.useOp('worktracker/work_item_cancel');
        this._routeSel = this.select((state) => state.router.routeKey);
        this._onDocClick = this._onDocClick.bind(this);
        this._onWindowReposition = this._onWindowReposition.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        document.addEventListener('click', this._onDocClick, true);
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        document.removeEventListener('click', this._onDocClick, true);
        this._closeMenuPortal();
    }

    updated(changed) {
        super.updated(changed);
        if (typeof this.variant !== 'string' || (this.variant !== 'row' && this.variant !== 'card')) {
            throw new Error(`WorktrackerWorkItemCard: invalid variant "${this.variant}"`);
        }
        if (changed.has('_menuOpen')) {
            if (this._menuOpen) {
                this._openMenuPortal();
            } else {
                this._closeMenuPortal();
            }
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
        if (this._menuPortal && path.includes(this._menuPortal)) {
            return;
        }
        this._menuOpen = false;
    }

    _onWindowReposition() {
        if (this._menuOpen) {
            this._syncMenuPortalPosition();
        }
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

    _ensureMenuPortal() {
        if (this._menuPortal !== null) {
            return;
        }
        const portal = document.createElement('div');
        portal.setAttribute('data-wt-work-item-card-menu', '');
        const style = document.createElement('style');
        style.textContent = `
            [data-wt-work-item-card-menu] .menu {
                position: fixed;
                z-index: var(--z-popover, 1100);
                min-width: 11rem;
                padding: var(--space-1);
                background: var(--glass-solid-strong);
                border: 1px solid var(--glass-border-medium);
                border-radius: var(--radius-lg);
                box-shadow: var(--glass-shadow-medium);
            }
            [data-wt-work-item-card-menu] .menu-item {
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
            [data-wt-work-item-card-menu] .menu-item:hover {
                background: var(--glass-solid-medium);
            }
            [data-wt-work-item-card-menu] .menu-item.danger {
                color: var(--danger);
            }
        `;
        const content = document.createElement('div');
        content.setAttribute('data-wt-menu-content', '');
        portal.appendChild(style);
        portal.appendChild(content);
        document.body.appendChild(portal);
        this._menuPortal = portal;
        this._menuContent = content;
        window.addEventListener('resize', this._onWindowReposition);
        window.addEventListener('scroll', this._onWindowReposition, true);
    }

    _menuPositionStyle() {
        const trigger = this.renderRoot.querySelector('.menu-trigger');
        if (!(trigger instanceof HTMLElement)) {
            return 'top: 0; right: 0;';
        }
        const rect = trigger.getBoundingClientRect();
        const spaceBelow = window.innerHeight - rect.bottom;
        const flipUp = spaceBelow < MENU_ESTIMATE_PX && rect.top > MENU_ESTIMATE_PX;
        const right = Math.max(8, window.innerWidth - rect.right);
        if (flipUp) {
            const bottom = Math.max(8, window.innerHeight - rect.top + 4);
            return `right: ${right}px; bottom: ${bottom}px; top: auto;`;
        }
        const top = Math.max(8, rect.bottom + 4);
        return `right: ${right}px; top: ${top}px; bottom: auto;`;
    }

    _openMenuPortal() {
        this._ensureMenuPortal();
        this._syncMenuPortalPosition();
    }

    _syncMenuPortalPosition() {
        if (this._menuContent === null || !this._menuOpen) {
            return;
        }
        const pos = this._menuPositionStyle();
        render(html`
            <div class="menu" role="menu" style=${pos} @click=${(e) => e.stopPropagation()}>
                ${this._renderMenuItems()}
            </div>
        `, this._menuContent);
    }

    _closeMenuPortal() {
        window.removeEventListener('resize', this._onWindowReposition);
        window.removeEventListener('scroll', this._onWindowReposition, true);
        if (this._menuContent !== null) {
            render(html``, this._menuContent);
            this._menuContent = null;
        }
        if (this._menuPortal !== null) {
            this._menuPortal.remove();
            this._menuPortal = null;
        }
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
                </div>
            </div>
        `;
    }
}

customElements.define('worktracker-work-item-card', WorktrackerWorkItemCard);
