import { html, render as litRender } from '../lit-shim.js';
import { PlatformElement } from '../platform-element/index.js';
import '@platform/lib/components/platform-icon.js';
import '@platform/lib/components/glass-spinner.js';
import '@platform/lib/components/platform-user-chip.js';
import { nextModalLayerZIndex } from '../utils/modal-z-stack.js';
import { formatPlatformDate } from '../utils/format-platform-date.js';

const PREVIEW_WIDTH = 360;
const PREVIEW_GAP = 10;
const PREVIEW_VIEWPORT_PADDING = 12;
const PREVIEW_EXPECTED_HEIGHT = 220;

let _previewStylesInjected = false;

function _ensurePreviewStyles() {
    if (_previewStylesInjected) {
        return;
    }
    _previewStylesInjected = true;
    const style = document.createElement('style');
    style.id = 'platform-work-item-preview-portal-styles';
    style.textContent = `
        .platform-work-item-preview-portal {
            position: fixed;
            width: ${PREVIEW_WIDTH}px;
            max-width: min(${PREVIEW_WIDTH}px, calc(100vw - 24px));
            border: 1px solid var(--glass-border-medium);
            border-left: 3px solid var(--work-item-state-open);
            background: var(--glass-solid-strong);
            backdrop-filter: blur(var(--glass-blur-strong, 16px));
            -webkit-backdrop-filter: blur(var(--glass-blur-strong, 16px));
            border-radius: var(--radius-lg);
            padding: var(--space-3);
            box-shadow: var(--glass-shadow-strong, 0 16px 40px rgba(0, 0, 0, 0.35));
            display: flex;
            flex-direction: column;
            gap: var(--space-2);
            opacity: 0;
            transform: translateY(4px);
            transition: opacity 140ms ease, transform 140ms ease;
            color: var(--text-primary);
            font-family: var(--font-sans);
        }
        .platform-work-item-preview-portal[data-open="true"] {
            opacity: 1;
            transform: translateY(0);
        }
        .platform-work-item-preview-portal[data-state="open"] {
            border-left-color: var(--work-item-state-open);
        }
        .platform-work-item-preview-portal[data-state="in_progress"] {
            border-left-color: var(--work-item-state-in_progress);
        }
        .platform-work-item-preview-portal[data-state="blocked"] {
            border-left-color: var(--work-item-state-blocked);
        }
        .platform-work-item-preview-portal[data-state="done"] {
            border-left-color: var(--work-item-state-done);
        }
        .platform-work-item-preview-portal[data-state="cancelled"] {
            border-left-color: var(--work-item-state-cancelled);
        }
        .platform-work-item-preview-portal[data-state="failed"] {
            border-left-color: var(--work-item-state-failed);
        }
        .platform-work-item-preview-portal__header {
            display: flex;
            align-items: flex-start;
            gap: var(--space-2);
        }
        .platform-work-item-preview-portal__meta {
            min-width: 0;
            display: flex;
            flex-direction: column;
            gap: 4px;
        }
        .platform-work-item-preview-portal__title {
            margin: 0;
            color: var(--text-primary);
            font-size: var(--text-sm);
            font-weight: 700;
            line-height: 1.3;
            word-break: break-word;
        }
        .platform-work-item-preview-portal__sub {
            display: flex;
            align-items: center;
            gap: var(--space-2);
            flex-wrap: wrap;
            color: var(--text-secondary);
            font-size: var(--text-xs);
        }
        .platform-work-item-preview-portal__pill {
            display: inline-flex;
            align-items: center;
            padding: 2px 6px;
            border-radius: var(--radius-full);
            font-size: var(--text-xs);
        }
        .platform-work-item-preview-portal__pill[data-state="open"] {
            color: var(--work-item-state-open);
            background: var(--work-item-state-open-subtle);
        }
        .platform-work-item-preview-portal__pill[data-state="in_progress"] {
            color: var(--work-item-state-in_progress);
            background: var(--work-item-state-in_progress-subtle);
        }
        .platform-work-item-preview-portal__pill[data-state="blocked"] {
            color: var(--work-item-state-blocked);
            background: var(--work-item-state-blocked-subtle);
        }
        .platform-work-item-preview-portal__pill[data-state="done"] {
            color: var(--work-item-state-done);
            background: var(--work-item-state-done-subtle);
        }
        .platform-work-item-preview-portal__pill[data-state="cancelled"] {
            color: var(--work-item-state-cancelled);
            background: var(--work-item-state-cancelled-subtle);
        }
        .platform-work-item-preview-portal__pill[data-state="failed"] {
            color: var(--work-item-state-failed);
            background: var(--work-item-state-failed-subtle);
        }
        .platform-work-item-preview-portal__pill.kind {
            color: var(--text-secondary);
            background: var(--glass-tint-medium);
        }
        .platform-work-item-preview-portal__state-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            flex-shrink: 0;
            margin-top: 5px;
            background: var(--work-item-state-open);
        }
        .platform-work-item-preview-portal[data-state="open"] .platform-work-item-preview-portal__state-dot {
            background: var(--work-item-state-open);
        }
        .platform-work-item-preview-portal[data-state="in_progress"] .platform-work-item-preview-portal__state-dot {
            background: var(--work-item-state-in_progress);
        }
        .platform-work-item-preview-portal[data-state="blocked"] .platform-work-item-preview-portal__state-dot {
            background: var(--work-item-state-blocked);
        }
        .platform-work-item-preview-portal[data-state="done"] .platform-work-item-preview-portal__state-dot {
            background: var(--work-item-state-done);
        }
        .platform-work-item-preview-portal[data-state="cancelled"] .platform-work-item-preview-portal__state-dot {
            background: var(--work-item-state-cancelled);
        }
        .platform-work-item-preview-portal[data-state="failed"] .platform-work-item-preview-portal__state-dot {
            background: var(--work-item-state-failed);
        }
        .platform-work-item-preview-portal[data-state="cancelled"] .platform-work-item-preview-portal__title {
            text-decoration: line-through;
            color: var(--text-secondary);
        }
        .platform-work-item-preview-portal__description {
            margin: 0;
            color: var(--text-secondary);
            font-size: var(--text-xs);
            line-height: 1.35;
            white-space: pre-wrap;
            word-break: break-word;
        }
        .platform-work-item-preview-portal__footer {
            display: flex;
            justify-content: flex-end;
        }
        .platform-work-item-preview-portal__open-btn {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            border: 1px solid var(--glass-border-subtle);
            background: var(--glass-bg-subtle);
            color: var(--text-primary);
            border-radius: var(--radius-md);
            padding: 6px 10px;
            font-size: var(--text-xs);
            cursor: pointer;
        }
        .platform-work-item-preview-portal__open-btn:hover {
            background: var(--glass-bg-medium);
        }
        .platform-work-item-preview-portal__center {
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 76px;
            color: var(--text-secondary);
            font-size: var(--text-xs);
        }
    `;
    document.head.appendChild(style);
}

