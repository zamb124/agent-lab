/**
 * platform-work-item-row — строка списка WorkItem (Linear-style).
 * Данные: prop `.item` (полный WorkItem) или lazy через work-item-id.
 */

import { html, css } from '../lit-shim.js';
import type { CSSResultGroup, PropertyDeclarations, PropertyValues, TemplateResult } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import { openWorkItemDetail, isMobileViewport } from '../utils/work-item-deeplink.js';
import type { OpController } from '../base/use-resource.js';
import type { I18nState } from '../events/reducers/i18n.js';
import { formatPlatformDate } from '../utils/format-platform-date.js';
import './platform-icon.js';
import './platform-user-chip.js';

const STATES = Object.freeze(['open', 'in_progress', 'blocked', 'done', 'cancelled', 'failed']);

export interface WorkItemAssignment {
    assignee_kind?: string;
    user_ids?: unknown[];
    claimed_by_user_id?: unknown;
}

interface WorkItemLink {
    link_kind?: string;
    entity_id?: string;
}

export interface WorkItemLite {
    work_item_id?: string;
    title?: string;
    state?: string;
    due_date?: string;
    assignment?: WorkItemAssignment;
    links?: WorkItemLink[];
    [key: string]: unknown;
}

export function isIsoDateLike(value: unknown): value is string {
    return typeof value === 'string' && value.length >= 10 && /^\d{4}-\d{2}-\d{2}/.test(value);
}

export function workItemAssigneeUserId(item: WorkItemLite): string {
    const assignment = item && item.assignment;
    if (!assignment || typeof assignment !== 'object') {
        return '';
    }
    if (assignment.assignee_kind === 'users') {
        if (!Array.isArray(assignment.user_ids) || assignment.user_ids.length === 0) {
            return '';
        }
        const userId = assignment.user_ids[0];
        return typeof userId === 'string' ? userId : '';
    }
    if (assignment.assignee_kind === 'queue') {
        const claimed = assignment.claimed_by_user_id;
        return typeof claimed === 'string' ? claimed : '';
    }
    return '';
}

function _crmEntityId(item: WorkItemLite): string {
    if (!item || !Array.isArray(item.links)) {
        return '';
    }
    for (const link of item.links) {
        if (link && link.link_kind === 'crm_entity' && typeof link.entity_id === 'string') {
            return link.entity_id;
        }
    }
    return '';
}

export class PlatformWorkItemRow extends PlatformElement {
    static i18nNamespace = 'platform';

    static override properties: PropertyDeclarations = {
        item: { attribute: false },
        workItemId: { type: String, attribute: 'work-item-id' },
        selected: { type: Boolean, reflect: true },
        showPreview: { type: Boolean, attribute: 'show-preview' },
    };
    declare item: WorkItemLite | null;
    declare workItemId: string;
    declare selected: boolean;
    declare showPreview: boolean;

    static override styles: CSSResultGroup = [
        PlatformElement.styles,
        css`
            :host {
                display: block;
                min-width: 0;
            }
            .row {
                display: flex;
                align-items: center;
                gap: var(--space-3);
                min-height: 60px;
                padding: var(--space-3) var(--space-4);
                border-radius: var(--radius-md);
                border: 1px solid transparent;
                cursor: pointer;
                transition: background 120ms ease, border-color 120ms ease;
            }
            .row:hover {
                background: var(--glass-tint-subtle);
            }
            :host([selected]) .row {
                background: var(--accent-subtle);
                border-color: color-mix(in srgb, var(--accent) 40%, transparent);
            }
            .state-dot {
                width: 10px;
                height: 10px;
                border-radius: 50%;
                flex-shrink: 0;
                background: var(--work-item-state-open);
            }
            .state-dot[data-state='in_progress'] { background: var(--work-item-state-in_progress); }
            .state-dot[data-state='blocked'] { background: var(--work-item-state-blocked); }
            .state-dot[data-state='done'] { background: var(--work-item-state-done); }
            .state-dot[data-state='cancelled'] { background: var(--work-item-state-cancelled); }
            .state-dot[data-state='failed'] { background: var(--work-item-state-failed); }
            .main {
                flex: 1;
                min-width: 0;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }
            .title {
                margin: 0;
                font-size: var(--text-sm);
                font-weight: var(--font-medium);
                color: var(--text-primary);
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .meta {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                font-size: var(--text-xs);
                color: var(--text-tertiary);
            }
            .side {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-shrink: 0;
            }
            .loading {
                padding: var(--space-3) var(--space-4);
                color: var(--text-tertiary);
                font-size: var(--text-sm);
            }
        `,
    ];

