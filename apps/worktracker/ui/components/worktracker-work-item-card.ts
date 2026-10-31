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
import type { PropertyValues } from 'lit';
import type { SelectController } from '@platform/lib/events/select-controller.js';
import type { OpController } from '@platform/lib/base/use-resource.js';
import { queueUnclaimed as _queueUnclaimed, workItemAllowsSilentComplete } from '../_helpers/work-item-detail-shared.js';
import type { WorkItemLike } from '../_helpers/work-item-detail-shared.js';

const TERMINAL_STATES = new Set(['done', 'cancelled', 'failed']);
const MENU_ESTIMATE_PX = 220;


export class WorktrackerWorkItemCard extends PlatformElement {
    static i18nNamespace = 'worktracker';
    declare item: WorkItemLike | null;
    declare variant: string;
    declare selected: boolean;
    declare showPreview: boolean;
    declare _menuOpen: boolean;
    private _menuPortal: HTMLDivElement | null;
    private _menuContent: HTMLDivElement | null;
    private _claimOp: OpController;
    private _completeOp: OpController;
    private _cancelOp: OpController;
    private _routeSel: SelectController<unknown>;


    static override properties = {
        item: { attribute: false },
        variant: { type: String },
        selected: { type: Boolean, reflect: true },
        showPreview: { type: Boolean, attribute: 'show-preview' },
        _menuOpen: { state: true },
    };

    static override styles = [
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
                gap: var(--space-2);
                min-width: 0;
                min-height: var(--worktracker-row-min-height);
                padding: var(--worktracker-row-padding-y)
                    var(--worktracker-row-padding-x);
                transition: background 120ms ease;
            }
            :host([variant="row"]) .shell {
                border: none;
                border-radius: 0;
                background: transparent;
            }
            :host([variant="card"]) .shell {
                border: 1px solid var(--glass-border-subtle);
                background: var(--worktracker-surface-bg);
                border-radius: var(--radius-lg);
                padding: var(--space-3);
                min-height: auto;
                box-shadow: var(--glass-shadow-subtle);
                transition:
                    background var(--motion-duration-micro) ease,
                    border-color var(--motion-duration-micro) ease,
                    box-shadow var(--motion-duration-micro) ease;
            }
            :host([selected]) .shell {
                background: transparent;
            }
            :host([variant="row"][selected]) .shell {
                box-shadow: none;
            }
            :host(:not([selected])) .shell:hover {
                background: transparent;
            }
            :host([variant="card"]:not([selected])) .shell:hover {
                border-color: var(--glass-border-medium);
                box-shadow: var(--glass-shadow-medium);
                background: var(--glass-tint-subtle);
            }
            :host([variant="card"][selected]) .shell {
                background: var(--accent-subtle);
                border-color: color-mix(in srgb, var(--accent) 45%, var(--glass-border-subtle));
                box-shadow: inset 3px 0 0 var(--accent), var(--glass-shadow-subtle);
            }
            .body {
                flex: 1;
                min-width: 0;
                cursor: pointer;
                overflow: hidden;
                display: flex;
                align-items: center;
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
        this._menuPortal = null;
        this._menuContent = null;
        this._claimOp = this.useOp('worktracker/work_item_claim');
        this._completeOp = this.useOp('worktracker/work_item_complete');
        this._cancelOp = this.useOp('worktracker/work_item_cancel');
        this._routeSel = this.select((state) => state.router.routeKey);
        this._onDocClick = this._onDocClick.bind(this);
        this._onWindowReposition = this._onWindowReposition.bind(this);
    }

    override connectedCallback() {
        super.connectedCallback();
        this.useDomEvent(document, 'click', this._onDocClick, true);
    }

    override disconnectedCallback() {
        super.disconnectedCallback();
        this._closeMenuPortal();
    }

    override updated(changed: PropertyValues<this>) {
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

    private _onDocClick(event: Event) {
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

    private _onWindowReposition() {
        if (this._menuOpen) {
            this._syncMenuPortalPosition();
        }
    }

    private _workItemId(): string {
        if (!this.item || typeof this.item.work_item_id !== 'string') {
            throw new Error('WorktrackerWorkItemCard: item.work_item_id required');
        }
        return this.item.work_item_id;
    }

    private _isTerminal(): boolean {
        return Boolean(this.item && typeof this.item.state === 'string' && TERMINAL_STATES.has(this.item.state));
    }

    private _showClaim() {
        return Boolean(this.item && _queueUnclaimed(this.item));
    }

    private _openDetail(event?: Event) {
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

    private _toggleMenu(event: Event) {
        event.stopPropagation();
        this._menuOpen = !this._menuOpen;
    }

    private _ensureMenuPortal() {
        if (this._menuPortal !== null) {
            return;
        }
        const portal = document.createElement('div');
        portal.setAttribute('data-wt-work-item-card-menu', '');
        const style = document.createElement('style');
        style.textContent = `
            [data-wt-work-item-card-menu] .menu {
                position: fixed;
                z-index: var(--platform-popover-z-index);
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
                color: var(--error);
            }
        `;
        const content = document.createElement('div');
        content.setAttribute('data-wt-menu-content', '');
        portal.appendChild(style);
        portal.appendChild(content);
        document.body.appendChild(portal);
        this._menuPortal = portal;
        this._menuContent = content;
        this.useDomEvent(window, 'resize', this._onWindowReposition);
        this.useDomEvent(window, 'scroll', this._onWindowReposition, true);
    }

    private _menuPositionStyle() {
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

    private _openMenuPortal() {
        this._ensureMenuPortal();
        this._syncMenuPortalPosition();
    }

    private _syncMenuPortalPosition() {
        if (this._menuContent === null || !this._menuOpen) {
            return;
        }
        const pos = this._menuPositionStyle();
        render(html`
            <div class="menu" role="menu" style=${pos} @click=${(e: Event) => e.stopPropagation()}>
                ${this._renderMenuItems()}
            </div>
        `, this._menuContent);
    }

    private _closeMenuPortal() {
        if (this._menuContent !== null) {
            render(html``, this._menuContent);
            this._menuContent = null;
        }
        if (this._menuPortal !== null) {
            this._menuPortal.remove();
            this._menuPortal = null;
        }
    }

    private async _runAction(action: string): Promise<void> {
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

    private _renderMenuItems() {
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
        if (!this._isTerminal() && workItemAllowsSilentComplete(this.item)) {
            items.push(html`
                <button type="button" class="menu-item" role="menuitem" @click=${() => this._runAction('complete')}>
                    <platform-icon name="check" size="14"></platform-icon>
                    ${this.t('work_item_card.complete')}
                </button>
            `);
        }
        if (!this._isTerminal()) {
            items.push(html`
                <button type="button" class="menu-item danger" role="menuitem" @click=${() => this._runAction('cancel')}>
                    <platform-icon name="close" size="14"></platform-icon>
                    ${this.t('work_item_card.cancel')}
                </button>
            `);
        }
        return items;
    }

    override render() {
        const workItemId = this._workItemId();
        const badgeVariant = this.variant === 'card' ? 'card' : 'row';
        return html`
            <div class="shell">
                <div class="body" @click=${(e: Event) => this._openDetail(e)}>
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
                        @click=${(e: Event) => this._toggleMenu(e)}
                    >
                        <platform-icon name="more-vert" size="16"></platform-icon>
                    </button>
                </div>
            </div>
        `;
    }
}

customElements.define('worktracker-work-item-card', WorktrackerWorkItemCard);
