/**
 * platform-work-item-badge — cross-service chip/row/card для WorkItem.
 *
 * Источник данных: prop `.item` (zero HTTP) или lazy GET через `platform/work_item_get`.
 * Hover preview — `<platform-work-item-preview>` (если `show-preview`).
 */

import { html, css } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import { openWorkItemDetail } from '../utils/work-item-deeplink.js';
import { formatPlatformDate } from '../utils/format-platform-date.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/platform-user-chip.js';
import './platform-work-item-preview.js';

const ALLOWED_SIZES = new Set(['sm', 'md']);
const ALLOWED_VARIANTS = new Set(['chip', 'row', 'card']);

function _assigneeUserId(item) {
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

function _isIsoDateLike(value) {
    return typeof value === 'string' && value.length >= 10 && /^\d{4}-\d{2}-\d{2}/.test(value);
}

export class PlatformWorkItemBadge extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        workItemId: { type: String, attribute: 'work-item-id' },
        item: { attribute: false },
        size: { type: String },
        variant: { type: String },
        interactive: { type: Boolean },
        showPreview: { type: Boolean, attribute: 'show-preview' },
        embedded: { type: Boolean, reflect: true },
        _previewOpen: { state: true },
        _previewAnchorRect: { state: true },
        _previewPinned: { state: true },
    };

    static styles = [
        PlatformElement.styles,
        css`
            :host {
                display: inline-flex;
                max-width: 100%;
                min-width: 0;
                position: relative;
            }
            .badge {
                display: inline-flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
                max-width: 100%;
                border: 1px solid var(--glass-border-subtle);
                background: var(--glass-tint-subtle);
                color: var(--text-primary);
                border-radius: var(--radius-md);
                padding: var(--space-1) var(--space-2);
                font: inherit;
                text-align: left;
            }
            :host([variant="chip"]) .badge {
                border-radius: var(--radius-full);
            }
            :host([variant="row"]) .badge,
            :host([variant="card"]) .badge {
                width: 100%;
                min-height: 56px;
                padding: var(--space-2) var(--space-3);
                border-left: 3px solid var(--work-item-state-open);
            }
            :host([variant="row"]) .badge[data-state="open"],
            :host([variant="card"]) .badge[data-state="open"] {
                border-left-color: var(--work-item-state-open);
            }
            :host([variant="row"]) .badge[data-state="in_progress"],
            :host([variant="card"]) .badge[data-state="in_progress"] {
                border-left-color: var(--work-item-state-in_progress);
            }
            :host([variant="row"]) .badge[data-state="blocked"],
            :host([variant="card"]) .badge[data-state="blocked"] {
                border-left-color: var(--work-item-state-blocked);
            }
            :host([variant="row"]) .badge[data-state="done"],
            :host([variant="card"]) .badge[data-state="done"] {
                border-left-color: var(--work-item-state-done);
            }
            :host([variant="row"]) .badge[data-state="cancelled"],
            :host([variant="card"]) .badge[data-state="cancelled"] {
                border-left-color: var(--work-item-state-cancelled);
            }
            :host([variant="row"]) .badge[data-state="failed"],
            :host([variant="card"]) .badge[data-state="failed"] {
                border-left-color: var(--work-item-state-failed);
            }
            :host([variant="row"]) .badge[data-state="done"],
            :host([variant="card"]) .badge[data-state="done"],
            :host([variant="row"]) .badge[data-state="cancelled"],
            :host([variant="card"]) .badge[data-state="cancelled"] {
                opacity: 0.72;
            }
            :host([variant="card"]) .badge {
                flex-direction: column;
                align-items: stretch;
                gap: var(--space-2);
            }
            .badge.interactive {
                cursor: pointer;
            }
            .badge.interactive:hover {
                background: var(--glass-tint-medium);
                border-color: var(--glass-border-medium);
            }
            .state-dot {
                width: 8px;
                height: 8px;
                border-radius: 50%;
                flex-shrink: 0;
            }
            .state-dot[data-state="open"] { background: var(--work-item-state-open); }
            .state-dot[data-state="in_progress"] { background: var(--work-item-state-in_progress); }
            .state-dot[data-state="blocked"] { background: var(--work-item-state-blocked); }
            .state-dot[data-state="done"] { background: var(--work-item-state-done); }
            .state-dot[data-state="cancelled"] { background: var(--work-item-state-cancelled); }
            .state-dot[data-state="failed"] { background: var(--work-item-state-failed); }
            .priority-mark {
                width: 6px;
                height: 6px;
                border-radius: 50%;
                flex-shrink: 0;
            }
            .priority-mark[data-priority="high"] { background: var(--work-item-priority-high); }
            .priority-mark[data-priority="urgent"] { background: var(--work-item-priority-urgent); }
            .main {
                min-width: 0;
                flex: 1;
                display: flex;
                flex-direction: column;
                gap: 2px;
            }
            .title-row {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                min-width: 0;
            }
            .title {
                font-size: var(--text-sm);
                font-weight: 600;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .badge[data-state="cancelled"] .title {
                text-decoration: line-through;
                color: var(--text-secondary);
            }
            .meta {
                display: flex;
                align-items: center;
                gap: var(--space-2);
                flex-wrap: wrap;
                color: var(--text-secondary);
                font-size: var(--text-xs);
            }
            .pill {
                display: inline-flex;
                align-items: center;
                gap: 4px;
                padding: 2px 6px;
                border-radius: var(--radius-full);
                font-size: var(--text-xs);
            }
            .pill[data-state="open"] {
                color: var(--work-item-state-open);
                background: var(--work-item-state-open-subtle);
            }
            .pill[data-state="in_progress"] {
                color: var(--work-item-state-in_progress);
                background: var(--work-item-state-in_progress-subtle);
            }
            .pill[data-state="blocked"] {
                color: var(--work-item-state-blocked);
                background: var(--work-item-state-blocked-subtle);
            }
            .pill[data-state="done"] {
                color: var(--work-item-state-done);
                background: var(--work-item-state-done-subtle);
            }
            .pill[data-state="cancelled"] {
                color: var(--work-item-state-cancelled);
                background: var(--work-item-state-cancelled-subtle);
            }
            .pill[data-state="failed"] {
                color: var(--work-item-state-failed);
                background: var(--work-item-state-failed-subtle);
            }
            .pill.kind {
                color: var(--text-secondary);
                background: var(--glass-tint-medium);
            }
            .card-top {
                display: flex;
                align-items: flex-start;
                gap: var(--space-2);
                width: 100%;
            }
            .card-footer {
                display: flex;
                align-items: center;
                justify-content: space-between;
                gap: var(--space-2);
                width: 100%;
            }
            .loading {
                color: var(--text-tertiary);
                font-size: var(--text-xs);
            }
            :host([embedded]) .badge {
                border: none;
                background: transparent;
                padding: var(--space-1) 0;
            }
            :host([embedded][variant="row"]) .badge,
            :host([embedded][variant="card"]) .badge {
                border-left-width: 3px;
                border-left-style: solid;
                padding-left: var(--space-2);
            }
        `,
    ];

    constructor() {
        super();
        this.workItemId = '';
        this.item = null;
        this.size = 'md';
        this.variant = 'chip';
        this.interactive = false;
        this.showPreview = true;
        this.embedded = false;
        this._previewOpen = false;
        this._previewAnchorRect = null;
        this._previewPinned = false;
        this._previewCloseTimer = null;
        this._getOp = this.useOp('platform/work_item_get');
        this._locale = this.select((s) => (
            typeof s.i18n.locale === 'string' && s.i18n.locale.length > 0 ? s.i18n.locale : 'en'
        ));
    }

    updated(changed) {
        super.updated(changed);
        if (this.size && !ALLOWED_SIZES.has(this.size)) {
            throw new Error(`platform-work-item-badge: invalid size "${this.size}"`);
        }
        if (this.variant && !ALLOWED_VARIANTS.has(this.variant)) {
            throw new Error(`platform-work-item-badge: invalid variant "${this.variant}"`);
        }
        if ((changed.has('workItemId') || changed.has('item')) && this._resolvedItem() === null) {
            this._ensureLoaded();
        }
    }

    _resolvedItem() {
        if (this.item && typeof this.item === 'object') {
            return this.item;
        }
        const result = this._getOp.lastResult;
        if (result && typeof result === 'object' && typeof result.work_item_id === 'string') {
            return result;
        }
        return null;
    }

    _ensureLoaded() {
        const id = this._effectiveWorkItemId();
        if (!id) {
            return;
        }
        if (this._getOp.busy) {
            return;
        }
        const cached = this._getOp.lastResult;
        if (cached && typeof cached === 'object' && cached.work_item_id === id) {
            return;
        }
        this._getOp.run({ work_item_id: id });
    }

    _effectiveWorkItemId() {
        if (this.item && typeof this.item.work_item_id === 'string') {
            return this.item.work_item_id;
        }
        return typeof this.workItemId === 'string' ? this.workItemId : '';
    }

    _formatDue(value) {
        if (!_isIsoDateLike(value)) {
            return '';
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return '';
        }
        return formatPlatformDate(parsed, this._locale.value, { day: '2-digit', month: 'short' });
    }

    _onClick() {
        if (!this.interactive) {
            return;
        }
        const id = this._effectiveWorkItemId();
        if (!id) {
            throw new Error('platform-work-item-badge: work_item_id required for navigation');
        }
        openWorkItemDetail(id, this.bus, { mode: 'page' });
    }

    _onMouseEnter() {
        if (!this.showPreview) {
            return;
        }
        if (this._previewCloseTimer !== null) {
            clearTimeout(this._previewCloseTimer);
            this._previewCloseTimer = null;
        }
        const rect = this.getBoundingClientRect();
        this._previewAnchorRect = {
            top: rect.top,
            left: rect.left,
            right: rect.right,
            bottom: rect.bottom,
            width: rect.width,
            height: rect.height,
        };
        this._previewOpen = true;
    }

    _onMouseLeave() {
        if (!this.showPreview || this._previewPinned) {
            return;
        }
        this._schedulePreviewClose();
    }

    _schedulePreviewClose() {
        if (this._previewCloseTimer !== null) {
            clearTimeout(this._previewCloseTimer);
        }
        this._previewCloseTimer = window.setTimeout(() => {
            this._previewCloseTimer = null;
            if (!this._previewPinned) {
                this._previewOpen = false;
            }
        }, 120);
    }

    _onPreviewEnter() {
        this._previewPinned = true;
        if (this._previewCloseTimer !== null) {
            clearTimeout(this._previewCloseTimer);
            this._previewCloseTimer = null;
        }
    }

    _onPreviewLeave() {
        this._previewPinned = false;
        this._previewOpen = false;
    }

    _onPreviewOpen() {
        const id = this._effectiveWorkItemId();
        if (!id) {
            throw new Error('platform-work-item-badge: work_item_id required for open');
        }
        openWorkItemDetail(id, this.bus, { mode: 'page' });
    }

    _renderMeta(item) {
        const priority = typeof item.priority === 'string' ? item.priority : 'normal';
        const state = typeof item.state === 'string' ? item.state : 'open';
        const kind = typeof item.kind === 'string' ? item.kind : 'generic';
        const due = this._formatDue(item.due_date);
        const assigneeUserId = _assigneeUserId(item);
        const showPriority = priority === 'high' || priority === 'urgent';
        return html`
            <div class="meta">
                <span class="pill" data-state=${state}>${this.t(`work_item_badge.state.${state}`)}</span>
                <span class="pill kind">${this.t(`work_item_badge.kind.${kind}`)}</span>
                ${showPriority ? html`
                    <span
                        class="priority-mark"
                        data-priority=${priority}
                        title=${this.t(`work_item_badge.priority.${priority}`)}
                    ></span>
                ` : null}
                ${due ? html`<span>${due}</span>` : null}
                ${assigneeUserId
                    ? html`<platform-user-chip user-id=${assigneeUserId} size="sm" .interactive=${false}></platform-user-chip>`
                    : null}
            </div>
        `;
    }

    render() {
        const id = this._effectiveWorkItemId();
        if (!id) {
            throw new Error('platform-work-item-badge: work-item-id or .item required');
        }
        const item = this._resolvedItem();
        const loading = item === null && this._getOp.busy;
        const state = item && typeof item.state === 'string' ? item.state : 'open';
        const title = item && typeof item.title === 'string' ? item.title : id;
        const interactiveClass = this.interactive ? 'interactive' : '';
        const body = this.variant === 'card'
            ? html`
                <div class="card-top">
                    <span class="state-dot" data-state=${state}></span>
                    <div class="main">
                        <div class="title-row"><span class="title">${title}</span></div>
                        ${item ? this._renderMeta(item) : null}
                    </div>
                </div>
            `
            : html`
                <span class="state-dot" data-state=${state}></span>
                <div class="main">
                    <div class="title-row"><span class="title">${loading ? this.t('work_item_badge.loading') : title}</span></div>
                    ${this.variant !== 'chip' && item ? this._renderMeta(item) : null}
                </div>
            `;
        return html`
            <button
                type="button"
                class="badge ${interactiveClass}"
                data-state=${state}
                ?disabled=${!this.interactive}
                @click=${this._onClick}
                @mouseenter=${this._onMouseEnter}
                @mouseleave=${this._onMouseLeave}
            >
                ${body}
            </button>
            <platform-work-item-preview
                ?preview-open=${this._previewOpen}
                work-item-id=${id}
                .item=${item}
                .anchorRect=${this._previewAnchorRect}
                @preview-enter=${this._onPreviewEnter}
                @preview-leave=${this._onPreviewLeave}
                @open=${this._onPreviewOpen}
            ></platform-work-item-preview>
        `;
    }
}

customElements.define('platform-work-item-badge', PlatformWorkItemBadge);