    constructor() {
        super();
        this.item = null;
        this.workItemId = '';
        this.selected = false;
        this.showPreview = false;
        this._getOp = null;
    }

    private _getOp: OpController | null;

    override connectedCallback(): void {
        super.connectedCallback();
        this._getOp = this.useOp('worktracker/work_item_get');
    }

    override updated(changed: PropertyValues<this>): void {
        super.updated(changed);
        if (
            (changed.has('workItemId') || changed.has('item'))
            && !this.item
            && typeof this.workItemId === 'string'
            && this.workItemId.length > 0
            && this._getOp
            && !this._getOp.busy
        ) {
            this._getOp.run({ work_item_id: this.workItemId });
        }
    }

    _resolvedItem(): WorkItemLite | null {
        if (this.item && typeof this.item === 'object' && typeof this.item.work_item_id === 'string') {
            return this.item;
        }
        const result = (this._getOp?.lastResult ?? null) as WorkItemLite | null;
        if (result && typeof result === 'object' && typeof result.work_item_id === 'string') {
            return result;
        }
        return null;
    }

    _onOpen(): void {
        const item = this._resolvedItem();
        const id = item
            ? item.work_item_id
            : (typeof this.workItemId === 'string' ? this.workItemId : '');
        if (!id) {
            throw new Error('platform-work-item-row: work_item_id required');
        }
        this.emit('work-item-open', {
            work_item_id: id,
            item,
            crm_entity_id: item ? _crmEntityId(item) : '',
            mobile: isMobileViewport(),
        });
        if (!this.hasAttribute('data-no-default-nav')) {
            openWorkItemDetail(id, this.bus);
        }
    }

    override render(): TemplateResult {
        const item = this._resolvedItem();
        if (!item) {
            return html`<div class="loading">${this.t('work_item_badge.loading')}</div>`;
        }
        const state = item.state && (STATES as readonly string[]).includes(item.state) ? item.state : 'open';
        const locale = this.select((s) => (s.i18n as I18nState).locale).value ?? 'ru';
        const due = typeof item.due_date === 'string' && item.due_date.length >= 10
            ? formatPlatformDate(item.due_date, locale)
            : '';
        const assignee = workItemAssigneeUserId(item);
        return html`
            <div class="row" role="button" tabindex="0"
                @click=${() => this._onOpen()}
                @keydown=${(e: KeyboardEvent) => {
                    if (e.key === 'Enter' || e.key === ' ') {
                        e.preventDefault();
                        this._onOpen();
                    }
                }}>
                <span class="state-dot" data-state=${state}></span>
                <div class="main">
                    <p class="title">${item.title}</p>
                    <div class="meta">
                        <span>${this.t(`work_item_badge.state.${state}`)}</span>
                        ${due ? html`<span>· ${due}</span>` : ''}
                    </div>
                </div>
                <div class="side">
                    ${assignee
                        ? html`<platform-user-chip user-id=${assignee} size="sm"></platform-user-chip>`
                        : html`<span class="meta">${this.t('work_item.row_unassigned')}</span>`}
                </div>
            </div>
        `;
    }
}

customElements.define('platform-work-item-row', PlatformWorkItemRow);