function _isIsoDateLike(value) {
    return typeof value === 'string' && value.length >= 10 && /^\d{4}-\d{2}-\d{2}/.test(value);
}

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

export class PlatformWorkItemPreview extends PlatformElement {
    static i18nNamespace = 'platform';

    static properties = {
        previewOpen: { type: Boolean, reflect: true, attribute: 'preview-open' },
        workItemId: { type: String, attribute: 'work-item-id' },
        item: { attribute: false },
        anchorRect: { attribute: false },
    };

    constructor() {
        super();
        this.previewOpen = false;
        this.workItemId = '';
        this.item = null;
        this.anchorRect = null;
        this._getOp = this.useOp('platform/work_item_get');
        this._locale = this.select((s) => (
            typeof s.i18n.locale === 'string' && s.i18n.locale.length > 0 ? s.i18n.locale : 'en'
        ));
        this._portal = null;
        this._onReposition = this._onReposition.bind(this);
    }

    connectedCallback() {
        super.connectedCallback();
        _ensurePreviewStyles();
    }

    disconnectedCallback() {
        super.disconnectedCallback();
        this._closePortal();
    }

    updated(changed) {
        super.updated(changed);
        if (changed.has('previewOpen')) {
            if (this.previewOpen) {
                this._openPortal();
            } else {
                this._closePortal();
                return;
            }
        }
        if (this.previewOpen) {
            if ((changed.has('previewOpen') || changed.has('workItemId') || changed.has('item'))
                && this._resolvedItem() === null) {
                this._ensureLoaded();
            }
            this._renderPortal();
            this._reposition();
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
        if (typeof this.workItemId !== 'string' || this.workItemId.length === 0) {
            return;
        }
        if (this._getOp.busy) {
            return;
        }
        const cached = this._getOp.lastResult;
        if (cached && typeof cached === 'object' && cached.work_item_id === this.workItemId) {
            return;
        }
        this._getOp.run({ work_item_id: this.workItemId });
    }

    _formatDate(value) {
        if (!_isIsoDateLike(value)) {
            return '';
        }
        const parsed = new Date(value);
        if (Number.isNaN(parsed.getTime())) {
            return '';
        }
        return formatPlatformDate(parsed, this._locale.value, { day: '2-digit', month: 'short', year: 'numeric' });
    }

    _description(item) {
        const text = item && typeof item.description === 'string' ? item.description.trim() : '';
        if (text.length <= 180) {
            return text;
        }
        return `${text.slice(0, 180)}...`;
    }

    _openPortal() {
        if (this._portal) {
            return;
        }
        const node = document.createElement('div');
        node.className = 'platform-work-item-preview-portal';
        node.style.zIndex = String(nextModalLayerZIndex());
        node.addEventListener('mouseenter', () => this.emit('preview-enter'));
        node.addEventListener('mouseleave', () => this.emit('preview-leave'));
        document.body.appendChild(node);
        this._portal = node;
        this._resizeObserver = new ResizeObserver(this._onReposition);
        this._resizeObserver.observe(document.documentElement);
        document.addEventListener('scroll', this._onReposition, true);
        requestAnimationFrame(() => {
            if (this._portal) {
                this._portal.dataset.open = 'true';
            }
        });
    }

    _closePortal() {
        if (this._resizeObserver) {
            this._resizeObserver.disconnect();
            this._resizeObserver = null;
        }
        document.removeEventListener('scroll', this._onReposition, true);
        if (this._portal && this._portal.parentNode) {
            litRender(null, this._portal);
            this._portal.remove();
        }
        this._portal = null;
    }

    _onReposition() {
        if (!this._portal) {
            return;
        }
        requestAnimationFrame(() => this._reposition());
    }

    _reposition() {
        if (!this._portal) {
            return;
        }
        if (this.anchorRect === null || typeof this.anchorRect !== 'object') {
            return;
        }
        const leftSource = typeof this.anchorRect.left === 'number' ? this.anchorRect.left : 0;
        const topSource = typeof this.anchorRect.top === 'number' ? this.anchorRect.top : 0;
        const heightSource = typeof this.anchorRect.height === 'number' ? this.anchorRect.height : 0;
        const viewportWidth = window.innerWidth;
        const viewportHeight = window.innerHeight;
        const maxLeft = Math.max(PREVIEW_VIEWPORT_PADDING, viewportWidth - PREVIEW_WIDTH - PREVIEW_VIEWPORT_PADDING);
        const left = Math.min(Math.max(PREVIEW_VIEWPORT_PADDING, leftSource), maxLeft);
        const belowTop = topSource + heightSource + PREVIEW_GAP;
        const aboveTop = topSource - PREVIEW_GAP - PREVIEW_EXPECTED_HEIGHT;
        const top = belowTop + PREVIEW_EXPECTED_HEIGHT <= viewportHeight
            ? belowTop
            : Math.max(PREVIEW_VIEWPORT_PADDING, aboveTop);
        this._portal.style.left = `${Math.round(left)}px`;
        this._portal.style.top = `${Math.round(top)}px`;
    }

    _emitOpen() {
        if (typeof this.workItemId !== 'string' || this.workItemId.length === 0) {
            return;
        }
        this.emit('open', { workItemId: this.workItemId });
    }

    _renderPortal() {
        if (!this._portal) {
            return;
        }
        const item = this._resolvedItem();
        const loading = item === null && this._getOp.busy;
        if (item && typeof item.state === 'string') {
            this._portal.dataset.state = item.state;
        } else {
            delete this._portal.dataset.state;
        }
        const tpl = item
            ? html`
                <div class="platform-work-item-preview-portal__header">
                    <span class="platform-work-item-preview-portal__state-dot"></span>
                    <div class="platform-work-item-preview-portal__meta">
                        <p class="platform-work-item-preview-portal__title">${item.title}</p>
                        <div class="platform-work-item-preview-portal__sub">
                            <span class="platform-work-item-preview-portal__pill" data-state=${item.state}>
                                ${this.t(`work_item_badge.state.${item.state}`)}
                            </span>
                            <span class="platform-work-item-preview-portal__pill kind">
                                ${this.t(`work_item_badge.kind.${item.kind}`)}
                            </span>
                            ${item.priority === 'high' || item.priority === 'urgent'
                                ? html`<span class="platform-work-item-preview-portal__pill kind">
                                    ${this.t(`work_item_badge.priority.${item.priority}`)}
                                </span>`
                                : null}
                            ${_isIsoDateLike(item.due_date) ? html`<span>${this._formatDate(item.due_date)}</span>` : null}
                        </div>
                    </div>
                </div>
                ${_assigneeUserId(item)
                    ? html`<platform-user-chip user-id=${_assigneeUserId(item)} size="sm" .interactive=${false}></platform-user-chip>`
                    : null}
                ${this._description(item).length > 0
                    ? html`<p class="platform-work-item-preview-portal__description">${this._description(item)}</p>`
                    : null}
                <div class="platform-work-item-preview-portal__footer">
                    <button type="button" class="platform-work-item-preview-portal__open-btn" @click=${() => this._emitOpen()}>
                        <platform-icon name="arrow-right" size="14"></platform-icon>
                        ${this.t('work_item_preview.open')}
                    </button>
                </div>
            `
            : html`
                <div class="platform-work-item-preview-portal__center">
                    ${loading
                        ? html`<glass-spinner size="16"></glass-spinner>`
                        : this.t('work_item_preview.not_found')}
                </div>
            `;
        litRender(tpl, this._portal);
    }

    render() {
        return html``;
    }
}

customElements.define('platform-work-item-preview', PlatformWorkItemPreview);
